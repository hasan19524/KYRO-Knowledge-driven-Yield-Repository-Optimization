"""End-to-end synchronization race test (§62 / §15).

Sequence under test (the locked guarantee):
  1. run_sync publishes history and blocks waiting for the worker to apply.
  2. A live push lands WHILE the repo is SYNCING -> durably parked (deferred),
     nothing applied, repo still SYNCING.
  3. The worker starts: backfill applies, head re-read shows the new commit,
     target extends, the new range publishes, the parked event flushes.
  4. READY commits only when published == applied == latest head AND zero
     deferred events remain - verified by the final state.
"""

from __future__ import annotations

import threading

from sqlalchemy import func, select

from app.db.models import (
    Commit,
    EventStatus,
    IngestionEvent,
    RepositoryStatus,
)
from app.ingest.processor import HandleOutcome
from tests.conftest import (
    apply_event,
    event_row,
    live_event_for_head,
    repo_row,
    wait_for,
)
from tests.test_sync_manager import GID, _onboard, _setup


def test_live_push_during_sync_parks_then_flushes_before_ready(
    db, indexer, kafka_topics, worker_factory
):
    env = _setup(db, indexer, kafka_topics, worker_factory, timeout=90.0)
    env.fake.push("c1", {"a.py": "1\n"})
    c2 = env.fake.push("c2", {"a.py": "2\n"})
    _onboard(env, run=False)

    # --- run_sync in a background thread; it publishes then waits ---------
    result: dict[str, str] = {}

    def _run() -> None:
        result["status"] = env.manager.run_sync(GID)

    sync_thread = threading.Thread(target=_run, name="e2e-sync-run")
    sync_thread.start()
    try:
        # Phase A: history published, worker not running -> sync is blocked
        # inside _wait_applied; repo is SYNCING.
        assert wait_for(
            lambda: repo_row(db, GID).backfill_published_through_commit == c2,
            timeout=20,
        ), "history must be published before the race window opens"
        repo = repo_row(db, GID)
        assert repo.status == RepositoryStatus.SYNCING.value
        assert repo.synced_through_commit is None

        # Phase B: live push lands mid-sync -> parked durably, NOT applied.
        c3 = env.fake.push("c3 live", {"b.py": "3\n"})
        live = live_event_for_head(env.fake, delivery_id="e2e-live-1")
        outcome = apply_event(env.processor, live, topic="kyro.github.push")
        assert outcome == HandleOutcome.DEFERRED

        row = event_row(db, "e2e-live-1")
        assert row is not None
        assert row.status == EventStatus.DEFERRED.value
        assert row.pg_status == "pending"  # never applied while parked
        assert repo_row(db, GID).status == RepositoryStatus.SYNCING.value
        with db() as session:
            assert session.scalar(select(func.count()).select_from(Commit)) == 0

        # Phase C: worker starts -> backfill applies, target extends to c3,
        # parked live event flushes, READY commits only at the very end.
        env.worker.start()
        assert wait_for(
            lambda: repo_row(db, GID).status == RepositoryStatus.READY.value,
            timeout=60,
        ), "sync must reach READY after the race is resolved"
        sync_thread.join(timeout=30)
    finally:
        env.worker.stop()
        sync_thread.join(timeout=90)

    # --- final state: everything caught up, nothing parked ---------------
    assert result.get("status") == RepositoryStatus.READY.value
    assert not sync_thread.is_alive()

    repo = repo_row(db, GID)
    assert repo.status == RepositoryStatus.READY.value
    assert repo.backfill_published_through_commit == c3
    assert repo.synced_through_commit == c3
    assert repo.last_error is None
    assert repo.sync_completed_at is not None

    live_row = event_row(db, "e2e-live-1")
    assert live_row.status == EventStatus.PROCESSED.value
    assert live_row.pg_status == "done"

    with db() as session:
        # c1 + c2 (backfill) + c3 (backfill extension); the parked live event
        # re-applied the same commit idempotently.
        assert session.scalar(select(func.count()).select_from(Commit)) == 3
        deferred = session.scalar(
            select(func.count())
            .select_from(IngestionEvent)
            .where(IngestionEvent.status == EventStatus.DEFERRED.value)
        )
        assert deferred == 0
        statuses = session.scalars(select(IngestionEvent.status)).all()
        assert all(s == EventStatus.PROCESSED.value for s in statuses)

    # The parked live event's commit content made it into the index.
    assert repo_row(db, GID).full_name == "acme/kyro-demo"
