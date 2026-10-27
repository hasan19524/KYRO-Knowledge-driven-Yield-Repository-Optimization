# KYRO Master Research Dataset

- Generated: 2026-10-20T15:11:28Z (UTC) by `research/analysis/master_report.py`
- Sources: `research\results\server_metrics.csv` (live samplers), `app_requests_*.csv` (real application traffic), `algo_comparison.*`, `fleet*.*` (experiments)

> **Labeling (paper requirement):** everything in section A is
> *measured* from the running application on this laptop. The 50
> nodes in section C are *virtual* heterogeneous servers driven by
> the same *real* trace - trace-driven simulation, not 50 machines.
> Burst-generated commits are real pipeline executions with
> generated file content, labeled `burst` throughout.

## A. Real measured servers (live telemetry)

### A.1 Request latency per server (HTTP/TCP probes)
| server | total_ms_mean | total_ms_p50 | total_ms_p95 | total_ms_max | ttfb_ms_mean | ttfb_ms_p95 | connect_ms_mean | error_rate | availability |
|---|---|---|---|---|---|---|---|---|---|
| backend | 22.6823 ms | 23.01 ms | 36.548 ms | 576.41 ms | 11.7961 ms | 18.795 ms | - | 0 ratio | 1 ratio |
| chroma | 11.4232 ms | 14.11 ms | 24.984 ms | 30.71 ms | 2.3631 ms | 4.376 ms | - | 0 ratio | 0 ratio |
| frontend | 109.2362 ms | 94.76 ms | 168.443 ms | 576.06 ms | 99.8037 ms | 156.928 ms | - | 0 ratio | 1 ratio |
| kafka | 7.2503 ms | 0.87 ms | 21.958 ms | 28.81 ms | - | - | 7.1419 ms | 0 ratio | 1 ratio |
| n8n | 14.0377 ms | 15.2 ms | 26.989 ms | 44.18 ms | 3.0829 ms | 5.507 ms | - | 0 ratio | 1 ratio |
| postgres | 9.1503 ms | 11.95 ms | 22.864 ms | 30.27 ms | - | - | 9.0264 ms | 0 ratio | 1 ratio |
| router | 113.5299 ms | 98.48 ms | 171.183 ms | 498.87 ms | 102.1694 ms | 159.049 ms | - | 0 ratio | 1 ratio |

### A.2 Container CPU / RAM / IO (docker stats, 1 Hz)
| container | cpu_pct_mean | cpu_pct_p95 | cpu_pct_max | mem_used_bytes_mean | mem_used_bytes_max | mem_pct_of_limit_mean | mem_pct_of_limit_max | net_io_bytes_total_delta | block_io_bytes_total_delta | pids_mean | pids_max |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kyro-chroma | 0.898 | 4.32 | 25.48 | 55,323,936.1762 bytes | 77,447,823 bytes | 0.8902 | 1.2462 | 0 bytes | 0 bytes | 10.8625 count | 20 count |
| kyro-kafka | 32.4788 | 192.508 | 238.56 | 1,260,697,411.1662 bytes | 1,372,242,051 bytes | 20.2853 | 22.0802 | 0 bytes | 0 bytes | 118.3849 count | 140 count |
| kyro-n8n | 2.4549 | 16.992 | 64.55 | 514,831,420.5615 bytes | 544,735,232 bytes | 8.2839 | 8.7651 | 0 bytes | 0 bytes | 20.0913 count | 28 count |
| kyro-postgres | 1.0285 | 4.57 | 18.1 | 57,092,401.6177 bytes | 65,410,170 bytes | 0.9186 | 1.0525 | 0 bytes | 0 bytes | 9.7664 count | 16 count |

### A.3 Host processes (1 Hz psutil)
| role | cpu_pct_mean | cpu_pct_p95 | cpu_pct_max | rss_bytes_mean | rss_bytes_max |
|---|---|---|---|---|---|
| backend | 0.1883 | 1.5 | 24.1 | 44,320,687.0611 bytes | 143,187,968 bytes |
| frontend | 1.5375 | 14.5 | 60.3 | 110,930,428.6421 bytes | 339,017,728 bytes |
| other | 1.565 | 0 | 99.6 | 16,345,355.7597 bytes | 98,304,000 bytes |
| router | 0.0743 | 0 | 5.2 | 51,800,057.3427 bytes | 54,411,264 bytes |
| sampler | 12.148 | 88.7 | 101.7 | 12,292,879.2267 bytes | 33,304,576 bytes |
| tunnel | 0.0794 | 0 | 7.1 | 44,744,811.2178 bytes | 46,526,464 bytes |
| worker | 6.6886 | 3.6 | 739.3 | 69,749,845.3187 bytes | 474,279,936 bytes |

