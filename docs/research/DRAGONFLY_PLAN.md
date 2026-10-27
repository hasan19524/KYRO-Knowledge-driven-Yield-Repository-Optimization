# DRAGONFLY RESEARCH PLAN — DA-Based Load Balancing & Intelligent Resource Allocation for KYRO's Real Git-Ingestion Pipeline

**Status:** PLAN ONLY — nothing implemented yet. Review this, approve, then Phase 0 starts.
**Date:** 2026-10-20
**Constraints this plan is built around:** 1 laptop, 16 GB RAM, 0 money, free tools only, one server (no cloud, no VPS). Every data point must be REAL, produced by the real KYRO pipeline.

---

## 1. The idea in plain language

**What we already have.** KYRO is a real, running ingestion pipeline:
GitHub push → webhook (HMAC) → n8n → Kafka → Python worker → Postgres + Chroma.
Every commit that flows through it creates **real rows with real timestamps**: the
event, its processing duration, the files it touched, the chunks it embedded, and
real CPU/RAM usage by every container while it happened.

**What the Dragonfly Algorithm (DA) is.** A swarm-intelligence optimizer (Mirjalili,
2016; 3,300+ citations) inspired by dragonfly swarms. Each "dragonfly" is a
candidate solution; the swarm moves through the solution space using five weighted
behaviors — separation, alignment, cohesion, attraction to **food** (the best solution
found so far) and distraction from a **predator** (the worst region). That balance of
"copy the neighborhood / chase the best / avoid the worst" is what makes it explore
and converge.

**What we will build.** A DA-based **scheduler + resource allocator** that sits in
front of KYRO's ingestion workers and answers two coupled questions, in real time:

1. **Load balancing:** which worker container should process each incoming ingestion
   task (commit/push event)?
2. **Intelligent resource allocation:** how much CPU/RAM budget should each worker
   hold right now, within the fixed 16 GB envelope?

**Why it is research-grade and not a toy.** The scheduler is trained and judged on a
**real workload trace** — real arrival times, real burstiness, real task sizes, real
processing durations taken from KYRO's own database — and then validated live on a
real (small) container cluster on the same laptop. No synthetic task generators, no
CloudSim, no fabricated numbers.

**What you personally do:** read this document, say "approved" (or ask questions).
Later: review each phase's output. Phase 1 will push ~600 real commits to your
`KYRO-ingestion-test` repo from this laptop — that is intended, that repo exists for
exactly this. Nothing else is required from you; no GitHub-App setting changes, no
money, no cloud accounts.

---

## 2. The research gap ("what can we fill with the most real data")

Literature scan (2016–2026) on *Dragonfly Algorithm + cloud scheduling / resource
allocation*:

| What others do | Why it is a gap |
|---|---|
| DA scheduling evaluated on **synthetic workloads** (CloudSim, uniform random task generators) — the dominant pattern | Synthetic arrivals are smooth and Poisson-like. **Real git/CI ingestion is bursty and self-similar** (push storms). Nobody has shown how DA behaves on a genuinely bursty, real trace. |
| Public mega-traces (Google Borg, Azure) reused for scheduling studies | Traces are huge, anonymized datacenter workloads — **not reproducible at laptop scale** and not representative of event-driven repo-ingestion pipelines. A student cannot rerun the experiments. |
| "Cloud" experiments assume elastic, near-infinite nodes | Real constrained environments (single host, hard 16 GB cap, heterogeneous containers) are understudied — this is where small teams and edge setups actually live. |
| Scheduling OR allocation studied separately | **Joint** task assignment + CPU/RAM budget reallocation under a hard memory ceiling — the actual problem in a fixed-size cluster — rarely studied together. |
| No public real dataset for this workload class | **We will produce one:** a real, timestamped trace of a GitHub→Kafka→worker ingestion pipeline at ≥10k tasks, released with the paper (dataset card + reproducibility package). |

