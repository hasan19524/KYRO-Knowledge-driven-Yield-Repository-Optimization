# KYRO Research Trace Schema (binding contract)

All collectors write under `research/data/`. All timestamps UTC ISO-8601 with `Z`.
Every file is append-only, one header row, UTF-8 no BOM. `ts` = collection time.

## 1. `live/resources_YYYYMMDD.csv` — 1 Hz container resource samples
`ts,container,cpu_pct,mem_used_bytes,mem_limit_bytes,net_io_bytes,block_io_bytes,pids`

## 2. `live/db_events_YYYYMMDD.jsonl` — every NEW ingestion_events row, full fidelity
One JSON object per line:
`{"ts": <poll time>, "id", "event_id", "topic", "partition", "offset",
  "repository_github_id", "kind", "status", "pg_status", "index_status",
  "attempts", "error", "created_at", "updated_at", "processed_at",
  "payload": {...}}`

## 3. `live/db_counts_YYYYMMDD.csv` — 10 s table-size snapshots
`ts,commits,commit_files,files,ingestion_events`

## 4. `live/commit_files_YYYYMMDD.jsonl` — per-new-commit aggregates (real work size)
`{"ts", "commit_row_id", "repo_github_id", "sha", "committed_at",
  "n_files", "additions", "deletions", "changes", "patch_bytes"}`

## 5. `live/queues_YYYYMMDD.csv` — 3 s Kafka lag per partition (both topics)
`ts,topic,partition,end_offset,committed_offset,lag`

## 6. `trace/tasks.csv` — THE schedulable workload trace (derived, stable)
Task unit = one ingestion event (one Kafka message = what a scheduler assigns).
`task_id,arrival_ts,kind,repo_github_id,repo_name,commits_in_event,files_touched,
additions,deletions,changes,patch_bytes,service_seconds,attempts,status,
pg_status,index_status,processed_ts`
`service_seconds = processed_at - created_at` (NULL if never processed → keep row,
flag `status`); `commits/files/...` aggregated from the event payload commits and
commit_files join. Sorted by `arrival_ts`.

## 7. `trace/resources.csv` — derived from #1 (same columns, single file)

## 8. `trace/queries.csv` — real /api/query latencies (if load run)
`ts,repo_github_id,latency_seconds,top_k,hits,mode`

## Rules
- Collectors NEVER write to KYRO's DB. Read-only SELECTs only.
- Missing/partial rows are kept and flagged, never dropped or imputed.
- Generated-commit bursts are labeled: events from repo `KYRO-ingestion-test`
  (github_id 1395956448) pushed during a burst window carry
  `experiment_label` in the derived tasks.csv (`burst` vs `organic` vs `backfill`).
