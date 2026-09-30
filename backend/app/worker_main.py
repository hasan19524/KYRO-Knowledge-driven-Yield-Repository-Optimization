"""Ingestion worker entrypoint.

Consumes the locked topics:

  kyro.github.push     (live events, produced by n8n)
  kyro.github.backfill (historical events, produced by the sync manager)

Offset discipline (manual commits only after durable success) and
per-repository ordering live in app.kafka.consumer / app.ingest.processor.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import threading

from app import config
from app.db import get_session_factory
from app.github.auth import GitHubAppAuth
from app.github.client import GitHubClient
from app.ingest.indexer import ChromaIndexer
from app.ingest.processor import EventProcessor
from app.kafka.consumer import IngestionWorker
from app.kafka.topics import ensure_backfill_topic, ensure_live_topic

log = logging.getLogger("kyro.worker")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    topics = [config.LIVE_TOPIC, config.BACKFILL_TOPIC]
    ensure_live_topic()
    ensure_backfill_topic()

    session_factory = get_session_factory()
    indexer = ChromaIndexer()
    github = GitHubClient(GitHubAppAuth())
    processor = EventProcessor(session_factory, indexer, github)

    n_workers = max(1, config.WORKER_CONCURRENCY)
    workers = [
        IngestionWorker(processor, topics=topics, client_id=f"kyro-worker-{i}")
        for i in range(n_workers)
    ]

    stop = threading.Event()

    def _handle_signal(signum, frame) -> None:
        log.info("worker_signal signal=%s", signum)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        # non-main thread / unsupported platform
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, _handle_signal)

    threads: list[threading.Thread] = []
    for i, worker in enumerate(workers):
        t = threading.Thread(
            target=worker.run_forever, name=f"kyro-worker-{i}", daemon=True
        )
        t.start()
        threads.append(t)
    log.info(
        "worker_started concurrency=%d topics=%s group=%s bootstrap=%s",
        n_workers,
        topics,
        config.CONSUMER_GROUP,
        config.KAFKA_BOOTSTRAP_SERVERS,
    )

    try:
        while not stop.wait(0.5):
            pass
    finally:
        for worker in workers:
            worker.stop()
        for t in threads:
            t.join(timeout=10)
        log.info("worker_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