### A.4 Kafka queue backlog per topic (3 s sampler)
| topic | lag_mean | lag_p95 | lag_max | backlog_area | throughput |
|---|---|---|---|---|---|
| kyro.github.backfill | 0.2 messages | 1 messages | 1 messages | 6,056.5 messages*s | 0 messages/s |
| kyro.github.push | 0.026 messages | 0 messages | 3 messages | 777.5 messages*s | 0.0245 messages/s |

### A.5 Application request latency (real HTTP traffic, `app_requests_*.csv`)
| phase | entrypoint | requests | http_ok | mean_ms | p95_ms | max_ms |
|---|---|---|---|---|---|---|
| github_start | backend | 4 | 0/4 | 7.4 | 21.0 | 21.0 |
| github_start | router | 4 | 4/4 | 46.8 | 60.9 | 60.9 |
| health | backend | 5 | 5/5 | 26.1 | 34.8 | 34.8 |
| login | backend | 5 | 5/5 | 177.5 | 190.8 | 190.8 |
| login | router | 2 | 2/2 | 240.9 | 259.6 | 259.6 |
| page_load | frontend | 3 | 3/3 | 73.6 | 105.1 | 105.1 |
| page_load | router | 3 | 3/3 | 83.9 | 111.4 | 111.4 |
| register | backend | 2 | 2/2 | 239.9 | 288.3 | 288.3 |
| register | router | 2 | 2/2 | 304.3 | 357.2 | 357.2 |
| repo_detail | backend | 1 | 0/1 | 27.2 | 27.2 | 27.2 |
| repo_list | backend | 2 | 2/2 | 31.3 | 40.3 | 40.3 |
| repo_list | router | 2 | 2/2 | 137.4 | 147.5 | 147.5 |

### A.6 Pipeline throughput & service times
| metric | value | unit | samples |
|---|---|---|---|
| burst_pushes_camp01 | 105 | count | 170 |
| burst_pushes_campaign2 | 17 | count | 170 |
| burst_pushes_live_traffic | 40 | count | 170 |
| burst_pushes_ok | 167 | count | 170 |
| burst_pushes_total | 170 | count | 170 |
| burst_pushes_validate_e2e | 6 | count | 170 |
| commit_files_delta | 902 | count | 763 |
| commit_files_total | 2,236 | count | 763 |
| commit_work_additions | 203,372 | count | 302 |
| commit_work_changes | 254,118 | count | 302 |
| commit_work_commits | 302 | count | 302 |
| commit_work_deletions | 50,748 | count | 302 |
| commit_work_files | 2,236 | count | 302 |
| commit_work_patch_bytes | 8,574,273 | count | 302 |
| commits_delta | 223 | count | 763 |
| commits_total | 302 | count | 763 |
| events_per_minute_mean | 0.01 | events/min | 254 |
| events_per_minute_peak | 17 | events/min | 254 |
| events_processed | 166 | count | 254 |
| events_total | 254 | count | 254 |
| files_delta | 880 | count | 763 |
| files_total | 1,582 | count | 763 |
| ingestion_events_delta | 166 | count | 763 |
| ingestion_events_total | 254 | count | 763 |
| service_seconds_max | 1,292.0607 | s | 166 |
| service_seconds_mean | 27.5727 | s | 166 |
| service_seconds_p50 | 1.6786 | s | 166 |
| service_seconds_p95 | 40.4379 | s | 166 |

### A.7 Arrival burstiness (research signal)
| metric | value | unit | samples |
|---|---|---|---|
| inter_arrival_cv | 8.7514 | ratio | 253 |
| inter_arrival_max | 592,097.324 | s | 253 |
| inter_arrival_mean | 6,035.9969 | s | 253 |
| inter_arrival_p95 | 561.604 | s | 253 |

## B. Identical requests x 3 algorithms

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

Raw runs: `results/algo_comparison.csv`. Fairness: the request set is asserted identical across algorithms in code.

