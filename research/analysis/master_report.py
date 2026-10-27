"""Assemble the single master research dataset file:

    research/results/MASTER_DATASET.md

Merges, with explicit measured-vs-virtual labeling:
  A. REAL measured servers: per-server latency / CPU / RAM / net / queue /
     pipeline metrics (from server_metrics.csv, produced by server_report.py)
     plus live application request latency (app_requests_*.csv).
  B. Same-N-requests algorithm comparison: dragonfly vs fcfs vs round_robin
     (algo_comparison.md, produced by run_comparison.py) + B.2 statistical
     significance (stats_report.md), B.3 GA/PSO baselines
     (baselines_comparison.md), B.4 offered-load sweep (load_sweep.md).
  C. 50-server fleet experiment (fleet50_summary.md + fleet_server_data.csv).
  D. Track B live scale-out (trackb_live.csv + lag/stats series).
  E. Data inventory: every collected file with row counts, plus honesty notes.

Read-only over its inputs; regenerates MASTER_DATASET.md fully each run.

Usage:
  python -m research.analysis.master_report --results research/results \
      --live research/data/live --out research/results/MASTER_DATASET.md
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path


# ------------------------------------------------------------------- helpers
def _fmt(value: float) -> str:
    if value != value:  # NaN
        return "n/a"
    if float(value).is_integer() and abs(value) < 1e15:
        return f"{int(value):,}"
    r = round(float(value), 4)
    return f"{r:,}".rstrip("0").rstrip(".")


def _p95(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def load_server_metrics(
    path: Path,
) -> dict[tuple[str, str], dict[str, tuple[float, str, int]]]:
    """{(family, server): {metric: (value, unit, samples)}}"""
    out: dict[tuple[str, str], dict[str, tuple[float, str, int]]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                key = (row["family"], row["server"])
                out.setdefault(key, {})[row["metric"]] = (
                    float(row["value"]),
                    row["unit"],
                    int(row["samples"] or 0),
                )
            except (KeyError, ValueError):
                continue
    return out


def pivot_table(
    data: dict[tuple[str, str], dict[str, tuple[float, str, int]]],
    family: str,
    columns: list[str],
    first_header: str,
) -> list[str]:
    """One markdown table per family: server in rows, metrics in columns."""
    servers = sorted(name for (fam, name) in data if fam == family)
    if not servers:
        return [f"_no data collected for family `{family}`_", ""]
    present = [c for c in columns if any(c in data[(family, s)] for s in servers)]
    lines = [
        "| " + first_header + " | " + " | ".join(present) + " |",
        "|" + "---|" * (len(present) + 1),
    ]
    for s in servers:
        cells = []
        for c in present:
            if c in data[(family, s)]:
                v, unit, _ = data[(family, s)][c]
                cells.append(
                    _fmt(v) + (f" {unit}" if unit not in ("%", "", None) else "")
                )
            else:
                cells.append("-")
        lines.append("| " + s + " | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def kv_table(
    data: dict[tuple[str, str], dict[str, tuple[float, str, int]]], family: str
) -> list[str]:
    metrics: dict[str, tuple[float, str, int]] = {}
    for (fam, _s), m in data.items():
        if fam == family:
            for k, v in m.items():
                metrics.setdefault(k, v)
    if not metrics:
        return [f"_no data collected for family `{family}`_", ""]
    lines = ["| metric | value | unit | samples |", "|---|---|---|---|"]
    for k in sorted(metrics):
        v, unit, samples = metrics[k]
        lines.append(f"| {k} | {_fmt(v)} | {unit or '-'} | {samples or '-'} |")
    lines.append("")
    return lines


def app_request_table(live_dir: Path) -> list[str]:
    rows: list[dict] = []
    for path in sorted(live_dir.glob("app_requests_*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    if not rows:
        return ["_no application request data collected yet_", ""]
    groups: dict[tuple[str, str], list[tuple[float, int]]] = {}
    for r in rows:
        try:
            ms = float(r["total_ms"])
            status = int(r["status"])
        except (KeyError, ValueError):
            continue
        ok = 1 if 200 <= status < 400 else 0
        groups.setdefault((r["phase"], r["entrypoint"]), []).append((ms, ok))
    lines = [
        "| phase | entrypoint | requests | http_ok | mean_ms | p95_ms | max_ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for phase, entry in sorted(groups):
        vals = [ms for ms, _ in groups[(phase, entry)]]
        ok = sum(o for _, o in groups[(phase, entry)])
        mean = sum(vals) / len(vals)
        lines.append(
            f"| {phase} | {entry} | {len(vals)} | {ok}/{len(vals)} "
            f"| {mean:.1f} | {_p95(vals):.1f} | {max(vals):.1f} |"
        )
    lines.append("")
    return lines


def csv_table(path: Path, max_rows: int = 40) -> list[str]:
    """Generic markdown rendering of a result CSV (truncated, honestly labeled)."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return ["_empty file_", ""]
    cols = list(rows[0].keys())
    lines = [
        "| " + " | ".join(cols) + " |",
        "|" + "---|" * len(cols),
    ]
    for r in rows[:max_rows]:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    if len(rows) > max_rows:
        rest = ["_... more rows_"] + [""] * (len(cols) - 1)
        lines.append("| " + " | ".join(rest) + " |")
    lines.append("")
    return lines


