"""SyncManager state-machine tests (§10-§16, §39, §56, §62).

Covers: onboarding -> publish -> apply -> READY, timeout -> SYNC_FAILED,
auth revocation -> ACCESS_REVOKED, finalize refusal when deferred events
exist, advisory-lock exclusion, full-resync boundary clearing, and
pending-sync discovery for the supervisor.
"""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import func, select, text

from app.db.models import (
    Commit,
    EventStatus,
    IngestionEvent,
    Repository,
    RepositoryStatus,
)
from app.github.backfill import BackfillService
from app.ingest.processor import EventProcessor
from app.sync.manager import SyncManager
from tests.conftest import repo_row
from tests.fake_github import FakeGitHub, make_github_client

GID = 1395956448


def _setup(db, indexer, kafka_topics, worker_factory, *, timeout=30.0):
    fake = FakeGitHub()
    client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, client)
    manager = SyncManager(
        db,
        BackfillService(client),
        processor,
        client,
        backfill_topic=kafka_topics.backfill,
        timeout=timeout,
        poll_interval=0.05,
        publish_batch=2,
        concurrency=2,
    )
    harness = worker_factory(
        topics=[kafka_topics.backfill, kafka_topics.live],
        fake=fake,
        processor=processor,
    )
    return SimpleNamespace(
        fake=fake,
        client=client,
        processor=processor,
        manager=manager,
        worker=harness,
    )


def _onboard(env, *, run: bool = False):
    return env.manager.onboard(
        github_repository_id=GID,
        owner=env.fake.owner,
        name=env.fake.name,
        installation_id=env.fake.installation_id,
        default_branch=env.fake.default_branch or "main",
        run=run,
    )


def test_onboard_publish_apply_reaches_ready(db, indexer, kafka_topics, worker_factory):
    """Happy path: full history published, applied by the worker, READY."""
    env = _setup(db, indexer, kafka_topics, worker_factory)
    shas = [env.fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(3)]

    snap = _onboard(env, run=False)
    assert snap["status"] == RepositoryStatus.SYNCING.value
    assert snap["backfill_published_through_commit"] is None

    env.worker.start()
    try:
        status = env.manager.run_sync(GID)
    finally:
        env.worker.stop()

    assert status == RepositoryStatus.READY.value
    snap = env.manager.snapshot(GID)
    assert snap["status"] == RepositoryStatus.READY.value
    assert snap["backfill_published_through_commit"] == shas[-1]
    assert snap["synced_through_commit"] == shas[-1]
    assert snap["deferred_events"] == 0
    assert snap["sync_completed_at"] is not None
    assert snap["last_error"] is None

    with db() as session:
        n = session.scalar(select(func.count()).select_from(Commit))
        assert n == 3
        rows = session.execute(select(IngestionEvent.status, IngestionEvent.kind)).all()
        assert len(rows) == 3
        assert all(s == EventStatus.PROCESSED.value for s, _ in rows)
        assert all(k == "backfill" for _, k in rows)


def test_resume_after_ready_publishes_only_new_commits(
    db, indexer, kafka_topics, worker_factory
):
    """Boundary kept on re-onboard: only the new range is published."""
    env = _setup(db, indexer, kafka_topics, worker_factory)
    for i in range(2):
        env.fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"})
    _onboard(env, run=False)
    env.worker.start()
    try:
        assert env.manager.run_sync(GID) == RepositoryStatus.READY.value
        published_first = repo_row(db, GID).backfill_published_through_commit

        # Two more commits, re-onboard (SYNCING again) and sync: only the
        # new range goes out, and the repo lands READY at the new head.
        env.fake.push("c2", {"f2.py": "2\n"})
        new_head = env.fake.push("c3", {"f3.py": "3\n"})
        _onboard(env, run=False)
        assert env.manager.run_sync(GID) == RepositoryStatus.READY.value
    finally:
        env.worker.stop()

    repo = repo_row(db, GID)
    assert repo.backfill_published_through_commit == new_head
    assert repo.synced_through_commit == new_head
    assert published_first != new_head
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Commit)) == 4


def test_timeout_marks_sync_failed(db, indexer, kafka_topics, worker_factory):
    """No worker consuming -> applied never catches up -> SYNC_FAILED."""
    env = _setup(db, indexer, kafka_topics, worker_factory, timeout=1.5)
    env.fake.push("c0", {"a.py": "1\n"})
    _onboard(env, run=False)

    # worker created but never started: events publish, nothing applies
    status = env.manager.run_sync(GID)

    assert status == RepositoryStatus.SYNC_FAILED.value
    repo = repo_row(db, GID)
    assert repo.status == RepositoryStatus.SYNC_FAILED.value
    assert repo.last_error and "timed out" in repo.last_error
    # events were published (boundary advanced) even though apply timed out
    assert repo.backfill_published_through_commit == env.fake.head
    assert repo.synced_through_commit is None


def test_auth_revoked_marks_access_revoked(db, indexer, kafka_topics, worker_factory):
    """401 from GitHub -> ACCESS_REVOKED (never stuck in SYNCING)."""
    env = _setup(db, indexer, kafka_topics, worker_factory)
    env.fake.push("c0", {"a.py": "1\n"})
    env.fake.auth_mode = "revoked"
    _onboard(env, run=False)

    status = env.manager.run_sync(GID)
    assert status == RepositoryStatus.ACCESS_REVOKED.value
    repo = repo_row(db, GID)
    assert repo.status == RepositoryStatus.ACCESS_REVOKED.value
    assert repo.last_error