**Our fill, stated as a paper thesis:**
*"DA-based joint load balancing and resource allocation, evaluated on a real bursty
git-ingestion trace and validated on a real single-host container cluster, against
strong baselines (including GA and PSO), fully reproducible on a 16 GB laptop."*

**On "GAs":** Genetic Algorithms are the classic competitor in this literature. GA
and PSO will be implemented as **first-class baselines** (same budget, same seeds,
same metrics), so the paper can honestly say where DA wins, ties, or loses versus
GAs and PSO. If DA does not beat them, that negative result is reported too — that
is what makes the paper credible.

---

## 3. What "100% real data" means here — precise definitions

Nothing is ever hand-written into a database. Every row is produced by the running
pipeline.

| Category | Real? | Explanation |
|---|---|---|
| Commits, file contents, diffs, authors, timestamps | ✅ real | Genuine `git` objects committed and pushed from this laptop to GitHub; fetched back by the real worker via the real GitHub API. |
| Webhook → n8n → Kafka → worker flow | ✅ real | The exact production path, HMAC and all. |
| Task durations, inter-arrival times, error/retry behavior | ✅ measured | Read from `ingestion_events.created_at/processed_at` etc. Never invented. |
| CPU/RAM per container during load | ✅ measured | `docker stats` sampled at 1 Hz during the load bursts. |
| Commit *content* (the file bodies inside the ~600 generated commits) | ⚠️ generated, but real | Programmatically produced realistic code/text files. They are real git objects flowing through the real pipeline with real durations — but they are not organic human commits. Stated as a threat to validity in the paper; the 77 organic upstream commits are kept as a labeled organic subset for comparison. |
| The 10–50 "node" cluster in experiments | ⚠️ simulated | **Track A** experiments run in a trace-driven discrete-event simulator. **Track B** re-runs the winning configurations on 2–4 REAL containers to prove the simulator's conclusions hold on real hardware. This two-track design is standard in scheduling research and is the only honest way to study 50 nodes on a 16 GB laptop. |

**"Real but scattered" (your fallback request) is already the design:**
Real push storms cannot be a perfectly even stream — and they *should not* be.
Git workloads arrive in scattered bursts. We deliberately run several real bursts
spread over 1–2 days (morning/evening, different sizes). The trace's burstiness is a
**feature**, not an artifact: it is the exact property that makes DA interesting to
study versus round-robin. If any single collection window fails, bursts collected in
other windows are still 100% real and still compose into one valid trace.

---

## 4. Measured baseline (numbers taken today, not estimates)

**Database (live, today):**
| Table | Rows |
|---|---|
| `commits` | 79 |
| `commit_files` | 1,334 |
| `files` | 702 |
| `ingestion_events` | 88 |
| `repositories` | 11 |

**Upstream organic history available (all 6 repos, GitHub API today):**
`acumen_teams_personal` 49 · `leetcode_grind` 15 · `KYRO-ingestion-test` 9 ·
`Nexus` 2 · `baba_birthday` 1 · `mothers-day` 1 → **77 commits total.**

⇒ Organic history alone can never reach 10k rows (~1.3k commit_files max).
**Conclusion: the load-generation bursts in Phase 1 are mandatory, not optional.**
A full resync of all 6 repos still happens first — those 77 organic commits are
real data we must not leave on the table.

**RAM snapshot (today):** Docker VM capped at 5.8 GB (n8n 0.5 GB, Kafka 1.1 GB,
Postgres 0.04 GB, Chroma 0.02 GB), system 15.7 GB total with 2.8 GB free while the
whole stack runs. Feasible plan, with pause rules in §9.

---

## 5. How the real 10k+ row workload trace is produced (Phase 1 design)

**Row math (target: ≥10,000 workload rows):**
- Resync all 6 repos → +77 organic commits, +~1.3k commit_files (real).
- Generate **~600 real commits** on `KYRO-ingestion-test` (repo already installed in
  the App — zero settings changes), each touching ~10–20 files:
  - 600 `commits` rows
  - ~600 `ingestion_events` rows with **real** created→processed durations
  - **~9,000 `commit_files` rows** (size/additions/deletions = real diff stats)
  - ~10k+ new `files`/chunk vectors in Postgres + Chroma
