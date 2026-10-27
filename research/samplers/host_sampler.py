"""Host-process resource sampler (backend uvicorn, workers, next dev, etc.)

Docker containers are covered by resource_sampler.py; this covers the HOST
python/node processes that actually execute ingestion work. Uses psutil from
research/.venv. Writes research/data/live/host_YYYYMMDD.csv at 1 Hz.

Stop: STOP_HOST_SAMPLER file in this directory.
"""

from __future__ import annotations

import datetime as dt
import os
import time
from pathlib import Path

import psutil

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
STOP_FILE = Path(__file__).resolve().parent / "STOP_HOST_SAMPLER"
HEADER = ["ts", "pid", "name", "cpu_pct", "rss_bytes", "cmd_hint"]

# Processes worth tracking: ingestion workers, api, frontend, router, tunnel.
INTEREST = ("python", "node", "cloudflared")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    path = OUT_DIR / f"host_{day}.csv"
    first = not path.exists()
    print(f"[host_sampler] writing {path} every 1.0s", flush=True)
    seen_pids: set[int] = set()
    while not STOP_FILE.exists():
        t0 = time.monotonic()
        try:
            now = (
                dt.datetime.now(dt.timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            rows = []
            for p in psutil.process_iter(
                ["pid", "name", "cmdline", "cpu_percent", "memory_info"]
            ):
                try:
                    name = (p.info["name"] or "").lower()
                    if not any(k in name for k in INTEREST):
                        continue
                    cpu = p.info["cpu_percent"]
                    if cpu is None:
                        continue
                    cmd = " ".join(p.info["cmdline"] or [])[:160]
                    # Skip noise: browsers, editors, unrelated node tools
                    if not any(
                        k in cmd
                        for k in (
                            "app.worker_main",
                            "app.main:app",
                            "app.sync_main",
                            "public_router",
                            "next",
                            "cloudflared",
                            "resource_sampler",
                            "db_sampler",
                            "host_sampler",
                            "burst_generator",
                            "research",
                        )
                    ):
                        continue
                    rows.append(
                        (
                            now,
                            p.pid,
                            p.info["name"],
                            round(cpu, 2),
                            p.info["memory_info"].rss,
                            cmd,
                        )
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if rows:
                new_file = first
                with path.open("a", encoding="utf-8") as f:
                    if new_file:
                        f.write(",".join(HEADER) + "\n")
                        first = False
                    for r in rows:
                        # cmd_hint last and already quoted-free; csv-safe via quotes
                        f.write(f'{r[0]},{r[1]},"{r[2]}",{r[3]},{r[4]},"{r[5]}"\n')
        except Exception as exc:  # noqa: BLE001 - sampler survives anything
            print(f"[host_sampler] error: {exc}", flush=True)
        elapsed = time.monotonic() - t0
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
    print("[host_sampler] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
