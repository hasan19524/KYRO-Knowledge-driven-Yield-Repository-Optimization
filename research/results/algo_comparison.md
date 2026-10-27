# Algorithm Comparison — identical real workload

- Trace: `research/data/trace/tasks.csv`
- Arrival window: `[2026-10-20T12:00:00Z .. +inf]` (kept {'burst': 150})
- Requests per algorithm: **74** (identical set, asserted in code)
- Seeds: 50 · Workers: 4 · Speeds: 1,0.9,0.8,1.1 · SLA: 30.0s
- Runs: 150 (3 algorithms x 50 seeds)

| metric | **dragonfly** | **fcfs** | **round_robin** | best |
|---|---|---|---|---|
| makespan_s | 5274.102 ± 0.000 | 5274.189 ± 0.000 | 5274.258 ± 0.123 | dragonfly |
| mean_flow_s | 2.349 ± 0.000 | 2.584 ± 0.000 | 2.759 ± 0.051 | dragonfly |
| p95_flow_s | 7.705 ± 0.000 | 8.475 ± 0.000 | 9.256 ± 0.402 | dragonfly |
| sla_violations | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | dragonfly |
| imbalance_cv | 1.732 ± 0.000 | 1.732 ± 0.000 | 0.261 ± 0.069 | round_robin |
| util_mean | 0.008 ± 0.000 | 0.009 ± 0.000 | 0.010 ± 0.000 | round_robin |

Lower is better for: makespan, mean_flow, p95_flow, sla_violations, imbalance_cv.
util_mean higher = more utilized workers.

Raw per-run rows: `algo_comparison.csv` (regenerate with run_comparison.py).