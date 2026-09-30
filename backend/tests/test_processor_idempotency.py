"""Deferral, flush, idempotency and failure handling (§15, §62, §63).

Covers:
  * live events for non-READY repos park durably (DEFERRED) without applying
  * redelivery of a parked event does not double-park
  * flush_deferred applies parked events in arrival order before READY
  * Chroma failure -> retry -> redelivery reuses phase-1 results (no dupes)
  * permanent failure (missing GitHub credentials) records FAILED + SYNC_FAILED
  * mark_failure is durable even when the phase-1 tx rolled back
  * invalid payloads are recorded, never applied, and do not block
"""

from __future__ import annotations

import json

from sqlalchemy import func, select

from app.db.models import (
    Commit,
    EventStatus,
    IngestionEvent,
    Repository,
    RepositoryStatus,
)
from app.ingest.processor import EventProcessor, HandleOutcome
from tests.conftest import (
    apply_event,
    build_backfill_events,
    event_row,
    live_event,
    live_event_for_head,
    repo_row,
)


def _commit_count(db) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(Commit))


def test_live_event_defers_for_non_ready_repo(processor_env):
    """§15: live event while SYNCING parks durably; nothing is applied."""
    evt = live_event(delivery_id="defer-1", before="a" * 40, after="b" * 40)

    outcome = apply_event(processor_env.processor, evt, topic="kyro.github.push")
    assert outcome == HandleOutcome.DEFERRED

    row = event_row(processor_env.db, "defer-1")
    assert row is not None
    assert row.status == EventStatus.DEFERRED.value
    assert row.pg_status == "pending"  # never applied
    assert _commit_count(processor_env.db) == 0

    repo = repo_row(processor_env.db, 1395956448)
    assert repo.status == RepositoryStatus.SYNCING.value


def test_redelivery_of_parked_event_does_not_double_park(processor_env):
    evt = live_event(delivery_id="defer-2", after="b" * 40)
    assert apply_event(processor_env.processor, evt).value == "deferred"
    assert apply_event(processor_env.processor, evt).value == "duplicate"

    with processor_env.db() as session:
        n = session.scalar(
            select(func.count())
            .select_from(IngestionEvent)
            .where(IngestionEvent.event_id == "defer-2")
        )
        assert n == 1


def test_backfill_events_are_never_deferred(processor_env):
    """Backfill must apply even while the repo is SYNCING (it drives SYNCING)."""
    fake = processor_env.fake
    fake.push("init", {"a.py": "1\n"})
    evt = build_backfill_events(fake)[0]
    assert apply_event(processor_env.processor, evt).value == "processed"
    repo = repo_row(processor_env.db, 1395956448)
    assert repo.status == RepositoryStatus.SYNCING.value
    assert _commit_count(processor_env.db) == 1


def test_flush_deferred_applies_in_arrival_order(processor_env):
    """§15/§62: parked live events flush before READY, in arrival order."""
    fake = processor_env.fake
    c1 = fake.push("init", {"a.py": "v1\n"})
    # Backfill brings the repo to SYNCING with c1 applied.
    bf = build_backfill_events(fake)
    assert apply_event(processor_env.processor, bf[0]).value == "processed"

    # Two pushes arrive live while still SYNCING -> both park.
    c2 = fake.push("second", {"a.py": "v2\n"})
    c3 = fake.push("third", {"a.py": "v3\n"})
    live_c2 = _live_event_for(fake, index=-2, delivery_id="live-c2")
    live_c3 = live_event_for_head(fake, delivery_id="live-c3")
    assert apply_event(processor_env.processor, live_c2).value == "deferred"
    assert apply_event(processor_env.processor, live_c3).value == "deferred"
    assert processor_env.processor.count_deferred(1395956448) == 2

    flushed = processor_env.processor.flush_deferred(1395956448)
    assert flushed == 2
    assert processor_env.processor.count_deferred(1395956448) == 0

    # Both commits now exist, content is the newest, rows processed.
    with processor_env.db() as session:
        repo = repo_row(processor_env.db, 1395956448)
        shas = set(
            session.scalars(
                select(Commit.github_commit_sha).where(Commit.repository_id == repo.id)
            ).all()
        )
        assert {c1, c2, c3} <= shas
        for eid in ("live-c2", "live-c3"):
            row = event_row(processor_env.db, eid)
            assert row.status == EventStatus.PROCESSED.value
            assert row.index_status == "done"

    with processor_env.db() as session:
        repo = repo_row(processor_env.db, 1395956448)
        from app.db.models import File

        f = session.scalar(
            select(File).where(File.repository_id == repo.id, File.path == "a.py")
        )
        assert f.current_content == "v3\n"
        assert f.current_content_commit_sha == c3


def _live_event_for(fake, *, index: int, delivery_id: str):
    """Live event for fake.commits[index] (uses real detail + parent)."""
    commit = fake.commits[index]
    before = commit.parents[0] if commit.parents else None
    changes = [
        {
            "path": e["filename"],
            "status": e["status"],
            "additions": e["additions"],
            "deletions": e["deletions"],
            "changes": e["changes"],
            "sha": e["sha"],
            "patch": e["patch"],
        }
        for e in commit.files
    ]
    modified = [
        e["filename"] for e in commit.files if e["status"] not in ("added", "removed")
    ]
    return live_event(
        delivery_id=delivery_id,
        owner=fake.owner,
        name=fake.name,
        installation_id=fake.installation_id,
        before=before,
        after=commit.sha,
        commits=[
            {
                "sha": commit.sha,
                "message": commit.message,
                "timestamp": commit.timestamp,
                "author": {
                    "name": commit.author_name,
                    "email": commit.author_email,
                    "username": None,
                },
                "committer": {
                    "name": commit.author_name,
                    "email": commit.author_email,
                    "username": None,
                },
                "added": [
                    e["filename"] for e in commit.files if e["status"] == "added"
                ],
                "modified": modified,
                "removed": [
                    e["filename"] for e in commit.files if e["status"] == "removed"
                ],
            }
        ],
        changes=changes,
    )


