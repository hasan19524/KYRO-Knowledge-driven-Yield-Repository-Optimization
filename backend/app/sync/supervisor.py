"""Sync supervisor: resumes repositories left in SYNCING (crash recovery).

A sync run interrupted by a process restart leaves the repository in
SYNCING with a durable published boundary; the supervisor picks it up and
continues. It never touches other statuses (SYNC_FAILED/ACCESS_REVOKED
require an explicit re-sync).
"""

from __future__ import annotations

import logging
import threading

from app import config
from app.sync.manager import SyncManager

log = logging.getLogger("kyro.sync.supervisor")


class SyncSupervisor(threading.Thread):
    def __init__(
        self,
        manager: SyncManager,
        *,
        interval: float | None = None,
        name: str = "kyro-sync-supervisor",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.manager = manager
        self.interval = (
            interval if interval is not None else config.SYNC_SUPERVISOR_INTERVAL_S
        )
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        log.info("sync_supervisor_started interval=%.1fs", self.interval)
        while not self._stop.wait(self.interval):
            try:
                for github_id in self.manager.pending_sync_ids():
                    if self.manager.is_active(github_id):
                        continue
                    log.info(
                        "sync_supervisor_resume github_repository_id=%d", github_id
                    )
                    self.manager.trigger(github_id)
            except Exception:
                log.exception("sync_supervisor_iteration_error")
        log.info("sync_supervisor_stopped")


__all__ = ["SyncSupervisor"]
