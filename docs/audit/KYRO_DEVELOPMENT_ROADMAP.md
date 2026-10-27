# KYRO — Development Gap Analysis & Completion Roadmap

**Date:** 2026-10-13
**Companion to:** `KYRO_SYSTEM_AUDIT.md`, `KYRO_E2E_VERIFICATION.md`

Priorities: **P0** blocker · **P1** required before declaring the development phase complete · **P2** important engineering work · **P3** optional.

**No P0 findings exist.** The application starts, authenticates securely (invalid bearer is terminal), isolates users, retrieves with grounded references, and renders through a hardened proxy.

---

## 1. CONFIRMED REMAINING WORK

### P1-1 — Live GitHub ingestion is not verified end to end
- **Subsystem:** Ingestion / Sync
- **Description:** The GitHub → n8n → Kafka → worker → PG → Chroma chain has never been exercised with a real signed GitHub delivery in this environment. `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` are empty.
- **Evidence:** `.env`/`backend/.env` show both empty; no real delivery logged. Code + 160-suite cover everything up to the network boundary.
- **Impact:** The headline ingestion promise is unproven live. Cannot claim the development phase is fully complete until demonstrated or explicitly scoped out.
- **Required action:** With real GitHub App credentials on a **test** repository, send one legitimate signed push, confirm: n8n 200 → Kafka message → worker PROCESSED → PG rows → Chroma docs → query returns references. Record the transcript.
- **Dependencies:** GitHub App install on a disposable repo; `KYRO_WEBHOOK_SECRET` matching.
- **Acceptance criteria:** One full live ingestion captured; identifiers consistent across PG/Chroma.
- **Effort:** 0.5–1 day (environment-dependent). **Blocks milestone:** yes (or formally scoped out).

### P1-2 — n8n compare-API call is unauthenticated (breaks private repos & branch create/delete)
- **Subsystem:** Ingestion / n8n
- **Description:** The `HTTP Request` node calls `api.github.com/repos/…/compare/…` with **no auth header**. Private repos → 404/403; branch create/delete pushes (all-zero before/after) → permanently invalid URL. The node has no `onError`, so the execution fails **before** Kafka publish and GitHub redelivers indefinitely.
- **Evidence:** `kyro-github-webhook.json` (HTTP Request node has only `url`, no auth/headers).
- **Impact:** Live ingestion silently does not work for private repos or branch-creation/deletion pushes.
- **Required action:** Authenticate the compare call with the GitHub App installation token (reuse existing `app.github.auth`), or add `onError` handling that publishes an event without `changes` for branch create/delete / non-push events. Also add an event-type filter (`x-github-event == push`) so non-push events are not transformed.
- **Effort:** 1–2 days. **Blocks milestone:** yes for private-repo support; otherwise P2.

### P2-1 — Worker test flake (harness double-poll race)
- **Subsystem:** Tests
- **Description:** `WorkerHarness.start()` background thread + `drain()` main thread both poll one Kafka consumer, racing offset-commit assertions. `test_failed_partition_does_not_block_other_repos` flakes under load.
- **Evidence:** See E2E report §4 (captured `assert 1 == 2` at `tests/test_worker_kafka.py:279`; harness at `tests/conftest.py:228-276`).
- **Required action:** Make `drain()` the sole poller (or add a consumer mutex). Do not raise timeouts or weaken assertions. Prove with ≥5 repeated runs.
- **Effort:** 0.5 day. **Blocks milestone:** no (test-reliability only).

### P2-2 — Deleted code is never removed from the Chroma index
- **Subsystem:** Retrieval / Ingestion
- **Description:** Deletions are persisted (`is_deleted=true`, `current_content=NULL`) and indexed with `status=deleted`, but `ChromaIndexer` has no delete call and query-time ranking has no status filter → deleted/removed code remains retrievable forever and can surface in answers.
- **Evidence:** `indexer.py` (only `upsert`/`reset`); `retrieval/ranking.py` dedups on `(path,status,document)` with no status exclusion.
- **Required action:** Decide policy — either exclude `status=deleted` (and superseded historical docs) at query time, or delete Chroma docs when a file is removed/renamed. Prefer a query-time filter + a periodic PG→Chroma reconcile to keep Chroma rebuildable-from-PG.
- **Effort:** 1–2 days. **Blocks milestone:** no (quality/accuracy risk).

