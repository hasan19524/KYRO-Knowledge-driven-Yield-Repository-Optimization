# 50-Server Fleet Comparison - identical real workload

- Trace: `research/data/trace/tasks.csv` arrival window `[2026-10-20T12:00:00Z .. +inf]` (kept {'burst': 150})
- Requests per run: **74** (identical for every algorithm and fleet size, asserted in code)
- Algorithms: dragonfly, fcfs, round_robin · Fleet sizes: [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100] · Seeds: 30 · SLA: 30.0s
- Speed envelope: uniform [0.5, 1.5] per node (fixed fleet, seed 20261020)
- Node profiles: 9 real measured KYRO service profiles from live 1 Hz samplers (backend, frontend, kyro-chroma, kyro-kafka, kyro-n8n, kyro-postgres, router, tunnel, worker)

> **Measured vs virtual:** task arrivals, service demands, and all
> `*_measured` columns come from the running application. The 50 nodes are
> a controlled heterogeneous fleet (trace-driven simulation), the standard
> setup for scheduling research on one machine - not 50 physical servers.

## Per-fleet-size comparison (mean over seeds)

| size | algorithm | makespan_s | mean_flow_s | p95_flow_s | sla_viol | imbalance_cv | util_mean |
|---|---|---|---|---|---|---|---|
| 5 | dragonfly | 5274.1 ± 0.00 | 2.446 ± 0.000 | 8.021 | 0.0 | 2.000 | 0.0069 |
| 5 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 1.938 | 0.0133 |
| 5 | round_robin | 5274.5 ± 0.39 | 3.444 ± 0.064 | 10.019 | 0.0 | 0.369 | 0.0097 |
| 10 | dragonfly | 5273.9 ± 0.00 | 1.763 ± 0.000 | 5.782 | 0.0 | 3.000 | 0.0025 |
| 10 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 2.918 | 0.0067 |
| 10 | round_robin | 5274.4 ± 0.41 | 3.253 ± 0.083 | 9.888 | 0.0 | 0.422 | 0.0046 |
| 15 | dragonfly | 5273.9 ± 0.00 | 1.763 ± 0.000 | 5.782 | 0.0 | 3.742 | 0.0016 |
| 15 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 3.643 | 0.0044 |
| 15 | round_robin | 5274.4 ± 0.39 | 3.123 ± 0.118 | 9.291 | 0.0 | 0.535 | 0.0029 |
| 20 | dragonfly | 5273.9 ± 0.00 | 1.763 ± 0.000 | 5.782 | 0.0 | 4.359 | 0.0012 |
| 20 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 4.246 | 0.0033 |
| 20 | round_robin | 5274.4 ± 0.39 | 2.997 ± 0.081 | 8.944 | 0.0 | 0.549 | 0.0021 |
| 25 | dragonfly | 5273.9 ± 0.00 | 1.763 ± 0.000 | 5.782 | 0.0 | 4.899 | 0.0010 |
| 25 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 4.773 | 0.0027 |
| 25 | round_robin | 5274.3 ± 0.38 | 2.931 ± 0.090 | 8.766 | 0.0 | 0.590 | 0.0016 |
| 30 | dragonfly | 5273.9 ± 0.00 | 1.763 ± 0.000 | 5.782 | 0.0 | 5.385 | 0.0008 |
| 30 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 5.248 | 0.0022 |
| 30 | round_robin | 5274.3 ± 0.34 | 2.935 ± 0.100 | 8.946 | 0.0 | 0.685 | 0.0014 |
| 40 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 6.245 | 0.0006 |
| 40 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 6.087 | 0.0017 |
| 40 | round_robin | 5274.3 ± 0.39 | 2.905 ± 0.097 | 8.692 | 0.0 | 0.746 | 0.0010 |
| 50 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 7.000 | 0.0005 |
| 50 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 6.824 | 0.0013 |
| 50 | round_robin | 5274.3 ± 0.35 | 2.858 ± 0.130 | 8.972 | 0.0 | 0.868 | 0.0008 |
| 60 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 7.681 | 0.0004 |
| 60 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 7.489 | 0.0011 |
| 60 | round_robin | 5274.2 ± 0.31 | 2.908 ± 0.137 | 8.944 | 0.0 | 0.989 | 0.0007 |
| 70 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 8.307 | 0.0003 |
| 70 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 8.099 | 0.0010 |
| 70 | round_robin | 5274.3 ± 0.30 | 2.923 ± 0.106 | 8.812 | 0.0 | 0.990 | 0.0006 |
| 80 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 8.888 | 0.0003 |
| 80 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 8.667 | 0.0008 |
| 80 | round_robin | 5274.3 ± 0.33 | 2.895 ± 0.116 | 8.818 | 0.0 | 1.093 | 0.0005 |
| 90 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 9.434 | 0.0003 |
| 90 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 9.199 | 0.0007 |
| 90 | round_robin | 5274.3 ± 0.33 | 2.850 ± 0.117 | 8.712 | 0.0 | 1.199 | 0.0004 |
| 100 | dragonfly | 5273.9 ± 0.00 | 1.728 ± 0.000 | 5.668 | 0.0 | 9.950 | 0.0002 |
| 100 | fcfs | 5275.0 ± 0.00 | 4.751 ± 0.000 | 15.931 | 0.0 | 9.702 | 0.0007 |
| 100 | round_robin | 5274.3 ± 0.35 | 2.847 ± 0.114 | 8.658 | 0.0 | 1.304 | 0.0004 |

## Winners per fleet size

| size | makespan | mean_flow | imbalance |
|---|---|---|---|
| 5 | dragonfly | dragonfly | round_robin |
| 10 | dragonfly | dragonfly | round_robin |
| 15 | dragonfly | dragonfly | round_robin |
| 20 | dragonfly | dragonfly | round_robin |
| 25 | dragonfly | dragonfly | round_robin |
| 30 | dragonfly | dragonfly | round_robin |
| 40 | dragonfly | dragonfly | round_robin |
| 50 | dragonfly | dragonfly | round_robin |
| 60 | dragonfly | dragonfly | round_robin |
| 70 | dragonfly | dragonfly | round_robin |
| 80 | dragonfly | dragonfly | round_robin |
| 90 | dragonfly | dragonfly | round_robin |
| 100 | dragonfly | dragonfly | round_robin |

## Files
- `fleet_server_data.csv` - per-server rows (size x algorithm x node): tasks, busy, utilization, flow, SLA, measured profile
- `fleet_runs.csv` - raw per-seed runs
- `fleet_nodes.csv` - fleet definition

Regenerate: `python -m research.experiments.fleet50 --tasks research/data/trace/tasks.csv`