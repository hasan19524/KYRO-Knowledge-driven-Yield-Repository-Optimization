"""Build the multi-server (50-node) scheduling dataset on the REAL workload trace.

Feeds the identical real trace (same N requests, asserted) to
{dragonfly, fcfs, round_robin} across fleets of --sizes heterogeneous
virtual worker nodes (default sweep 5..100; requirement: >= 50) and writes:

  research/results/fleet_nodes.csv        static 50-node fleet definition
  research/results/fleet_runs.csv         raw per-(size, algo, seed) runs
  research/results/fleet_server_data.csv  per-(size, algo, node) metrics
  research/results/fleet50_summary.md     human-readable comparison

HONESTY MODEL (also stated in the generated summary):
  * MEASURED inputs: task arrivals + service demands come from the real KYRO
    pipeline trace (webhook -> Kafka -> worker -> Postgres); every node's
    profile columns (cpu_peak_pct_measured, ram_mean_mb_measured) are computed
    from the live 1 Hz samplers of the actually-running application.
  * VIRTUAL nodes: this laptop has ~9 measurable services, not 50 physical
    machines. The 50 nodes are a controlled heterogeneous fleet (documented
    speed envelope 0.5..1.5), the standard trace-driven simulation setup for
    scheduling research. Node profiles anchor each virtual node to a real
    measured KYRO service.

Usage:
  python -m research.experiments.fleet50 --tasks research/data/trace/tasks.csv \
      --since 2026-10-20T12:00:00Z --seeds 30 --sizes 10,20,30,40,50
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics as stats
from pathlib import Path

from research.experiments.run_comparison import apply_window
from research.extract.load_tasks import load_tasks
from research.schedulers import ALGORITHMS, get_scheduler
from research.sim.engine import run_simulation

LIVE_DIR = Path(__file__).resolve().parents[1] / "data" / "live"
OUT_DIR = Path(__file__).resolve().parents[1] / "results"
FLEET_SEED = 20261020  # fixed: fleet definition is stable across reruns
N_NODES = 100  # fleet ceiling (requirement: >= 50 servers; 100 gives curve headroom)
SPEED_MIN, SPEED_MAX = 0.5, 1.5  # documented heterogeneity envelope


# --------------------------------------------------------------- measured profiles
def _num(value: str) -> float:
    return float(str(value).strip().rstrip("%") or 0.0)


def _host_role(cmd_hint: str, name: str) -> str | None:
    """Map a host process to an application role; None = not an app server."""
    c = cmd_hint.lower()
    if "worker_main" in c:
        return "worker"
    if "uvicorn" in c:
        return "backend"
    if "next" in c or "next-server" in name.lower():
        return "frontend"
    if "public_router" in c:
        return "router"
    if "cloudflared" in c:
        return "tunnel"
    return None  # samplers/measurement tools are instruments, not servers


def load_profiles(live_dir: Path) -> list[dict]:
    """Compute real per-service CPU peak + mean RAM from the live samplers."""
    prof: dict[str, dict] = {}

    for path in sorted(live_dir.glob("resources_*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    key = row["container"]
                    p = prof.setdefault(
                        key, {"name": key, "kind": "container", "cpu": [], "ram": []}
                    )
                    p["cpu"].append(_num(row["cpu_pct"]))
                    p["ram"].append(_num(row["mem_used_bytes"]))
                except (KeyError, ValueError, TypeError):
                    continue

    for path in sorted(live_dir.glob("host_*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    role = _host_role(row.get("cmd_hint", ""), row.get("name", ""))
                    if role is None:
                        continue
                    p = prof.setdefault(
                        role, {"name": role, "kind": "host", "cpu": [], "ram": []}
                    )
                    p["cpu"].append(_num(row["cpu_pct"]))
                    p["ram"].append(_num(row["rss_bytes"]))
                except (KeyError, ValueError, TypeError):
                    continue

    profiles = []
    for p in prof.values():
        if not p["cpu"]:
            continue
        profiles.append(
            {
                "name": p["name"],
                "kind": p["kind"],
                "cpu_peak": round(max(p["cpu"]), 2),
                "ram_mean_mb": round(sum(p["ram"]) / len(p["ram"]) / 1e6, 1),
                "samples": len(p["cpu"]),
            }
        )
    profiles.sort(key=lambda x: x["name"])
    return profiles


def build_fleet(profiles: list[dict], n: int = N_NODES) -> list[dict]:
    """Fixed heterogeneous fleet: measured profiles + documented speed envelope."""
    if not profiles:
        raise SystemExit("ERROR: no measured profiles found in research/data/live")
    rng = random.Random(FLEET_SEED)
    pool = profiles[:]
    rng.shuffle(pool)
    nodes = []
    for i in range(n):
        p = pool[i % len(pool)]
        nodes.append(
            {
                "node_id": i,
                "speed": round(rng.uniform(SPEED_MIN, SPEED_MAX), 4),
                "profile": p["name"],
                "profile_kind": p["kind"],
                "cpu_peak_measured": p["cpu_peak"],
                "ram_mean_mb_measured": p["ram_mean_mb"],
            }
        )
    return nodes


# ------------------------------------------------------------------- aggregation
def _p95(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]


def _mean(xs: list[float]) -> float:
    return float(stats.fmean(xs)) if xs else float("nan")


def _std(xs: list[float]) -> float:
    return float(stats.stdev(xs)) if len(xs) > 1 else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", default="research/data/trace/tasks.csv")
    ap.add_argument("--since", default="2026-10-20T12:00:00Z")
    ap.add_argument("--until", default=None)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--sizes", default="5,10,15,20,25,30,40,50,60,70,80,90,100")
    ap.add_argument("--sla", type=float, default=30.0)
    ap.add_argument("--out-prefix", default=str(OUT_DIR / "fleet"))
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]
    if max(sizes) > N_NODES:
        raise SystemExit(f"ERROR: sizes<= {N_NODES}")

    trace_path, window_stats = apply_window(args.tasks, args.since, args.until)
    tasks = load_tasks(trace_path)
    if not tasks:
        print(f"ERROR: no schedulable tasks in {trace_path}")
        return 2

    profiles = load_profiles(LIVE_DIR)
    fleet = build_fleet(profiles, N_NODES)
    print(
        f"[fleet] profiles from live samplers: {[p['name'] for p in profiles]}",
        flush=True,
    )
    print(
        f"[fleet] fleet of {N_NODES} nodes, speeds "
        f"{min(n['speed'] for n in fleet)}..{max(n['speed'] for n in fleet)}, "
        f"requests={len(tasks)} seeds={args.seeds} sizes={sizes}",
        flush=True,
    )

    # nodes[i] data accumulators keyed by (size, algo)
    runs: list[dict] = []
    node_stats: dict[tuple[int, str], dict[int, dict]] = {}
    n_requests = len(tasks)

    for size in sizes:
        nodes = fleet[:size]
        speeds = [n["speed"] for n in nodes]
        for algo in ALGORITHMS:
            acc = {
                i: {"counts": [], "busy": [], "util": [], "flows": [], "sla": 0}
                for i in range(size)
            }
            for seed in range(args.seeds):
                sched = get_scheduler(algo, seed)
                res = run_simulation(tasks, sched, size, speeds, args.sla, seed)
                assert res.n_tasks == n_requests, "algorithms saw different N"
                runs.append(
                    {
                        "fleet_size": size,
                        "algorithm": algo,
                        "seed": seed,
                        "n_requests": res.n_tasks,
                        "makespan_s": round(res.makespan, 3),
                        "mean_flow_s": round(res.mean_flow, 3),
                        "p95_flow_s": round(res.p95_flow, 3),
                        "sla_violations": res.sla_violations,
                        "imbalance_cv": round(res.imbalance_cv, 4),
                        "util_mean": round(_mean(res.utilization), 4),
                        # scheduler overhead (wall time inside dispatch()); engine
                        # instrumentation, deterministic call count
                        "dispatch_cpu_s": round(
                            res.extra.get("dispatch_cpu_s", 0.0), 6
                        ),
                        "dispatch_calls": res.extra.get("dispatch_calls", 0),
                    }
                )
                counts = [0] * size
                for row in res.per_task:
                    wid = row["worker"]
                    counts[wid] += 1
                    acc[wid]["flows"].append(row["flow"])
                    if row["flow"] > args.sla:
                        acc[wid]["sla"] += 1
                for i in range(size):
                    util = res.utilization[i]
                    acc[i]["counts"].append(counts[i])
                    acc[i]["util"].append(util)
                    acc[i]["busy"].append(util * res.makespan)
            node_stats[(size, algo)] = acc
            mk = [
                r["makespan_s"]
                for r in runs
                if r["fleet_size"] == size and r["algorithm"] == algo
            ]
            mf = [
                r["mean_flow_s"]
                for r in runs
                if r["fleet_size"] == size and r["algorithm"] == algo
            ]
            print(
                f"[fleet] size={size:>2} {algo:<12} "
                f"makespan={_mean(mk):8.1f}s mean_flow={_mean(mf):5.2f}s "
                f"({args.seeds} seeds done)",
                flush=True,
            )

    out = Path(args.out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1) fleet definition
    with (out.parent / "fleet_nodes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fleet[0].keys()))
        w.writeheader()
        w.writerows(fleet)

    # 2) raw runs
    with (out.parent / "fleet_runs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        w.writeheader()
        w.writerows(runs)

    # 3) THE per-server dataset: (size, algo, node) aggregated over seeds
    server_rows = []
    for size in sizes:
        nodes = fleet[:size]
        for algo in ALGORITHMS:
            acc = node_stats[(size, algo)]
            for node in nodes:
                a = acc[node["node_id"]]
                flows = a["flows"]
                server_rows.append(
                    {
                        "fleet_size": size,
                        "algorithm": algo,
                        "node_id": node["node_id"],
                        "speed_factor": node["speed"],
                        "profile_source": node["profile"],
                        "profile_kind": node["profile_kind"],
                        "cpu_peak_pct_measured": node["cpu_peak_measured"],
                        "ram_mean_mb_measured": node["ram_mean_mb_measured"],
                        "tasks_assigned_mean": round(_mean(a["counts"]), 2),
                        "tasks_assigned_total": sum(a["counts"]),
                        "busy_s_mean": round(_mean(a["busy"]), 2),
                        "utilization_pct_mean": round(_mean(a["util"]) * 100, 3),
                        "mean_flow_s": "" if not flows else round(_mean(flows), 3),
                        "p95_flow_s": "" if not flows else round(_p95(flows), 3),
                        "sla_violations_pooled": a["sla"],
                        "seeds_with_tasks": sum(1 for c in a["counts"] if c > 0),
                    }
                )
    server_csv = out.parent / "fleet_server_data.csv"
    with server_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(server_rows[0].keys()))
        w.writeheader()
        w.writerows(server_rows)

    # 4) summary markdown
    lines = [
        "# 50-Server Fleet Comparison - identical real workload",
        "",
        f"- Trace: `{args.tasks}` arrival window `[{args.since or '-inf'} .. {args.until or '+inf'}]`"
        + (f" (kept {window_stats})" if window_stats else ""),
        f"- Requests per run: **{n_requests}** (identical for every algorithm and fleet size, asserted in code)",
        f"- Algorithms: {', '.join(ALGORITHMS)} · Fleet sizes: {sizes} · Seeds: {args.seeds} · SLA: {args.sla}s",
        f"- Speed envelope: uniform [{SPEED_MIN}, {SPEED_MAX}] per node (fixed fleet, seed {FLEET_SEED})",
        f"- Node profiles: {len(profiles)} real measured KYRO service profiles from live 1 Hz samplers "
        f"({', '.join(p['name'] for p in profiles)})",
        "",
        "> **Measured vs virtual:** task arrivals, service demands, and all",
        "> `*_measured` columns come from the running application. The 50 nodes are",
        "> a controlled heterogeneous fleet (trace-driven simulation), the standard",
        "> setup for scheduling research on one machine - not 50 physical servers.",
        "",
        "## Per-fleet-size comparison (mean over seeds)",
        "",
        "| size | algorithm | makespan_s | mean_flow_s | p95_flow_s | sla_viol | imbalance_cv | util_mean |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for size in sizes:
        for algo in ALGORITHMS:
            rr = [r for r in runs if r["fleet_size"] == size and r["algorithm"] == algo]
            lines.append(
                f"| {size} | {algo} "
                f"| {_mean([r['makespan_s'] for r in rr]):.1f} ± {_std([r['makespan_s'] for r in rr]):.2f}"
                f" | {_mean([r['mean_flow_s'] for r in rr]):.3f} ± {_std([r['mean_flow_s'] for r in rr]):.3f}"
                f" | {_mean([r['p95_flow_s'] for r in rr]):.3f}"
                f" | {_mean([r['sla_violations'] for r in rr]):.1f}"
                f" | {_mean([r['imbalance_cv'] for r in rr]):.3f}"
                f" | {_mean([r['util_mean'] for r in rr]):.4f} |"
            )

    lines += [
        "",
        "## Winners per fleet size",
        "",
        "| size | makespan | mean_flow | imbalance |",
        "|---|---|---|---|",
    ]
    for size in sizes:
        cell = []
        for metric in ("makespan_s", "mean_flow_s", "imbalance_cv"):
            best = min(
                ALGORITHMS,
                key=lambda a: _mean(
                    [
                        r[metric]
                        for r in runs
                        if r["fleet_size"] == size and r["algorithm"] == a
                    ]
                ),
            )
            cell.append(best)
        lines.append(f"| {size} | {cell[0]} | {cell[1]} | {cell[2]} |")

    lines += [
        "",
        "## Files",
        "- `fleet_server_data.csv` - per-server rows (size x algorithm x node): tasks, busy, utilization, flow, SLA, measured profile",
        "- `fleet_runs.csv` - raw per-seed runs",
        "- `fleet_nodes.csv` - fleet definition",
        "",
        f"Regenerate: `python -m research.experiments.fleet50 --tasks {args.tasks}`",
    ]
    md_path = out.parent / "fleet50_summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nwrote {out.parent / 'fleet_nodes.csv'} ({len(fleet)} nodes)")
    print(f"wrote {out.parent / 'fleet_runs.csv'} ({len(runs)} runs)")
    print(f"wrote {server_csv} ({len(server_rows)} server rows)")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