### P2-3 — `SYNC_FAILED` repo not restored to READY after successful redelivery
- **Subsystem:** Ingestion / Sync
- **Description:** If all retries fail (e.g. transient Chroma outage), the repo flips to `SYNC_FAILED` and the partition pauses. A later worker restart redelivers and can repair Chroma, but the repo status is not restored to READY (only `SyncManager._try_finalize`, which requires `SYNCING`, sets READY) → query keeps returning 409 until a manual resync.
- **Evidence:** `consumer.py:177-191`, `processor.py:189-201`, `manager.py:801-834`.
- **Required action:** On a successful redelivery of a FAILED event, transition the repo out of `SYNC_FAILED` (to `SYNCING` so the supervisor re-finalizes, or directly to `READY` when caught up).
- **Effort:** 1 day. **Blocks milestone:** no.

### P2-4 — Frontend auth/UX correctness defects (confirmed)
- **Subsystem:** Frontend
- **Description (each independently confirmed by code inspection):**
  1. Signup **"Confirm password" is never validated** — state collected but never compared; mismatched confirmation still submits and creates the account with the first password (`AuthForms.tsx`).
  2. **Terms-of-Service checkbox does not gate signup** — ignored by `handleSubmit`.
  3. **Backend outage on `/app` is misdiagnosed as "logged out"** — `fetchCurrentUser` returns `null` for *any* non-OK (incl. proxy 502) → redirect to `/login`.
  4. **No mid-session 401 handling** — repository 401 shown as "backend offline"; query 401 shown as a chat error; no redirect/re-auth.
  5. **No in-flight send guard** — composer not disabled while a query is loading → overlapping queries possible.
- **Required action:** Add client-side confirm-password comparison + terms gating (pure-function + unit test); distinguish network/502 from 401 in `fetchCurrentUser`; add a 401 interceptor/route guard; disable the composer during loading.
- **Effort:** 1–2 days. **Blocks milestone:** items 1–2 are trivial and should be fixed (they are "confirmed small validation bugs" — authorized under Phase 14); 3–5 are P2 UX.

### P2-5 — CI dependency & secret hygiene gaps
- **Subsystem:** CI / Dependencies
- **Description:** `pip-audit` runs in CI but there is **no `npm audit`** for the frontend and **no secret scanning**. Python deps use broad ranges with no lock/hash pinning (`pip install` in Dockerfile is non-reproducible). `npm audit --omit=dev` currently reports **2 high-severity** issues (next 16.0.0–16.3.7 → fix next@16.4.0; source-map-js → `npm audit fix`).
- **Required action:** Add an `npm audit` step (and act on the 2 highs), add a secret-scanning step (gitleaks/trufflehog), and pin Python deps with a lock/hash file.
- **Effort:** 1–2 days. **Blocks milestone:** no.

### P3 — Optional improvements (do not expand scope)
- Dead UI controls presented as live (Settings gear, user chevron menu, Paperclip attach, composer repo pill, "Auto" dropdown, ⌘K/⌘F badges with no keybinding, "Remember me" no-op). Either wire or remove/hide.
- Fake dashboard/status stats in `AuthBrandPanel` / `TechnicalVisualization` (presented as live telemetry).
- Dead code: `src/config/design.ts` (imported nowhere), `storage.ts getChat()`, unused `AuthFields` error machinery.
- Stale `kafka/README.md` claims (acks-before-produce, "worker does not exist yet", "My workflow 2").
- `kafka/verify/consume_verify.py` shares the live consumer group `kyro-ingestion-workers` — running it against the live cluster would steal partitions from the real worker. Mark clearly or change group.
- No onboarding UI affordance despite backend+proxy supporting `POST /api/repositories/onboard`.
- `KYRO_API_KEY` unset ⇒ `/docs` exposed (dev-open). Force `KYRO_DOCS=off` in any shared environment. **RESOLVED (tunnel readiness):** key set in `backend/.env` + `frontend/.env.local` (host mode authenticated); `KYRO_DOCS=auto` hides `/docs` whenever the key is set; tests force `KYRO_API_KEY=""` hermetically in `backend/tests/conftest.py`.
- Two-file env split (`backend/.env` vs root `.env`) is easy to misconfigure; document prominently. **RESOLVED:** ownership headers in both files + `.env.example`, `frontend/.env.local` added for the native proxy, `KYRO_API_KEY` and the LLM keys now exist in **both** modes, inline GitHub App PEM added to the root file for container mode, and `scripts/check_env_sync.py` fails on any cross-file drift.

