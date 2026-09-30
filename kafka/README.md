# KYRO Kafka Infrastructure

Event pipeline:

```
GitHub -> GitHub Webhook -> n8n -> Kafka (kyro.github.push) -> Ingestion Workers -> PostgreSQL + ChromaDB
```

This directory contains the Kafka design, local/production configuration, and the
verification tooling. It does **not** change the pipeline architecture.

Contents:

| Path | Purpose |
|---|---|
| `local/docker-compose.yml` | Local 1-broker KRaft cluster (RF=1) |
| `local/create-topic.sh` | Create/normalize the local topic (5 partitions, 7-day retention) |
| `local/verify-partition-key.sh` | Prove key -> partition behavior (items 8/9) |
| `local/verify-consumer-group.sh` | Prove consumer-group partition distribution (items 10/11) |
| `production/broker.properties` | Production broker template (3 brokers, RF=3) with rationale |
| `production/create-topic.sh` | Production topic creation (RF=3, 5 partitions, 7-day retention) |
| `production/producer.properties` | Required producer durability settings |
| `production/consumer.properties` | Required consumer group / offset settings |
| `verify/consume_verify.py` | Reference ingestion-worker consumer: manual commit, idempotency by `event.id`, failure/retry (items 12/13/14) |
| `verify/requirements.txt` | Verification-only Python dependency |

---

## 1. Agreed architecture (unchanged)

| Decision | Value |
|---|---|
| Topic | `kyro.github.push` |
| Partitions | 5 |
| Partition key | `repository.github_id` (event field `repository.github_id`, GitHub repository ID) |
| Ordering | Strict per repository; different repositories in parallel |
| Failure | Failed event must not let later events of the same repository advance |
| Consumer group | `kyro-ingestion-workers` |
| Retention | 7 days (Kafka is a buffer/replay log, **not** the source of truth) |
| Delivery | At-least-once + idempotent processing keyed on `event.id` (`X-GitHub-Delivery`) |
| Production | 3 brokers, RF=3, `min.insync.replicas=2`, `unclean.leader.election.enable=false` |
| Local | 1 broker, RF=1 (RF=3 is invalid on a single broker and is never applied locally) |

Why 5 partitions: partition = unit of parallelism; 5 gives the initial architecture
room for concurrent repository processing. Keying by repository ID puts all pushes
of one repository on one partition, which is what makes strict per-repository
ordering possible at all (Kafka only guarantees order **within** a partition).

## 2. Local vs production

| | Local (`local/`) | Production (`production/`) |
|---|---|---|
| Brokers | 1 (KRaft combined, `node.id=1`) | 3 |
| Replication factor | 1 | 3 |
| `min.insync.replicas` | 1 | 2 |
| `unclean.leader.election.enable` | `false` (broker default) | `false` (pinned explicitly) |
| Partitions | 5 | 5 |
| Retention | 7 days (`retention.ms=604800000`) | 7 days |
| Offsets/transaction topic RF | 1 | 3 |
| Listeners | `HOST://:9092` -> `localhost:9092` (host tools) + `PLAINTEXT://:29092` -> `kyro-kafka:29092` (containers on `kyro-net`) | internal `:9092` per broker |

Local listeners exist because a single advertised address cannot serve both host
processes and containers (`localhost` means different things inside each
container). Production uses one internal listener between brokers/clients inside
the cluster network.

Local broker default retention is also set to `log.retention.ms=604800000` so any
future topic on the dev cluster follows the agreed 7-day rule.

## 3. Producer reliability

For producers we control (`production/producer.properties`):

- `acks=all` - a record counts as acknowledged only after **all in-sync
  replicas** persisted it. With `min.insync.replicas=2` the write fails (instead
  of being lost) when too few replicas are healthy. This is what makes "one
  broker failure must not lose accepted events" true end-to-end.
- `enable.idempotence=true` - broker-side dedup by `(producer.id, sequence)`, so
  retries cannot create duplicates or reorder records. It forces `acks=all`,
  retries=MAX and `max.in.flight<=5`, so no extra retry tuning is invented.
