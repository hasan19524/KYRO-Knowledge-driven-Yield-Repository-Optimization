"""Per-server HTTP/TCP latency probe -> research/data/live/http_latency_YYYYMMDD.csv.

Probes every service endpoint on a fixed cadence and records real round-trip
latency (TCP connect + first byte + total). This is the per-server latency
data requested for the research dataset.

Targets (KYRO's own services, local machine only):
  backend   http://127.0.0.1:8000/health
  frontend  http://127.0.0.1:3001/
  router    http://127.0.0.1:8090/
  n8n       http://127.0.0.1:5678/healthz
  chroma    http://127.0.0.1:8100/api/v1/heartbeat
  postgres  TCP 127.0.0.1:5433
  kafka     TCP 127.0.0.1:9092

Stop: STOP_HTTP_PROBE file in this directory.
"""

from __future__ import annotations

import csv
import datetime as dt
import socket
import time
from http.client import HTTPConnection
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
STOP_FILE = Path(__file__).resolve().parent / "STOP_HTTP_PROBE"
INTERVAL_S = 5.0
HEADER = [
    "ts",
    "server",
    "protocol",
    "status",
    "connect_ms",
    "ttfb_ms",
    "total_ms",
    "error",
]

HTTP_TARGETS = [
    ("backend", "127.0.0.1", 8000, "/health"),
    ("frontend", "127.0.0.1", 3001, "/"),
    ("router", "127.0.0.1", 8090, "/"),
    ("n8n", "127.0.0.1", 5678, "/healthz"),
    ("chroma", "127.0.0.1", 8100, "/api/v1/heartbeat"),
]
TCP_TARGETS = [
    ("postgres", "127.0.0.1", 5433),
    ("kafka", "127.0.0.1", 9092),
]


def now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def probe_http(name: str, host: str, port: int, path: str) -> list:
    t0 = time.perf_counter()
    connect_ms = ttfb_ms = -1.0
    status = 0
    err = ""
    try:
        conn = HTTPConnection(host, port, timeout=5.0)
        tc0 = time.perf_counter()
        conn.connect()
        connect_ms = (time.perf_counter() - tc0) * 1000
        r1 = time.perf_counter()
        conn.request("GET", path)
        resp = conn.getresponse()
        ttfb_ms = (time.perf_counter() - r1) * 1000
        status = resp.status
        resp.read(512)
        conn.close()
    except Exception as exc:  # noqa: BLE001 - probing must never die
        err = type(exc).__name__
        status = -1
    total_ms = (time.perf_counter() - t0) * 1000
    return [
        now_iso(),
        name,
        "http",
        status,
        round(connect_ms, 2),
        round(ttfb_ms, 2),
        round(total_ms, 2),
        err,
    ]


def probe_tcp(name: str, host: str, port: int) -> list:
    t0 = time.perf_counter()
    status = 0
    err = ""
    connect_ms = -1.0
    try:
        s = socket.create_connection((host, port), timeout=5.0)
        connect_ms = (time.perf_counter() - t0) * 1000
        s.close()
        status = 1
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__
        status = -1
    total_ms = (time.perf_counter() - t0) * 1000
    return [
        now_iso(),
        name,
        "tcp",
        status,
        round(connect_ms, 2),
        -1.0,
        round(total_ms, 2),
        err,
    ]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    path = OUT_DIR / f"http_latency_{day}.csv"
    first = not path.exists()
    print(f"[http_probe] writing {path} every {INTERVAL_S}s", flush=True)
    while not STOP_FILE.exists():
        t0 = time.monotonic()
        rows = [probe_http(n, h, p, q) for (n, h, p, q) in HTTP_TARGETS]
        rows += [probe_tcp(n, h, p) for (n, h, p) in TCP_TARGETS]
        try:
            with path.open("a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if first:
                    w.writerow(HEADER)
                    first = False
                w.writerows(rows)
        except Exception as exc:  # noqa: BLE001
            print(f"[http_probe] write error: {exc}", flush=True)
        elapsed = time.monotonic() - t0
        if elapsed < INTERVAL_S:
            time.sleep(INTERVAL_S - elapsed)
    print("[http_probe] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