### B.2 Statistical significance (Mann-Whitney U + Holm + Cliff's delta)
### Methods
Per-seed metric values (one independent observation per seed) from each results file were compared for every unordered algorithm pair using a **two-sided Mann-Whitney U test (Wilcoxon rank-sum)** (`scipy.stats.mannwhitneyu`, `alternative="two-sided"`).  Because multiple pairwise tests are performed per file, raw p-values were corrected with the **Holm-Bonferroni step-down procedure applied within each input file across all of that file's tests** (both the raw p-value and the adjusted `p_holm` are reported).  Effect size is **Cliff's delta**, computed directly as `(#(a>b) - #(a<b)) / (n_a * n_b)`, with the standard **Romano et al. thresholds**: |delta| < 0.147 negligible, < 0.33 small, < 0.474 medium, otherwise large.  Comparisons are called significant at `p_holm < 0.05`.

### algo_comparison

Total pairwise tests: 12.

### Significant results (p_holm < 0.05)

| group | metric | algorithm_a | algorithm_b | n_a | n_b | U | p_value | p_holm | cliff_delta | effect_label | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| - | makespan_s | dragonfly | fcfs | 50 | 50 | 0 | 2.628e-23 | 3.154e-22 | -1.000 | large | - |
| - | makespan_s | dragonfly | round_robin | 50 | 50 | 300 | 5.07e-14 | 1.521e-13 | -0.760 | large | - |
| - | makespan_s | fcfs | round_robin | 50 | 50 | 900 | 0.005576 | 0.01115 | -0.280 | small | - |
| - | mean_flow_s | dragonfly | fcfs | 50 | 50 | 0 | 2.628e-23 | 3.154e-22 | -1.000 | large | - |
| - | mean_flow_s | dragonfly | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | mean_flow_s | fcfs | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | p95_flow_s | dragonfly | fcfs | 50 | 50 | 0 | 2.628e-23 | 3.154e-22 | -1.000 | large | - |
| - | p95_flow_s | dragonfly | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | p95_flow_s | fcfs | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | imbalance_cv | dragonfly | round_robin | 50 | 50 | 2500 | 2.251e-20 | 2.026e-19 | 1.000 | large | - |
| - | imbalance_cv | fcfs | round_robin | 50 | 50 | 2500 | 2.251e-20 | 2.026e-19 | 1.000 | large | - |

### Full results

| group | metric | algorithm_a | algorithm_b | n_a | n_b | U | p_value | p_holm | cliff_delta | effect_label | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| - | makespan_s | dragonfly | fcfs | 50 | 50 | 0 | 2.628e-23 | 3.154e-22 | -1.000 | large | - |
| - | makespan_s | dragonfly | round_robin | 50 | 50 | 300 | 5.07e-14 | 1.521e-13 | -0.760 | large | - |
| - | makespan_s | fcfs | round_robin | 50 | 50 | 900 | 0.005576 | 0.01115 | -0.280 | small | - |
| - | mean_flow_s | dragonfly | fcfs | 50 | 50 | 0 | 2.628e-23 | 3.154e-22 | -1.000 | large | - |
| - | mean_flow_s | dragonfly | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | mean_flow_s | fcfs | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | p95_flow_s | dragonfly | fcfs | 50 | 50 | 0 | 2.628e-23 | 3.154e-22 | -1.000 | large | - |
| - | p95_flow_s | dragonfly | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | p95_flow_s | fcfs | round_robin | 50 | 50 | 0 | 2.251e-20 | 2.026e-19 | -1.000 | large | - |
| - | imbalance_cv | dragonfly | fcfs | 50 | 50 | - | 1 | 1 | 0.000 | degenerate-identical | all values identical across both groups (zero variance, deterministic scheduler under this trace; significance undecidable) |
| - | imbalance_cv | dragonfly | round_robin | 50 | 50 | 2500 | 2.251e-20 | 2.026e-19 | 1.000 | large | - |
| - | imbalance_cv | fcfs | round_robin | 50 | 50 | 2500 | 2.251e-20 | 2.026e-19 | 1.000 | large | - |

### fleet_runs

Tested within each `fleet_size` group.

Total pairwise tests: 156.

### Significant results (p_holm < 0.05)

