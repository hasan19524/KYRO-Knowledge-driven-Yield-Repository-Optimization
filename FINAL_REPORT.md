# §37 — KYRO Final Report

Honest completion status for the KYRO master plan (phases 1–22). Every claim
below is tied to a command actually executed against the live system; nothing
is inferred from intent.

## 1. Status

| Area | Status |
|---|---|
| Backend ingestion pipeline (phases 1–18) | Complete — 76/76 tests pass |
| Secret/config hygiene (phase 2) | Complete — scan clean, root `.env` gitignored |
| Two-stack compose + data-preserving cutover (phases 5–10) | Complete — verified live |
| Auth, honest `/health`, frontend RAG proxy (phases 11–16) | Complete — verified live |
| CI (phase 17) | Complete — `.github/workflows/ci.yml` committed |
| End-to-end verification (phase 18) | Complete — see §4 |
| Root README | Complete |
| Real-GitHub ingestion | **Blocked — GitHub App credentials intentionally absent** (see §5) |

## 2. Architecture as built (locked, unchanged)

```
GitHub → n8n (webhook `github`) → Kafka (kyro.github.push) → worker
        → PostgreSQL (source of truth) + ChromaDB (index, never source of truth)
Frontend → /backend/[...path] proxy (server-side X-API-Key) → FastAPI
        → Chroma retrieval → Gemini → cited answer
```

- Two compose stacks: `infra/` (`kyro-infra`: postgres, chroma, kafka, n8n)
  and `app/` (`kyro-app`: migrate, backend, worker, frontend) on external
  network `kyro-network`. All volumes use explicit `name:` so `up`/`down`
  never destroys data; images digest-pinned.
- Topics: `kyro.github.push` (live, key=`repository.github_id`) and
  `kyro.github.backfill` (5 partitions), consumer group
  `kyro-ingestion-workers`, at-least-once with `X-GitHub-Delivery` idempotency.
- Auth: `X-API-Key` on POST query/onboard/resync (disabled when
  `KYRO_API_KEY` unset, constant-time compare); the browser never holds the
  key — the Next.js proxy injects it server-side.

## 3. Regression gates (all executed)

| Gate | Command | Result |
|---|---|---|
| Unit/integration tests | `python -m pytest tests/` (windowed batches, engine instability §7) | **76 passed, 0 failed** |
| Lint | `ruff check app tests alembic` | clean |
| Types | `pyright app tests alembic` | 0 errors, 0 warnings |
| Frontend lint | `npm run lint` | clean |
| Frontend build | `npm run build` | OK — routes `/`, `/_not-found`, `ƒ /backend/[...path]` |
| CI definition | `.github/workflows/ci.yml` | backend (services: PG/Chroma/Kafka) + frontend + `compose config` |

Test batch breakdown (each executed, exit 0):
`test_events_schema+test_github_client+test_query_api` 32 ·
`test_persistence` 9 · `test_processor_idempotency` 9 ·
`test_backfill_service` 10 · `test_sync_manager` 10 ·
`test_worker_kafka` 5 · `test_e2e_sync` 1 → **76**.

## 4. End-to-end verification (live containers)

Executed against the running stacks (Oct 3, 2026):

1. **Honest health** — `GET :8000/health`
   - all dependencies up: `200 {"status":"ok","checks":{"postgres":"ok","chroma":"ok"}}`
   - with Chroma stopped: `503 {"status":"degraded","checks":{"postgres":"ok","chroma":"error"}}`
   - restored: back to `200 ok`.
2. **Auth** — direct `POST :8000/api/query` without key → `401`;
   through the proxy → server-side key injected (proxied query returned
   `404` for unknown repo, not `401`, proving injection).
3. **RAG query (synthetic READY repo, github_repository_id=900001)** —
   `POST :3000/backend/api/query` →
   `200 {"status":"READY",...,"answer":"Based on the commit message for commit
   e2e000000000, the purpose of this synthetic repository is...","references":
   [{README.md},{main.py}],"chunks_considered":2}` — retrieval, citation
   bridge (PG↔Chroma metadata), and Gemini generation all live. Before the
   fix in §6 this returned 502.