---

## 2. DEFINING "DEVELOPMENT PHASE COMPLETE"

**A. Core product functionality** — ingest repos, index code, answer natural-language questions grounded in the repo, multi-user with isolation, web UI with login/signup. **Implemented.**

**B. Reliability & correctness** — idempotent ingestion, consistent PG/Chroma, correct ranking/references. **Implemented** (P2-2/P2-3 are accuracy/recovery refinements, not correctness breaks).

**C. Security & access control** — terminal invalid-bearer, PBKDF2, hash-only sessions, ownership enforced, hardened proxy, loopback infra, HMAC webhook. **Implemented and verified.**

**D. Installation & deployment** — two compose stacks, automatic additive migrations, loopback ports. **Implemented** (minor `--env-file` doc gap).

**E. Testing & verification** — 160 backend + 12 frontend tests + live E2E across auth/retrieval/proxy. **Implemented** (one flaky worker test; live GitHub leg unverified).

**F. Performance** — not benchmarked; no demonstrated bottleneck. **N/A for a dev milestone.**

**G. Documentation** — README accurate on ports/commands/counts; minor gaps. **Implemented.**

**H. Optional future features** — onboarding UI, deleted-code cleanup UI, etc. **Out of scope.**

### Objective acceptance criteria for the development milestone
1. Backend suite green (160/160) and frontend gates green (lint/test/build) — **MET.**
2. Live auth + isolation + retrieval + proxy E2E green — **MET.**
3. Invalid bearer terminal with no fallback — **MET (verified live).**
4. Live GitHub ingestion demonstrated **or** formally scoped out as a known limitation — **OPEN (P1-1).**
5. Confirmed P1/P2 defects either fixed or accepted with documented rationale — **PARTIAL (P1-2, P2-1…P2-5 open).**

---

## 3. THREE DIFFERENT STANDARDS (do not conflate)

### (1) Current development milestone — **essentially COMPLETE, conditional**
Conditional on: closing P1-1 (demonstrate or scope out) and P1-2 (private-repo/branch ingestion), plus fixing the two trivial frontend validation bugs (P2-4 items 1–2). Everything else is P2/P3 that need not block a local dev completion.

### (2) Controlled demonstration readiness — **NEAR**
For a reliable demo you additionally need: real indexed data for the repo you will show (via one real ingestion or a seeded fixture), a `KYRO_API_KEY`-set config so auth is on, and the P2-4 UX items so the signup/query flows don't hit the confirm-password/backend-outage rough edges. The retrieval + auth + proxy flows themselves are demo-ready today (proven live).

### (3) Production readiness — **FAR (separate effort)**
Requires, beyond the above: resolve/mitigate the Chroma CVE (or isolate network), lock+pin all dependencies, secret scanning, `KYRO_DOCS=off`, real secret management, horizontal-scale review of the in-process rate limiter, PG→Chroma reconcile job, deleted-code index cleanup, session-expiry UX, observability/alerting, and a production GitHub App + webhook with TLS. These are explicitly **outside** the current development scope.

---

## 4. ORDERED COMPLETION CHECKLIST

- [ ] P1-1: Run one real signed GitHub ingestion on a test repo (or record it as out-of-scope).
- [ ] P1-2: Authenticate the n8n compare call + add event-type filter + branch-create/delete handling.
- [ ] P2-4.1: Validate signup "confirm password" (pure function + unit test).
- [ ] P2-4.2: Gate signup on the terms checkbox.
- [ ] P2-1: Fix `WorkerHarness` double-poll; prove with ≥5 repeated runs.
- [ ] P2-2: Exclude/ delete deleted-code docs from retrieval; keep Chroma rebuildable.
- [ ] P2-3: Restore repo status after successful redelivery of a FAILED event.
- [ ] P2-4.3–5: Distinguish 502 from 401; add mid-session 401 handling; guard in-flight sends.
- [ ] P2-5: Add `npm audit` + secret scanning to CI; pin Python deps; act on the 2 npm highs.
- [ ] P3: Remove/wire dead UI; delete dead modules; fix stale `kafka/README.md`; change `consume_verify.py` group; force docs off when a key is set.