| group | metric | algorithm_a | algorithm_b | n_a | n_b | U | p_value | p_holm | cliff_delta | effect_label | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 5 | makespan_s | dragonfly | round_robin | 30 | 30 | 90 | 1.774e-09 | 3.549e-09 | -0.800 | large | - |
| 5 | makespan_s | fcfs | round_robin | 30 | 30 | 810 | 1.774e-09 | 3.549e-09 | 0.800 | large | - |
| 5 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 5 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.05e-12 | 1.092e-10 | -1.000 | large | - |
| 5 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 5 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 5 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.05e-12 | 1.092e-10 | -1.000 | large | - |
| 5 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 5 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 5 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 5 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 10 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 10 | makespan_s | dragonfly | round_robin | 30 | 30 | 45 | 5.622e-11 | 3.935e-10 | -0.900 | large | - |
| 10 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 5.622e-11 | 3.935e-10 | 0.900 | large | - |
| 10 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 10 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.173e-12 | 1.149e-10 | -1.000 | large | - |
| 10 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 10 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 10 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.173e-12 | 1.149e-10 | -1.000 | large | - |
| 10 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 10 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 10 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 10 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 15 | makespan_s | dragonfly | round_robin | 30 | 30 | 30 | 1.64e-11 | 1.968e-10 | -0.933 | large | - |
| 15 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 1.64e-11 | 1.968e-10 | 0.933 | large | - |
| 15 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 15 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.197e-12 | 1.149e-10 | -1.000 | large | - |
| 15 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 15 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.197e-12 | 1.149e-10 | -1.000 | large | - |
| 15 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 15 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 20 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.538e-12 | 1.149e-10 | -0.967 | large | - |
| 20 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 1.646e-11 | 1.968e-10 | 0.933 | large | - |
| 20 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 20 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.199e-12 | 1.149e-10 | -1.000 | large | - |
| 20 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.199e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 20 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.202e-12 | 1.149e-10 | -1.000 | large | - |
| 20 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.202e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 20 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.202e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.202e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 25 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.545e-12 | 1.149e-10 | -0.967 | large | - |
| 25 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 1.648e-11 | 1.968e-10 | 0.933 | large | - |
| 25 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 25 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.203e-12 | 1.149e-10 | -1.000 | large | - |
| 25 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.203e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 25 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.207e-12 | 1.149e-10 | -1.000 | large | - |
| 25 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.207e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 25 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.204e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.204e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 30 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.566e-12 | 1.149e-10 | -0.967 | large | - |
| 30 | makespan_s | fcfs | round_robin | 30 | 30 | 885 | 4.566e-12 | 1.149e-10 | 0.967 | large | - |
| 30 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 30 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 30 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.211e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 30 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 30 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 30 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 40 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.574e-12 | 1.149e-10 | -0.967 | large | - |
| 40 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 1.19e-10 | 5.948e-10 | 0.900 | large | - |
| 40 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 40 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 40 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 40 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 40 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 40 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 50 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.574e-12 | 1.149e-10 | -0.967 | large | - |
| 50 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 1.19e-10 | 5.948e-10 | 0.900 | large | - |
| 50 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 50 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 50 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 50 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 50 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 50 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 60 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.57e-12 | 1.149e-10 | -0.967 | large | - |
| 60 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 3.357e-11 | 2.686e-10 | 0.933 | large | - |
| 60 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 60 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 60 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 60 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 60 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 60 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 70 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.21e-12 | 1.149e-10 | -1.000 | large | - |
| 70 | makespan_s | fcfs | round_robin | 30 | 30 | 900 | 1.21e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 70 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 70 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 70 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 70 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 70 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 80 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 80 | makespan_s | fcfs | round_robin | 30 | 30 | 885 | 4.57e-12 | 1.149e-10 | 0.967 | large | - |
| 80 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 80 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 80 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.211e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 80 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 80 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.211e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 80 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 90 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 90 | makespan_s | fcfs | round_robin | 30 | 30 | 885 | 4.57e-12 | 1.149e-10 | 0.967 | large | - |
| 90 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 90 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 90 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 90 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 90 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 90 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 100 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 100 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 1.19e-10 | 5.948e-10 | 0.900 | large | - |
| 100 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 100 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.21e-12 | 1.149e-10 | -1.000 | large | - |
| 100 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.21e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 100 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 100 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 100 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |

### Full results

