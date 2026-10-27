# KYRO - Operations Guide (local demo)

How to **start** the whole system, how to **talk** to KYRO once it is running, and what is
**actually verified** versus what is not. Written for running the stack on one Windows
machine for a local/college demo.

> KYRO is **not production-ready**. Everything here runs locally on Hasan's machine.
> See the honest status at the bottom of this file.

---

## 1. The two stacks

The deployment is designed as two container groups that can run independently:

| Stack | Components | Notes |
|---|---|---|
| **A - data plane** | PostgreSQL `:5433`, Chroma `:8100`, Kafka `:9092`, n8n `:5678` | docker-compose (`infra\docker-compose.yml`); volumes are persistent - **never** `docker compose down -v` |
| **B - application** | Backend (FastAPI `:8000`), Worker (Kafka consumer), Frontend (Next.js `:3001`) | run as native processes against Stack A |

For the local demo everything runs natively on Windows; Stack A runs in Docker.

---

## 2. How to start everything

Open the repo root: `D:\projects\professional\KYRO\KYRO-Knowledge-driven-Yield-Repository-Optimization`

### Step 1 - Stack A: infrastructure (Docker)

```powershell
powershell -File "$env:TEMP\opencode\ensure-infra.ps1"
```

Starts (health-gated, preserves all volumes): `kyro-postgres` `:5433`, `kyro-chroma` `:8100`,
`kyro-kafka` `:9092`. Verify:

```powershell
docker ps --format "{{.Names}} {{.Status}}" | Select-String kyro
```

Then n8n (workflow engine that authenticates GitHub webhooks with HMAC and publishes to Kafka):

```powershell
docker compose -f infra\docker-compose.yml --env-file .env up -d kyro-n8n
# health check:
Invoke-WebRequest http://127.0.0.1:5678/healthz -UseBasicParsing
```

The `KYRO-N8N` workflow must be **Active** (import once via the n8n UI if it is missing).
Unsigned webhooks are rejected with 401 (fail-closed) - that is correct.

### Step 2 - Backend (`:8000`)

```powershell
cd backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`backend\.env` (gitignored) supplies the process's secrets and auth: `GEMINI_API_KEY`,
`GITHUB_APP_ID` / `GITHUB_APP_INSTALLATION_ID` / `GITHUB_APP_PRIVATE_KEY_PATH`, the LLM
chain keys (`NVIDIA_API_KEY`, `OPENROUTER_API_KEY`), `KYRO_API_KEY` (host mode is
**authenticated**), and `RATE_LIMIT_QUERY_PER_MIN=300` (demo/load-campaign headroom).
Database/Chroma/Kafka URLs are intentionally absent: `config.py` defaults already target
`127.0.0.1:5433` / `:8100` / `:9092`. Consistency across the env files:
`..\scripts\check_env_sync.py`. Verify:
`Invoke-RestMethod http://127.0.0.1:8000/health` must return
`{"status":"ok","checks":{"postgres":"ok","chroma":"ok"}}`.

### Step 3 - Worker (Kafka consumer)

```powershell
cd backend
.venv\Scripts\python.exe -m app.worker_main
```

Must log `worker_started ... topics=['kyro.github.push','kyro.github.backfill']` with all
partitions assigned.

### Step 4 - Frontend (`:3001`)

```powershell
cd frontend
# frontend/.env.local (auto-loaded by Next.js) already carries:
#   KYRO_BACKEND_URL=http://127.0.0.1:8000   KYRO_API_KEY=<same as backend/.env>
# The next line is only a fallback if you delete that file:
$env:KYRO_BACKEND_URL = "http://127.0.0.1:8000"
npm run dev
```

The port is pinned to **3001** in `frontend/package.json` (`next dev -p 3001`):
a local watchdog on this machine reaps whatever process holds host `:3000`,
which killed every dev server placed there. Nothing probes `:3001`.

### Step 5 (optional) - Public tunnel for real GitHub webhooks

Real GitHub deliveries need a public URL. A Cloudflare Quick Tunnel provides one without
any account; it is **temporary** (URL changes each restart):

```powershell
cloudflared\tunnel.exe tunnel --url http://127.0.0.1:5678 --no-autoupdate
```

The printed `https://....trycloudflare.com` URL must be set as the webhook Payload URL
(`.../webhook/github`) on the GitHub App/repo **immediately before a test push**, with the
webhook secret equal to `KYRO_WEBHOOK_SECRET`. A repo-level webhook on
`KYRO-ingestion-test` (`id 698074039`) already exists for this; the App-level webhook URL
can only be changed manually in the GitHub UI (API returns 401/403 for it).

---

## 3. How to talk to KYRO

### Option A - the web UI (easiest)

Open **http://127.0.0.1:3001**, register/login (the auth token stays in an httpOnly cookie;
the browser never sees it), pick a repository, and ask questions. The Next.js proxy injects
the backend URL and the service key server-side (`frontend/.env.local` in host mode).