4. **n8n → Kafka → worker (real public repo, real SHAs)** —
   `POST localhost:5678/webhook/github` with `x-github-delivery`
   `8828211e-8946-4b46-9759-9a3be5148f14`, repository
   `octocat/Hello-World` (real id 1296269), consecutive SHAs
   `7629413…→7fd1a60…` → webhook `200 Workflow was started`; n8n's GitHub
   compare ran untouched; worker logged
   `event_deferred … topic=kyro.github.push partition=3 offset=8` and PG
   holds `ingestion_events` row (`kind=live, status=deferred`, idempotency by
   delivery UUID). A third delivery landed as row id 35 — duplicate-safe.
5. **Onboard** — `POST /backend/api/repositories/onboard` → `202` with
   `status=SYNCING`, `deferred_events: 1`; in-process sync attempt fails in
   ~45 ms with `last_error = "GitHub App credentials are not configured…"`
   → repo `SYNC_FAILED` (visible, never silent).
6. **Worker credential failure path (no fake credentials)** — one
   production-shaped backfill event (real octocat compare data, published via
   the real `BackfillProducer` to `kyro.github.backfill`) produced:
   - PG: `event_id=backfill:1296269:7629413…, kind=backfill, status=failed,
     error=permanent_github_credentials: GitHub App credentials are not
     configured…`
   - worker log: `event_permanent_failure reason=github_credentials` →
     `event_failed_persisted` → `partition_paused … offset_not_committed`
   - a no-file-diff backfill event in the same run processed cleanly
     (`status=processed`) — both branches verified.
7. **Restart policies** — `docker inspect` on all `kyro-*` containers:
   `unless-stopped` (migrate: `no`, one-shot by design). Containers
   auto-recover across engine restarts.
8. **Auth/health unit coverage** — the 5 new tests (auth open/enforced,
   health ok/503-postgres/503-chroma) are part of the 76.

## 5. Credential-blocked (documented, never faked)

- `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY(_PATH)` / `GITHUB_APP_INSTALLATION_ID`
  are absent by design in this environment. Real GitHub backfill/content
  fetch cannot run; per plan, GitHub-dependent tests stay mocked/skipped and
  the failure surfaces explicitly (`SYNC_FAILED`, `status=failed` +
  `permanent_github_credentials`) instead of being simulated.
- Fresh-setup instructions for real credentials live in `.env.example` and
  `n8n/README.md`.

## 6. Fixes landed this session

- **Retired LLM model**: `backend/app/gemini_service.py` hardcoded the retired
  `gemini-2.0-flash` (HTTP 404 from Google → query 502). Now
  `config.GEMINI_MODEL`, default `gemini-3.8-flash`, env-overridable.
- **Chroma ONNX model persistence**: first Chroma query downloads an ~80 MB
  embedding model inside the backend/worker containers. Added named volume
  `kyro-chroma-model-cache` → `/root/.cache/chroma` so rebuilds don't pay the
  download; verified `model.onnx` cached (167 MB) and a subsequent query
  returns 200 in ~26 s.
- Root `README.md` added (quickstart, ports, API, secrets, gates).

## 7. Environment incident (transparency)

Docker Desktop was in an **auto-updater kill-loop**: every few minutes it
downloaded updater 234817, killed the engine to install, the install failed
without elevation, and Desktop exited — leaving 60–90 s engine windows.
Symptoms initially looked like an engine crash (`services: exit status 1`,
pipe `dockerDesktopLinuxEngine` vanishing). Resolution: the user approved the
already-downloaded installer (one UAC approval); Desktop updated to
4.93.0 / engine 29.8.1. Windows lengthened but remained minutes-long, so all
verification (tests in 7 batches, E2E steps) was executed to fit inside
engine windows. Container data survived every incident (no volume loss).

## 8. Known limitations (pre-existing, unchanged)

- n8n Kafka node publishes with `acks=1` (locked known limitation — not
  "fixed" without an audit decision).
