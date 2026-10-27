# KYRO Real-Time Server & Pipeline Metrics

- Window covered: 2026-10-02T22:19:11.189206Z .. 2026-10-20T14:31:09.082000Z (UTC)
- Generated: 2026-10-20T14:31:10.312442Z by `research/analysis/server_report.py`
- Source: `research/data/live` (live samplers, read-only aggregation)
- Master dataset: `results/server_metrics.csv` (179 rows)

## Container resources (docker stats, 1 Hz)

| server | cpu_pct_mean | cpu_pct_p50 | cpu_pct_p95 | cpu_pct_max | mem_used_bytes_mean | mem_used_bytes_max | mem_pct_of_limit_mean | mem_pct_of_limit_max | net_io_bytes_total_delta | block_io_bytes_total_delta | pids_mean | pids_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kyro-chroma | 0.898 | 0 | 4.32 | 25.48 | 52.76 MiB | 73.86 MiB | 0.8902 | 1.246 | 0 B | 0 B | 10.86 | 20 |
| kyro-kafka | 32.48 | 4.64 | 192.5 | 238.6 | 1.17 GiB | 1.28 GiB | 20.29 | 22.08 | 0 B | 0 B | 118.4 | 140 |
| kyro-n8n | 2.455 | 0.27 | 16.99 | 64.55 | 490.98 MiB | 519.50 MiB | 8.284 | 8.765 | 0 B | 0 B | 20.09 | 28 |
| kyro-postgres | 1.028 | 0.27 | 4.57 | 18.1 | 54.45 MiB | 62.38 MiB | 0.9186 | 1.052 | 0 B | 0 B | 9.766 | 16 |

## Host processes (host sampler, 1 Hz)

| server | cpu_pct_mean | cpu_pct_p95 | cpu_pct_max | rss_bytes_mean | rss_bytes_max |
| --- | --- | --- | --- | --- | --- |
| backend | 0.1883 | 1.5 | 24.1 | 42.27 MiB | 136.55 MiB |
| frontend | 1.538 | 14.5 | 60.3 | 105.79 MiB | 323.31 MiB |
| other | 1.565 | 0 | 99.6 | 15.59 MiB | 93.75 MiB |
| router | 0.07427 | 0 | 5.2 | 49.40 MiB | 51.89 MiB |
| sampler | 12.15 | 88.7 | 101.7 | 11.72 MiB | 31.76 MiB |
| tunnel | 0.07942 | 0 | 7.1 | 42.67 MiB | 44.37 MiB |
| worker | 6.689 | 3.6 | 739.3 | 66.52 MiB | 452.31 MiB |

## Service latency probes (HTTP / TCP)

| server | total_ms_mean | total_ms_p50 | total_ms_p95 | total_ms_max | ttfb_ms_mean | ttfb_ms_p95 | error_rate | availability | connect_ms_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| backend | 22.68 | 23.01 | 36.55 | 576.4 | 11.8 | 18.79 | 0 | 1 |  |
| chroma | 11.42 | 14.11 | 24.98 | 30.71 | 2.363 | 4.376 | 0 | 0 |  |
| frontend | 109.2 | 94.76 | 168.4 | 576.1 | 99.8 | 156.9 | 0 | 1 |  |
| kafka | 7.25 | 0.87 | 21.96 | 28.81 |  |  | 0 | 1 | 7.142 |
| n8n | 14.04 | 15.2 | 26.99 | 44.18 | 3.083 | 5.507 | 0 | 1 |  |
| postgres | 9.15 | 11.95 | 22.86 | 30.27 |  |  | 0 | 1 | 9.026 |
| router | 113.5 | 98.48 | 171.2 | 498.9 | 102.2 | 159.0 | 0 | 1 |  |

## Kafka queue backlog (per topic)

| server | lag_mean | lag_p95 | lag_max | backlog_area | throughput |
| --- | --- | --- | --- | --- | --- |
| kyro.github.backfill | 0.2 | 1 | 1 | 6,056.5 | 0 |
| kyro.github.push | 0.02601 | 0 | 3 | 777.5 | 0.02447 |

## Ingestion pipeline (overall)

| server | events_total | events_processed | service_seconds_mean | service_seconds_p50 | service_seconds_p95 | service_seconds_max | events_per_minute_peak | events_per_minute_mean | commits_total | commits_delta | commit_files_total | commit_files_delta | files_total | files_delta | ingestion_events_total | ingestion_events_delta | commit_work_commits | commit_work_files | commit_work_additions | commit_work_deletions | commit_work_changes | commit_work_patch_bytes | burst_pushes_total | burst_pushes_ok | burst_pushes_camp01 | burst_pushes_live_traffic | burst_pushes_campaign2 | burst_pushes_validate_e2e |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 254 | 166 | 27.57 | 1.679 | 40.44 | 1,292.1 | 17 | 0.00998 | 302 | 223 | 2,236 | 902 | 1,582 | 880 | 254 | 166 | 302 | 2,236 | 203,372 | 50,748 | 254,118 | 8,574,273 | 170 | 167 | 105 | 40 | 17 | 6 |

## Event arrival burstiness (inter-arrival times)

| server | inter_arrival_mean | inter_arrival_cv | inter_arrival_p95 | inter_arrival_max |
| --- | --- | --- | --- | --- |
| overall | 6,036.0 | 8.751 | 561.6 | 592,097.3 |

## Data notes

File presence at generation time:

- `resources_*.csv`: present (1 file(s))
- `host_*.csv`: present (1 file(s))
- `http_latency_*.csv`: present (1 file(s))
- `queues_*.csv`: present (1 file(s))
- `db_counts_*.csv`: present (1 file(s))
- `db_events_*.jsonl`: present (1 file(s))
- `commit_files_*.jsonl`: present (1 file(s))
- `burst_manifest.jsonl`: present (1 file(s))

Anomalies / processing notes:

- host_process: 283 row(s) with unrecognized cmd_hint -> role 'other'
- latency: chroma returned non-200/1 status on 1223/1223 probe(s) (codes: 410)
- pipeline: earliest created_at is 17.6 day(s) before first observation (backfill events) - created_at-based windows, events_per_minute_mean and inter-arrival stats include that skew