### Option B - the REST API directly

All example calls below assume the backend at `http://127.0.0.1:8000` and the service key
loaded into `$KYRO` (the value lives in `backend/.env` — load it, never print it):

```powershell
$KYRO = ((Get-Content .\backend\.env) -match '^KYRO_API_KEY=' -replace '^KYRO_API_KEY=','')
```

The host backend runs **authenticated** since the tunnel-readiness fix: add
`-Headers @{ "X-API-Key" = $KYRO }` to each call below. `GET /health` and the
`api/auth/*` routes stay open without it. `/docs` is hidden while the key is set
(`KYRO_DOCS=auto`); set `KYRO_DOCS=on` in `backend/.env` (and restart) to browse the
interactive schema locally.

**Ask a question about a repository** (the core "talk to KYRO" endpoint):

```powershell
$payload = @{
    github_repository_id = 1305850991    # Nexus; see the repo list below for others
    question             = "What does this repository contain? Summarize its main files and purpose."
    top_k                = 5
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/query -Method Post `
    -Headers @{ "X-API-Key" = $KYRO } -ContentType "application/json" -Body $payload
```

Response: `{ answer, references: [{commit_sha, path, status, ...}], ... }`. The answer is
generated by an LLM over the retrieved chunks, and every claim can be traced to a
`references` entry (chunks the model actually saw).

The `github_repository_id` is the **GitHub numeric id** (not the KYRO internal id):

| Repository | github_repository_id |
|---|---|
| hasan19524/KYRO-ingestion-test | 1395956448 |
| hasan19524/leetcode_grind | 1323133421 |
| hasan19524/baba_birthday | 1346607173 |
| hasan19524/mothers-day | 1234129195 |
| hasan19524/Nexus | 1305850991 |
| hasan19524/acumen_teams_personal | 1286911921 |

**Onboard another repository** (any repo visible to the GitHub App installation):

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/repositories/onboard -Method Post `
    -Headers @{ "X-API-Key" = $KYRO } -ContentType "application/json" `
    -Body '{"github_repository_id": <id>}'
# -> 202 accepted; backfill runs through Kafka; poll GET /api/repositories for status READY
```

**List repositories / their status:**

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/repositories `
    -Headers @{ "X-API-Key" = $KYRO }
```

**Re-sync a repository** (re-run its backfill):

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/repositories/<github_repository_id>/resync" `
    -Method Post -Headers @{ "X-API-Key" = $KYRO }