- **Push storms, scattered:** ~20–30 pushes per burst, 3–5 bursts over 1–2 days,
  different times of day → real inter-arrival times and real burstiness.
- **Resource trace:** `docker stats` at 1 Hz for the duration of every burst →
  thousands of real CPU/RAM samples per container.
- **Query-side trace (optional but planned):** 100–300 real `/api/query` calls
  (retrieval-stage timing; LLM stage kept off or minimal to avoid quota burn) →
  real end-to-end latency samples for SLA analysis.

**Export:** one trace file (`trace.jsonl` / CSV) where each row is
`(arrival_ts, task_kind, files_touched, bytes_changed, service_seconds, worker,
cpu_before, mem_before, ...)`. Everything else in the paper is computed from this
file. The file itself ships with the paper.

**Safety rails:** GitHub API budget (5,000 req/h installation token) respected —
bursts spaced, backoff on 429; disk impact < 100 MB; no `docker compose down -v`
anywhere; no secrets printed; DB schema untouched (no migration needed — existing
tables already hold everything).

---

## 6. The scheduler itself (system design)

**Decision variables (search space DA explores):**
1. Task→worker assignment matrix `A` (which of the `N` workers processes each task).
2. Resource vector `R` (CPU shares + memory limit per worker), hard-constrained by
   `Σ R ≤ 16 GB − reserved(Kafka+Postgres+Chroma+n8n)`.

**Objective (fitness) — all terms computed from real trace data:**
```
fitness = w1·makespan
        + w2·mean_flow_time          (queue wait + processing, per task)
        + w3·load_imbalance          (variance of worker utilization)
        + w4·sla_violations          (tasks slower than a real-derived threshold)
        + w5·resource_waste          (allocated-but-idle CPU/mem)
        subject to: Σ memory(R) ≤ budget
```
Weights are exposed and swept in experiments (sensitivity analysis is a paper table).

**DA adaptation to discrete assignment:** standard permutation/mapping encoding —
dragonfly position vector is decoded into an assignment matrix by ranking
(task-priority per worker), which keeps DA's continuous dynamics while making the
output a valid discrete schedule. Convergence is logged every iteration for the
paper's convergence plots.

**Where it runs:**
- **Track A (scale):** discrete-event simulator in Python (numpy, no heavy deps)
  replaying the real trace on virtual clusters of 10–50 heterogeneous nodes.
  30 seeds per configuration — statistically defensible.
- **Track B (reality check):** the DA controller as a small Python process that
  assigns real Kafka consumption to 2–4 real Docker worker containers with
  heterogeneous CPU/mem limits, processing real push bursts. Proves the simulator's
  conclusions on real hardware with real durations.

**Why not Kubernetes/kind:** k8s would test *kube-scheduler*, not DA; adds ~1 GB+
image + control-plane RAM we do not have; and contradicts the "one server" rule.
Plain Docker containers as worker nodes + our own dispatcher is the honest,
research-correct choice here — the scheduler under study must be *ours*.

---

## 7. Baselines (the fair fight)

| Baseline | Why included |
|---|---|
| Round-Robin | The dumb classic every reviewer expects |
| Random | Lower bound sanity check |
| Least-Connections / shortest-queue | The strong simple heuristic — often beats fancy algorithms; must be included or the paper is not credible |
| SJF / EDF (offline, oracle-aided) | Upper-bound references using real trace knowledge |
| **GA (Genetic Algorithm)** | The "GAs" competitor from the literature |
| **PSO (Particle Swarm)** | The other standard swarm competitor (a DF+PSO hybrid exists in the literature — we compare against plain PSO and note the hybrid) |

All baselines get identical time budgets, identical seeds, identical metrics.

---

## 8. Phases (what gets done, in order, with acceptance criteria)

