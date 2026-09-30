"""Worker/Kafka tests (§14, §39, §63): offset discipline, ordering,
duplicate redelivery, retry-exhaustion pause, cross-repo independence."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import (
    Commit,
    EventStatus,
    File,
    IngestionEvent,
    Repository,
    RepositoryStatus,
)
from app.ingest.processor import EventProcessor
from tests.conftest import (
    KAFKA_BOOTSTRAP,
    build_backfill_events,
    event_row,
    live_event,
    produce,
    repo_row,
)
from tests.fake_github import FakeGitHub

GID = 1395956448


def _committed_total(harness, topic: str, partitions: int = 5) -> int:
    total = 0
    for p in range(partitions):
        off = harness.committed(topic, p)
        if off > 0:
            total += off
    return total


def test_offsets_committed_only_after_success(
    db, indexer, kafka_topics, worker_factory, producer_factory
):
    """§63: offsets advance exactly past successfully handled messages."""
    fake = FakeGitHub()
    fake.push("c0", {"a.py": "1\n"})
    fake.push("c1", {"a.py": "2\n"})
    events = build_backfill_events(fake)

    harness = worker_factory(topics=[kafka_topics.backfill], fake=fake)
    producer = producer_factory()
    for evt in events:
        producer.send(GID, evt, topic=kafka_topics.backfill)
    producer.flush()

    harness.start()
    try:
        harness.drain(expected=2)
        committed = _committed_total(harness, kafka_topics.backfill)
    finally:
        harness.stop()

    assert committed == 2
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Commit)) == 2
        n = session.scalar(select(func.count()).select_from(IngestionEvent))
        assert n == 2


def test_duplicate_delivery_over_kafka_commits_both_offsets(
    db, indexer, kafka_topics, worker_factory, producer_factory
):
    """Same event.id twice (at-least-once): 2 offsets committed, 1 row."""
    fake = FakeGitHub()
    fake.push("c0", {"a.py": "1\n"})
    (evt,) = build_backfill_events(fake)

    harness = worker_factory(topics=[kafka_topics.backfill], fake=fake)
    producer = producer_factory()
    producer.send(GID, evt, topic=kafka_topics.backfill)
    producer.send(GID, evt, topic=kafka_topics.backfill)
    producer.flush()

    harness.start()
    try:
        harness.drain(expected=2)
        committed = _committed_total(harness, kafka_topics.backfill)
    finally:
        harness.stop()

    # both offsets committed (second was a DUPLICATE, still durable)
    assert committed == 2
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Commit)) == 1
        assert session.scalar(select(func.count()).select_from(IngestionEvent)) == 1


def test_same_repo_events_stay_ordered_on_one_partition(
    db, indexer, kafka_topics, worker_factory, producer_factory
):
    """§39: key=github_repository_id -> one partition -> FIFO applied."""
    fake = FakeGitHub()
    shas = [fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(4)]
    events = build_backfill_events(fake)

    harness = worker_factory(topics=[kafka_topics.backfill], fake=fake)
    producer = producer_factory()
    for evt in events:
        producer.send(GID, evt, topic=kafka_topics.backfill)
    producer.flush()

    harness.start()
    try:
        harness.drain(expected=4)
    finally:
        harness.stop()

    repo = repo_row(db, GID)
    assert repo.synced_through_commit == shas[-1]
    assert repo.backfill_published_through_commit is None  # manager sets that
    with db() as session:
        rows = session.scalars(
            select(Commit)
            .where(
                Commit.repository_id.in_(
                    select(Repository.id).where(Repository.github_repository_id == GID)
                )
            )
            .order_by(Commit.id)
        ).all()
        # applied in publication (chronological) order: parents first
        assert [r.github_commit_sha for r in rows] == shas
        assert rows[1].parent_sha == shas[0]
        assert rows[2].parent_sha == shas[1]
        # newest content won (ordering held end to end)
        f = session.scalar(
            select(File).where(
                File.repository_id == rows[0].repository_id,
                File.path == "f3.py",
            )
        )
        assert f.current_content == "3\n"


def test_retries_exhausted_pauses_partition_without_committing(
    db, failing_indexer, kafka_topics, worker_factory, producer_factory, monkeypatch
):
    """§63: transient failures exhaust -> FAILED row + partition paused,
    offset NOT committed (redelivered after restart)."""
    monkeypatch.setattr("app.kafka.consumer.MAX_EVENT_ATTEMPTS", 2)
    monkeypatch.setattr("app.kafka.consumer.EVENT_RETRY_BASE_DELAY_S", 0.01)
    monkeypatch.setattr("app.kafka.consumer.EVENT_RETRY_MAX_DELAY_S", 0.02)

    fake = FakeGitHub()
    fake.push("c0", {"a.py": "1\n"})
    (evt,) = build_backfill_events(fake)

    harness = worker_factory(
        topics=[kafka_topics.backfill],
        fake=fake,
        indexer_override=failing_indexer,
    )
    failing_indexer.fail = True
    producer = producer_factory()
    producer.send(GID, evt, topic=kafka_topics.backfill)
    producer.flush()

    harness.start()
    try:
        harness.drain(expected=1)
        committed = _committed_total(harness, kafka_topics.backfill)
        paused = harness.paused_partitions
    finally:
        harness.stop()

    # no offset was committed for the failing message
    assert committed == 0
    assert len(paused) == 1
    (paused_topic, _paused_partition) = next(iter(paused))
    assert paused_topic == kafka_topics.backfill
    assert failing_indexer.calls == 2  # MAX_EVENT_ATTEMPTS

    row = event_row(db, evt["event"]["id"])
    assert row.status == EventStatus.FAILED.value
    assert row.error and "retries_exhausted" in row.error
    repo = repo_row(db, GID)
    assert repo.status == RepositoryStatus.SYNC_FAILED.value
    with db() as session:
        # Phase-1 (PostgreSQL) is durable: the commit row exists even though
        # the event failed at the Chroma phase and its offset never advanced.
        assert session.scalar(select(func.count()).select_from(Commit)) == 1
    assert row.pg_status == "done"


def test_failed_partition_does_not_block_other_repos(
    db, indexer, kafka_topics, worker_factory
):
    """§63: repo A's poisoned partition pauses; repo B on P1 keeps flowing."""
    fake = FakeGitHub()
    b_shas = [fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(2)]
    b_events = build_backfill_events(fake)

    # Repo A (gid 999): backfill event whose modified file has no patch and
    # no known content -> forces a GitHub content fetch -> unconfigured App
    # credentials -> permanent FAILED (partition P0 pauses).
    a_gid = 999
    a_evt = live_event(
        delivery_id="a-1",
        github_id=a_gid,
        before="a" * 40,
        after="b" * 40,
        commits=[
            {
                "sha": "b" * 40,
                "message": "x",
                "timestamp": "2025-01-01T10:00:00Z",
                "author": {"name": "A", "email": "a@x.com", "username": None},
                "committer": {"name": "A", "email": "a@x.com", "username": None},
                "added": [],
                "modified": ["auth.py"],
                "removed": [],
            }
        ],
        changes=[
            {
                "path": "auth.py",
                "status": "modified",
                "additions": 1,
                "deletions": 1,
                "changes": 2,
                "sha": "f" * 40,
                "patch": None,  # no offline path -> must fetch -> fails
            }
        ],
    )
    a_evt["event"]["classification"] = "initial_backfill"
    a_evt["event"]["id"] = f"backfill:{a_gid}:" + "b" * 40
    a_evt["backfill"] = {
        "sequence": 0,
        "is_initial_commit": False,
        "parent_sha": "a" * 40,
        "sync_target_commit": "b" * 40,
    }

    # Processor with UNCONFIGURED GitHub credentials (auth present but empty).
    from app.github.auth import GitHubAppAuth
    from app.github.client import GitHubClient

    auth = GitHubAppAuth(app_id="", private_key_pem="")
    gh = GitHubClient(auth=auth, transport=fake.transport())
    processor = EventProcessor(db, indexer, gh)
    harness = worker_factory(topics=[kafka_topics.backfill], processor=processor)

    produce(
        KAFKA_BOOTSTRAP,
        kafka_topics.backfill,
        str(a_gid),
        a_evt,
        partition=0,
    )
    for evt in b_events:
        produce(
            KAFKA_BOOTSTRAP,
            kafka_topics.backfill,
            str(GID),
            evt,
            partition=1,
        )

    harness.start()
    try:
        harness.drain(expected=3)
        committed_p0 = harness.committed(kafka_topics.backfill, 0)
        committed_p1 = harness.committed(kafka_topics.backfill, 1)
        paused = harness.paused_partitions
    finally:
        harness.stop()

    # P0 paused without commit; P1 committed normally.
    assert committed_p0 == -1
    assert committed_p1 == len(b_events)
    assert (kafka_topics.backfill, 0) in paused
    assert len(paused) == 1

    # Repo B unaffected: fully applied, still SYNCING (manager finalizes).
    assert repo_row(db, GID).synced_through_commit == b_shas[-1]
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Commit)) == len(b_shas)

    # Repo A durably failed (event + repository), never applied.
    a_row = event_row(db, a_evt["event"]["id"])
    assert a_row.status == EventStatus.FAILED.value
    assert "github_credentials" in a_row.error
    a_repo = repo_row(db, a_gid)
    assert a_repo.status == RepositoryStatus.SYNC_FAILED.value
    with db() as session:
        a_commits = session.scalar(
            select(func.count())
            .select_from(Commit)
            .where(
                Commit.repository_id.in_(
                    select(Repository.id).where(
                        Repository.github_repository_id == a_gid
                    )
                )
            )
        )
        assert a_commits == 0
