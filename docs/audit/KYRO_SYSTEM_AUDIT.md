# KYRO — Comprehensive System Audit

**Date:** 2026-10-13
**Auditor:** Independent verification pass (post-integration)
**Repository:** `D:\projects\professional\KYRO\KYRO-Knowledge-driven-Yield-Repository-Optimization`
**Git state:** branch `main`, HEAD `317c0b7` ("Milestone: security remediation …"), **44 uncommitted paths** (the entire three-way integration; preserved, not committed). No tracked file was modified by this audit.

> This is an engineering audit of the *actual* codebase, not a restatement of the integration report. Every "verified" claim below was re-confirmed by reading source or by running a live command during this audit. Where a subsystem could not be verified, the reason is stated explicitly.

---

## A. EXECUTIVE SUMMARY

**Overall status: WORKING, with a clearly-scoped verification gap in live GitHub ingestion.**

KYRO is a functioning monorepo application. The three-way integration (Hasan's ingestion + Maaz's retrieval + Lubna's frontend) is genuinely coherent: the components share one backend, one PostgreSQL, one ChromaDB, one auth model, and one frontend proxy. This audit re-ran the full backend suite (**160/160**), the frontend gates (lint 0, tests 12/12, build OK), and — most importantly — executed **live end-to-end tests against real running servers** covering authentication, user isolation, retrieval (through real Chroma + PostgreSQL + Gemini), and the browser-facing proxy. All E2E layers passed.

**What works (verified live):**
- Registration / login / logout / session validation, PBKDF2 password hashing, hash-only session storage.
- **Invalid bearer sessions are terminal (401) with NO fallback to dev-open/default-user** — the single most important auth property, proven live.
- Cross-user repository isolation (query + resync denied for non-owners; owner control reaches it).
- Retrieval: repository-scoped Chroma search → ranking → PostgreSQL enrichment → live Gemini → structured answer with references that map to indexed chunks.
- Browser proxy: HTTP-only cookie set, token stripped from body, cookie→Bearer forwarding, allowlist blocking admin/arbitrary paths, CSRF origin rejection.
- Ingestion pipeline code (Kafka consumer semantics, worker three-phase processing, idempotency, partition pause) — deterministic and correct in tests.
- n8n webhook HMAC verification — **runtime-verified** against native-crypto ground truth (14/15 vectors; the 1 "fail" is an empty body correctly failing closed).

**What is NOT verified:**
- **Live GitHub → n8n → Kafka ingestion with a real signed delivery.** Blocked by environment: `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` are empty in both `.env` files. The pipeline is code-correct and unit/e2e-tested with fakes, but the real GitHub leg is **NOT VERIFIED** (see Feature Matrix).

**Critical problems:** No P0 blockers. The application starts, authenticates, isolates users, retrieves, and renders. The most significant *functional* risks are (1) the n8n compare-API call is unauthenticated, which breaks live ingestion of private repositories and of branch create/delete pushes, and (2) an upstream ChromaDB CVE with no confirmed patched release (mitigated by loopback-only binding).

**Is the development milestone complete?** For a **local development / demonstration milestone — essentially yes**, conditional on: fixing a small set of confirmed P2 defects (frontend form validation, worker-test flake, deleted-code retention, private-repo ingestion) and recording the ingestion E2E limitation. It is **not** production-ready (see the Roadmap for the separate production bar).

**Main reasons for that conclusion:** the integrated system was exercised live across every tier that does not require real GitHub credentials, and every such check passed; the one unverified tier is gated by missing credentials, not by a discovered defect.

---

## B. SYSTEM INVENTORY

| Component | Responsibility | Key source | Depends on | Verified operation |
|---|---|---|---|---|
| **FastAPI backend** | REST API: auth, repositories, query; hosts sync supervisor | `backend/app/main.py`, `app/api/*` | PostgreSQL, ChromaDB, Gemini | Live (E2E + `/health`) |
| **Account auth** | Register/login/logout/me, sessions, PBKDF2 | `app/api/account.py`, `app/api/auth.py`, `app/security/passwords.py` | PostgreSQL `users`, `user_sessions` | Live (E2E) |
| **Repositories API** | List/onboard/resync/query, ownership enforcement | `app/api/repositories.py` | retrieval package, Chroma, PG, Gemini | Live (E2E) |
| **Retrieval/RAG** | Ranking, dedup, char budget, grounded prompt (ported from Maaz) | `app/retrieval/{ranking,prompt}.py` | ChromaIndexer, PG enrichment, Gemini | Live (E2E) |
| **Ingestion worker** | Kafka consume → PG tx → Chroma upsert → commit | `app/kafka/consumer.py`, `app/ingest/{processor,persistence,indexer}.py` | Kafka, PG, Chroma, GitHub (optional) | Tests (160 suite); live path gated by creds |
| **Sync/backfill** | GitHub App history walk, event production, READY finalize | `app/github/*`, `app/sync/manager.py` | GitHub App creds, Kafka, PG | Tests; live gated by creds |
| **n8n webhook** | GitHub receive → HMAC verify → transform → Kafka publish | `n8n/workflows/kyro-github-webhook.json` | KYRO_WEBHOOK_SECRET, Kafka | HMAC runtime-verified; full leg gated by creds |
| **Kafka** | Two topics (push/backfill), 5 partitions, keyed by repo id | `infra/docker-compose.yml`, `app/kafka/*` | broker | Tests (real broker via conftest) |
| **PostgreSQL** | Source of truth: repos, commits, files, events, users, sessions | `app/db/models.py`, alembic | — | Live |
| **ChromaDB** | Semantic index (rebuildable from PG) | `app/ingest/indexer.py` | — | Live (E2E) |
| **Frontend (Next.js 16)** | Lubna's UI + main's wiring; `/backend` proxy | `frontend/src/**`, `src/app/backend/*` | backend | Live (E2E + build) |

**APIs:** `/health`, `/api/auth/{register,login,logout,me}`, `/api/repositories[...]`, `/api/query`, plus admin `/api/users` (browser-blocked).
**Databases:** PostgreSQL `kyro` (host port 5433), ChromaDB collection `kyro_changes` (host port 8100).
**Infra:** `infra/docker-compose.yml` (postgres/chroma/kafka/n8n), `app/docker-compose.yml` (migrate/backend/worker/frontend).

### Configuration split (audit-relevant)
- Host-run backend loads **`backend/.env`** (`config.py:6-7`). *(Post-tunnel-readiness fix: this file now carries the full native set — GEMINI/NVIDIA/OPENROUTER keys, GitHub App ids/path, `KYRO_API_KEY`, `RATE_LIMIT_QUERY_PER_MIN=300` — so the host backend runs **authenticated**; the test suite forces `KYRO_API_KEY=""` hermetically in `tests/conftest.py`.)* Before the fix it contained only `GEMINI_API_KEY` and the host backend ran in **dev-open mode** (`KYRO_API_KEY` unset).
- The Docker app stack injects `env_file: ../.env` (root) plus `environment:` overrides.
- Root `.env` contains `KYRO_API_KEY`, `KYRO_WEBHOOK_SECRET`, `GEMINI_API_KEY` (all SET). This two-file split is a documented-by-`.env.example` but easy-to-misconfigure arrangement (see finding DOC-2). **Remediated:** ownership headers added to both files, `frontend/.env.local` added for the native proxy, LLM keys + inline GitHub App PEM added to the root file (container mode), and `scripts/check_env_sync.py` verifies the shared keys match.

---

## C. ACTUAL ARCHITECTURE

### Ingestion
```
GitHub push ──HMAC──▶ n8n (/webhook/github)
                        │  Verify HMAC (fail-closed 401)
                        │  transform (delivery id, repo id, commits, changes)
                        │  HTTP GET api.github.com/compare  ← UNAUTHENTICATED (see SEC-F)
                        ▼
              Kafka topic kyro.github.push (key = repository.github_id)
                        ▼
        IngestionWorker (group kyro-ingestion-workers, manual offset commit)
              phase1 PG tx  →  phase2 Chroma upsert  →  phase3 mark processed
                        ▼
              PostgreSQL (authoritative)  +  ChromaDB kyro_changes
```
Backfill is a **separate topic** (`kyro.github.backfill`) produced by `SyncManager` via the GitHub App API (properly authenticated), one event per commit with deterministic ids `backfill:<repo_id>:<sha>`.

### Retrieval
```
Frontend (selected repo + question)
  ─▶ Next.js /backend/api/query proxy (cookie→Bearer)
  ─▶ FastAPI require_user (ownership) 
  ─▶ Chroma scoped search (where repository_id = repo pk)
  ─▶ ranking: similarity = 1 - distance, threshold 0.1, overfetch 4x, dedup, char budget
  ─▶ PG enrichment (commit/file metadata)
  ─▶ Gemini (grounded prompt + refusal sentence)
  ─▶ QueryResponse{status,repository,question,answer,references[],chunks_considered}
  ─▶ frontend renders answer + references
```

### Authentication
```
Login/Signup ─▶ /backend/api/auth/* proxy ─▶ FastAPI account endpoints
   │  register/login: PBKDF2 password, token = kyro_sess_+token_urlsafe(32)
   │  only SHA-256 token hash persisted; token moved into httpOnly kyro_session cookie
   ▼
Authenticated request: proxy forwards cookie as Authorization: Bearer
   ▼
require_user: bearer session checked FIRST; invalid/expired → 401 TERMINAL (no dev-open fallback)
   ▼
CurrentUser{id,handle,is_default} → repository ownership enforced
```

### Frontend/backend boundary
All browser network traffic is same-origin `/backend/*` (verified: no `fetch()` to any other host, no `NEXT_PUBLIC_` key, no direct Gemini call). The proxy allowlists paths, injects the shared key server-side, strips the token, and rejects cross-origin POSTs.

---

## D. FEATURE MATRIX

| Feature | Status | Evidence |
|---|---|---|
| User registration | IMPLEMENTED_AND_VERIFIED | E2E register 201, httpOnly cookie, PBKDF2 in DB |
| Login / logout / session | IMPLEMENTED_AND_VERIFIED | E2E login 200, logout 204, /me 401 after |
| Session expiry enforced (TTL) | IMPLEMENTED_NOT_END_TO_END_VERIFIED | Code + unit tests; E2E used fresh tokens (no TTL wait) |
| Invalid bearer terminal (no fallback) | IMPLEMENTED_AND_VERIFIED | E2E: invalid bearer → 401 while dev-open active |
| Password hashing (PBKDF2, not plaintext) | IMPLEMENTED_AND_VERIFIED | DB inspection: `pbkdf2_sha256$` prefix |
| Hash-only session storage | IMPLEMENTED_AND_VERIFIED | DB: no raw token persisted |
| No account enumeration | IMPLEMENTED_AND_VERIFIED | E2E: unregistered login → same 401 message |
| User repository isolation (query/resync) | IMPLEMENTED_AND_VERIFIED | E2E: non-owner 403/404, owner control 200 |
| Retrieval end-to-end (Chroma+PG+Gemini) | IMPLEMENTED_AND_VERIFIED | E2E: answer + 2 references matching indexed chunks |
| References map to indexed chunks | IMPLEMENTED_AND_VERIFIED | E2E: reference paths ⊆ indexed paths |
| Cross-user retrieval denial | IMPLEMENTED_AND_VERIFIED | E2E with indexed data present → denied |
| Frontend proxy allowlist + CSRF + cookie | IMPLEMENTED_AND_VERIFIED | Proxy E2E 19/19 |
| Frontend route guard `/app` | IMPLEMENTED_AND_VERIFIED | `/me` → redirect; page 200; guard on mount |
| Query rate limiting / field length caps | IMPLEMENTED_NOT_END_TO_END_VERIFIED | Code + config; not exercised live at limit |
| Ingestion: Kafka→worker→PG→Chroma | IMPLEMENTED_NOT_END_TO_END_VERIFIED | 160-suite (real broker fakes); live GitHub leg gated |
| Ingestion: live GitHub webhook (signed) | **BLOCKED_BY_ENVIRONMENT** | `GITHUB_APP_ID`/`PRIVATE_KEY` empty; no real delivery sent |
| Backfill (GitHub App history walk) | **BLOCKED_BY_ENVIRONMENT** | Requires GitHub App credentials |
| n8n HMAC verification | IMPLEMENTED_AND_VERIFIED | Runtime-verified vs native crypto (14/15; empty body fails closed = safe) |
| n8n full transform→Kafka (real GitHub) | IMPLEMENTED_NOT_END_TO_END_VERIFIED | compare-API step unauthenticated (see SEC-F) |
| Deleted-file removal from index | PARTIALLY_IMPLEMENTED | Deleted docs indexed with `status=deleted` but never removed from Chroma |
| Onboarding UI (add repository) | MISSING (UI) | Backend+proxy support `POST /repositories/onboard`; no frontend affordance |

---

## E. SECURITY STATUS (prior findings re-verified)

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | ChromaDB host/LAN exposure | **MITIGATED_BUT_NOT_FULLY_FIXED** | `infra/docker-compose.yml:60` binds `127.0.0.1:8100`. Upstream CVE (chromadb 1.5.9, CVE-2026-45829/PYSEC-2026-311) — **no confirmed patched release**; CI suppresses the 2 IDs. Image digest-pinned, no tag. |
| 2 | Frontend proxy admin-path exposure | **VERIFIED_FIXED** | `proxyPolicy.ts` allowlist; E2E blocked `/api/users`, `/api/users/1/rotate-key`, `/backend/docs`, path-traversal. |
| 3 | GitHub webhook HMAC | **VERIFIED_FIXED** | n8n "Verify HMAC" node, fail-closed; **runtime-verified** this audit (14/15 vs native crypto; empty body fails closed). Env gate `KYRO_WEBHOOK_SECRET`. |
| 4 | Kafka/PostgreSQL host/LAN exposure | **VERIFIED_FIXED** | `127.0.0.1:5433`, `127.0.0.1:9092`. |
| 5 | n8n host/LAN exposure | **VERIFIED_FIXED** | `127.0.0.1:5678`. |
| 6 | CSRF on state-changing proxied requests | **VERIFIED_FIXED** | `isAllowedOrigin`; E2E cross-origin POST → 403, same-origin → 204. |
| 7 | Query/resync rate limiting | **VERIFIED_FIXED** | `rate_limit()` deps on query/resync; per-email auth limits. In-process per-worker (documented). |
| 8 | Max request-field lengths | **VERIFIED_FIXED** (backend) | `Field(max_length=…)` on auth + query; frontend has no caps (server-side 422). |
| 9 | OpenAPI/docs by environment | **VERIFIED_FIXED** | `KYRO_DOCS` auto = off when `KYRO_API_KEY` set; host backend (key unset) showed docs on = correct for dev. |
| 10 | Environment-driven CORS | **VERIFIED_FIXED** | `CORS_ORIGINS` env + `CORSMiddleware`. |
| 11 | Dependency auditing in CI | **MITIGATED_BUT_NOT_FULLY_FIXED** | `pip-audit` in CI; **no `npm audit`**, **no secret scanning**. |
| 12 | Documentation accuracy | **MITIGATED_BUT_NOT_FULLY_FIXED** | Ports table & commands match compose; minor gaps (quickstart missing `--env-file`, CI runs extra steps). |

### New security/correctness findings from this audit
- **SEC-F (P1):** n8n compare-API HTTP Request node has **no GitHub authentication** → live ingestion of **private repositories** and of **branch create/delete pushes** (all-zero before/after) fails at the compare step before Kafka publish; GitHub will redeliver repeatedly. Not a data-exposure risk, but a functional ingestion blocker for those cases.
- **SEC-G (P2, informational):** Backend `/docs` is enabled whenever `KYRO_API_KEY` is unset (dev-open). Loopback-bound, but a host process could reach it. Acceptable for dev; must be forced `off` in any shared environment. **RESOLVED:** `KYRO_API_KEY` is now set host-side, so `KYRO_DOCS=auto` serves no `/docs`/`/redoc`/`/openapi.json` in either mode (`KYRO_DOCS=on` remains the explicit demo override).

---

## F. KEY FINDINGS (classified)

Finding IDs and the full P0–P3 roadmap are in `KYRO_DEVELOPMENT_ROADMAP.md`. Summary of the material items:

- **No P0 (blockers).** Auth cannot be bypassed (invalid bearer terminal), no cross-user data exposure observed, ingestion does not corrupt persisted data (three-phase + idempotent repair verified).
- **P1 — required before declaring the development phase complete:**
  - P1-1 Live GitHub ingestion E2E is **unverified** (credentials absent) — must be demonstrated once credentials exist, or explicitly scoped out.
  - P1-2 n8n unauthenticated compare call breaks private-repo / branch-create-delete ingestion (SEC-F).
- **P2 — important engineering work:**
  - Worker test flake (`test_failed_partition_does_not_block_other_repos`) — harness double-poll race (see E2E report §Flake).
  - Deleted code never removed from Chroma (retrievable forever).
  - `SYNC_FAILED` repo not auto-restored to READY after a successful redelivery (stays failed until manual resync).
  - Frontend: signup "confirm password" never validated; terms checkbox does not gate submit; backend outage on `/app` misdiagnosed as "logged out"; no mid-session 401 handling; no in-flight send guard.
  - No `npm audit` / secret scanning in CI; broad dependency ranges (no lock for Python).
- **P3 — optional:** dead UI controls (Settings, ⌘K/⌘F, attach, mode dropdown), fake dashboard stats, dead `config/design.ts`, stale `kafka/README.md` claims, no onboarding UI affordance.

---

## G. WHAT IS LEGITIMATELY COMPLETE

1. **Backend auth + isolation** — implemented and verified live (the security-critical core).
2. **Retrieval/RAG** — implemented and verified live end-to-end through the real stack.
3. **Frontend proxy security boundary** — implemented and verified live.
4. **Ingestion pipeline correctness** — implemented, deterministic, and test-verified (160-suite) for everything short of the real GitHub network calls.
5. **Infrastructure hardening** — all host ports loopback-bound; migrations automatic and additive.

**Not yet "complete":** live GitHub ingestion demonstration, the P2 defect set, and CI dependency/secret hygiene.

---

## H. SECURITY & DEPENDENCY STATUS UPDATE (this pass — Task 8)

Original findings in §E/§F are preserved. This re-inspects the current files
(not the prior report) and reports status honestly. Nothing unresolved was
suppressed as "fixed"; nothing was blindly upgraded.

### ChromaDB upstream CVEs — STILL OPEN (no fix available)
`pip-audit -r backend/requirements.txt` reports **5 known vulnerabilities in the
pinned `chromadb 1.5.9`**, all with **`fix_versions: []`** (no patched release
exists upstream), so upgrading cannot remediate them yet:

| ID | Alias | Nature |
|----|-------|--------|
| PYSEC-2026-311 | CVE-2026-45829 | Pre-auth RCE via collections endpoint with `trust_remote_code=true` + malicious model repo |
| PYSEC-2026-3814 | CVE-2026-45833 | Authenticated (UPDATE_COLLECTION) RCE, same mechanism |
| PYSEC-2026-3815 | CVE-2026-45831 | SimpleRBAC cross-tenant (no tenant/db/collection scoping) |
| PYSEC-2026-3813 | CVE-2026-45830 | Authenticated users can read/write/delete any tenant's collection |

- **CI already carries an explicit `--ignore-vuln` baseline** for exactly these 5 IDs (`.github/workflows/ci.yml:73-80`) — an honest, documented acknowledgment, not a hidden suppression. `pip-audit` is present and gated in CI ("fail on NEW vulnerabilities"); every other Python dependency audited clean (0 vulns).
- **Exposure is materially mitigated:** the Chroma container binds `127.0.0.1:8100` (loopback-only, never LAN/Internet); the backend **never sets `trust_remote_code`** (grep-confirmed); usage is **single-tenant** (one `kyro_changes` collection, no multi-tenant RBAC); the frontend never joins the `kyro-data` network. The RCE/cross-tenant vectors are therefore not reachable through KYRO's own usage.
- **Not remediated** — genuinely blocked on an upstream fix; flagged as a **dependency/architecture decision**, not fixed.

### npm dependencies — STILL OPEN (2 high in prod deps)
`npm audit --omit=dev` still reports **2 high**: `next@16.3.7` (several App-Router/Image-Optimization advisories; fix requires `next@16.4.0`, **outside the stated dependency range**) and `source-map-js` (build-time). `npm audit` (incl. dev) shows 7 high. **Not upgraded** — a next major/minor bump is a framework decision requiring its own test cycle; `npm audit fix --force` was deliberately **not** run. **Not gated in CI** (no `npm audit` step).

### Python dependencies — OK (gated)
`pip-audit` is installed in CI and run against `backend/requirements.txt` with the 5 chromadb IDs baseline-ignored. Reproducible; leaks no secrets.

### Secret scanning — GAP (STILL OPEN)
No `gitleaks`/`trufflehog`/equivalent step in CI. Only `pip-audit` is present. Noted as a gap; out of this pass's scope.

### OpenAPI / interactive docs — OK
`main.py:_docs_enabled()` serves `/docs`, `/redoc`, `/openapi.json` **only in development** (`KYRO_API_KEY` unset) unless `KYRO_DOCS` forces on/off; disabled whenever an API key is set. Verified in current code.

### Host/port exposure — OK
All host-published ports bound to `127.0.0.1` (PG 5433, Chroma 8100, Kafka 9092, n8n 5678). This pass also corrected the **Kafka `advertised.listeners`** from `localhost:9092` to `127.0.0.1:9092` so host clients are not re-routed to the IPv6 `::1` loopback (see roadmap §6 / P2-1).

### Authentication configuration — OK
Terminal-bearer 401 (invalid bearer rejected; no API-key fallback) is preserved and was re-verified live this pass. PBKDF2 + hash-only session tokens; the browser never sees the session token (proxy strips it into an httpOnly cookie — live-verified this pass).