| Phase | What | Duration | Acceptance criteria |
|---|---|---|---|
| **0 — Baseline & harness** | Freeze metric definitions; RAM budget table; simulator skeleton; trace schema; precise RAM profiling of the running stack | ~0.5 day | Metrics doc + skeleton code reviewed; no behavior changes to KYRO |
| **1 — Real data harvest** | Full resync of 6 repos; 3–5 scattered real push bursts (~600 commits) on `KYRO-ingestion-test`; `docker stats` 1 Hz sampling; optional query-load trace; export `trace` file | 1–1.5 days (wall-clock: bursts spread over 1–2 days) | ≥10,000 real rows; trace file replays cleanly; organic vs generated commits labeled |
| **2 — Simulator + baselines** | Trace-driven discrete-event simulator; implement RR/Random/LQ/SJF/EDF/GA/PSO; run 30 seeds × configurations; baseline results table | 1–1.5 days | Baseline table reproducible from one command; sanity checks pass (RR≈Random, SJF≤RR on makespan) |
| **3 — DA implementation + tuning** | DA scheduler/allocator; convergence logging; parameter sweep (population, iterations, behavior weights); sensitivity analysis | 1–2 days | DA runs end-to-end on trace; no constraint violations; convergence curves produced |
| **4 — DA vs baselines, then live validation** | Full experiment matrix on simulator; then live run: 2–4 real containers, DA vs best baseline on real push bursts | ~1 day | All paper tables/figures produced; live run confirms (or honestly contradicts) simulator ranking |
| **5 — Analytics & paper package** | Statistics (Wilcoxon signed-rank + effect sizes across 30 seeds), figures (CDFs, heatmaps, Gantt, convergence), dataset card, reproducibility README, results section draft | 1–2 days | One-command reproduction of every figure from the released trace; paper-ready assets |

Total ≈ **6–8 working days.** Each phase ends with a report to you; nothing merges
silently; KYRO's existing behavior is untouched unless a phase explicitly says so.

---

## 9. 16 GB RAM budget (the "one server" rule, made numeric)

| Component | Budget | Notes |
|---|---|---|
| Docker VM (existing: n8n, Kafka, Postgres, Chroma) | 5.8 GB cap (already set) | Measured ~1.7 GB used idle |
| Worker containers for Track B (2–4) | ≤ 2.5 GB | Heterogeneous limits *are* the experiment |
| DA controller + simulator (numpy) | ≤ 0.5 GB | |
| OS + browser + background | ~2 GB | |
| **Pause rules** | Frontend dev server paused during Phase 4 live runs (saves ~0.5–1 GB); browser tabs closed | |
| **Never** | kind/k8s, second Docker VM, any paid/cloud resource | |

If free RAM drops below ~1.5 GB during a run, the harness auto-pauses the run
(checkpointed, resumable) instead of thrashing — enforced, not hoped for.

---

## 10. Risks & fallbacks

| Risk | Fallback |
|---|---|
| GitHub API rate limits during bursts (5k req/h) | Space bursts; existing backoff/deferral path in worker; reduce commit size |
| Bursts come out less bursty than hoped | Burstiness is measured, not assumed — if the trace is smoother, that becomes a reported finding and the simulator can additionally replay the trace under controlled burst-inflation (clearly labeled as transformed, never as real) |
| DA converges worse than shortest-queue | Report it honestly; the comparison methodology is still publishable (negative results are science) |
| LLM quota burn from query load | Query trace = retrieval stage only by default |
| Disk growth | < 100 MB total; monitored |
| Laptop busy / other work needed | Every phase checkpointed; runs pause and resume |

---

## 11. Hard rules (unchanged from our working agreement)

1. Never `docker compose down -v`; never delete DB data.
2. Never fabricate a data point; generated-but-real is labeled as such, always.
3. No secrets in logs, code, commits, or chat.
4. Repo stays uncommitted; minimal diffs; explain before acting.
5. KYRO's product behavior (sign-in, repo connect, ingestion, queries) is not broken
   or rewritten for the research track — the research observes and schedules it,
   nothing more.