def test_chroma_failure_retries_then_redelivery_succeeds(db, failing_indexer):
    """§59: phase-1 durable, phase-2 retryable; redelivery never duplicates."""
    from tests.fake_github import FakeGitHub, make_github_client

    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n"})
    client, _ = make_github_client(fake)
    processor = EventProcessor(db, failing_indexer, client)
    evt = build_backfill_events(fake)[0]

    failing_indexer.fail = True
    assert apply_event(processor, evt).value == HandleOutcome.RETRY.value

    row = event_row(db, evt["event"]["id"])
    assert row is not None
    assert row.pg_status == "done"  # phase 1 committed
    assert row.status == EventStatus.PROCESSING.value
    assert row.error and "chroma" in row.error.lower()
    assert _commit_count(db) == 1  # applied exactly once

    # Redelivery with Chroma healthy: rebuild index items from PG, finish.
    failing_indexer.fail = False
    assert apply_event(processor, evt).value == HandleOutcome.PROCESSED.value
    row = event_row(db, evt["event"]["id"])
    assert row.status == EventStatus.PROCESSED.value
    assert row.index_status == "done"
    assert row.error is None
    assert _commit_count(db) == 1  # still exactly once
    assert failing_indexer.calls == 2


def test_missing_github_credentials_fails_permanently(db, indexer):
    """Missing App credentials -> FAILED (no offset commit), repo SYNC_FAILED."""
    from app.github.auth import GitHubAppAuth
    from app.github.client import GitHubClient
    from tests.fake_github import FakeGitHub

    fake = FakeGitHub()
    auth = GitHubAppAuth(app_id="", private_key_pem="")
    client = GitHubClient(auth=auth, transport=fake.transport())
    processor = EventProcessor(db, indexer, client)

    # READY repo; modified file with no patch -> forces a GitHub content
    # fetch -> require_configured() raises GitHubCredentialsMissing.
    with db() as session, session.begin():
        session.add(
            Repository(
                github_repository_id=1395956448,
                name="kyro-demo",
                full_name="acme/kyro-demo",
                owner="acme",
                default_branch="main",
                github_installation_id=791001,
                status=RepositoryStatus.READY.value,
            )
        )
    evt = live_event(
        delivery_id="creds-1",
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
                "patch": None,  # forces step-3 fetch
            }
        ],
    )

    outcome = apply_event(processor, evt, topic="kyro.github.push")
    assert outcome == HandleOutcome.FAILED

    # Failure durably recorded despite the phase-1 rollback (§63).
    row = event_row(db, "creds-1")
    assert row is not None
    assert row.status == EventStatus.FAILED.value
    assert row.error and "github_credentials" in row.error

    repo = repo_row(db, 1395956448)
    assert repo.status == RepositoryStatus.SYNC_FAILED.value
    assert repo.last_error and "github_credentials" in repo.last_error


def test_mark_failure_is_durable_without_prior_row(processor_env):
    """mark_failure (retries exhausted) creates the row + flips the repo."""
    fake = processor_env.fake
    fake.push("init", {"a.py": "1\n"})
    evt = build_backfill_events(fake)[0]

    # Simulate: phase-1 transient failure rolled back everything, worker
    # exhausts retries and calls mark_failure.
    processor_env.processor.mark_failure(
        json.dumps(evt).encode("utf-8"),
        "offset kyro.github.backfill[0]@3: retries_exhausted",
    )

    row = event_row(processor_env.db, evt["event"]["id"])
    assert row is not None
    assert row.status == EventStatus.FAILED.value
    assert "retries_exhausted" in row.error

    repo = repo_row(processor_env.db, 1395956448)
    assert repo.status == RepositoryStatus.SYNC_FAILED.value
    assert "retries_exhausted" in repo.last_error
    assert _commit_count(processor_env.db) == 0  # never applied


def test_mark_failure_does_not_unfail_processed_repo_state(processor_env):
    """A later failure on a READY repo flips it to SYNC_FAILED (visible)."""
    fake = processor_env.fake
    fake.push("init", {"a.py": "1\n"})
    evt = build_backfill_events(fake)[0]
    apply_event(processor_env.processor, evt)

    with processor_env.db() as session, session.begin():
        repo = session.scalar(select(Repository).limit(1))
        repo.status = RepositoryStatus.READY.value

    processor_env.processor.mark_failure(json.dumps(evt).encode("utf-8"), "boom")
    repo = repo_row(processor_env.db, 1395956448)
    assert repo.status == RepositoryStatus.SYNC_FAILED.value
    assert repo.last_error == "boom"


def test_invalid_payload_recorded_never_applied(processor_env):
    outcome = processor_env.processor.handle_raw(
        b"this is not json",
        topic="kyro.github.push",
        partition=2,
        offset=7,
    )
    assert outcome == HandleOutcome.INVALID
    with processor_env.db() as session:
        row = session.scalar(
            select(IngestionEvent).where(
                IngestionEvent.status == EventStatus.INVALID.value
            )
        )
        assert row is not None
        assert row.event_id.startswith("invalid:")
        assert row.partition == 2
        assert row.offset == 7
    assert _commit_count(processor_env.db) == 0
