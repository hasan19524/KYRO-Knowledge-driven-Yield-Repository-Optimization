"""Ingestion worker: Kafka consumer loop with offset discipline.

Guarantees:
- Manual, per-message offset commits ONLY after the processor reports
  PROCESSED / DUPLICATE / DEFERRED / INVALID (each of which is durably
  recorded in PostgreSQL first).
- Transient failures are retried in place (same message, exponential
  backoff) up to MAX_EVENT_ATTEMPTS; ordering is preserved because the
  partition is not advanced past the failing message.
- Exhausted retries mark the event FAILED in PostgreSQL and PAUSE the
  partition for the remainder of the session (never skip an offset).
  Remaining already-fetched messages from the paused partition are dropped
  from this session; uncommitted offsets redeliver after restart.
- Cross-repo concurrency: each worker thread owns one consumer; messages
  from different repositories on different partitions proceed independently
  (except when a paused partition blocks later messages — required by
  at-least-once ordering rules, and live events for SYNCING repos are
  deferred rather than blocking).
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time

from confluent_kafka import (
    Consumer,
    KafkaError,
    KafkaException,
    Message,
    TopicPartition,
)

from app.config import (
    BACKFILL_TOPIC,
    CONSUMER_GROUP,
    EVENT_RETRY_BASE_DELAY_S,
    EVENT_RETRY_MAX_DELAY_S,
    KAFKA_BOOTSTRAP_SERVERS,
    LIVE_TOPIC,
    MAX_EVENT_ATTEMPTS,
    WORKER_POLL_TIMEOUT_MS,
)
from app.ingest.processor import EventProcessor, HandleOutcome

log = logging.getLogger("kyro.kafka.consumer")


class IngestionWorker:
    def __init__(
        self,
        processor: EventProcessor,
        *,
        bootstrap: str | None = None,
        group_id: str | None = None,
        topics: list[str] | None = None,
        client_id: str | None = None,
    ) -> None:
        self.processor = processor
        self.topics = topics or [LIVE_TOPIC, BACKFILL_TOPIC]
        self._paused: set[tuple[str, int]] = set()
        self._lock = threading.Lock()
        self._running = False
        conf: dict = {
            "bootstrap.servers": bootstrap or KAFKA_BOOTSTRAP_SERVERS,
            "group.id": group_id or CONSUMER_GROUP,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            "fetch.wait.max.ms": 50,
        }
        if client_id:
            conf["client.id"] = client_id
        self.consumer = Consumer(conf)

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.consumer.subscribe(self.topics, on_assign=self._on_assign)
        self._running = True

    def stop(self) -> None:
        self._running = False
        with contextlib.suppress(Exception):
            self.consumer.close()

    def _on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        log.info(
            "partitions_assigned %s",
            [(p.topic, p.partition) for p in partitions],
        )
        with self._lock:
            self._paused.clear()

    # ------------------------------------------------------------------ loop
    def poll_once(
        self, *, num_messages: int = 200, timeout_s: float | None = None
    ) -> int:
        """Poll and process one batch. Returns number of messages handled."""
        timeout = (
            timeout_s if timeout_s is not None else WORKER_POLL_TIMEOUT_MS / 1000.0
        )
        try:
            msgs = self.consumer.consume(num_messages=num_messages, timeout=timeout)
        except KafkaException as exc:
            log.warning("kafka_consume_error error=%s", exc)
            return 0

        handled = 0
        for msg in msgs:
            err = msg.error()
            if err is not None:
                if err.code() == KafkaError._PARTITION_EOF:
                    continue
                log.error("kafka_message_error error=%s", err)
                continue
            tp = (msg.topic(), msg.partition())
            with self._lock:
                if tp in self._paused:
                    # Partition gave up earlier this session; do not process or
                    # commit (offset stays uncommitted -> redelivered on restart).
                    continue
            self._handle(msg)
            handled += 1
        return handled

    def run_forever(self) -> None:
        self.start()
        try:
            while self._running:
                self.poll_once()
        finally:
            self.stop()

    # ---------------------------------------------------------------- handle
    def _handle(self, msg: Message) -> None:
        topic = msg.topic()
        partition = msg.partition()
        offset = msg.offset()
        if topic is None or partition is None or offset is None:
            # Error messages never reach here (filtered in poll_once), but the
            # confluent stubs still type these as Optional - guard anyway.
            log.error("message_missing_metadata error=%s", msg.error())
            return
        raw = msg.value()
        if raw is None:
            log.error(
                "empty_message topic=%s partition=%d offset=%d",
                topic,
                partition,
                offset,
            )
            self._commit(msg)
            return

        attempts = 0
        last_error = ""
        while True:
            attempts += 1
            try:
                outcome = self.processor.handle_raw(
                    raw, topic=topic, partition=partition, offset=offset
                )
            except Exception as exc:  # defensive: processor is exception-safe
                outcome = HandleOutcome.RETRY
                last_error = f"unhandled:{exc}"

            if outcome in (
                HandleOutcome.PROCESSED,
                HandleOutcome.DUPLICATE,
                HandleOutcome.DEFERRED,
                HandleOutcome.INVALID,
            ):
                self._commit(msg)
                return

            if outcome is HandleOutcome.FAILED:
                # Processor already recorded event FAILED + repo SYNC_FAILED.
                self._pause(topic, partition)
                return

            # RETRY
            if attempts >= MAX_EVENT_ATTEMPTS:
                last_error = (
                    last_error or f"retries_exhausted after {attempts} attempts"
                )
                self.processor.mark_failure(
                    raw, f"offset {topic}[{partition}]@{offset}: {last_error}"
                )
                self._pause(topic, partition)
                return
            delay = min(
                EVENT_RETRY_BASE_DELAY_S * (2 ** (attempts - 1)),
                EVENT_RETRY_MAX_DELAY_S,
            )
            log.warning(
                "event_attempt_retry attempt=%d/%d topic=%s partition=%d offset=%d sleep=%.2fs",
                attempts,
                MAX_EVENT_ATTEMPTS,
                topic,
                partition,
                offset,
                delay,
            )
            time.sleep(delay)

    def _commit(self, msg: Message) -> None:
        try:
            self.consumer.commit(message=msg, asynchronous=False)
        except KafkaException as exc:
            log.error(
                "offset_commit_failed topic=%s partition=%d offset=%d error=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
                exc,
            )

    def _pause(self, topic: str, partition: int) -> None:
        with self._lock:
            if (topic, partition) in self._paused:
                return
            self._paused.add((topic, partition))
        try:
            self.consumer.pause([TopicPartition(topic, partition)])
        except Exception as exc:
            log.error(
                "partition_pause_failed topic=%s partition=%d error=%s",
                topic,
                partition,
                exc,
            )
        log.error(
            "partition_paused topic=%s partition=%d reason=event_failure_exhausted offset_not_committed",
            topic,
            partition,
        )

    @property
    def paused_partitions(self) -> set[tuple[str, int]]:
        with self._lock:
            return set(self._paused)


__all__ = ["IngestionWorker"]