def test_missing_branch_marks_sync_failed(db, indexer, kafka_topics, worker_factory):
    """Branch 404 (empty/missing repo on GitHub) -> SYNC_FAILED, not stuck."""
    env = _setup(db, indexer, kafka_topics, worker_factory)  # no commits pushed
    _onboard(env, run=False)

    status = env.manager.run_sync(GID)
    assert status == RepositoryStatus.SYNC_FAILED.value
    assert "not found" in (repo_row(db, GID).last_error or "")


def test_finalize_refused_while_deferred_events_exist(
    db, indexer, kafka_topics, worker_factory
):
    """§62: SYNCING -> READY only with zero parked live events."""
    env = _setup(db, indexer, kafka_topics, worker_factory)
    target = "a" * 40
    with db() as session, session.begin():
        session.add(
            Repository(
                github_repository_id=GID,
                name="kyro-demo",
                full_name="acme/kyro-demo",
                owner="acme",
                default_branch="main",
                status=RepositoryStatus.SYNCING.value,
                backfill_published_through_commit=target,
                synced_through_commit=target,
                sync_target_commit=target,
            )
        )
        session.add(
            IngestionEvent(
                event_id="parked-1",
                repository_github_id=GID,
                kind="live",
                status=EventStatus.DEFERRED.value,
                payload={"parked": True},
            )
        )

    assert env.manager._try_finalize(GID, target) is False
    assert repo_row(db, GID).status == RepositoryStatus.SYNCING.value

    with db() as session, session.begin():
        row = session.scalar(
            select(IngestionEvent).where(IngestionEvent.event_id == "parked-1")
        )
        row.status = EventStatus.PROCESSED.value  # flush happened

    assert env.manager._try_finalize(GID, target) is True
    assert repo_row(db, GID).status == RepositoryStatus.READY.value


def test_finalize_refused_on_boundary_mismatch(
    db, indexer, kafka_topics, worker_factory
):
    """published != target or synced != target -> no premature READY."""
    env = _setup(db, indexer, kafka_topics, worker_factory)
    with db() as session, session.begin():
        session.add(
            Repository(
                github_repository_id=GID,
                name="kyro-demo",
                full_name="acme/kyro-demo",
                owner="acme",
                status=RepositoryStatus.SYNCING.value,
                backfill_published_through_commit="b" * 40,  # != target
                synced_through_commit="a" * 40,
            )
        )
    assert env.manager._try_finalize(GID, "a" * 40) is False
    assert repo_row(db, GID).status == RepositoryStatus.SYNCING.value


def test_advisory_lock_blocks_second_sync_run(
    db, indexer, kafka_topics, worker_factory
):
    """Cross-process exclusion: another holder of the advisory lock wins."""
    env = _setup(db, indexer, kafka_topics, worker_factory)
    env.fake.push("c0", {"a.py": "1\n"})
    _onboard(env, run=False)

    holder = db()
    # Advisory locks live on the pooled CONNECTION, not the SQLAlchemy
    # session: they survive rollback/close and MUST be unlocked explicitly
    # or every later test's pg_try_advisory_lock fails forever.
    lock_conn = holder.connection()
    try:
        assert lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": GID}
        ).scalar()

        status = env.manager.run_sync(GID)
        # Did not run: returned current status without publishing.
        assert status == RepositoryStatus.SYNCING.value
        assert repo_row(db, GID).backfill_published_through_commit is None
    finally:
        try:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": GID})
            holder.commit()
        except Exception:
            holder.rollback()
        holder.close()

    # Lock holder gone: the run proceeds normally now.
    env.worker.start()
    try:
        assert env.manager.run_sync(GID) == RepositoryStatus.READY.value
    finally:
        env.worker.stop()


def test_resync_full_clears_published_boundary(
    db, indexer, kafka_topics, worker_factory
):
    env = _setup(db, indexer, kafka_topics, worker_factory)
    env.fake.push("c0", {"a.py": "1\n"})
    _onboard(env, run=False)
    env.worker.start()
    try:
        assert env.manager.run_sync(GID) == RepositoryStatus.READY.value
        snap = env.manager.resync(GID, full=True, run=False)
        assert snap["status"] == RepositoryStatus.SYNCING.value
        assert snap["backfill_published_through_commit"] is None
        # full re-publish works end to end
        assert env.manager.run_sync(GID) == RepositoryStatus.READY.value
    finally:
        env.worker.stop()
    assert repo_row(db, GID).synced_through_commit == env.fake.head


def test_pending_sync_ids_discovers_interrupted_runs(
    db, indexer, kafka_topics, worker_factory
):
    env = _setup(db, indexer, kafka_topics, worker_factory)
    assert env.manager.pending_sync_ids() == []

    _onboard(env, run=False)  # SYNCING, never run (simulated crash)
    assert env.manager.pending_sync_ids() == [GID]

    env.fake.push("c0", {"a.py": "1\n"})
    env.worker.start()
    try:
        env.manager.run_sync(GID)
    finally:
        env.worker.stop()
    assert env.manager.pending_sync_ids() == []