- Live events produced by the n8n workflow do not carry
  `previous_path` for renames (backfill events do); see
  `backend/app/schemas/events.py` `ChangeBlock`.
- Repository auto-creation on first live event parks the event as
  `deferred` until backfill reaches `READY` (by design — live events can
  never overtake backfill).
- Worker test suite and E2E validation exercised failure/deferral/duplicate
  paths; happy-path real-repo backfill requires §5 credentials.

## 9. Commits

| Commit | Contents |
|---|---|
| `8942ab7` | Backend phases 1–18, Kafka/n8n infra, tests, security scaffolding |
| `82615ed` | Phase 4 (next 16.3.7, lint fixes) |
| `d3ad5b4` | Two-stack compose split, data-preserving volumes |
| `d68e1ac` | Phases 5–10 (compose stacks, frontend image, n8n export, refs) |
| `86803df` | Phases 11–16 (honest `/health`, X-API-Key auth, RAG proxy, frontend wiring) |
| `fcf99da` | Phase 17 (GitHub Actions CI) |
| *(this)* | Gemini model fix, ONNX cache volume, root README, §37 report |

---

# §38 — User authentication, user management, multi-repository isolation

Backend-only milestone. Every claim below is tied to a command executed in
this session (tests, gates, live migration, live smoke); nothing is inferred
from intent. Retrieval pipeline, ingestion design (GitHub → n8n → Kafka →
worker → PostgreSQL + Chroma), frontend, and RAG logic were **not** modified.

## 1. Status (24 acceptance criteria → evidence)

| Criterion | Evidence |
|---|---|
| Users table + per-user keys | Migration §2, `app/db/models.py`, tests `test_users_schema_*`, `test_create_user_issues_key_once_*` |
| Identity server-side only | `app/api/auth.py` (`require_user`); request schemas carry no user id; `test_client_supplied_user_id_is_ignored` |
| User 1 → many repositories | `repositories.owner_user_id` FK; `test_one_user_owns_multiple_repositories` |
| Ownership checked on every repo op | onboard/list/detail/resync/query all identity-scoped (`app/api/repositories.py`); `test_cross_user_access_rejected_both_directions` (A→B and B→A) |
| Cross-user access rejected, both directions | list `[]`, detail/query `404` (no existence leak), resync `404` |
| Onboard conflict | unowned claim OK; owned-by-other → `409`; `test_onboard_conflict_and_re_onboard`, `test_unowned_repositories_are_claimable_by_first_onboard` |
| Client-supplied user id never trusted | `OnboardRequest` has no ownership field; manager overwrites from identity |
| Kafka payload never carries KYRO user id | `resolve_repository` never reads/writes `owner_user_id` (invariant docstring); `test_events_never_assign_arbitrary_ownership` |
| Unresolvable ownership → no guessed owner | created rows stay `owner NULL` (quarantine); live event on unowned → existing `deferred` path (`test_events_never_assign_arbitrary_ownership`) |
| Worker preserves PG ownership | backfill/live events leave `owner_user_id` untouched; owner-change-between-events wins; `test_worker_preserves_ownership_and_current_owner_wins` |
| Admin-guarded user management | `/api/users` (create/list/detail/rotate/deactivate/reactivate/delete) = `require_admin`; `test_admin_guard_and_invalid_credentials` |
| Deactivated keys rejected | always `401`, even in dev mode; `test_deactivated_user_rejected_even_in_dev_mode` |
| Key secrecy | SHA-256 hash only in DB; plaintext returned once (issue/rotate); never logged (grep verified) |
| Legacy shared-key identity preserved | shared key → `default` identity; proxy/frontend unchanged; `test_shared_key_identity_sees_legacy_repositories`, live smoke §5 |
| Dev mode preserved | no `KYRO_API_KEY` → open, acts as `default`; `test_dev_mode_without_credentials_stays_open` |
| Data preserved on migration | backfill all existing repos → `default`; isolated upgrade/downgrade/upgrade test + live DB (2/2 repos backfilled) |
| DELETE blocked while owning repos | app `409` + DB `ON DELETE RESTRICT` (both tested) |
| Reindexing (resync) ownership-scoped | `resync` requires visibility; not-owned → `404` before any enqueue |
| Failure handling has no side effects | rejected attempt leaves row untouched; `test_auth_failures_leave_no_side_effects` |
| Vector keys/traceability unchanged | `build_doc_id`/metadata untouched; owner traceable via `repository_id → repositories.owner_user_id`; `test_index_keys_preserved_and_traceable_to_owner` |
| Existing tests green | 95/95 (76 baseline + 19 new) |
| ruff / pyright | 0 issues / 0 errors (§6) |
| Frontend/retrieval untouched | no changes under `frontend/`, retrieval/ranking/prompt code unchanged (diff confined to §2 files) |

