"""Experiment runner: identical workload x {dragonfly, fcfs, round_robin}.

Feeds the EXACT SAME set of real trace tasks to every scheduler (same N
requests, same worker pool, same seeds) so the comparison is fair by
construction, then writes:

  research/results/algo_comparison.csv   one row per (algorithm, seed)
  research/results/algo_comparison.md    mean/std per algorithm + ranking

Because the real trace spans several days (historic backfills + today's
bursts), --since/--until can restrict the arrival window so makespan is
dominated by scheduling decisions instead of idle calendar days. The window
is applied BEFORE loading, exported to a visible tasks_windowed.csv, and
identical for all three algorithms - honest filtering, not per-algo tuning.

Usage:
  python -m research.experiments.run_comparison \
      --tasks research/data/trace/tasks.csv --seeds 10 \
      --workers 4 --speeds 1.0,0.9,0.8,1.1 --sla 30 \
      --since 2026-10-20T12:00:00Z
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as stats
from datetime import datetime
from pathlib import Path

from research.extract.load_tasks import load_tasks
from research.schedulers import get_scheduler
from research.sim.engine import run_simulation

OUT_DIR = Path(__file__).resolve().parent.parent / "results"
DEFAULT_ALGOS = ["dragonfly", "fcfs", "round_robin"]  # core three studied algorithms


def _mean(xs: list[float]) -> float:
    return float(stats.fmean(xs)) if xs else float("nan")


def _std(xs: list[float]) -> float:
    return float(stats.stdev(xs)) if len(xs) > 1 else 0.0


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def apply_window(
    tasks_csv: str | Path,
    since: str | None,
    until: str | None,
) -> tuple[Path, dict[str, int]]:
    """Filter tasks.csv rows to [since, until] on arrival_ts (inclusive).

    Returns (path_to_load, stats). Without --since/--until the original file
    is returned untouched. The filtered file is written next to the original
    as tasks_windowed.csv so the exact experiment input is inspectable.
    """
    src = Path(tasks_csv)
    if not since and not until:
        return src, {}
    t0 = _parse_ts(since) if since else None
    t1 = _parse_ts(until) if until else None
    with src.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    kept: dict[str, int] = {}
    total = len(rows)
    out_rows = []
    for r in rows:
        try:
            arr = _parse_ts(r["arrival_ts"])
        except (KeyError, ValueError):
            continue
        if (t0 is None or arr >= t0) and (t1 is None or arr <= t1):
            out_rows.append(r)
            label = (r.get("experiment_label") or r.get("kind") or "?").strip() or "?"
            kept[label] = kept.get(label, 0) + 1
    out = src.parent / "tasks_windowed.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(
        f"window [{since or '-inf'} .. {until or '+inf'}]: "
        f"kept {len(out_rows)}/{total} rows ({kept})"
    )
    return out, kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True, help="trace tasks.csv path")
    ap.add_argument(
        "--seeds", type=int, default=10, help="seeds per algorithm (paper target: 30)"
    )
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--speeds", default="1.0,0.9,0.8,1.1", help="per-worker speed factors"
    )
    ap.add_argument("--sla", type=float, default=30.0, help="SLA seconds on flow time")
    ap.add_argument(
        "--since",
        default=None,
        help="ISO ts lower bound on arrival (e.g. 2026-10-20T12:00:00Z); same window for all algorithms",
    )
    ap.add_argument(
        "--until",
        default=None,
        help="ISO ts upper bound on arrival (inclusive)",
    )
    ap.add_argument("--out-prefix", default=str(OUT_DIR / "algo_comparison"))
    ap.add_argument(
        "--algorithms",
        default=",".join(DEFAULT_ALGOS),
        help="comma-separated scheduler names (default: the three studied algorithms)",
    )
    args = ap.parse_args()

    algos = [a.strip() for a in args.algorithms.split(",") if a.strip()]
    if not algos:
        print("ERROR: --algorithms must name at least one scheduler")
        return 2

    trace_path, window_stats = apply_window(args.tasks, args.since, args.until)
    tasks = load_tasks(trace_path)
    if not tasks:
        print(f"ERROR: no tasks loaded from {args.tasks} (run build_trace.py first)")
        return 2
    speeds = [float(s) for s in args.speeds.split(",")]
    if len(speeds) != args.workers:
        print(f"ERROR: {len(speeds)} speeds for {args.workers} workers")
        return 2

    # THE FAIRNESS CONTRACT: one trace object, reused unchanged for every run.
    n_requests = len(tasks)
    rows: list[dict] = []
    flow_rows: list[dict] = []
    for algo in algos:
        for seed in range(args.seeds):
            sched = get_scheduler(algo, seed)
            res = run_simulation(tasks, sched, args.workers, speeds, args.sla, seed)
            rows.append(
                {
                    "algorithm": algo,
                    "seed": seed,
                    "n_requests": res.n_tasks,
                    "makespan_s": round(res.makespan, 3),
                    "mean_flow_s": round(res.mean_flow, 3),
                    "p95_flow_s": round(res.p95_flow, 3),
                    "sla_violations": res.sla_violations,
                    "imbalance_cv": round(res.imbalance_cv, 4),
                    "util_mean": round(_mean(res.utilization), 4),
                    "util_min": round(min(res.utilization), 4),
                    "util_max": round(max(res.utilization), 4),
                    # scheduler overhead: wall time spent inside dispatch() (paper metric)
                    "dispatch_cpu_s": round(res.extra.get("dispatch_cpu_s", 0.0), 6),
                    "dispatch_calls": res.extra.get("dispatch_calls", 0),
                }
            )
            # per-task long format: source data for CDF / boxplot diagrams
            for row in res.per_task:
                flow_rows.append(
                    {
                        "algorithm": algo,
                        "seed": seed,
                        "task_id": row["task_id"],
                        "arrival_s": round(row["arrival"], 3),
                        "start_s": round(row["start"], 3),
                        "finish_s": round(row["finish"], 3),
                        "flow_s": round(row["flow"], 3),
                        "worker_id": row["worker"],
                    }
                )
            print(
                f"{algo:>10} seed={seed} requests={res.n_tasks} "
                f"makespan={res.makespan:.1f}s mean_flow={res.mean_flow:.1f}s "
                f"p95={res.p95_flow:.1f}s sla_viol={res.sla_violations} "
                f"cv={res.imbalance_cv:.3f}"
            )

    # sanity: identical request counts everywhere (fairness check)
    assert {r["n_requests"] for r in rows} == {n_requests}, (
        "ALGORITHMS SAW DIFFERENT REQUEST COUNTS - comparison invalid"
    )

    out_csv = Path(args.out_prefix + ".csv")
    out_md = Path(args.out_prefix + ".md")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # per-task flow samples (long format) -> CDF / boxplot diagram source data
    flows_csv = out_csv.parent / "flow_samples.csv"
    with flows_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(flow_rows[0].keys()))
        w.writeheader()
        w.writerows(flow_rows)
    print(f"flow samples: {len(flow_rows)} rows -> {flows_csv}")

    # aggregate
    metrics = [
        "makespan_s",
        "mean_flow_s",
        "p95_flow_s",
        "sla_violations",
        "imbalance_cv",
        "util_mean",
    ]
    lower_better = set(metrics) - {
        "util_mean"
    }  # higher util = better balance here? keep util informational
    agg: dict[str, dict[str, tuple[float, float]]] = {}
    for algo in algos:
        a_rows = [r for r in rows if r["algorithm"] == algo]
        agg[algo] = {
            m: (_mean([r[m] for r in a_rows]), _std([r[m] for r in a_rows]))
            for m in metrics
        }

    # ranking per metric (best mean; util_mean -> closest to 1.0 is ideal balance? report highest)
    winners: dict[str, str] = {}
    for m in metrics:
        if m in lower_better:
            winners[m] = min(agg, key=lambda a: agg[a][m][0])
        else:
            winners[m] = max(agg, key=lambda a: agg[a][m][0])

    lines = [
        "# Algorithm Comparison — identical real workload",
        "",
        f"- Trace: `{args.tasks}`",
        f"- Arrival window: `[{args.since or '-inf'} .. {args.until or '+inf'}]`"
        + (f" (kept {window_stats})" if window_stats else ""),
        f"- Requests per algorithm: **{n_requests}** (identical set, asserted in code)",
        f"- Seeds: {args.seeds} · Workers: {args.workers} · Speeds: {args.speeds} · SLA: {args.sla}s",
        f"- Runs: {len(rows)} ({len(algos)} algorithms x {args.seeds} seeds)",
        "",
        "| metric | " + " | ".join(f"**{a}**" for a in algos) + " | best |",
        "|---|" + "---|" * (len(algos) + 1),
    ]
    for m in metrics:
        cells = [f"{agg[a][m][0]:.3f} ± {agg[a][m][1]:.3f}" for a in algos]
        lines.append(f"| {m} | " + " | ".join(cells) + f" | {winners[m]} |")
    lines += [
        "",
        "Lower is better for: makespan, mean_flow, p95_flow, sla_violations, imbalance_cv.",
        "util_mean higher = more utilized workers.",
        "",
        "Raw per-run rows: `{out_csv.name}` (regenerate with run_comparison.py).".replace(
            "{out_csv.name}", out_csv.name
        ),
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nwrote {out_csv} ({len(rows)} rows)")
    print(f"wrote {out_md}")
    print("winners:", json.dumps(winners))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