- If Kafka stays unavailable beyond the in-process retries (kafkajs retries
  transient connect/send failures for tens of seconds), the n8n execution fails
  and is visible/retryable in n8n. Recovery for that window is the n8n
  execution retry - **not** GitHub redelivery, because n8n replies to the
  GitHub webhook immediately (HTTP 200) before Kafka produce finishes. GitHub
  redelivery still covers the case where n8n itself is unreachable or returns
  a non-2xx. No extra outage database is introduced, per the agreed decision.

**n8n producer (current state):** the n8n Kafka node's "Acks" option maps to
`acks=1` (leader only); it cannot express `acks=all`, and it does not expose
idempotence. Local RF=1 makes leader-ack equivalent to full-ack (leader *is* the
only replica), so local durability is exact. In production (RF=3) this is a real
gap - see "Open items" below.

## 4. Consumer / offset strategy

`production/consumer.properties` + `verify/consume_verify.py`:

- `group.id=kyro-ingestion-workers`; Kafka distributes the 5 partitions among
  group members and never assigns one partition to two consumers at once.
- `enable.auto.commit=false`: commit **only after** the event is processed and
  persisted (at-least-once). A crash/failure before commit -> redelivery ->
  retry; auto-commit would commit on a timer regardless of outcome and skip
  failed events.
- `auto.offset.reset=earliest`: a brand-new group starts at the oldest retained
  event, never silently skipping history.
- Strict ordering: a worker processes its partitions serially. On failure it
  does not commit, so the failed event (and everything after it in that
  partition) is redelivered first - later pushes of the same repository wait.
- Expected side effect of at-least-once: duplicates after rebalance/crash are
  normal, hence idempotency (below). Exactly-once is not claimed.

## 5. Idempotency

- Key: `event.id` = `X-GitHub-Delivery` (already present in the normalized
  event produced by n8n; no schema change).
- Mechanism: consumer records the event as processed **in the same atomic step
  as the downstream write** (unique row on `event.id` in PostgreSQL; `INSERT ..
  ON CONFLICT DO NOTHING` = already-processed). Duplicates are detected and
  skipped; the offset still advances.
- `verify/consume_verify.py` demonstrates the same logic with a local seen-set
  file because the ingestion worker/Postgres does not exist yet.

## 6. n8n integration

The active workflow `My workflow 2` (id `mlEODTybeNYN2wzq`) built the final
delta event but had **no Kafka node** - nothing was published. Required for
Kafka integration, a `Kafka Publish` node was appended after
`Code in JavaScript1` (existing normalize/compare logic untouched):

- topic `kyro.github.push`
- message = the full normalized event JSON (`sendInputData`)
- key = `={{ String($json.repository.github_id) }}` (agreed partition key)
- option `acks` enabled (n8n maximum: leader acknowledgement)
- credential `Kafka local` (`kafkaLocalKyro01`): bootstrap `kyro-kafka:29092`,
  SSL off, no auth - contains no secret material.

n8n and Kafka share the user-defined Docker network `kyro-net` (the default
`bridge` network has no name resolution). n8n was restarted so the published
workflow and credential are live.

## 7. Verification results (all actually executed)

Run from repo root with Git Bash (`bash kafka/local/...`) or PowerShell.