## 2. Files changed

| File | Change |
|---|---|
| `backend/app/db/models.py` | `User` (handle unique, `api_key_hash` unique nullable, `is_active`, timestamps), `DEFAULT_USER_HANDLE`, `Repository.owner_user_id` (FK `ON DELETE RESTRICT`, indexed) + relationship (`passive_deletes=True` so the DB, not the ORM, enforces RESTRICT) |
| `backend/alembic/versions/7c3f1a9d2e45_users_repository_ownership.py` | **Migration** (down_revision `0f9d27246cef`): create `users`, seed `default`, add `repositories.owner_user_id`, backfill all existing repos → `default`; downgrade drops column + table |
| `backend/app/api/auth.py` | `CurrentUser`, `require_user`, `require_admin`, `may_access`, `hash_api_key`/`generate_api_key`, legacy `require_api_key`; `get_state` moved here (re-exported) |
| `backend/app/api/users.py` | **New** — admin-guarded lifecycle API (see §4) |
| `backend/app/api/repositories.py` | All 5 endpoints → `require_user` + owner scoping; conflict → `409`; not-owned → `404`; query ownership **before** status gates |
| `backend/app/sync/manager.py` | `RepositoryOwnershipConflict`; visibility scoping on `onboard`/`resync`/`snapshot`/`list_snapshots` (keyword `owner_user_id=None` = internal unscoped, back-compatible) |
| `backend/app/ingest/persistence.py` | Ownership invariant documented on `resolve_repository` (code intentionally unchanged — payload has no KYRO identity) |
| `backend/app/main.py` | Includes `users_router`; dev-mode warning mentions `default` identity |
| `backend/tests/conftest.py` | `ADMIN_TABLES` += `users` (teardown wipe) |
| `backend/tests/test_query_api.py` | Auth-enforced test now expects `401` without key / `200` with correct key |
| `backend/tests/test_user_auth.py` | **New** — 19 tests covering criteria above |
| `README.md` | API table + "Authentication & repository isolation" section; test count 95 |
| `FINAL_REPORT.md` | This section |

## 3. Migration (verified twice: isolated + live)

- `7c3f1a9d2e45` — additive only; no destructive operation; downgrade path tested.
- Isolated proof (`test_migration_upgrade_downgrade_preserves_repository_data`):
  fresh DB `kyro_mig_check` → `upgrade` → seed rows → `downgrade` → data intact
  → `upgrade` again, subprocess alembic both directions.
- **Live application** (real `kyro` DB, localhost:5433): `0f9d27246cef →
  7c3f1a9d2e45`; before: 2 repositories, no `owner_user_id` column; after:
  `users = [default]`, `2/2 repositories backfilled`. Then rebuilt
  `kyro-backend:local` and recreated migrate/backend/worker —
  `[kyro-migrate] OK: schema at head` (idempotent no-op).

## 4. Authentication & user management implementation

- `require_user` (sync, DB-backed): shared `KYRO_API_KEY` (constant-time
  `secrets.compare_digest`) → `default` identity; else per-user key looked up
  by SHA-256 hash → active user; inactive → `401` always; production with
  unknown/missing key → `401`; dev mode (key unset) → open as `default`.