| group | metric | algorithm_a | algorithm_b | n_a | n_b | U | p_value | p_holm | cliff_delta | effect_label | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 5 | makespan_s | dragonfly | round_robin | 30 | 30 | 90 | 1.774e-09 | 3.549e-09 | -0.800 | large | - |
| 5 | makespan_s | fcfs | round_robin | 30 | 30 | 810 | 1.774e-09 | 3.549e-09 | 0.800 | large | - |
| 5 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 5 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.05e-12 | 1.092e-10 | -1.000 | large | - |
| 5 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 5 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 5 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.05e-12 | 1.092e-10 | -1.000 | large | - |
| 5 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 5 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 5 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 5 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.05e-12 | 1.092e-10 | 1.000 | large | - |
| 10 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 10 | makespan_s | dragonfly | round_robin | 30 | 30 | 45 | 5.622e-11 | 3.935e-10 | -0.900 | large | - |
| 10 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 5.622e-11 | 3.935e-10 | 0.900 | large | - |
| 10 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 10 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.173e-12 | 1.149e-10 | -1.000 | large | - |
| 10 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 10 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 10 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.173e-12 | 1.149e-10 | -1.000 | large | - |
| 10 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 10 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 10 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 10 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.173e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 15 | makespan_s | dragonfly | round_robin | 30 | 30 | 30 | 1.64e-11 | 1.968e-10 | -0.933 | large | - |
| 15 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 1.64e-11 | 1.968e-10 | 0.933 | large | - |
| 15 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 15 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.197e-12 | 1.149e-10 | -1.000 | large | - |
| 15 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 15 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.197e-12 | 1.149e-10 | -1.000 | large | - |
| 15 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 15 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 15 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.197e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 20 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.538e-12 | 1.149e-10 | -0.967 | large | - |
| 20 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 1.646e-11 | 1.968e-10 | 0.933 | large | - |
| 20 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 20 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.199e-12 | 1.149e-10 | -1.000 | large | - |
| 20 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.199e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 20 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.202e-12 | 1.149e-10 | -1.000 | large | - |
| 20 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.202e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 20 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.202e-12 | 1.149e-10 | 1.000 | large | - |
| 20 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.202e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 25 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.545e-12 | 1.149e-10 | -0.967 | large | - |
| 25 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 1.648e-11 | 1.968e-10 | 0.933 | large | - |
| 25 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 25 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.203e-12 | 1.149e-10 | -1.000 | large | - |
| 25 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.203e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 25 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.207e-12 | 1.149e-10 | -1.000 | large | - |
| 25 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.207e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 25 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.204e-12 | 1.149e-10 | 1.000 | large | - |
| 25 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.204e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 30 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.566e-12 | 1.149e-10 | -0.967 | large | - |
| 30 | makespan_s | fcfs | round_robin | 30 | 30 | 885 | 4.566e-12 | 1.149e-10 | 0.967 | large | - |
| 30 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 30 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 30 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.211e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 30 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 30 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 30 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 30 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 40 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.574e-12 | 1.149e-10 | -0.967 | large | - |
| 40 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 1.19e-10 | 5.948e-10 | 0.900 | large | - |
| 40 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 40 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 40 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 40 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 40 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 40 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 40 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 50 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.574e-12 | 1.149e-10 | -0.967 | large | - |
| 50 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 1.19e-10 | 5.948e-10 | 0.900 | large | - |
| 50 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 50 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 50 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 50 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 50 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 50 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 50 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 60 | makespan_s | dragonfly | round_robin | 30 | 30 | 15 | 4.57e-12 | 1.149e-10 | -0.967 | large | - |
| 60 | makespan_s | fcfs | round_robin | 30 | 30 | 870 | 3.357e-11 | 2.686e-10 | 0.933 | large | - |
| 60 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 60 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 60 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 60 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 60 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 60 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 60 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 70 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.21e-12 | 1.149e-10 | -1.000 | large | - |
| 70 | makespan_s | fcfs | round_robin | 30 | 30 | 900 | 1.21e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 70 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 70 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 70 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 70 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 70 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 70 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 80 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 80 | makespan_s | fcfs | round_robin | 30 | 30 | 885 | 4.57e-12 | 1.149e-10 | 0.967 | large | - |
| 80 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 80 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 80 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.211e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 80 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 80 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.211e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 80 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 80 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 90 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 90 | makespan_s | fcfs | round_robin | 30 | 30 | 885 | 4.57e-12 | 1.149e-10 | 0.967 | large | - |
| 90 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 90 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 90 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 90 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 90 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 90 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 90 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | makespan_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 100 | makespan_s | dragonfly | round_robin | 30 | 30 | 0 | 1.211e-12 | 1.149e-10 | -1.000 | large | - |
| 100 | makespan_s | fcfs | round_robin | 30 | 30 | 855 | 1.19e-10 | 5.948e-10 | 0.900 | large | - |
| 100 | mean_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 100 | mean_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.21e-12 | 1.149e-10 | -1.000 | large | - |
| 100 | mean_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.21e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | p95_flow_s | dragonfly | fcfs | 30 | 30 | 0 | 1.685e-14 | 2.629e-12 | -1.000 | large | - |
| 100 | p95_flow_s | dragonfly | round_robin | 30 | 30 | 0 | 1.212e-12 | 1.149e-10 | -1.000 | large | - |
| 100 | p95_flow_s | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | imbalance_cv | dragonfly | fcfs | 30 | 30 | 900 | 1.685e-14 | 2.629e-12 | 1.000 | large | - |
| 100 | imbalance_cv | dragonfly | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |
| 100 | imbalance_cv | fcfs | round_robin | 30 | 30 | 900 | 1.212e-12 | 1.149e-10 | 1.000 | large | - |

