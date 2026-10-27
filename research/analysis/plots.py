"""Generate publication diagrams from the research result datasets.

Reads only files produced by the established pipeline and writes PNGs to
research/results/figures/:

  flow_cdf.png          ECDF of per-task flow time, one line per algorithm
  flow_box.png          flow-time boxplot per algorithm (all seeds pooled)
  algo_bars.png         mean/p95 flow per algorithm (4-worker head-to-head)
  fleet_scaling.png     mean flow vs fleet size (10..100 servers) per algorithm
  fleet_imbalance.png   imbalance CV vs fleet size per algorithm
  server_resources.png  container CPU (mean/p95/max) + RAM bars
  server_latency.png    per-server latency mean/p95/max bars
  cpu_timeline.png      real CPU timeline during the load campaign
  app_latency.png       live application request latency by phase
  load_sweep.png        mean flow vs time-compression factor (offered load)
  dispatch_overhead.png scheduler dispatch() wall time per run (log scale)
  trackb_lag.png        Kafka backlog drain during Track B live phases

Missing inputs skip their figure with a console note (never fabricates data).

Usage:  python -m research.analysis.plots
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ALGO_ORDER = ["dragonfly", "fcfs", "round_robin", "ga", "pso"]
ALGO_STYLE = {
    "dragonfly": {"color": "#d62728", "marker": "o"},
    "fcfs": {"color": "#1f77b4", "marker": "s"},
    "round_robin": {"color": "#2ca02c", "marker": "^"},
    "ga": {"color": "#9467bd", "marker": "D"},
    "pso": {"color": "#8c564b", "marker": "v"},
}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(row: dict, key: str, default: float = float("nan")) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return default


def _save(fig, out_dir: Path, name: str) -> Path:
    path = out_dir / name
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def fig_flow_cdf(flows: list[dict], out: Path) -> Path | None:
    by: dict[str, list[float]] = {}
    for r in flows:
        v = _f(r, "flow_s")
        if v == v:
            by.setdefault(r.get("algorithm", "?"), []).append(v)
    if not by:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for algo in ALGO_ORDER:
        if algo not in by:
            continue
        vals = sorted(by[algo])
        y = [(i + 1) / len(vals) for i in range(len(vals))]
        st = ALGO_STYLE.get(algo, {})
        ax.step(
            vals,
            y,
            where="post",
            label=f"{algo} (n={len(vals)})",
            color=st.get("color"),
            marker=st.get("marker"),
            markevery=max(1, len(vals) // 12),
        )
    ax.set_xlabel("flow time (seconds)")
    ax.set_ylabel("ECDF")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Per-task flow time - identical real trace, all seeds pooled")
    return _save(fig, out, "flow_cdf.png")


def fig_flow_box(flows: list[dict], out: Path) -> Path | None:
    data, labels = [], []
    for algo in ALGO_ORDER:
        vals = [_f(r, "flow_s") for r in flows if r.get("algorithm") == algo]
        vals = [v for v in vals if v == v]
        if vals:
            data.append(vals)
            labels.append(algo)
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.boxplot(data, tick_labels=labels, showfliers=True)
    ax.set_ylabel("flow time (seconds)")
    ax.grid(alpha=0.3, axis="y")
    ax.set_title("Flow time distribution per algorithm (all seeds, all tasks)")
    return _save(fig, out, "flow_box.png")


def fig_algo_bars(runs: list[dict], out: Path) -> Path | None:
    if not runs:
        return None
    # only draw the algorithms actually present in this run (a core-3 file
    # must still render when the 5-algorithm order is the default)
    algos = [a for a in ALGO_ORDER if any(r.get("algorithm") == a for r in runs)]
    if not algos:
        return None
    metrics = ["mean_flow_s", "p95_flow_s"]
    stats: dict[str, dict[str, tuple[float, float]]] = {}
    for algo in algos:
        rows = [r for r in runs if r.get("algorithm") == algo]
        if not rows:
            continue
        stats[algo] = {}
        for m in metrics:
            vals = [_f(r, m) for r in rows]
            vals = [v for v in vals if v == v]
            mean = sum(vals) / len(vals)
            var = (
                sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
                if len(vals) > 1
                else 0.0
            )
            stats[algo][m] = (mean, var**0.5)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    width = 0.35
    xs = range(len(algos))
    for i, m in enumerate(metrics):
        means = [stats[a][m][0] for a in algos]
        stds = [stats[a][m][1] for a in algos]
        pos = [x + (i - 0.5) * width for x in xs]
        ax.bar(
            pos,
            means,
            width,
            yerr=stds,
            capsize=4,
            label=m,
            color=["#1f77b4", "#ff7f0e"][i],
        )
    ax.set_xticks(list(xs))
    ax.set_xticklabels(algos)
    ax.set_ylabel("seconds")
    ax.grid(alpha=0.3, axis="y")
    ax.legend()
    ax.set_title("Head-to-head on identical requests (mean +/- std over seeds)")
    return _save(fig, out, "algo_bars.png")


def fig_fleet(runs: list[dict], out_dir: Path) -> list[Path]:
    written: list[Path] = []
    if not runs:
        return written
    for metric, name, title in [
        ("mean_flow_s", "fleet_scaling.png", "Mean flow time vs fleet size"),
        ("imbalance_cv", "fleet_imbalance.png", "Load imbalance (CV) vs fleet size"),
    ]:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        any_data = False
        for algo in ALGO_ORDER:
            sizes = sorted(
                {int(r["fleet_size"]) for r in runs if r.get("algorithm") == algo}
            )
            xs, means, stds = [], [], []
            for s in sizes:
                vals = [
                    _f(r, metric)
                    for r in runs
                    if r.get("algorithm") == algo and int(r["fleet_size"]) == s
                ]
                vals = [v for v in vals if v == v]
                if not vals:
                    continue
                mean = sum(vals) / len(vals)
                var = (
                    sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
                    if len(vals) > 1
                    else 0.0
                )
                xs.append(s)
                means.append(mean)
                stds.append(var**0.5)
            if xs:
                any_data = True
                st = ALGO_STYLE.get(algo, {})
                ax.errorbar(
                    xs,
                    means,
                    yerr=stds,
                    label=algo,
                    marker=st.get("marker"),
                    color=st.get("color"),
                    capsize=3,
                )
        if not any_data:
            plt.close(fig)
            continue
        ax.set_xlabel("virtual servers (fleet size)")
        ax.set_ylabel("seconds" if metric.endswith("flow_s") else "CV")
        ax.grid(alpha=0.3)
        ax.legend()
        ax.set_title(title + " - identical real trace")
        written.append(_save(fig, out_dir, name))
    return written


def fig_server_resources(metrics: list[dict], out: Path) -> Path | None:
    rows = [r for r in metrics if r.get("family") == "resources"]
    if not rows:
        return None
    servers = sorted({r["server"] for r in rows})
    lookup = {(r["server"], r["metric"]): _f(r, "value") for r in rows}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    xs = range(len(servers))
    for i, (m, label) in enumerate(
        [("cpu_pct_mean", "mean"), ("cpu_pct_p95", "p95"), ("cpu_pct_max", "max")]
    ):
        ax1.bar(
            [x + (i - 1) * 0.26 for x in xs],
            [lookup.get((s, m), 0) for s in servers],
            0.26,
            label=label,
        )
    ax1.set_xticks(list(xs))
    ax1.set_xticklabels(servers, rotation=30, ha="right")
    ax1.set_ylabel("CPU %")
    ax1.set_title("Container CPU")
    ax1.legend()
    ax1.grid(alpha=0.3, axis="y")
    mem = [lookup.get((s, "mem_used_bytes_max"), 0) / 1e6 for s in servers]
    ax2.bar(list(xs), mem, color="#9467bd")
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels(servers, rotation=30, ha="right")
    ax2.set_ylabel("max RAM (MB)")
    ax2.set_title("Container peak memory")
    ax2.grid(alpha=0.3, axis="y")
    return _save(fig, out, "server_resources.png")


def fig_server_latency(metrics: list[dict], out: Path) -> Path | None:
    rows = [r for r in metrics if r.get("family") == "latency"]
    if not rows:
        return None
    servers = sorted({r["server"] for r in rows})
    lookup = {(r["server"], r["metric"]): _f(r, "value") for r in rows}
    fig, ax = plt.subplots(figsize=(7, 4.5))
    xs = range(len(servers))
    for i, (m, label) in enumerate(
        [("total_ms_mean", "mean"), ("total_ms_p95", "p95"), ("total_ms_max", "max")]
    ):
        ax.bar(
            [x + (i - 1) * 0.26 for x in xs],
            [lookup.get((s, m), 0) for s in servers],
            0.26,
            label=label,
        )
    ax.set_xticks(list(xs))
    ax.set_xticklabels(servers, rotation=30, ha="right")
    ax.set_ylabel("milliseconds")
    ax.set_title("Per-server request latency (probed every 5 s)")
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, out, "server_latency.png")


def _ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def fig_cpu_timeline(live: Path, out: Path) -> Path | None:
    # container CPU (kafka + n8n) from resources sampler
    series: dict[str, list[tuple[dt.datetime, float]]] = {}
    for path in sorted(live.glob("resources_*.csv")):
        for r in read_csv(path):
            if r.get("container") in ("kyro-kafka", "kyro-n8n"):
                try:
                    series.setdefault(r["container"], []).append(
                        (_ts(r["ts"]), _f(r, "cpu_pct"))
                    )
                except ValueError:
                    continue
    worker: list[tuple[dt.datetime, float]] = []
    for path in sorted(live.glob("host_*.csv")):
        for r in read_csv(path):
            if "worker_main" in (r.get("cmd_hint") or ""):
                try:
                    worker.append((_ts(r["ts"]), _f(r, "cpu_pct")))
                except ValueError:
                    continue
    if not series and not worker:
        return None
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

    def downsample(points, n=1500):
        if len(points) <= n:
            return points
        step = len(points) // n
        return points[::step]

    for name, st in [
        ("kyro-kafka", {"color": "#1f77b4"}),
        ("kyro-n8n", {"color": "#ff7f0e"}),
    ]:
        pts = downsample(sorted(series.get(name, [])))
        if pts:
            t0 = sorted(series[name])[0][0]
            axes[0].plot(
                [(p[0] - t0).total_seconds() / 60 for p in pts],
                [p[1] for p in pts],
                label=name,
                color=st["color"],
                linewidth=1,
            )
    axes[0].set_ylabel("CPU %")
    axes[0].set_title("Container CPU during live load (1 Hz)")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    if worker:
        pts = downsample(sorted(worker))
        t0 = sorted(worker)[0][0]
        axes[1].plot(
            [(p[0] - t0).total_seconds() / 60 for p in pts],
            [p[1] for p in pts],
            label="worker process",
            color="#d62728",
            linewidth=1,
        )
    axes[1].set_ylabel("CPU %")
    axes[1].set_xlabel("minutes since sampling start")
    axes[1].set_title("Ingestion worker CPU (1 Hz)")
    axes[1].legend()
    axes[1].grid(alpha=0.3)
    return _save(fig, out, "cpu_timeline.png")


def fig_app_latency(live: Path, out: Path) -> Path | None:
    groups: dict[tuple[str, str], list[float]] = {}
    for path in sorted(live.glob("app_requests_*.csv")):
        for r in read_csv(path):
            v = _f(r, "total_ms")
            if v == v:
                groups.setdefault(
                    (r.get("phase", "?"), r.get("entrypoint", "?")), []
                ).append(v)
    if not groups:
        return None
    keys = sorted(groups)
    means = [sum(v) / len(v) for k in keys for v in [groups[k]]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(range(len(keys)), means, color="#17becf")
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([f"{p}\n@{e}" for p, e in keys], rotation=0, fontsize=8)
    ax.set_ylabel("mean latency (ms)")
    ax.set_title("Live application request latency by phase (real HTTP)")
    ax.grid(alpha=0.3, axis="y")
    return _save(fig, out, "app_latency.png")


def fig_load_sweep(sweep: list[dict], out: Path) -> Path | None:
    """Mean flow vs time-compression factor (offered-load sweep)."""
    if not sweep:
        return None
    algos = [a for a in ALGO_ORDER if any(r.get("algorithm") == a for r in sweep)]
    algos += sorted({r.get("algorithm", "?") for r in sweep} - set(algos))
    factors = sorted(
        {v for v in (_f(r, "compression_factor") for r in sweep) if v == v}
    )
    if not algos or not factors:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.5))
    any_data = False
    for algo in algos:
        xs, means, stds = [], [], []
        for fac in factors:
            vals = [
                _f(r, "mean_flow_s")
                for r in sweep
                if r.get("algorithm") == algo and _f(r, "compression_factor") == fac
            ]
            vals = [v for v in vals if v == v]
            if not vals:
                continue
            mean = sum(vals) / len(vals)
            var = (
                sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
                if len(vals) > 1
                else 0.0
            )
            xs.append(fac)
            means.append(mean)
            stds.append(var**0.5)
        if not xs:
            continue
        any_data = True
        st = ALGO_STYLE.get(algo, {})
        ax.errorbar(
            xs,
            means,
            yerr=stds,
            label=algo,
            marker=st.get("marker"),
            color=st.get("color"),
            capsize=3,
        )
    if not any_data:
        plt.close(fig)
        return None
    ax.set_xscale("log", base=2)
    ax.set_xticks(factors)
    ax.set_xticklabels([f"{int(f)}x" if f != int(f) else f"{f}x" for f in factors])
    ax.set_xlabel("time-compression factor (arrivals scaled, service unchanged)")
    ax.set_ylabel("mean flow time (seconds)")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Offered-load sweep - derived variants of the real trace")
    return _save(fig, out, "load_sweep.png")


def fig_dispatch_overhead(runs: list[dict], out: Path) -> Path | None:
    """Per-run wall time spent inside scheduler dispatch() (log scale)."""
    if not runs or "dispatch_cpu_s" not in runs[0]:
        return None
    algos = [a for a in ALGO_ORDER if any(r.get("algorithm") == a for r in runs)]
    algos += sorted({r.get("algorithm", "?") for r in runs} - set(algos))
    means: dict[str, float] = {}
    for algo in algos:
        vals = [_f(r, "dispatch_cpu_s") for r in runs if r.get("algorithm") == algo]
        vals = [v for v in vals if v == v]
        if vals:
            means[algo] = sum(vals) / len(vals)
    if not means:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.5))
    xs = list(means.keys())
    ys = [max(means[a], 1e-7) for a in xs]
    colors = [ALGO_STYLE.get(a, {}).get("color", "#7f7f7f") for a in xs]
    ax.bar(xs, ys, color=colors)
    ax.set_yscale("log")
    ax.set_ylabel("CPU seconds per run inside dispatch() (log)")
    ax.grid(alpha=0.3, axis="y")
    ax.set_title("Scheduler dispatch overhead - identical trace, all seeds")
    return _save(fig, out, "dispatch_overhead.png")


def fig_trackb(results: Path, out: Path) -> Path | None:
    """Kafka backlog drain during the Track B live phases (real offsets)."""
    series: dict[str, tuple[list[tuple[float, float]], int]] = {}
    for path in sorted(results.glob("trackb_lag_*.csv")):
        rows = read_csv(path)
        pts, consumers = [], -1
        for r in rows:
            x, y = _f(r, "elapsed_s"), _f(r, "total_lag")
            if x == x and y == y and y >= 0:
                pts.append((x / 60.0, y))
            c = _f(r, "consumers", -1)
            if c == c and c >= 0:
                consumers = int(c)
        if pts:
            phase = path.stem.replace("trackb_lag_", "").upper()
            series[phase] = (pts, consumers)
    if not series:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for phase, (pts, consumers) in sorted(series.items()):
        label = (
            f"phase {phase} ({consumers} consumers)"
            if consumers >= 0
            else f"phase {phase}"
        )
        ax.plot([p[0] for p in pts], [p[1] for p in pts], label=label, linewidth=1.5)
    ax.set_xlabel("minutes since burst start")
    ax.set_ylabel("Kafka consumer-group lag (messages)")
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Track B live: backlog drain, 2 s offset polls (real Kafka)")
    return _save(fig, out, "trackb_lag.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="research/results")
    ap.add_argument("--live", default="research/data/live")
    args = ap.parse_args()
    results, live = Path(args.results), Path(args.live)
    fig_dir = results / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    flows = read_csv(results / "flow_samples.csv")
    runs4 = read_csv(results / "algo_comparison.csv")
    fleet_runs = read_csv(results / "fleet_runs.csv")
    metrics = read_csv(results / "server_metrics.csv")
    sweep = read_csv(results / "load_sweep.csv")

    written: list[Path] = []
    jobs = [
        (fig_flow_cdf(flows, fig_dir), "flow_cdf.png"),
        (fig_flow_box(flows, fig_dir), "flow_box.png"),
        (fig_algo_bars(runs4, fig_dir), "algo_bars.png"),
        (fig_server_resources(metrics, fig_dir), "server_resources.png"),
        (fig_server_latency(metrics, fig_dir), "server_latency.png"),
        (fig_cpu_timeline(live, fig_dir), "cpu_timeline.png"),
        (fig_app_latency(live, fig_dir), "app_latency.png"),
        (fig_load_sweep(sweep, fig_dir), "load_sweep.png"),
        (fig_dispatch_overhead(runs4, fig_dir), "dispatch_overhead.png"),
        (fig_trackb(results, fig_dir), "trackb_lag.png"),
    ]
    written += [p for p, _ in jobs if p]
    written += fig_fleet(fleet_runs, fig_dir)

    made = {p.name for p in written}
    expected = {
        "flow_cdf.png",
        "flow_box.png",
        "algo_bars.png",
        "fleet_scaling.png",
        "fleet_imbalance.png",
        "server_resources.png",
        "server_latency.png",
        "cpu_timeline.png",
        "app_latency.png",
        "load_sweep.png",
        "dispatch_overhead.png",
        "trackb_lag.png",
    }
    for name in sorted(expected - made):
        print(f"[plots] skipped {name} (source data missing)")
    print(f"[plots] wrote {len(written)} figures to {fig_dir}:")
    for p in sorted(written):
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
