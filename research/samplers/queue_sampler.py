"""Kafka queue-lag sampler -> research/data/live/queues_YYYYMMDD.csv.

Every --interval seconds records, for both KYRO topics and every partition:
  end_offset (messages available), committed_offset (group's position),
  lag = end - committed for consumer group `kyro-ingestion-workers`.

lag is the REAL queueing delay signal for the load-balancing research:
it is what a scheduler would see as backlog depth over time.

Uses confluent_kafka (same lib as the backend, in backend\\.venv).
Stop: STOP_QUEUE_SAMPLER file in this directory.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import time
from pathlib import Path

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
STOP_FILE = Path(__file__).resolve().parent / "STOP_QUEUE_SAMPLER"
HEADER = ["ts", "topic", "partition", "end_offset", "committed_offset", "lag"]
TOPICS = ["kyro.github.push", "kyro.github.backfill"]
GROUP = "kyro-ingestion-workers"
BOOTSTRAP = "127.0.0.1:9092"


def now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=3.0)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    path = OUT_DIR / f"queues_{day}.csv"
    first = not path.exists()

    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    # committed offsets need a Consumer handle on the group (no join, no poll)
    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP,
            "group.id": GROUP,
            "enable.auto.commit": False,
            # do NOT join/steal partitions: we only read committed offsets
            "partition.assignment.strategy": "range",
        }
    )
    print(f"[queue_sampler] writing {path} every {args.interval}s", flush=True)
    errors = 0
    while not STOP_FILE.exists():
        t0 = time.monotonic()
        try:
            md = admin.list_topics(timeout=10)
            tps: list[TopicPartition] = []
            for t in TOPICS:
                td = md.topics.get(t)
                if td is None:
                    continue
                tps.extend(TopicPartition(t, p) for p in sorted(td.partitions))
            if tps:
                ends = consumer.get_watermark_offsets
                # watermarks: (low, high)
                committed = consumer.committed(tps, timeout=10.0)
                cmap = {(tp.topic, tp.partition): tp.offset for tp in committed}
                rows = []
                for tp in tps:
                    try:
                        _, high = ends(tp, timeout=10.0)
                    except Exception:  # noqa: BLE001
                        continue
                    c = cmap.get((tp.topic, tp.partition), -1001)
                    c_off = -1 if c in (-1001, -1) else c
                    lag = (
                        high - c_off if c_off >= 0 else high
                    )  # no commit yet -> all pending
                    rows.append([now_iso(), tp.topic, tp.partition, high, c_off, lag])
                if rows:
                    with path.open("a", newline="", encoding="utf-8") as f:
                        w = csv.writer(f)
                        if first:
                            w.writerow(HEADER)
                            first = False
                        w.writerows(rows)
            errors = 0
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[queue_sampler] error#{errors}: {exc}", flush=True)
            if errors > 30:
                time.sleep(15)
        wait = args.interval - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
    consumer.close()
    print("[queue_sampler] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
