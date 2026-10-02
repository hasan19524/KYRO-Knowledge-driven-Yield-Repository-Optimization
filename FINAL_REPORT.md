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