### load_sweep

Tested within each `compression_factor` group.

Total pairwise tests: 48.

### Significant results (p_holm < 0.05)

| group | metric | algorithm_a | algorithm_b | n_a | n_b | U | p_value | p_holm | cliff_delta | effect_label | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 1 | makespan_s | dragonfly | round_robin | 20 | 20 | 50 | 3.039e-06 | 3.039e-05 | -0.750 | large | - |
| 1 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 1 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 1 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | p95_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 1 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 2 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 2 | makespan_s | dragonfly | round_robin | 20 | 20 | 50 | 3.039e-06 | 3.039e-05 | -0.750 | large | - |
| 2 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 2 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 2 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | p95_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | imbalance_cv | dragonfly | fcfs | 20 | 20 | 400 | 4.683e-10 | 2.248e-08 | 1.000 | large | - |
| 2 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 2 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 4 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 4 | makespan_s | dragonfly | round_robin | 20 | 20 | 100 | 0.0003842 | 0.002689 | -0.500 | large | - |
| 4 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 4 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 5.452e-09 | 1.799e-07 | -1.000 | large | - |
| 4 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 5.452e-09 | 1.799e-07 | -1.000 | large | - |
| 4 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 4 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 4 | p95_flow_s | fcfs | round_robin | 20 | 20 | 50 | 3.039e-06 | 3.039e-05 | -0.750 | large | - |
| 4 | imbalance_cv | dragonfly | fcfs | 20 | 20 | 400 | 4.683e-10 | 2.248e-08 | 1.000 | large | - |
| 4 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 4 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 8 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 8 | makespan_s | fcfs | round_robin | 20 | 20 | 350 | 1.427e-06 | 1.569e-05 | 0.750 | large | - |
| 8 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 8 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 8 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 8 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 8 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 8 | p95_flow_s | fcfs | round_robin | 20 | 20 | 100 | 0.00386 | 0.02316 | -0.500 | large | - |
| 8 | imbalance_cv | dragonfly | fcfs | 20 | 20 | 400 | 4.683e-10 | 2.248e-08 | 1.000 | large | - |
| 8 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 8 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |

### Full results

