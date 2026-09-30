#!/usr/bin/env python3
"""KYRO ingestion-worker verification consumer.

Demonstrates the agreed consumption strategy (decisions 5/6/8/12):
  * consumer group: kyro-ingestion-workers
  * at-least-once: offsets are committed MANUALLY, only after the event was
    processed (enable.auto.commit=false)
  * idempotency by event.id (X-GitHub-Delivery): a redelivered event is
    detected and skipped; the offset still advances so the log keeps moving.
    (Production equivalent: a unique row in PostgreSQL; this script keeps the
    seen-set in a local state file so the demo survives restarts.)
  * strict per-repository ordering: partitions are processed serially; when an
    event fails, its offset is not committed, so it is redelivered on the next
    run and later events for that repository cannot advance past it.

Usage:
  python consume_verify.py                       # process until idle
  FAIL_ON=<event.id> python consume_verify.py    # fail that event: exit 1
                                                 # WITHOUT committing it
Environment:
  BOOTSTRAP   broker list (default localhost:9092)
  STATE_FILE  seen-event store (default ./kafka-verify-state.json)
  TOPIC       default kyro.github.push
"""

from __future__ import annotations

import json
import os
import sys

from confluent_kafka import Consumer, KafkaException

TOPIC = os.environ.get("TOPIC", "kyro.github.push")
STATE_FILE = os.environ.get(
    "STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "kafka-verify-state.json"),
)
FAIL_ON = os.environ.get("FAIL_ON")
IDLE_SECONDS = 6.0


def load_seen() -> set[str]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as fh:
            return set(json.load(fh).get("seen", []))
    return set()


def save_seen(seen: set[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump({"seen": sorted(seen)}, fh, indent=2)


def main() -> int:
    conf = {
        "bootstrap.servers": os.environ.get("BOOTSTRAP", "localhost:9092"),
        "group.id": "kyro-ingestion-workers",
        # Commit only after successful processing -> at-least-once.
        "enable.auto.commit": False,
        # First run of a new group starts at the oldest retained event.
        "auto.offset.reset": "earliest",
        "client.id": "kyro-verify-consumer",
    }

    consumer = Consumer(conf)
    consumer.subscribe([TOPIC])
    seen = load_seen()
    print(
        f"SUBSCRIBED group=kyro-ingestion-workers topic={TOPIC} seen_ids={len(seen)}",
        flush=True,
    )

    processed = duplicates = 0
    idle_since = None
    try:
        while True:
            msgs = consumer.consume(num_messages=100, timeout=IDLE_SECONDS)
            if not msgs:
                if idle_since is None:
                    idle_since = True
                    continue
                break

            for msg in msgs:
                if msg.error() is not None:
                    raise KafkaException(msg.error())
                if msg.value() is None:  # tombstone / control message
                    consumer.commit(message=msg, asynchronous=False)
                    continue

                event = json.loads(msg.value())
                event_id = event.get("event", {}).get("id")
                repo_id = event.get("repository", {}).get("github_id")
                loc = f"partition={msg.partition()} offset={msg.offset()}"

                if event_id in seen:
                    # Idempotent skip: already fully processed in an earlier
                    # delivery. Commit so this offset is not redelivered forever.
                    duplicates += 1
                    print(
                        f"SKIP_DUPLICATE event.id={event_id} repo={repo_id} {loc}",
                        flush=True,
                    )
                    consumer.commit(message=msg, asynchronous=False)
                    continue

                if FAIL_ON and event_id == FAIL_ON:
                    # Simulated processing failure: no commit for this offset.
                    # The failed event (and everything after it for this
                    # partition) stays uncommitted and will be redelivered.
                    print(
                        f"FAIL_EVENT event.id={event_id} repo={repo_id} {loc} (offset NOT committed, exiting)",
                        flush=True,
                    )
                    print(
                        f"SUMMARY processed={processed} duplicates={duplicates} failed=1",
                        flush=True,
                    )
                    return 1

                # "Process": here just validation; persistence would happen
                # before the commit in a real worker.
                if repo_id is None:
                    print(
                        f"FAIL_EVENT event.id={event_id} missing repository.github_id {loc} (offset NOT committed)",
                        flush=True,
                    )
                    return 1

                processed += 1
                seen.add(event_id)
                save_seen(seen)
                consumer.commit(message=msg, asynchronous=False)
                print(
                    f"PROCESSED event.id={event_id} repo={repo_id} {loc} committed",
                    flush=True,
                )
    finally:
        try:
            positions = []
            for tp in sorted(consumer.assignment(), key=lambda t: t.partition):
                committed = consumer.committed([tp], timeout=10)[0]
                offset = (
                    committed.offset if committed and committed.offset >= 0 else "none"
                )
                positions.append(f"p{tp.partition}={offset}")
            print(
                f"COMMITTED_POSITIONS {' '.join(positions) if positions else '(no assignment)'}",
                flush=True,
            )
        finally:
            consumer.close()

    print(f"SUMMARY processed={processed} duplicates={duplicates} failed=0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