| # | Check | Result |
|---|---|---|
| 1 | Container status | `kyro-kafka`, `apache/kafka:4.3.1`, Up, `0.0.0.0:9092->9092` |
| 2 | Kafka version | `4.3.1` |
| 3 | Topic list | `__consumer_offsets`, `kyro.github.push` |
| 4 | Topic description | 5 partitions, RF=1, every partition `Leader: 1, Replicas: 1, Isr: 1` |
| 5 | Retention config | topic `retention.ms=604800000` (dynamic) + broker `log.retention.ms=604800000`, `cleanup.policy=delete` |
| 6 | Exactly 5 partitions | `PartitionCount: 5` |
| 7 | RF compatible with 1 broker | 1 broker (`node.id=1`), `default.replication.factor=1`, `min.insync.replicas=1`, RF=1 <= broker count |
| 8 | Same key -> same partition | key `100` x3 -> all `Partition 3` (offsets 0,1,2 of that batch, in order) |
| 9 | Different keys -> different partitions | `100`->P3, `200`->P0, `300`->P1 |
| 10 | 2 consumers, one group | consumer A got P0,P1,P2; consumer B got P3,P4 |
| 11 | No partition assigned twice | overlap check: `OK: no partition is assigned to two consumers simultaneously` |
| 12 | Offsets committed per strategy | after processing: P0=1/1, P1=1/1, P3=4/4, LAG=0 (manual commits only) |
| 13 | Failed event retried, later events waited | fail on `retry-test-001`: `FAIL_EVENT ... offset NOT committed`, P3 stayed at committed=4 while log-end=6 (LAG=2 -> the next repo event did **not** advance); re-run processed offset 4 then 5 -> committed=6, LAG=0 |
| 14 | Duplicate detected by `event.id` | redelivered `retry-test-001` -> `SKIP_DUPLICATE ... offset=6`, offset still advanced (7/7, LAG=0) |
| E2E | GitHub webhook -> n8n -> Kafka | simulated push webhook (HTTP 200) produced the full event to `kyro.github.push`; message key = `repository.github_id` |

Cross-client partitioner consistency (bonus): key `100` -> P3 from both n8n
(KafkaJS) and the Java CLI producer; key `200` -> P0 from both. Same repository
ID lands on the same partition regardless of which client produced it.

## 8. Open items requiring manual action / decisions

1. **n8n producer cannot use `acks=all`.** The n8n Kafka node maps its acks
   option to `acks=1` only. In production (RF=3) a leader-only ack can lose the
   most recent acknowledged event if the leader dies before followers replicate.
   Compensations already in place: GitHub webhook redelivery + idempotent
   consumer. Options (decision needed): (a) accept this with redelivery as the
   safety net, (b) upgrade/replace the n8n node when it supports `acks=all`, or
   (c) put a thin producer in front of Kafka with `acks=all`. Nothing was
   silently changed.
2. **Webhook ack timing vs Kafka downtime.** n8n answers the GitHub webhook
   with 200 immediately, so a Kafka outage during produce surfaces only as a
   failed n8n execution (retryable there); GitHub will not redeliver in that
   scenario. GitHub reddelivery applies when n8n is down/unreachable. Decide
   whether that split is acceptable or whether the webhook should respond only
   after the Kafka node succeeds (which would enable GitHub redelivery but also
   expose GitHub's 10s webhook timeout to the GitHub Compare API call).
3. **Ingestion worker** does not exist yet; `verify/consume_verify.py` is the
   executable reference for the required commit/dedup behavior. When it is
   built, move the seen-set into PostgreSQL (`event.id` unique row) as
   described above.
4. Old local container (`apache/kafka:latest`, ad-hoc `docker run`, no volume)
   was replaced by the compose file; the previous topic had **0 messages**, so
   no data was lost. Topic data now lives in the named volume
   `local_kyro-kafka-data`.
5. `kafka/verify/kafka-verify-state.json` and `.venv/` are local runtime state
   and gitignored; delete them to reset verification state.

## 9. Quick commands

```bash
# recreate/normalize local topic
bash kafka/local/create-topic.sh

# key -> partition behavior
bash kafka/local/verify-partition-key.sh

# consumer group distribution (2 consumers)
bash kafka/local/verify-consumer-group.sh

# reference worker: process until idle, commit after each event
kafka/verify/.venv/Scripts/python.exe kafka/verify/consume_verify.py

# same, but fail one event (offset must NOT advance for it)
FAIL_ON=<event.id> kafka/verify/.venv/Scripts/python.exe kafka/verify/consume_verify.py
```

Production (3 brokers) settings are applied per broker from
`production/broker.properties` + `production/create-topic.sh`; they are never
applied to the local cluster.
