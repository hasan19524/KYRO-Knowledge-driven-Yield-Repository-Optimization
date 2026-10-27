"""Track B: live scale-out validation of the simulated worker fleet.

One invocation = ONE measured phase of the REAL KYRO pipeline:

  1. wait for the kyro-ingestion-workers consumer group to be fully drained
     (lag == 0 twice in a row) so every phase starts from the same state;
  2. snapshot consumer-group topology (members, partition assignment,
     host vs container members via source-IP heuristic) and docker stats
     for kyro-trackb-* containers;
  3. drive a REAL commit burst (burst_generator -> real webhook -> n8n ->
     Kafka -> workers) while a poller records group lag (+ container
     stats) every --poll-s seconds;
  4. wait until the backlog drains (lag == 0 twice after the last push);
  5. append one summary row to research/results/trackb_live.csv and write
     the full series to research/results/trackb_lag_<phase>.csv and
     research/results/trackb_stats_<phase>.csv.

Typical protocol (run from the repo root, research venv):

  # Phase A - baseline (host workers only)
  python research/scripts/trackb_experiment.py --phase A --pushes 40

  # scale out: start extra worker containers on kyro-data, then
  # Phase B - scaled
  python research/scripts/trackb_experiment.py --phase B --pushes 40

Honesty: every number here is measured from the live system (real pushes,
real Kafka offsets, real docker stats). Containers are labeled
kyro-trackb-* and identified in the group output by source IP (host
processes reach Kafka through the docker gateway .1; containers have their
own kyro-data addresses).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BURST_GEN = REPO_ROOT / "research" / "scripts" / "burst_generator.py"
RESULTS = REPO_ROOT / "research" / "results"
MANIFEST = REPO_ROOT / "research" / "data" / "live" / "burst_manifest.jsonl"
GROUP = "kyro-ingestion-workers"
KAFKA_CG_CMD = [
    "docker",
    "exec",
    "kyro-kafka",
    "/opt/kafka/bin/kafka-consumer-groups.sh",
    "--bootstrap-server",
    "localhost:29092",
    "--describe",
    "--group",
    GROUP,
]

SUMMARY_FIELDS = [
    "phase",
    "label",
    "pushes_requested",
    "commits_confirmed",
    "burst_start_utc",
    "last_push_utc",
    "drain_end_utc",
    "drain_s",
    "post_burst_drain_s",
    "lag_peak",
    "consumers_before",
    "consumers_after",
    "container_members_after",
    "containers_tracked",
    "container_mem_mb_peak",
    "host_free_ram_mb_after",
    "burst_exit_code",
]


def _now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _run(cmd: list[str], timeout: int = 60) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed rc={p.returncode}: {p.stderr[:400]}")
    return p.stdout


def group_snapshot() -> dict:
    """Describe the consumer group: total lag, members, partition split."""
    out = _run(KAFKA_CG_CMD, timeout=45)
    members: dict[str, dict] = {}
    total_lag = 0
    partitions = 0
    for line in out.splitlines():
        parts = line.split()
        # observed format: 9 columns (GROUP TOPIC PARTITION CURRENT-OFFSET
        # LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID); empty groups show "-"
        if len(parts) < 9 or parts[0] != GROUP:
            continue  # header / warnings
        topic, part, lag_s, cid, host = parts[1], parts[2], parts[5], parts[6], parts[7]
        lag = int(lag_s) if lag_s.isdigit() else 0
        total_lag += lag
        partitions += 1
        if cid == "-":
            cid = f"(unassigned {topic}/{part})"
        m = members.setdefault(
            cid, {"host": host, "partitions": 0, "lag": 0, "topics": set()}
        )
        m["partitions"] += 1
        m["lag"] += lag
        m["topics"].add(topic)
    # source-IP heuristic: host worker processes reach Kafka via the docker
    # gateway (.1); containers hold distinct kyro-data addresses.
    n_container = sum(
        1
        for m in members.values()
        if not m["host"].endswith(".1") and m["host"].startswith("/")
    )
    for m in members.values():
        m["topics"] = sorted(m["topics"])
        m["kind"] = (
            "unassigned"
            if m["host"] == "-"
            else (
                "container"
                if (m["host"].startswith("/") and not m["host"].endswith(".1"))
                else "host"
            )
        )
    return {
        "members": members,
        "consumers": len(members),
        "container_members": n_container,
        "partition_rows": partitions,
        "total_lag": total_lag,
        "raw": out,
    }


def docker_stats(names_prefix: str = "kyro-trackb-") -> list[dict]:
    """One-shot `docker stats --no-stream` for the trackb containers."""
    try:
        out = _run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}",
            ],
            timeout=30,
        )
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) != 3 or not parts[0].startswith(names_prefix):
            continue
        cpu = float(parts[1].replace("%", ""))
        mem_txt = parts[2].split("/")[0].strip()
        m = re.match(r"([\d.]+)\s*([KMGT]i?B)", mem_txt)
        mem_mb = 0.0
        if m:
            val = float(m.group(1))
            unit = m.group(2)
            mem_mb = val * {
                "KiB": 1 / 1024,
                "MiB": 1.0,
                "GiB": 1024.0,
                "TiB": 1024.0 * 1024,
                "KB": 1 / 1000,
                "MB": 1.0,
                "GB": 1000.0,
            }.get(unit, 1.0)
        rows.append({"name": parts[0], "cpu_pct": cpu, "mem_mb": round(mem_mb, 1)})
    return rows


def _manifest_last_push(label: str) -> tuple[str | None, int]:
    """Last ok push ts + total confirmed commits for this label."""
    last, commits = None, 0
    if not MANIFEST.exists():
        return None, 0
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") == "push" and rec.get("label") == label and rec.get("ok"):
            commits += int(rec.get("k_commits", 0))
            last = rec.get("ts")
    return last, commits


def _wait_drained(snap_fn, timeout_s: float, max_pre_lag: int = 1) -> tuple[float, int]:
    """Poll until the backlog is stable and clean; return (mono_t, pre_lag).

    Succeeds when lag==0 twice in a row, OR when lag is STABLE at a small
    value <= max_pre_lag across consecutive samples. The latter tolerates a
    known phantom offset: kyro.github.backfill partition 4 reports a stable
    lag of 1 with ZERO deliverable messages (verified via console-consumer
    reading 0 messages from earliest) - a transactional control-record
    artifact that never drains. It is identical in every phase, so it does
    not bias the comparison; the measured series record it explicitly.
    """
    deadline = time.monotonic() + timeout_s
    prev_lag: int | None = None
    stable_count = 0
    stable_lag = -1
    zero_count = 0
    while time.monotonic() < deadline:
        try:
            lag = snap_fn()["total_lag"]
        except Exception:
            lag = -1
        if lag == 0:
            stable_count = 0
            zero_count += 1
            if zero_count >= 2:
                return time.monotonic(), 0
        else:
            zero_count = 0
            if lag == prev_lag and 0 < lag <= max_pre_lag:
                stable_count += 1
                stable_lag = lag
                if stable_count >= 2:
                    return time.monotonic(), stable_lag
            else:
                stable_count = 0
        prev_lag = lag
        time.sleep(2.0)
    raise TimeoutError(f"group not drained within {timeout_s}s (last lag={prev_lag})")


class _SeriesPoller(threading.Thread):
    """Records group lag (+ periodic container stats) every poll_s seconds."""

    def __init__(self, lag_path: Path, stats_path: Path, poll_s: float):
        super().__init__(daemon=True)
        self.lag_path = lag_path
        self.stats_path = stats_path
        self.poll_s = poll_s
        self.stop_evt = threading.Event()
        self.peak_lag = 0
        self.peak_mem_mb = 0.0
        self.samples = 0
        self._tick = 0

    def run(self) -> None:
        with self.lag_path.open("w", newline="", encoding="utf-8") as lf:
            lw = csv.writer(lf)
            lw.writerow(["ts_utc", "elapsed_s", "total_lag", "consumers"])
            t0 = time.monotonic()
            while not self.stop_evt.is_set():
                try:
                    snap = group_snapshot()
                    lag, cons = snap["total_lag"], snap["consumers"]
                except Exception:
                    lag, cons = -1, -1
                elapsed = round(time.monotonic() - t0, 1)
                lw.writerow([_now(), elapsed, lag, cons])
                lf.flush()
                self.peak_lag = max(self.peak_lag, lag)
                self.samples += 1
                if self._tick % 3 == 0:  # every 3rd tick: container stats
                    stats = docker_stats()
                    if stats and self._tick == 0:
                        with self.stats_path.open(
                            "w", newline="", encoding="utf-8"
                        ) as sf:
                            sw = csv.writer(sf)
                            sw.writerow(
                                ["ts_utc", "elapsed_s", "name", "cpu_pct", "mem_mb"]
                            )
                    if stats:
                        with self.stats_path.open(
                            "a", newline="", encoding="utf-8"
                        ) as sf:
                            sw = csv.writer(sf)
                            for row in stats:
                                sw.writerow(
                                    [
                                        _now(),
                                        elapsed,
                                        row["name"],
                                        row["cpu_pct"],
                                        row["mem_mb"],
                                    ]
                                )
                        self.peak_mem_mb = max(
                            self.peak_mem_mb, max(r["mem_mb"] for r in stats)
                        )
                self._tick += 1
                self.stop_evt.wait(self.poll_s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", required=True, help="A, B, C, ... (CSV label)")
    ap.add_argument("--pushes", type=int, default=40, help="real pushes in the burst")
    ap.add_argument("--commits-per-hour", type=int, default=300, help="API-safe pacing")
    ap.add_argument("--poll-s", type=float, default=2.0)
    ap.add_argument("--quiesce-timeout", type=float, default=600.0)
    ap.add_argument("--drain-timeout", type=float, default=1200.0)
    ap.add_argument(
        "--skip-quiesce",
        action="store_true",
        help="do not wait for lag==0 before starting (documented deviation)",
    )
    ap.add_argument("--out", default=str(RESULTS / "trackb_live.csv"))
    args = ap.parse_args()

    phase = args.phase.upper()
    label = f"trackb_{phase.lower()}"
    RESULTS.mkdir(parents=True, exist_ok=True)

    # 1) quiesce: every phase starts from an empty backlog
    if args.skip_quiesce:
        print("[trackb] quiesce: SKIPPED (--skip-quiesce)")
        pre_lag = -1
    else:
        print("[trackb] waiting for pre-burst quiesce (lag==0 x2 or stable <=1) ...")
        _, pre_lag = _wait_drained(group_snapshot, args.quiesce_timeout)
        if pre_lag > 0:
            print(
                f"[trackb] quiesced with stable PRE-EXISTING phantom lag={pre_lag} "
                "(control-record artifact, identical in all phases)"
            )
        else:
            print("[trackb] group drained")

    snap_before = group_snapshot()
    stats_before = docker_stats()
    print(
        f"[trackb] before: consumers={snap_before['consumers']} "
        f"(containers={snap_before['container_members']}) lag={snap_before['total_lag']}"
    )

    # 2) burst + series polling
    lag_csv = RESULTS / f"trackb_lag_{phase.lower()}.csv"
    stats_csv = RESULTS / f"trackb_stats_{phase.lower()}.csv"
    poller = _SeriesPoller(lag_csv, stats_csv, args.poll_s)
    poller.start()

    burst_start = _now()
    t_mono_start = time.monotonic()
    print(f"[trackb] starting burst: {args.pushes} pushes, label={label}")
    proc = subprocess.Popen(
        [
            sys.executable,
            str(BURST_GEN),
            "--burst",
            str(args.pushes),
            "--label",
            label,
            "--commits-per-hour",
            str(args.commits_per_hour),
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"  [burst] {line.rstrip()}")
    proc.wait()
    burst_rc = proc.returncode
    if burst_rc != 0:
        print(f"[trackb] WARNING burst exited rc={burst_rc}")

    # 3) drain
    print("[trackb] burst done; waiting for drain (lag==0 x2 or stable <=1) ...")
    drain_end_mono, _post_lag = _wait_drained(group_snapshot, args.drain_timeout)
    poller.stop_evt.set()
    poller.join(timeout=10)
    drain_s = round(drain_end_mono - t_mono_start, 1)

    last_push, commits = _manifest_last_push(label)
    snap_after = group_snapshot()
    stats_after = docker_stats()

    drain_end = _now()
    post_burst: float | str = ""
    if last_push:
        try:
            t_push = dt.datetime.fromisoformat(last_push.replace("Z", "+00:00"))
            t_done = dt.datetime.fromisoformat(drain_end.replace("Z", "+00:00"))
            post_burst = round((t_done - t_push).total_seconds(), 1)
        except ValueError:
            post_burst = ""

    row = {
        "phase": phase,
        "label": label,
        "pushes_requested": args.pushes,
        "commits_confirmed": commits,
        "burst_start_utc": burst_start,
        "last_push_utc": last_push or "",
        "drain_end_utc": drain_end,
        # burst wall time (start -> drained) is the honest end-to-end number;
        # post_burst_drain_s = last push -> drained (pure backlog catch-up).
        "drain_s": drain_s,
        "post_burst_drain_s": post_burst,
        "lag_peak": poller.peak_lag,
        "consumers_before": snap_before["consumers"],
        "consumers_after": snap_after["consumers"],
        "container_members_after": snap_after["container_members"],
        "containers_tracked": len(stats_after),
        "container_mem_mb_peak": round(poller.peak_mem_mb, 1),
        "host_free_ram_mb_after": round(
            psutil.virtual_memory().available / 1024 / 1024
        ),
        "burst_exit_code": burst_rc,
    }

    out = Path(args.out)
    exists = out.exists()
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)

    # console summary + honest member breakdown
    print("[trackb] members after:")
    for cid, m in snap_after["members"].items():
        print(
            f"  {m['kind']:>9} {cid[:46]:46} host={m['host']} parts={m['partitions']}"
        )
    print(f"[trackb] row -> {out}")
    print(f"[trackb] lag series -> {lag_csv} (peak lag {poller.peak_lag})")
    print(f"[trackb] stats series -> {stats_csv}")
    print(f"[trackb] summary: {json.dumps(row)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