| group | metric | algorithm_a | algorithm_b | n_a | n_b | U | p_value | p_holm | cliff_delta | effect_label | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 1 | makespan_s | dragonfly | round_robin | 20 | 20 | 50 | 3.039e-06 | 3.039e-05 | -0.750 | large | - |
| 1 | makespan_s | fcfs | round_robin | 20 | 20 | 150 | 0.1222 | 0.4888 | -0.250 | small | - |
| 1 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 1 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 1 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | p95_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 1 | imbalance_cv | dragonfly | fcfs | 20 | 20 | - | 1 | 1 | 0.000 | degenerate-identical | all values identical across both groups (zero variance, deterministic scheduler under this trace; significance undecidable) |
| 1 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 1 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 2 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 2 | makespan_s | dragonfly | round_robin | 20 | 20 | 50 | 3.039e-06 | 3.039e-05 | -0.750 | large | - |
| 2 | makespan_s | fcfs | round_robin | 20 | 20 | 150 | 0.1222 | 0.4888 | -0.250 | small | - |
| 2 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 2 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 2 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | p95_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 2 | imbalance_cv | dragonfly | fcfs | 20 | 20 | 400 | 4.683e-10 | 2.248e-08 | 1.000 | large | - |
| 2 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 2 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 4 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 4 | makespan_s | dragonfly | round_robin | 20 | 20 | 100 | 0.0003842 | 0.002689 | -0.500 | large | - |
| 4 | makespan_s | fcfs | round_robin | 20 | 20 | 200 | 1 | 1 | 0.000 | negligible | - |
| 4 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 4 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 5.452e-09 | 1.799e-07 | -1.000 | large | - |
| 4 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 5.452e-09 | 1.799e-07 | -1.000 | large | - |
| 4 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 4 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 4 | p95_flow_s | fcfs | round_robin | 20 | 20 | 50 | 3.039e-06 | 3.039e-05 | -0.750 | large | - |
| 4 | imbalance_cv | dragonfly | fcfs | 20 | 20 | 400 | 4.683e-10 | 2.248e-08 | 1.000 | large | - |
| 4 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 4 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 8 | makespan_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 8 | makespan_s | dragonfly | round_robin | 20 | 20 | 150 | 0.01945 | 0.09725 | -0.250 | small | - |
| 8 | makespan_s | fcfs | round_robin | 20 | 20 | 350 | 1.427e-06 | 1.569e-05 | 0.750 | large | - |
| 8 | mean_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 8 | mean_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 8 | mean_flow_s | fcfs | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 8 | p95_flow_s | dragonfly | fcfs | 20 | 20 | 0 | 4.683e-10 | 2.248e-08 | -1.000 | large | - |
| 8 | p95_flow_s | dragonfly | round_robin | 20 | 20 | 0 | 6.905e-09 | 2.141e-07 | -1.000 | large | - |
| 8 | p95_flow_s | fcfs | round_robin | 20 | 20 | 100 | 0.00386 | 0.02316 | -0.500 | large | - |
| 8 | imbalance_cv | dragonfly | fcfs | 20 | 20 | 400 | 4.683e-10 | 2.248e-08 | 1.000 | large | - |
| 8 | imbalance_cv | dragonfly | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |
| 8 | imbalance_cv | fcfs | round_robin | 20 | 20 | 400 | 6.905e-09 | 2.141e-07 | 1.000 | large | - |

### Notes

- Algorithms that are fully deterministic under this trace produce zero-variance per-seed samples (e.g. identical values across every seed).  For such pairs the Mann-Whitney significance is *undecidable*: a degenerate-identical comparison is reported with p = 1.0, p_holm = 1.0, cliff_delta = 0.0 and effect_label `degenerate-identical` rather than a fabricated p-value.  These cases must be discussed explicitly in the paper -- a deterministic scheduler's zero variance is a property of the trace, not evidence of no effect, and non-degenerate comparisons against a degenerate algorithm inherit heavily tied ranks.
- Groups with fewer than three seeds are flagged `low-n` in the note column; such p-values are indicative only.
- Input files absent or skipped: `baselines_comparison.csv`.

### B.3 GA / PSO baselines (matched compute budget to DA)
_baselines_comparison.md not found - run run_comparison.py --algorithms dragonfly,fcfs,round_robin,ga,pso_

### B.4 Offered-load sweep (time-compressed trace variants)
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

### Winner per factor (min mean mean_flow_s)

| factor | winner | mean_flow_s | runner-up | runner-up mean_flow_s |
|---|---|---|---|---|
| 1 | **dragonfly** | 2.349 | fcfs | 2.584 |
| 2 | **dragonfly** | 2.360 | fcfs | 2.597 |
| 4 | **dragonfly** | 2.389 | fcfs | 2.637 |
| 8 | **dragonfly** | 2.445 | fcfs | 2.706 |

Lower is better for all metrics. Service demands stay real in every scenario; only arrival timing is compressed.

Raw per-run rows: `load_sweep.csv` (regenerate with load_sweep.py).

## C. 50-server fleet (heterogeneous, same real trace)

