"""1 Hz docker resource sampler -> research/data/live/resources_YYYYMMDD.csv.

Long-running. Append-only. Never raises: transient docker errors are counted,
not fatal. Start:  python resource_sampler.py [--interval 1.0]
Stop: Ctrl-C or a file named STOP_RESOURCE_SAMPLER in this directory.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
STOP_FILE = Path(__file__).resolve().parent / "STOP_RESOURCE_SAMPLER"
HEADER = [
    "ts",
    "container",
    "cpu_pct",
    "mem_used_bytes",
    "mem_limit_bytes",
    "net_io_bytes",
    "block_io_bytes",
    "pids",
]


def _parse_size(s: str) -> int:
    """'43.4MiB' -> bytes. Handles b/KiB/MiB/GiB; bare number passes through."""
    s = s.strip()
    units = {
        "b": 1,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "k": 1000,
        "m": 1000**2,
        "g": 1000**3,
    }
    for suffix in ("gib", "mib", "kib", "g", "m", "k", "b"):
        if s.lower().endswith(suffix):
            try:
                return int(float(s[: -len(suffix)]) * units[suffix])
            except ValueError:
                return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def _parse_io(s: str) -> int:
    """'1.2kB / 3.4MB' -> total bytes (sum of both sides)."""
    total = 0
    for part in s.split("/"):
        total += _parse_size(part)
    return total


def sample_rows() -> list[list]:
    out = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}|{{.PIDs}}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"docker stats rc={out.returncode}: {out.stderr[:200]}")
    now = (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split("|")
        if len(parts) != 6:
            continue
        name, cpu, mem, net, block, pids = parts
        cpu_val = cpu.rstrip("%").strip() or "0"
        mem_used, _, mem_limit = mem.partition("/")
        rows.append(
            [
                now,
                name.strip(),
                cpu_val,
                _parse_size(mem_used),
                _parse_size(mem_limit),
                _parse_io(net),
                _parse_io(block),
                pids.strip(),
            ]
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    path = OUT_DIR / f"resources_{day}.csv"
    errors = 0
    print(f"[resource_sampler] writing {path} every {args.interval}s", flush=True)
    while not STOP_FILE.exists():
        t0 = time.monotonic()
        try:
            rows = sample_rows()
            new_file = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(HEADER)
                w.writerows(rows)
            errors = 0
        except Exception as exc:  # noqa: BLE001 - sampler must survive anything
            errors += 1
            print(
                f"[resource_sampler] error#{errors}: {exc}", file=sys.stderr, flush=True
            )
            if errors > 60:
                # docker CLI likely gone; back off hard rather than spin
                time.sleep(15)
        wait = args.interval - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
    print("[resource_sampler] stopped by STOP file", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
