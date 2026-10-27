# Offered-Load Sweep - time-compressed real trace

- Trace: `research/data/trace/tasks.csv`
- Arrival window: `[2026-10-20T12:00:00Z .. +inf]` (kept {'burst': 150})
- Scenarios: factor 1 (n=74), factor 2 (n=74), factor 4 (n=74), factor 8 (n=74) - time-compressed variants of the real trace; arrivals scaled by 1/factor, service times unchanged - derived offered-load scenarios, not fabricated measurements.
- Algorithms: dragonfly, fcfs, round_robin (identical task list per factor, asserted in code)
- Seeds: 20 (0..19) - Workers: 4 - Speeds: 1,0.9,0.8,1.1 - SLA: 30.0s
- Runs: 240 (4 factors x 3 algorithms x 20 seeds)

| factor | algorithm | mean_flow_s | p95_flow_s | sla_violations | imbalance_cv |
|---|---|---|---|---|---|
| 1 | dragonfly | 2.349 ± 0.000 | 7.705 ± 0.000 | 0.0 | 1.732 ± 0.000 |
| 1 | fcfs | 2.584 ± 0.000 | 8.475 ± 0.000 | 0.0 | 1.732 ± 0.000 |
| 1 | round_robin | 2.759 ± 0.052 | 9.253 ± 0.403 | 0.0 | 0.261 ± 0.070 |
| 2 | dragonfly | 2.360 ± 0.000 | 7.705 ± 0.000 | 0.0 | 1.617 ± 0.000 |
| 2 | fcfs | 2.597 ± 0.000 | 8.475 ± 0.000 | 0.0 | 1.616 ± 0.000 |
| 2 | round_robin | 2.759 ± 0.052 | 9.253 ± 0.403 | 0.0 | 0.261 ± 0.070 |
| 4 | dragonfly | 2.389 ± 0.000 | 7.705 ± 0.000 | 0.0 | 1.366 ± 0.000 |
| 4 | fcfs | 2.637 ± 0.000 | 8.475 ± 0.000 | 0.0 | 1.334 ± 0.000 |
| 4 | round_robin | 2.768 ± 0.043 | 9.180 ± 0.526 | 0.0 | 0.261 ± 0.059 |
| 8 | dragonfly | 2.445 ± 0.000 | 8.001 ± 0.000 | 0.0 | 0.999 ± 0.000 |
| 8 | fcfs | 2.706 ± 0.000 | 8.837 ± 0.000 | 0.0 | 0.967 ± 0.000 |
| 8 | round_robin | 2.747 ± 0.024 | 9.189 ± 0.795 | 0.0 | 0.139 ± 0.058 |

## Winner per factor (min mean mean_flow_s)

| factor | winner | mean_flow_s | runner-up | runner-up mean_flow_s |
|---|---|---|---|---|
| 1 | **dragonfly** | 2.349 | fcfs | 2.584 |
| 2 | **dragonfly** | 2.360 | fcfs | 2.597 |
| 4 | **dragonfly** | 2.389 | fcfs | 2.637 |
| 8 | **dragonfly** | 2.445 | fcfs | 2.706 |

Lower is better for all metrics. Service demands stay real in every scenario; only arrival timing is compressed.

Raw per-run rows: `load_sweep.csv` (regenerate with load_sweep.py).