- `require_admin`: shared key only (per-user keys never admin) or dev-open.
- Keys: `kyro_` + 48 hex chars, hashed at rest, returned exactly once.
- `/api/users`: handle `^[a-z0-9][a-z0-9_-]{2,31}$` (422), reserved/duplicate
  → 409, create → 201 `{id, handle, api_key}`; rotate → one-time key;
  deactivate/reactivate → 200; delete → 204 / 404 / 409 (still owns repos) /
  409 (legacy `default`). Race-safe via `IntegrityError` mapping.
- Never logged: logs contain only `user_id` + `handle` (grep verified).

## 5. Isolation mechanism + live smoke (production auth, real stack)

`may_access(repo, user)`: `None`→all (internal), `owner NULL`→default only
(fail-closed for per-user keys), else exact owner match. Executed live
against `:8000` after rebuild (`KYRO_API_KEY` set, len 64):

1. `GET /health` → `200 {"status":"ok",...}`
2. `GET /api/users` no key → `401 admin credentials required`
3. shared key → `200 [default]`
4. `POST /api/users {smoke-user}` → `201` + one-time `kyro_…` key
5. shared key list → `200` with both legacy repos (900001 READY, 1296269 SYNC_FAILED)
6. smoke-user key list → `200 []`
7. smoke-user detail of 900001 → `404` (no existence leak)
8. shared-key detail of 900001 → `200`
9. smoke-user `POST /api/query` on 900001 → `404` (ownership **before** status gates — would otherwise be a READY answer)
10. `DELETE /api/users/2` → `204` (owned 0 repos)
11. list after cleanup → only `default` (live DB restored)

## 6. Ingestion ownership, key preservation, reindexing, failure handling, vector metadata

- **Ingestion ownership**: events carry GitHub identity only
  (`repository_github_id`); `resolve_repository` never touches
  `owner_user_id`; first-ingestion rows stay unowned (quarantine); live
  events on unowned/unknown repos use the pre-existing deferral path
  (`status=deferred`), never a guessed owner; worker re-reads the PG record
  each event so an ownership change between events wins.
- **Key preservation**: shared-key/proxy path preserved byte-for-byte
  (`X-API-Key` → `default`); no frontend change; `github_repository_id`
  remains purely the external GitHub identity; all pre-existing behavior
  (query gating codes/messages, health, ingestion) unchanged — baseline 76
  tests untouched except the one auth expectation that intentionally moved.
- **Reindexing**: `resync` is ownership-scoped (not-owned → `404` before any
  work is enqueued); owner-visible re-sync reuses the same backfill machinery
  and keys.
- **Failure handling**: conflicts `409`, isolation `404` (identical to
  missing), bad/absent/deactivated creds `401`, delete-with-repos `409`,
  rejected attempts leave zero side effects, DB `RESTRICT` as last line of
  defense, deferred/failed events unchanged.
- **Vector metadata**: Chroma keys/metadata untouched
  (`repository_id, commit_id, file_id, github_repository_id, commit_sha,
  path, status`); traceability owner-side via `repository_id →
  repositories.owner_user_id` (tested).

## 7. Exact test results & gates

| Gate | Command | Result |
|---|---|---|
| Tests | `pytest` windowed (engine instability, §37 §7) | **95 passed, 0 failed** |
| Lint | `ruff check app tests alembic` | All checks passed |
| Types | `pyright app tests alembic` | 0 errors, 0 warnings |
| Format | `ruff format --check` (touched files) | 16 files already formatted |

Batch breakdown (each exit 0):
`test_user_auth+test_query_api` 36 · `test_events_schema+test_github_client` 15 ·
`test_persistence+test_processor_idempotency` 18 ·
`test_backfill_service+test_sync_manager` 20 ·
`test_worker_kafka+test_e2e_sync` 6 → **95** (76 pre-existing + 19 new).

## 8. Commits (this milestone)

| Commit | Contents |
|---|---|
| *(this)* | §38: users, per-user auth, repository isolation, ownership hardening, migration `7c3f1a9d2e45`, 19 tests, README |