- Trace: `research/data/trace/tasks.csv` arrival window `[2026-10-20T12:00:00Z .. +inf]` (kept {'burst': 150})
- Requests per run: **74** (identical for every algorithm and fleet size, asserted in code)
- Algorithms: dragonfly, fcfs, round_robin · Fleet sizes: [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100] · Seeds: 30 · SLA: 30.0s
- Speed envelope: uniform [0.5, 1.5] per node (fixed fleet, seed 20261020)
- Node profiles: 9 real measured KYRO service profiles from live 1 Hz samplers (backend, frontend, kyro-chroma, kyro-kafka, kyro-n8n, kyro-postgres, router, tunnel, worker)

> **Measured vs virtual:** task arrivals, service demands, and all
> `*_measured` columns come from the running application. The 50 nodes are
> a controlled heterogeneous fleet (trace-driven simulation), the standard
> setup for scheduling research on one machine - not 50 physical servers.

### Per-fleet-size comparison (mean over seeds)

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

### Winners per fleet size

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

### Files
- `fleet_server_data.csv` - per-server rows (size x algorithm x node): tasks, busy, utilization, flow, SLA, measured profile
- `fleet_runs.csv` - raw per-seed runs
- `fleet_nodes.csv` - fleet definition

Regenerate: `python -m research.experiments.fleet50 --tasks research/data/trace/tasks.csv`

Per-server rows: `results/fleet_server_data.csv` (450 rows = fleet sizes x algorithms x nodes).

## D. Track B live scale-out (real worker containers)

_trackb_live.csv not found - run `python research/scripts/trackb_experiment.py --phase A` first_

## E. Data inventory

| file | bytes | rows |
|---|---|---|
| `data/live/app_requests_20261020.csv` | 2,715 | 36 rows |
| `data/live/burst_manifest.jsonl` | 63,510 | 286 rows |
| `data/live/commit_files_20261020.jsonl` | 122,418 | 469 rows |
| `data/live/db_counts_20261020.csv` | 41,240 | 977 rows |
| `data/live/db_events_20261020.jsonl` | 12,526,635 | 371 rows |
| `data/live/host_20261020.csv` | 24,742,515 | 134,177 rows |
| `data/live/http_latency_20261020.csv` | 702,800 | 11,950 rows |
| `data/live/queues_20261020.csv` | 1,533,087 | 28,361 rows |
| `data/live/resources_20261020.csv` | 1,528,275 | 21,669 rows |
| `results/algo_comparison.csv` | 9,761 | 151 rows |
| `results/algo_comparison.md` | 1,131 | 21 lines |
| `results/fleet50_summary.md` | 5,430 | 81 lines |
| `results/fleet_nodes.csv` | 3,882 | 101 rows |
| `results/fleet_runs.csv` | 64,990 | 1,171 rows |
| `results/fleet_server_data.csv` | 135,483 | 1,786 rows |
| `results/flow_samples.csv` | 562,524 | 11,101 rows |
| `results/load_sweep.csv` | 13,023 | 241 rows |
| `results/load_sweep.md` | 2,153 | 36 lines |
| `results/load_sweep_smoke.csv` | 2,035 | 37 rows |
| `results/load_sweep_smoke.md` | 2,149 | 36 lines |
| `results/server_metrics.csv` | 19,674 | 180 rows |
| `results/server_metrics.md` | 4,778 | 77 lines |
| `results/stats_report.md` | 47,181 | 482 lines |
| `results/stats_significance.csv` | 24,751 | 217 rows |

## F. Data notes & honesty

- Load generator: **283 real pushes** succeeded (camp01: 105, campaign2: 133, live-traffic: 40, validate-e2e: 5) through the genuine webhook -> n8n -> Kafka -> worker path.
- Window: live samplers record continuously; tables state their own window in `server_metrics.csv`.
- `chroma` heartbeat answers HTTP 410 (flagged by server_report) - exclude or annotate in threat-to-validity.
- Direct-backend OAuth start returns 503 `public origin not configured` by design (github_oauth.py:110 allow-listed origins); the router/frontend entrypoints return the real 302 to GitHub (4/4).
- `repo_detail` 404 is access gating: the fresh load-test session does not own the probed repository (uniform 404 by design, not a failure).
- Unprocessed events (backlog drains) are kept in the trace with empty `service_seconds` and excluded from scheduling runs - never imputed.
- Service-time tail (max ~1292 s) is a real deferred backfill, not an error.
- All values are measured or computed from measured rows; nothing is fabricated. Generated-markdown rounding is cosmetic only.

Regenerate: `python -m research.analysis.master_report` (after `server_report.py` for the freshest telemetry).