---

## 5. FINAL RECOMMENDATION

1. **Is KYRO currently working?** **Yes.** It starts, authenticates, isolates users, retrieves grounded answers with references, and renders through a hardened proxy — all verified live.
2. **Which parts are verified?** Auth (incl. the critical invalid-bearer-terminal property), user isolation, retrieval end-to-end through real Chroma+PG+Gemini, the frontend proxy security boundary, the full backend+frontend test suites, and the n8n HMAC (runtime-verified). Ingestion is verified up to the GitHub network boundary.
3. **Is the core development milestone complete?** **Essentially yes, conditional** on demonstrating/scoping the live GitHub ingestion (P1-1), fixing the private-repo/branch ingestion gap (P1-2), and the two trivial frontend validation fixes.
4. **Top five remaining tasks:** P1-1 (live ingestion), P1-2 (n8n compare auth), P2-4.1/2 (frontend validation), P2-1 (worker flake), P2-2 (deleted-code retention).
5. **What should be done next?** Obtain GitHub App credentials and run one real ingestion (closes P1-1 and exercises the whole chain for real); in parallel, land the two one-line frontend validation fixes and the n8n compare-auth change.
6. **Explicitly out of current scope:** production hardening (dependency pinning at prod grade, secret management, observability, TLS, Chroma CVE patch availability), onboarding UI, and any new product features.

---

## 6. MILESTONE DEFECT RESOLUTION (this pass)

Original findings above are preserved unchanged. This section records what was
fixed, tested, and what remains open, in the required categories. Every test
count below was actually executed against the real stack (PG 5433 / Chroma 8100
/ Kafka 9092, all loopback-bound).

### VERIFIED_FIXED

**P2-1 — Kafka test-harness race (two root causes)**
- *Files changed:* `backend/tests/conftest.py` (`WorkerHarness`), `infra/docker-compose.yml` (Kafka `advertised.listeners`).
- *Fix:* (1) `WorkerHarness` now serializes `poll_once` on a `_poll_lock` held for the whole `drain()`, with a shared `_handled_total` counter — only one thread polls a consumer at a time, so synchronous offset commits land before `committed()` reads. (2) The residual flake was actually a second cause: the Kafka host listener was advertised as `localhost:9092`, which on Windows resolves IPv6-first to `::1` and hits this machine's loopback bug. Changed to `HOST://127.0.0.1:9092` (same pattern as every other host port in that file); data volume preserved (no `down -v`).
- *Tests:* `tests/test_worker_kafka.py` run 5× consecutively — **5/5, 5/5, 5/5, 5/5, 5/5 passed** (≈30–32 s per run, down from 56–117 s with flakes). Full suite below.
- *Verification:* VERIFIED. *Limitations:* none; production worker code untouched.

