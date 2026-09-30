"""Standalone synchronization supervisor entrypoint.

Resumes repositories stuck in SYNCING after a crash/restart. The API process
runs an identical supervisor when SYNC_SUPERVISOR_ENABLED=1; running this
separately is optional and safe (a PostgreSQL advisory lock keyed on the
repository id guarantees at most one active run per repository).
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading

from app import config
from app.kafka.topics import ensure_backfill_topic, ensure_live_topic
from app.state import build_state
from app.sync.supervisor import SyncSupervisor

log = logging.getLogger("kyro.sync_main")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ensure_live_topic()
    ensure_backfill_topic()
    state = build_state()
    supervisor = SyncSupervisor(state.sync_manager)
    supervisor.start()
    log.info(
        "sync_main_started bootstrap=%s interval=%.1fs",
        config.KAFKA_BOOTSTRAP_SERVERS,
        config.SYNC_SUPERVISOR_INTERVAL_S,
    )

    stop = threading.Event()

    def _handle(signum, frame) -> None:
        log.info("sync_main_signal signal=%s", signum)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, _handle)

    try:
        while not stop.wait(0.5):
            pass
    finally:
        supervisor.stop()
        supervisor.join(timeout=5)
        state.shutdown()
        log.info("sync_main_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
