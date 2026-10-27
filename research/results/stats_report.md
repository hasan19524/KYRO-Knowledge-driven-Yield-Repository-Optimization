# Statistical Significance Report (KYRO scheduler comparison)

## Methods
Per-seed metric values (one independent observation per seed) from each results file were compared for every unordered algorithm pair using a **two-sided Mann-Whitney U test (Wilcoxon rank-sum)** (`scipy.stats.mannwhitneyu`, `alternative="two-sided"`).  Because multiple pairwise tests are performed per file, raw p-values were corrected with the **Holm-Bonferroni step-down procedure applied within each input file across all of that file's tests** (both the raw p-value and the adjusted `p_holm` are reported).  Effect size is **Cliff's delta**, computed directly as `(#(a>b) - #(a<b)) / (n_a * n_b)`, with the standard **Romano et al. thresholds**: |delta| < 0.147 negligible, < 0.33 small, < 0.474 medium, otherwise large.  Comparisons are called significant at `p_holm < 0.05`.

## algo_comparison

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

## fleet_runs

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

## load_sweep

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

## Notes

- Algorithms that are fully deterministic under this trace produce zero-variance per-seed samples (e.g. identical values across every seed).  For such pairs the Mann-Whitney significance is *undecidable*: a degenerate-identical comparison is reported with p = 1.0, p_holm = 1.0, cliff_delta = 0.0 and effect_label `degenerate-identical` rather than a fabricated p-value.  These cases must be discussed explicitly in the paper -- a deterministic scheduler's zero variance is a property of the trace, not evidence of no effect, and non-degenerate comparisons against a degenerate algorithm inherit heavily tied ranks.
- Groups with fewer than three seeds are flagged `low-n` in the note column; such p-values are indicative only.
- Input files absent or skipped: `baselines_comparison.csv`.