```

**Login/session API** (open without the service key; the proxy attaches it automatically):
`POST /api/auth/register`, `POST /api/auth/login` (sets httpOnly cookie),
`GET /api/auth/me`, `POST /api/auth/logout`.

**Sign in with GitHub (OAuth)** — one-click redirect flow (`backend/app/api/github_oauth.py`):

- `GET /backend/api/auth/github/start` → 302 to GitHub's authorize page. The `state`
  param is an HMAC-signed blob (key = SHA-256 of `GITHUB_CLIENT_SECRET`, 10-minute TTL,
  no cookie needed — works across the tunnel and localhost alike). The `redirect_uri` is
  built per-request from the proxy-injected `X-Kyro-Self-Origin` header (fallback:
  `KYRO_PUBLIC_URL`), so no env change is needed when the tunnel URL rotates — but the
  new URL must still be saved as an **Authorization callback URL** on the GitHub App.
- `GET /backend/api/auth/github/callback` → validates `state`, exchanges the code, then
  resolves the account: `github_id` match → reuse; else email match → **link** to the
  existing password account (no duplicate accounts); else create. Sets the same httpOnly
  `kyro_session` cookie and 302s to `/app`. Any failure (tampered/expired state, GitHub
  error, rate limit, deactivated account) → 302 to `/login?error=github`. The GitHub user
  access token is used once for identity and **never stored** — repo listing uses the
  App's installation token instead.
- `GET /backend/api/github/repos` (session-guarded) → the installation's repos joined
  with KYRO onboarding state (`onboarded`, `status`). GitHub unreachable → 502 (never a
  fabricated list). The web UI's picker connects a repo via the existing
  `POST /api/repositories/onboard`, which starts the same backfill as Option B.
- Required `backend/.env` keys (synced by `scripts/check_env_sync.py`):
  `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` (the App's *client secret*, distinct from
  the webhook's App ID/private key), optional `KYRO_PUBLIC_URL`.
- Tests: `backend/tests/test_github_oauth.py` (14 cases) + the proxy allowlist cases in
  `frontend/tests/proxyPolicy.test.ts`.

### Option C - push code to GitHub (the "it ingests by itself" story)

With the tunnel running and the webhook URL pointed at it, a normal `git push` to any
onboarded repository triggers: GitHub delivery -> n8n HMAC verify -> Kafka -> worker ->
PostgreSQL + Chroma. Verified live with a real commit
(`5ad30d27cb9eb9a17db0271b0f0acd5712cc3a20`); see `docs/audit/KYRO_E2E_VERIFICATION.md` §8.

---

## 4. How answers are produced (the LLM chain)

Ingestion is **100% deterministic** - no LLM is involved in parsing/committing/indexing.
Embeddings are Chroma's local `all-MiniLM-L6-v2` (no API key needed).

Only the **query answer** uses an LLM, through a fallback chain
(`backend/app/llm_chain.py`):

```
opencode (zen)  ->  nvidia  ->  openrouter  ->  gemini
```

- One bounded attempt per provider; any failure (timeout, 4xx/5xx, empty content) falls
  through to the next; all-fail returns HTTP 502.
- Order and models are configurable via env: `LLM_PROVIDER_ORDER`, `OPENCODE_MODEL`,
  `NVIDIA_MODEL`, `OPENROUTER_MODEL`, `GEMINI_MODEL`, plus per-provider timeouts.
- Each answer logs which provider served it (`llm_served name=... elapsed=...`).
- **The opencode slot is key-gated and HTTP-only.** Zen's free tier only works from
  inside the OpenCode app itself (external HTTP callers get 403 `FreeTierError` -
  verified), and no CLI-bridge workaround is attempted. Without `OPENCODE_API_KEY`
  in `backend\.env` the slot is skipped quietly; **NVIDIA NIM serves** every query.
  If you ever get an OpenCode Console API key (paid), just add
  `OPENCODE_API_KEY=...` and restart the backend - the slot activates automatically.
- Your OpenRouter key (`OPENROUTER_API_KEY`) is configured as the third fallback.

---

## 5. What is actually verified (honest status)

**Verified working locally:**
- All **six** selected repositories ingested to `READY` through the real pipeline
  (GitHub App key-path auth, backfill, content resolution, PG + Chroma).
- **Real GitHub webhook delivery** end-to-end through the public tunnel
  (HMAC fail-closed, Kafka, worker, exact blob sha + content persisted).
- **Query answers with references** for all six repos (e.g. mothers-day refs=5,
  Nexus refs=4, acumen refs=5); the binary-file and deleted-file-chunk retrieval defects
  found in this pass are fixed and regression-tested.
- Backend regression: **177 tests passed**; frontend regression: **17/17** (from the
  previous pass, unchanged by this pass).
- LLM fallback chain: order honoured, failures fall through, all-fail raises - unit-tested
  with fakes; live behaviour confirmed via logs.

**Known limitations (demo scope):**
- The **Quick Tunnel URL is temporary** - it changes when `cloudflared` restarts. The
  webhook Payload URL must be updated before the next real push (manual step; the
  App-level webhook URL cannot be updated via API).
- The opencode/zen slot is inactive without a paid OpenCode Console API key (the free
  tier is client-gated to the OpenCode app; no workaround attempted). NVIDIA serves in
  its place; your OpenRouter key is the next fallback.
- Secrets live in gitignored local env files (root `.env` = container mode,
  `backend/.env` = native backend, `frontend/.env.local` = native proxy; cross-checked by
  `scripts/check_env_sync.py`); nothing production-grade (no secret manager, no TLS
  termination; per-user fixed-window rate limits only — no global IP cap).
- The two-stack container split (Stack A / Stack B) is **designed** for separate
  deployment but only Stack A is containerized in this demo; Stack B runs natively.
- Container GitHub auth: the root `.env` now carries the inline PEM
  (`GITHUB_APP_PRIVATE_KEY`, double-quoted multi-line) so a containerized backend can
  authenticate without mounting the Windows `..._KEY_PATH` — written but **not yet
  exercised**: Stack B has not been built since that fix.

**Explicitly not claimed:** production readiness, multi-user isolation hardening,
performance under load, or durability across machine restarts.

---

## 6. Troubleshooting quick reference

| Symptom | Likely cause / fix |
|---|---|
| `/health` shows `postgres: down` | Stack A not running - re-run `ensure-infra.ps1` |
| Query returns 502 with "all LLM providers failed" | No chain key valid - check `backend\.env` keys, or provider outage; logs show per-provider errors |
| Query returns `refs=0` | Repo not synced (check status), or question is off-topic for the indexed files |
| Webhook returns 401 from the tunnel | `KYRO_WEBHOOK_SECRET` mismatch between GitHub webhook config and `.env`, or unsigned request (expected fail-closed) |
| Webhook not delivered at all | Tunnel URL changed on restart - update the GitHub webhook Payload URL |
| Worker logs `offset reset ... out of range` | Normal after restart with compacted topic - events are idempotent, safe to reprocess |
| Gemini answers stop (quota) | Free-tier daily quota - the chain falls through to the next provider automatically |