**P2-2 — Deleted code contaminating current-code retrieval**
- *Files changed:* `backend/app/retrieval/ranking.py` (`rank_hits(exclude_file_ids=…)`), `backend/app/api/repositories.py` (query handler passes the repo's deleted `file_id`s).
- *Fix:* Query-time exclusion using PostgreSQL `files.is_deleted` as the source of truth. A path has one stable `files` row across commits, so excluding its `file_id` removes both the `status=deleted` marker and every historical change of that path. Exclusion happens *before* the top-K cap so deleted hits can't crowd current code out. Chroma is untouched (stays rebuildable); PG history preserved; repository isolation preserved (per-repo id set).
- *Tests:* 4 new unit tests in `tests/test_retrieval_components.py`; 1 new integration test `test_query_excludes_deleted_files_from_retrieval` in `tests/test_query_api.py` (real Chroma+PG; the deleted chunk is the *nearest* hit and is still dropped, its patch never reaches the prompt).
- *Verification:* VERIFIED (unit + integration). *Limitations:* historical diffs of a since-deleted file are excluded from *current-code* queries by design (the product has no as-of/historical query mode).

**P2-3 — Repository stuck in SYNC_FAILED after successful redelivery**
- *Files changed:* `backend/app/ingest/processor.py` (`_handle_payload`).
- *Fix:* When a non-duplicate event is re-processed for a repo in `SYNC_FAILED`, restore it to `SYNCING` (the existing state the supervisor resumes). Readiness is **not** set here — only `SyncManager._try_finalize` promotes `SYNCING→READY`, and only once backfill is genuinely complete (published==synced==head, zero deferred). `ACCESS_REVOKED` intentionally untouched (needs re-auth). A repo that fails again flips back via `mark_failure`.
- *Tests:* 2 new tests in `tests/test_processor_idempotency.py`: `test_successful_redelivery_recovers_sync_failed_repo` and `test_redelivery_does_not_mark_incomplete_repo_ready`.
- *Verification:* VERIFIED. *Limitations:* none; manual offset-commit, idempotency, and partition-failure semantics preserved.

**P2-4.1 — Signup confirm-password never compared**
**P2-4.2 — Terms checkbox did not gate submission**
- *Files changed:* `frontend/src/lib/signupValidation.ts` (new pure `validateSignupForm`), `frontend/src/components/auth/AuthForms.tsx` (wired into `SignupForm` submit + field/checkbox `error` props), `frontend/tests/signupValidation.test.ts` (new).
- *Fix:* Client-side gate before any network call: mismatched password/confirm → blocked with a field error; unchecked terms → blocked with a message. Backend password contract untouched; existing visual design/`AuthCheckbox`/`PasswordInput` reused. No legal claims added (label unchanged).
- *Tests:* 5 new `node --test` cases (match, mismatch, terms, both, empty-confirm-as-mismatch). Frontend suite now **17/17**; lint 0; build OK.
- *Verification:* VERIFIED_FIXED (logic). *Limitations:* not click-through-tested in a live browser (no browser-automation tool installed; installing one requires confirmation). The gating is pure client-side logic, covered by unit tests + lint + build.

**P2-4.3 — Backend outage misdiagnosed as logout**
**P2-4.4 — Mid-session auth expiry**
- *Files changed:* `frontend/src/lib/auth.ts` (`checkSession` discriminated union, `isSessionExpired`), `frontend/src/app/app/page.tsx` (3-state: authenticated / unauthenticated→login / error→retry UI), `frontend/src/components/app/repositorySection.tsx` (401→login redirect; 5xx/network→offline state), `frontend/src/components/app/AppShell.tsx` (`SessionExpiredError` on query 401 → logout + redirect).
- *Fix:* 401 is the only trigger for the login flow; 5xx/network show an outage/retry state instead of bouncing to login. Protected-request 401s clear client state and route through login (no loops). The httpOnly cookie model is preserved and the token is never exposed to JS.
- *Tests:* Live proxy E2E (below): `/backend/api/auth/me` with no cookie → **401 (not 502)**; bad bearer → **401**; register response carries **no `token`** (stripped into the httpOnly cookie); logout → 401. Backend suite (167) covers the server-side 401/403/404 gates.
- *Verification:* VERIFIED (server/proxy path + code). *Limitations:* the browser-side redirect/retry UI wasn't exercised in a live browser (no browser tool); verified by lint/build + code review.

**P2-4.5 — Duplicate in-flight queries**
- *Files changed:* `frontend/src/components/app/MainChat.tsx` (`inFlight` ref re-entry guard), `frontend/src/components/app/ChatComposer.tsx` (`busy` prop disables send + Enter while a query is in flight; recovers on success/failure via `finally`).
- *Fix:* Synchronous ref guard (state alone is async and can be raced) + composer disabled during flight; controls recover in `finally`.
- *Tests:* lint 0 / build OK / 17 tests. *Verification:* VERIFIED (code). *Limitations:* not click-through-tested live (no browser tool).

### MITIGATED_BUT_NOT_FULLY_FIXED

**P1-2 — n8n GitHub Compare API authentication**
- *Files changed:* `n8n/workflows/kyro-github-webhook.json` (Compare HTTP node `onError: continueRegularOutput`; JSON re-validated, 8 nodes intact).
- *What was fixed:* The Compare node no longer aborts the whole workflow on failure. A private-repo compare (404, unauthenticated), a branch create/delete (422, all-zeros base/head), or a transient error now continues; `Code in JavaScript1` already maps a missing/failed compare to `changes: []`, and the **backend worker self-enriches with its authenticated GitHub App installation-token client** (confirmed: `_attribute` builds attributions from the push body's commit `added/modified/removed` lists, and `apply_payload`→`resolver.resolve(patch=None,…)` fetches content via `client._headers`→`Bearer {installation_token}` — the same mechanism backfill uses). This removes the private-repo/branch ingestion break without touching Kafka topics, event identity, keys, or the worker contract.
- *What is NOT done (documented, not faked):* authenticating the Compare **inside n8n** — see BLOCKED_BY_ENVIRONMENT below. The event-type filter (push-only) still requires an n8n Switch/IF node (graph change) and was left untouched rather than applied untested to a production webhook.
- *Verification:* MITIGATED. Workflow JSON valid; the worker-fallback path is confirmed by code analysis and exercised by the existing processor tests (empty/`None` patch → resolver fetch). *Limitations:* **not integration-tested** — n8n is not in the test infra and GitHub App credentials are unavailable; private-repo ingestion is **not** claimed verified.

### BLOCKED_BY_ENVIRONMENT

**P1-1 — Live GitHub ingestion E2E** — `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` are empty in both `.env` files. A real signed delivery + backfill cannot be exercised. Unchanged from the prior audit; requires real credentials.

**P1-2 auth-in-n8n (the "exact missing requirement")** — n8n cannot safely mint GitHub App installation tokens: it has no native credential that auto-mints installation tokens from an App ID + private key (its GitHub credential is a static OAuth2/access token, which would expire hourly), and the Code node sandbox cannot reliably perform the RS256 JWT signing needed to exchange for one. Placing the App private key in n8n env to sign there is fragile and widens the secret surface. *Exact missing requirement:* either (a) an n8n credential type that mints GitHub App installation tokens, (b) a token-minting sidecar/endpoint the n8n HTTP node can call, or (c) moving compare enrichment into the authenticated backend worker (already the fallback). No credentials were invented; no real authenticated compare was performed.

**Live browser click-through (P2-4.1/2/3/4/5 UI)** — playwright/puppeteer are not installed and the browser-qa skill forbids installing them without confirmation. Client-side gating and session UI are covered by unit tests + lint + build + the live proxy E2E; a real click-through was not performed.

### STILL_OPEN

**ChromaDB CVEs (see §H of the system audit)** — 5 known vulns in the pinned `chromadb 1.5.9`, **no upstream fix available** (`fix_versions: []`). Not suppressible as "fixed"; carried as an explicit CI `--ignore-vuln` baseline. Exposure mitigated (loopback-only, single-tenant, `trust_remote_code` never used) but not remediated — blocked on an upstream release; a dependency decision.

**npm prod-dependency advisories** — 2 high in prod deps (`next@16.3.7` → fix needs `next@16.4.0`, outside the stated range; `source-map-js`). Not blindly upgraded (framework decision); not gated in CI (no `npm audit` step).

**Secret scanning in CI** — absent (only `pip-audit` is present). Gap noted; adding it is out of this pass's scope.

### Acceptance criteria mapping

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Compare auth addressed or dependency documented | MITIGATED + precisely documented (BLOCKED) |
| 2 | Branch create/delete handled without invalid compare | MITIGATED (compare failure no longer aborts; worker enriches) — not live-tested |
| 3 | Confirm-password validation | VERIFIED_FIXED |
| 4 | Terms acceptance gates signup | VERIFIED_FIXED |
| 5 | Deleted code excluded from current-code retrieval | VERIFIED_FIXED |
| 6 | Successful redelivery restores sync state | VERIFIED_FIXED |
| 7 | Kafka harness race removed | VERIFIED_FIXED |
| 8 | Kafka tests pass 5 repeated runs | VERIFIED (5/5 ×5) |
| 9 | Outage distinguished from 401 | VERIFIED (proxy live + code) |
| 10 | Mid-session expiry handled | VERIFIED (code + proxy) |
| 11 | Duplicate in-flight queries prevented | VERIFIED (code) |
| 12 | Auth + user isolation intact | VERIFIED (live + 167 tests) |
| 13 | Ingestion architecture intact | VERIFIED (contract preserved) |
| 14 | Retrieval + frontend designs intact | VERIFIED |
| 15 | Backend + frontend regression suites pass | VERIFIED (167 + 17, lint/build/ruff/pyright) |
| 16 | Security status reported honestly | VERIFIED (§H) |
| 17 | Documentation reflects actual state | VERIFIED (this section) |
| 18 | No existing data deleted/corrupted | VERIFIED (dev DB restored: 1 user/3 repos/0 sessions/7 events; no `down -v`) |

**Milestone verdict:** The development-completion defects that were safely fixable in this pass (P2-1, P2-2, P2-3, P2-4.1–5) are **VERIFIED_FIXED**. P1-2 is **MITIGATED** (private-repo/branch ingestion break removed via worker enrichment) with the n8n-auth requirement **precisely documented as BLOCKED**. **P1-1 (live GitHub ingestion) remains BLOCKED_BY_ENVIRONMENT** and is **not** claimed verified. Per the rules, the milestone is **not** declared fully complete while required acceptance criteria (live ingestion, n8n compare auth) remain unverified.

## 7. DEMO-PREP PASS - DEFECT RESOLUTION (this pass)

### RESOLVED

**P1-1 — Live GitHub ingestion E2E** — **RESOLVED.** Real GitHub App credentials were
supplied in `backend/.env` (App ID / Installation ID / PEM path; key-path auth proven by
minting an installation token and listing all 6 selected repos). A **real GitHub App
delivery** (real authored commit `5ad30d27cb9eb9a17db0271b0f0acd5712cc3a20`) was verified
end-to-end: GitHub -> Quick Tunnel -> n8n HMAC (fail-closed) -> Kafka -> worker -> PostgreSQL
(exact blob sha + content) -> Chroma. All six repos ingested to `READY`. Transcript in
`KYRO_E2E_VERIFICATION.md` §8.

**P2-2 (extended) — Deleted/binary chunks crowding the retrieval window** — **RESOLVED
(both halves).** (a) Query-time exclusion now also runs **inside the Chroma query**
(`$nin` on `file_id` for `is_deleted=true` files) so deleted chunks cannot occupy the
bounded overfetch window, in addition to the existing `rank_hits` filter. (b) A separate
persistence defect was found and fixed: **binary and empty files were wrongly tombstoned**
(`is_deleted=true`) because the resolver's `(content=None, source="fetch")` was treated as
deletion - live files were excluded from retrieval and their header-only chunks polluted
top-k. Fix: successful fetch with no decodable text keeps the file alive and indexes
nothing; real deletions unchanged. One-off data repair: 128 files un-tombstoned, 135 junk
chunks removed (1332 -> 1197). Regression-tested (4 new persistence tests); all six repos
now answer with references.

### ADDED (feature work requested for the demo)

**LLM provider fallback chain** — new `app/llm_chain.py`, wired behind the existing
`state.llm` seam. Order `opencode -> nvidia -> openrouter -> gemini` (env-configurable),
one bounded attempt per provider, failures fall through, all-fail = 502. The opencode
slot is key-gated + HTTP-only (zen free tier refuses external HTTP clients - verified -
so the slot is skipped without `OPENCODE_API_KEY`; the CLI-bridge workaround was
implemented then deliberately removed). NVIDIA/OpenRouter keys provisioned into
gitignored `backend/.env` (values never printed/logged). Live-verified: NVIDIA serves
every query (`llm_served name=nvidia`). 6 new chain-logic unit tests with fakes.

### REGRESSION
Backend `pytest -q`: **177 passed** (167 baseline + 10 new). Frontend untouched
(17/17 from prior pass). No production-readiness claims; see `docs/OPERATIONS.md` for the
honest demo-scope status.