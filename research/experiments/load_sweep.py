"""Offered-load sweep: {dragonfly, fcfs, round_robin} x time-compressed traces.

Sweeps the offered load of the REAL windowed trace by time compression: for
each factor c, every arrival is scaled by 1/c (arrival' = arrival / c) while
service times stay exactly as measured. c=1 is the original real trace; c>1
tightens inter-arrivals, so more real work competes for the same worker pool
per unit time -> higher offered load. Within a factor every algorithm gets
the IDENTICAL derived task list (fairness asserted in code, see
assert_same_task_list + the n_requests assert), so differences between
algorithms are scheduling decisions only.

HONESTY LABEL (also written into the .md header): these are time-compressed
variants of the real trace; arrivals scaled by 1/factor, service times
unchanged - derived offered-load scenarios, not fabricated measurements.

Outputs (one row per compression_factor x algorithm x seed):
  <out-prefix>.csv   exact downstream-parsed columns, see CSV_COLUMNS
  <out-prefix>.md    header + factor x algorithm table + winner per factor

Usage:
  python -m research.experiments.load_sweep \
      --tasks research/data/trace/tasks.csv --since 2026-10-20T12:00:00Z \
      --factors 1,2,4,8 --algorithms dragonfly,fcfs,round_robin --seeds 20 \
      --workers 4 --speeds 1.0,0.9,0.8,1.1 --sla 30 \
      --out-prefix research/results/load_sweep
"""

from __future__ import annotations

import argparse
import csv
import statistics as stats
from dataclasses import replace
from pathlib import Path

from research.experiments.run_comparison import apply_window  # reuse, don't copy
from research.extract.load_tasks import load_tasks
from research.schedulers import get_scheduler
from research.sim.engine import run_simulation
from research.sim.interface import Task

OUT_DIR = Path(__file__).resolve().parent.parent / "results"

# EXACT column order - downstream tools parse positionally, do not reorder.
CSV_COLUMNS = [
    "compression_factor",
    "algorithm",
    "seed",
    "n_requests",
    "makespan_s",
    "mean_flow_s",
    "p95_flow_s",
    "sla_violations",
    "imbalance_cv",
    "util_mean",
]

LABELING_SENTENCE = (
    "time-compressed variants of the real trace; arrivals scaled by "
    "1/factor, service times unchanged - derived offered-load scenarios, "
    "not fabricated measurements"
)


# ---------------------------------------------------------------------------
# Helpers (importable for tests: research/tests/test_load_sweep.py)
# ---------------------------------------------------------------------------


def compress_tasks(tasks: list[Task], factor: float) -> list[Task]:
    """Derived offered-load scenario: arrival' = arrival / factor.

    Service demands are UNCHANGED (they are real measurements). factor == 1
    returns an identical (fresh list, same Task objects) copy; factor > 1
    compresses time (higher offered load); 0 < factor < 1 stretches it.
    Returns a NEW list; the input is never mutated.
    """
    if factor <= 0:
        raise ValueError(f"compression factor must be > 0, got {factor}")
    if factor == 1:
        return list(tasks)
    return [replace(t, arrival=t.arrival / factor) for t in tasks]


def assert_same_task_list(reference: list[Task], candidate: list[Task]) -> None:
    """Fairness guard: both lists must describe the identical task set.

    Raises AssertionError the moment an algorithm is handed anything other
    than the exact derived list of its compression factor (different length,
    different task ids, arrivals or services).
    """
    if len(reference) != len(candidate):
        raise AssertionError(
            f"FAIRNESS VIOLATION: reference has {len(reference)} tasks but "
            f"candidate has {len(candidate)} - comparison invalid"
        )
    ref_sig = [(t.task_id, t.arrival, t.service) for t in reference]
    cand_sig = [(t.task_id, t.arrival, t.service) for t in candidate]
    if ref_sig != cand_sig:
        raise AssertionError(
            "FAIRNESS VIOLATION: task lists differ in (task_id, arrival, "
            "service) - comparison invalid"
        )


def _mean(xs: list[float]) -> float:
    return float(stats.fmean(xs)) if xs else float("nan")


def _std(xs: list[float]) -> float:
    return float(stats.stdev(xs)) if len(xs) > 1 else 0.0