def demote(text: str) -> str:
    """Drop a sub-document's H1 and demote its H2s to H3s for embedding."""
    body_lines = text.splitlines()
    if body_lines and body_lines[0].startswith("# "):
        body_lines = body_lines[1:]
    return "\n".join(
        ("### " + ln[3:]) if ln.startswith("## ") else ln for ln in body_lines
    ).strip()


def inventory(results: Path, live: Path) -> list[str]:
    lines = ["| file | bytes | rows |", "|---|---|---|"]
    targets = sorted(live.glob("*")) + sorted(results.glob("*"))
    for p in targets:
        if not p.is_file() or p.name == "MASTER_DATASET.md":
            continue
        try:
            if p.suffix in (".csv", ".jsonl"):
                with p.open(encoding="utf-8", errors="replace") as f:
                    n = sum(1 for _ in f)
                unit = "rows"
            elif p.suffix == ".md":
                with p.open(encoding="utf-8", errors="replace") as f:
                    n = sum(1 for _ in f)
                unit = "lines"
            else:
                n, unit = 0, ""
        except OSError:
            n, unit = 0, ""
        label = f"{'data/live/' if p.parent == live else 'results/'}{p.name}"
        lines.append(
            f"| `{label}` | {p.stat().st_size:,} | "
            + (f"{n:,} {unit}" if unit else "-")
            + " |"
        )
    lines.append("")
    return lines


