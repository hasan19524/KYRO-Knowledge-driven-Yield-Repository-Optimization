"""Kafka topic administration: idempotent create-if-missing.

The live topic (`kyro.github.push`) is created by kafka/local scripts and the
n8n pipeline; the worker only ever ensures existence so a fresh environment
cannot wedge the consumer. Existing topics are never re-partitioned or
re-configured here (normalization lives in the kafka/ scripts).
"""

from __future__ import annotations

import logging
import time

from confluent_kafka.admin import (
    AdminClient,
    NewTopic,  # pyright: ignore[reportPrivateImportUsage]
)

from app.config import (
    BACKFILL_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_MIN_INSYNC_REPLICAS,
    KAFKA_PARTITIONS,
    KAFKA_RETENTION_MS,
    LIVE_TOPIC,
)

log = logging.getLogger("kyro.kafka.topics")


def ensure_topic(
    name: str,
    bootstrap: str | None = None,
    *,
    partitions: int | None = None,
    replication_factor: int = 1,
    timeout_s: float = 15.0,
) -> None:
    """Create `name` if missing (idempotent). Never modifies an existing topic.

    Locked parameters: 5 partitions, 7-day retention, cleanup.policy=delete,
    min.insync.replicas per environment (1 local / higher in production via
    the kafka/ scripts).
    """
    bootstrap = bootstrap or KAFKA_BOOTSTRAP_SERVERS
    partitions = partitions if partitions is not None else KAFKA_PARTITIONS
    admin = AdminClient({"bootstrap.servers": bootstrap})
    deadline = time.monotonic() + timeout_s

    md = admin.list_topics(timeout=max(1.0, deadline - time.monotonic()))
    if name in md.topics:
        existing = md.topics[name].partitions
        if len(existing) != partitions:
            log.warning(
                "topic_partitions_mismatch topic=%s existing=%d wanted=%d "
                "(normalize via kafka/create-topic script; not recreating)",
                name,
                len(existing),
                partitions,
            )
        log.info("topic_present topic=%s partitions=%d", name, len(existing))
        return

    topic = NewTopic(
        name,
        num_partitions=partitions,
        replication_factor=replication_factor,
        config={
            "cleanup.policy": "delete",
            "retention.ms": str(KAFKA_RETENTION_MS),
            "min.insync.replicas": str(
                KAFKA_MIN_INSYNC_REPLICAS if replication_factor > 1 else 1
            ),
        },
    )
    futures = admin.create_topics([topic], request_timeout=10)
    for created, future in futures.items():
        try:
            future.result()
            log.info(
                "topic_created topic=%s partitions=%d rf=%d",
                created,
                partitions,
                replication_factor,
            )
        except Exception as exc:
            # Race with another creator or already-exists is fine.
            if "already exists" in str(exc).lower() or "TOPIC_ALREADY_EXISTS" in str(
                exc
            ):
                log.info("topic_race_exists topic=%s", created)
            else:
                raise

    while time.monotonic() < deadline:
        md = admin.list_topics(timeout=5)
        if name in md.topics and md.topics[name].partitions:
            return
        time.sleep(0.2)
    raise RuntimeError(f"topic {name} not visible after create")


def ensure_backfill_topic(
    bootstrap: str | None = None,
    *,
    partitions: int | None = None,
    replication_factor: int = 1,
    timeout_s: float = 15.0,
) -> None:
    """Ensure the locked backfill topic kyro.github.backfill exists."""
    ensure_topic(
        BACKFILL_TOPIC,
        bootstrap,
        partitions=partitions,
        replication_factor=replication_factor,
        timeout_s=timeout_s,
    )


def ensure_live_topic(bootstrap: str | None = None) -> None:
    """Ensure the existing live topic kyro.github.push exists (no mutation)."""
    ensure_topic(LIVE_TOPIC, bootstrap)


__all__ = ["ensure_backfill_topic", "ensure_live_topic", "ensure_topic"]
