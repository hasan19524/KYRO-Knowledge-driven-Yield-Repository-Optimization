"""Backfill event producer.

Ordering contract: a single producer instance is used per sync run; librdkafka
preserves per-partition ordering for a single producer, and the sync manager
emits events in strictly increasing commit order (oldest first). Key is
repository.github_id, matching the live topic's keying convention (§7).
Delivery guarantee: acks=all + idempotence; produce errors are surfaced
before the sync manager advances its published boundary.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from confluent_kafka import KafkaError, Producer

from app.config import BACKFILL_TOPIC, KAFKA_BOOTSTRAP_SERVERS

log = logging.getLogger("kyro.kafka.producer")


class BackfillDeliveryError(RuntimeError):
    pass


class BackfillProducer:
    def __init__(
        self, bootstrap: str | None = None, *, client_id: str = "kyro-sync"
    ) -> None:
        self._bootstrap = bootstrap or KAFKA_BOOTSTRAP_SERVERS
        self._errors: list[tuple[str, str]] = []
        self._producer = Producer(
            {
                "bootstrap.servers": self._bootstrap,
                "acks": "all",
                "enable.idempotence": True,
                "linger.ms": 5,
                "message.timeout.ms": 60_000,
                "client.id": client_id,
            }
        )
        self._produced = 0

    def send(
        self,
        repository_github_id: int,
        event: dict[str, Any],
        *,
        topic: str | None = None,
    ) -> None:
        topic = topic or BACKFILL_TOPIC
        payload = json.dumps(event, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        key = str(repository_github_id).encode("utf-8")

        def _cb(err: KafkaError | None, msg: Any) -> None:
            if err is not None:
                self._errors.append((topic, str(err)))
            else:
                self._produced += 1

        self._producer.produce(topic, key=key, value=payload, on_delivery=_cb)
        self._producer.poll(0)

    def flush(self, timeout: float = 30.0) -> int:
        remaining = self._producer.flush(timeout)
        if remaining:
            raise BackfillDeliveryError(
                f"{remaining} backfill messages unflushed after {timeout}s"
            )
        if self._errors:
            errors = self._errors[:]
            self._errors.clear()
            raise BackfillDeliveryError(f"backfill delivery failed: {errors[:3]}")
        produced, self._produced = self._produced, 0
        return produced

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._producer.flush(10)


__all__ = ["BackfillDeliveryError", "BackfillProducer"]