def _parse_factor(token: str) -> float | int:
    value = float(token)
    if value <= 0:
        raise ValueError(f"compression factors must be > 0, got {token!r}")
    return int(value) if value.is_integer() else value


def run_sweep(
    tasks: list[Task],
    factors: list[float | int],
    algorithms: list[str],
    seeds: int,
    n_workers: int,
    speeds: list[float],
    sla_s: float,
    progress: bool = False,
) -> list[dict]:
    """Run factors x algorithms x seeds -> one row per (factor, algo, seed).

    FAIRNESS CONTRACT: the derived list of each factor is built ONCE and the
    exact same list object is handed to every algorithm and every seed;
    n_requests equality is asserted per factor (mirrors run_comparison).
    """
    rows: list[dict] = []
    for factor in factors:
        derived = compress_tasks(tasks, factor)
        factor_rows: list[dict] = []
        for algo in algorithms:
            # re-derive per algorithm + assert: identical scenario by
            # construction, guarded so a future refactor cannot silently drift
            algo_list = compress_tasks(tasks, factor)
            assert_same_task_list(derived, algo_list)
            for seed in range(seeds):
                sched = get_scheduler(algo, seed)
                res = run_simulation(algo_list, sched, n_workers, speeds, sla_s, seed)
                assert res.n_tasks == len(algo_list), (
                    f"factor={factor} {algo} seed={seed}: simulator saw "
                    f"{res.n_tasks} tasks, expected {len(algo_list)}"
                )
                row = {
                    "compression_factor": factor,
                    "algorithm": algo,
                    "seed": seed,
                    "n_requests": res.n_tasks,
                    "makespan_s": round(res.makespan, 3),
                    "mean_flow_s": round(res.mean_flow, 3),
                    "p95_flow_s": round(res.p95_flow, 3),
                    "sla_violations": res.sla_violations,
                    "imbalance_cv": round(res.imbalance_cv, 4),
                    "util_mean": round(_mean(res.utilization), 4),
                }
                rows.append(row)
                factor_rows.append(row)
                if progress:
                    print(
                        f"factor={factor:>3} {algo:>10} seed={seed:>2} "
                        f"requests={res.n_tasks} "
                        f"makespan={res.makespan:.1f}s "
                        f"mean_flow={res.mean_flow:.1f}s "
                        f"p95={res.p95_flow:.1f}s "
                        f"sla_viol={res.sla_violations} "
                        f"cv={res.imbalance_cv:.3f}"
                    )
        # sanity: every algorithm saw the identical request count per factor
        assert {r["n_requests"] for r in factor_rows} == {len(derived)}, (
            f"factor={factor}: algorithms saw different request counts - "
            f"comparison invalid"
        )
    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def write_markdown(
    rows: list[dict],
    args,
    window_stats: dict[str, int],
    per_factor_n: dict[float | int, int],
    algorithms: list[str],
    factors: list[float | int],
    out_md: Path,
) -> None:
    lines = [
        "# Offered-Load Sweep - time-compressed real trace",
        "",
        f"- Trace: `{args.tasks}`",
        f"- Arrival window: `[{args.since or '-inf'} .. {args.until or '+inf'}]`"
        + (f" (kept {window_stats})" if window_stats else ""),
        "- Scenarios: "
        + ", ".join(f"factor {f} (n={per_factor_n[f]})" for f in factors)
        + f" - {LABELING_SENTENCE}.",
        f"- Algorithms: {', '.join(algorithms)} (identical task list per "
        f"factor, asserted in code)",
        f"- Seeds: {args.seeds} (0..{args.seeds - 1}) - Workers: {args.workers}"
        f" - Speeds: {args.speeds} - SLA: {args.sla}s",
        f"- Runs: {len(rows)} ({len(factors)} factors x {len(algorithms)} "
        f"algorithms x {args.seeds} seeds)",
        "",
        "| factor | algorithm | mean_flow_s | p95_flow_s | sla_violations | imbalance_cv |",
        "|---|---|" + "---|" * 4,
    ]
    metrics = ["mean_flow_s", "p95_flow_s", "imbalance_cv"]
    for factor in factors:
        for algo in algorithms:
            sub = [
                r
                for r in rows
                if r["compression_factor"] == factor and r["algorithm"] == algo
            ]
            cells = []
            for m in metrics:
                vals = [r[m] for r in sub]
                cells.append(f"{_mean(vals):.3f} ± {_std(vals):.3f}")
            viol = _mean([r["sla_violations"] for r in sub])
            lines.append(
                f"| {factor} | {algo} | {cells[0]} | {cells[1]} | "
                f"{viol:.1f} | {cells[2]} |"
            )

    lines += [
        "",
        "## Winner per factor (min mean mean_flow_s)",
        "",
        "| factor | winner | mean_flow_s | runner-up | runner-up mean_flow_s |",
        "|---|---|---|---|---|",
    ]
    for factor in factors:
        means = {}
        for algo in algorithms:
            vals = [
                r["mean_flow_s"]
                for r in rows
                if r["compression_factor"] == factor and r["algorithm"] == algo
            ]
            means[algo] = _mean(vals)
        ranked = sorted(means, key=lambda a: means[a])
        winner, runner = ranked[0], ranked[1] if len(ranked) > 1 else ranked[0]
        lines.append(
            f"| {factor} | **{winner}** | {means[winner]:.3f} | "
            f"{runner} | {means[runner]:.3f} |"
        )

    lines += [
        "",
        "Lower is better for all metrics. Service demands stay real in every "
        "scenario; only arrival timing is compressed.",
        "",
        "Raw per-run rows: `load_sweep.csv` (regenerate with load_sweep.py).",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", required=True, help="trace tasks.csv path")
    ap.add_argument(
        "--since",
        default=None,
        help="ISO ts lower bound on arrival (e.g. 2026-10-20T12:00:00Z)",
    )
    ap.add_argument("--until", default=None, help="ISO ts upper bound (inclusive)")
    ap.add_argument(
        "--factors",
        default="1,2,4,8",
        help="comma-separated time-compression factors (1 = original trace)",
    )
    ap.add_argument(
        "--algorithms",
        default="dragonfly,fcfs,round_robin",
        help="comma-separated scheduler names (see research.schedulers)",
    )
    ap.add_argument(
        "--seeds", type=int, default=20, help="seeds per (factor, algorithm)"
    )
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--speeds", default="1.0,0.9,0.8,1.1", help="per-worker speed factors"
    )
    ap.add_argument("--sla", type=float, default=30.0, help="SLA seconds on flow time")
    ap.add_argument("--out-prefix", default=str(OUT_DIR / "load_sweep"))
    args = ap.parse_args()

    factors = [_parse_factor(t) for t in args.factors.split(",")]
    algorithms = [a.strip() for a in args.algorithms.split(",") if a.strip()]
    if not algorithms:
        print("ERROR: --algorithms must name at least one scheduler")
        return 2

    # fail fast on unknown scheduler names BEFORE any simulation work
    for algo in algorithms:
        try:
            get_scheduler(algo, 0)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2

    speeds = [float(s) for s in args.speeds.split(",")]
    if len(speeds) != args.workers:
        print(f"ERROR: {len(speeds)} speeds for {args.workers} workers")
        return 2
    if args.seeds < 1:
        print(f"ERROR: --seeds must be >= 1, got {args.seeds}")
        return 2

    # load the windowed trace ONCE; every factor derives from this same list
    trace_path, window_stats = apply_window(args.tasks, args.since, args.until)
    tasks = load_tasks(trace_path)
    if not tasks:
        print(f"ERROR: no tasks loaded from {args.tasks} (run build_trace.py first)")
        return 2

    per_factor_n = {f: len(compress_tasks(tasks, f)) for f in factors}
    print(
        f"loaded {len(tasks)} schedulable tasks from {trace_path}; "
        f"factors {factors} -> n_requests {list(per_factor_n.values())}"
    )

    rows = run_sweep(
        tasks,
        factors,
        algorithms,
        args.seeds,
        args.workers,
        speeds,
        args.sla,
        progress=True,
    )

    out_csv = Path(args.out_prefix + ".csv")
    out_md = Path(args.out_prefix + ".md")
    write_csv(rows, out_csv)
    write_markdown(rows, args, window_stats, per_factor_n, algorithms, factors, out_md)

    print(f"\nwrote {out_csv} ({len(rows)} rows)")
    print(f"wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