---

# 39 - Security remediation

## 1. Status (audit groups → evidence)

| Group | Scope | Evidence |
|---|---|---|
| A. Network exposure | Host ports bound to `127.0.0.1` only (infra: 5433/8100/9092/5678; app: **8000/3000 — gap found & fixed this session**) | Live matrix: LAN IP `10.182.63.222` refuses all 6 ports, loopback opens all 6 |
| B. Frontend proxy | Path allowlist + CSRF origin guard, no admin/docs passthrough, API key stays server-side | `frontend/tests/` 10/10, lint+build clean; live battery: POST foreign origin 403, evil referer 403, `/api/users` & `/docs` 403, same-origin passes, GET read-only allowed |
| C. Webhook integrity | n8n verifies `X-Hub-Signature-256` (pure-JS HMAC-SHA256, fail-closed before Kafka) | 7/7 local vectors; live: unsigned 401, wrong-sig 401, valid 200 |
| D. Rate limiting & bounds | Fixed-window limiter (`resync` 10/min, `query` 60/min), query field caps | `test_security_remediation.py` 13/13; live: 11th resync 429 + `retry-after: 20` |
| E. Docs & CORS | `/docs`, `/redoc`, `/openapi.json` gated (`KYRO_DOCS`: auto/on/off - key present => off), explicit CORS allowlist (`CORS_ORIGINS`) | `test_security_surface.py` 7/7; live: all three 404 with `KYRO_API_KEY` set |
| F. CI / docs / 401 hygiene | pip-audit step (chromadb advisory ignored honestly), frontend `npm test`, README security surface, `.env.example` auth truth, n8n 401 body sanitized to static `{"error":"unauthorized"}` | Workflow JSON re-imported + published + active; live 401 bodies leak nothing |

## 2. Regression (115/115) - batched by design

Honest note: Docker Desktop's backend process dies ~2.5-5 min after every
launch on this machine (unidentified external cause, not OOM - watcher data
in `%TEMP%\kyro_watch.log`). Full-suite runs get killed mid-flight, so the
suite is executed in health-gated batches, each fitting one lifetime window:

| Batch | Tests | Result |
|---|---|---|
| `test_security_remediation + test_security_surface` | 20 | 20 passed |
| `test_events_schema + test_github_client` | 15 | 15 passed |
| `test_user_auth` | 19 | 19 passed |
| `test_query_api` | 17 | 17 passed |
| `test_persistence + test_processor_idempotency` | 18 | 18 passed |
| `test_backfill_service + test_sync_manager` | 20 | 20 passed |
| `test_worker_kafka + test_e2e_sync` | 6 | 6 passed (attempt 2; attempt 1 hit an engine death at 146 s) |
| **Total** | **115** | **0 failed** (95 baseline + 13 remediation + 7 surface) |

Gates: `ruff check` clean · `pyright` 0 errors · frontend `npm test` 10/10 ·
`npm run lint` clean · `npm run build` succeeded.

## 3. Live end-to-end (this session, real stack)

- Signed webhook -> n8n -> Kafka -> worker -> PostgreSQL: delivery
  `44744812-...` accepted (200), worker `event_deferred`, row in
  `ingestion_events` (no schema change; data ownership untouched).
- Rate limit: `POST /api/repositories/999999999/resync` x13 -> 10x404 then
  429 + `retry-after: 20` (nonexistent repo => no side effects).
- Docs gating: `/docs`, `/openapi.json`, `/redoc` -> 404 with key present.
- Auth: no key -> 401, key -> 200 on `/api/repositories`.
- Port matrix: all 6 published ports refused on LAN IP, open on loopback.

## 4. Honest limitations (unchanged)

- chromadb 1.5.9 pre-auth RCE (CVE-2026-45829 / PYSEC-2026-311) has no fixed
  release: mitigated by loopback-only binding + network policy, documented in
  README, and pip-audit skips exactly these five advisory IDs.
- The Docker Desktop death cycle is environmental; CI (GitHub Actions) runs
  the full suite normally in one shot.