def load_notes(live: Path) -> list[str]:
    manifest = live / "burst_manifest.jsonl"
    notes: list[str] = []
    if manifest.exists():
        labels: dict[str, int] = {}
        total = 0
        with manifest.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("event") == "push" and rec.get("ok"):
                    total += 1
                    labels[rec.get("label", "?")] = (
                        labels.get(rec.get("label", "?"), 0) + 1
                    )
        if total:
            parts = ", ".join(f"{k}: {v}" for k, v in sorted(labels.items()))
            notes.append(
                f"- Load generator: **{total} real pushes** succeeded ({parts}) "
                "through the genuine webhook -> n8n -> Kafka -> worker path."
            )
    return notes


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="research/results")
    ap.add_argument("--live", default="research/data/live")
    ap.add_argument("--out", default="research/results/MASTER_DATASET.md")
    args = ap.parse_args()

    results, live, out = Path(args.results), Path(args.live), Path(args.out)
    sm_path = results / "server_metrics.csv"
    data = load_server_metrics(sm_path) if sm_path.exists() else {}

    now = (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    sections: list[str] = []
    sections.append("# KYRO Master Research Dataset")
    sections.append("")
    sections.append(f"- Generated: {now} (UTC) by `research/analysis/master_report.py`")
    sections.append(
        f"- Sources: `{sm_path}` (live samplers), `app_requests_*.csv` "
        "(real application traffic), `algo_comparison.*`, `fleet*.*` (experiments)"
    )
    sections.append("")
    sections.append("> **Labeling (paper requirement):** everything in section A is")
    sections.append("> *measured* from the running application on this laptop. The 50")
    sections.append(
        "> nodes in section C are *virtual* heterogeneous servers driven by"
    )
    sections.append(
        "> the same *real* trace - trace-driven simulation, not 50 machines."
    )
    sections.append("> Burst-generated commits are real pipeline executions with")
    sections.append("> generated file content, labeled `burst` throughout.")
    sections.append("")

    # ---- A: measured servers
    sections.append("## A. Real measured servers (live telemetry)")
    sections.append("")
    sections.append("### A.1 Request latency per server (HTTP/TCP probes)")
    sections += pivot_table(
        data,
        "latency",
        [
            "total_ms_mean",
            "total_ms_p50",
            "total_ms_p95",
            "total_ms_max",
            "ttfb_ms_mean",
            "ttfb_ms_p95",
            "connect_ms_mean",
            "error_rate",
            "availability",
        ],
        "server",
    )
    sections.append("### A.2 Container CPU / RAM / IO (docker stats, 1 Hz)")
    sections += pivot_table(
        data,
        "resources",
        [
            "cpu_pct_mean",
            "cpu_pct_p95",
            "cpu_pct_max",
            "mem_used_bytes_mean",
            "mem_used_bytes_max",
            "mem_pct_of_limit_mean",
            "mem_pct_of_limit_max",
            "net_io_bytes_total_delta",
            "block_io_bytes_total_delta",
            "pids_mean",
            "pids_max",
        ],
        "container",
    )
    sections.append("### A.3 Host processes (1 Hz psutil)")
    sections += pivot_table(
        data,
        "host_process",
        [
            "cpu_pct_mean",
            "cpu_pct_p95",
            "cpu_pct_max",
            "rss_bytes_mean",
            "rss_bytes_max",
        ],
        "role",
    )
    sections.append("### A.4 Kafka queue backlog per topic (3 s sampler)")
    sections += pivot_table(
        data,
        "queue",
        [
            "lag_mean",
            "lag_p95",
            "lag_max",
            "backlog_area",
            "throughput",
        ],
        "topic",
    )
    sections.append(
        "### A.5 Application request latency (real HTTP traffic, `app_requests_*.csv`)"
    )
    sections += app_request_table(live)
    sections.append("### A.6 Pipeline throughput & service times")
    sections += kv_table(data, "pipeline")
    sections.append("### A.7 Arrival burstiness (research signal)")
    sections += kv_table(data, "arrival_burstiness")

    # ---- B: same requests, 3 algorithms
    sections.append("## B. Identical requests x 3 algorithms")
    sections.append("")
    algo_md = results / "algo_comparison.md"
    if algo_md.exists():
        sections.append(demote(algo_md.read_text(encoding="utf-8")))
        sections.append("")
        sections.append(
            "Raw runs: `results/algo_comparison.csv`. Fairness: the request "
            "set is asserted identical across algorithms in code."
        )
    else:
        sections.append("_algo_comparison.md not found - run run_comparison.py first_")

    sections.append("")
    sections.append(
        "### B.2 Statistical significance (Mann-Whitney U + Holm + Cliff's delta)"
    )
    stats_md = results / "stats_report.md"
    if stats_md.exists():
        sections.append(demote(stats_md.read_text(encoding="utf-8")))
    else:
        sections.append(
            "_stats_report.md not found - run research.analysis.stats_report first_"
        )

    sections.append("")
    sections.append("### B.3 GA / PSO baselines (matched compute budget to DA)")
    bas_md = results / "baselines_comparison.md"
    if bas_md.exists():
        sections.append(demote(bas_md.read_text(encoding="utf-8")))
    else:
        sections.append(
            "_baselines_comparison.md not found - run run_comparison.py "
            "--algorithms dragonfly,fcfs,round_robin,ga,pso_"
        )

    sections.append("")
    sections.append("### B.4 Offered-load sweep (time-compressed trace variants)")
    sweep_md = results / "load_sweep.md"
    if sweep_md.exists():
        sections.append(demote(sweep_md.read_text(encoding="utf-8")))
    else:
        sections.append(
            "_load_sweep.md not found - run research.experiments.load_sweep first_"
        )

    # ---- C: fleet
    sections.append("")
    sections.append("## C. 50-server fleet (heterogeneous, same real trace)")
    sections.append("")
    fleet_md = results / "fleet50_summary.md"
    if fleet_md.exists():
        sections.append(demote(fleet_md.read_text(encoding="utf-8")))
        sections.append("")
        sections.append(
            "Per-server rows: `results/fleet_server_data.csv` "
            "(450 rows = fleet sizes x algorithms x nodes)."
        )
    else:
        sections.append("_fleet50_summary.md not found - run fleet50.py first_")

    # ---- D: Track B live scale-out
    sections.append("")
    sections.append("## D. Track B live scale-out (real worker containers)")
    sections.append("")
    tb = results / "trackb_live.csv"
    if tb.exists():
        sections += csv_table(tb)
        sections.append(
            "Lag series: `results/trackb_lag_*.csv` (2 s offset polls); "
            "container resources: `results/trackb_stats_*.csv`. "
            "Phase A = baseline host workers; later phases add `kyro-trackb-*` "
            "containers on the kyro-data network running the same rebuilt "
            "image as the host code. Every value is a live measurement."
        )
        sections.append("")
    else:
        sections.append(
            "_trackb_live.csv not found - run "
            "`python research/scripts/trackb_experiment.py --phase A` first_"
        )
        sections.append("")

    # ---- E: inventory + notes
    sections.append("## E. Data inventory")
    sections.append("")
    sections += inventory(results, live)
    sections.append("## F. Data notes & honesty")
    sections.append("")
    sections += load_notes(live)
    notes = [
        "- Window: live samplers record continuously; tables state their own "
        "window in `server_metrics.csv`.",
        "- `chroma` heartbeat answers HTTP 410 (flagged by server_report) - "
        "exclude or annotate in threat-to-validity.",
        "- Direct-backend OAuth start returns 503 `public origin not configured` "
        "by design (github_oauth.py:110 allow-listed origins); the router/"
        "frontend entrypoints return the real 302 to GitHub (4/4).",
        "- `repo_detail` 404 is access gating: the fresh load-test session does "
        "not own the probed repository (uniform 404 by design, not a failure).",
        "- Unprocessed events (backlog drains) are kept in the trace with empty "
        "`service_seconds` and excluded from scheduling runs - never imputed.",
        "- Service-time tail (max ~1292 s) is a real deferred backfill, not an error.",
        "- All values are measured or computed from measured rows; nothing is "
        "fabricated. Generated-markdown rounding is cosmetic only.",
    ]
    sections += notes
    sections.append("")
    sections.append(
        "Regenerate: `python -m research.analysis.master_report` "
        "(after `server_report.py` for the freshest telemetry)."
    )
    sections.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sections), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
