# KYRO — Knowledge-driven Yield Repository Optimization

KYRO ingests a GitHub repository's full history, indexes it into PostgreSQL
(source of truth) + ChromaDB (vector index), and answers natural-language
questions about the code through a RAG pipeline (FastAPI → retrieval → LLM →
cited answer) served through a Next.js frontend.

## Architecture (locked)

```
GitHub push webhook
   └─► n8n (normalize) ──► Kafka topic kyro.github.push
                              └─► ingestion worker
                                    ├─► PostgreSQL  (repos, commits, files, events — source of truth)
                                    └─► ChromaDB    (chunks + embeddings — index, never source of truth)

Browser ──► Next.js frontend ──► /backend/[...path] proxy (server-side, injects X-API-Key)
                                  └─► FastAPI ──► Chroma retrieval ──► Gemini LLM ──► cited answer
```

Invariants: n8n + Kafka are never replaced; Chroma is never the source of
truth; two topics — `kyro.github.push` (live) and `kyro.github.backfill`
(5 partitions, RF=1) — consumer group `kyro-ingestion-workers`,
at-least-once with `X-GitHub-Delivery` idempotency.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/` | FastAPI API, ingestion worker, Alembic migrations, tests |
| `frontend/` | Next.js UI (chat over repo, repository selector) |
| `infra/docker-compose.yml` | **Stack A** — postgres, chroma, kafka, n8n (`name: kyro-infra`) |
| `app/docker-compose.yml` | **Stack B** — migrate, backend, worker, frontend (`name: kyro-app`) |
| `n8n/` | Workflow export + idempotent bootstrap script |
| `kafka/` | Topic bootstrap notes |
| `.github/workflows/ci.yml` | CI: ruff + pyright + pytest (with services), frontend lint/build, compose validation |

## Quickstart

Prerequisites: Docker Desktop, a Gemini API key.

```powershell
# 1. Configure secrets (root .env is gitignored; never commit it)
copy .env.example .env        # then set GEMINI_API_KEY; KYRO_API_KEY enables API auth

# 2. Infrastructure (data volumes are named + preserved — never use `down -v`)
docker compose -f infra/docker-compose.yml up -d

# 3. n8n workflow import (once per fresh n8n volume; see n8n/README.md)
powershell -ExecutionPolicy Bypass -File n8n\bootstrap.ps1

# 4. Application (builds images, runs migrations, starts api/worker/ui)
docker compose -f app/docker-compose.yml up -d --build
```

Open http://localhost:3000 — add a repository
(`POST /api/repositories/onboard`), wait for `READY`, then ask questions.

### Ports

| Service | Host port |
|---|---|
| Frontend | 3000 |
| FastAPI | 8000 |
| n8n | 5678 |
| PostgreSQL | 5433 |
| Kafka | 9092 |
| ChromaDB | 8100 |

## API

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | open | Honest health: `200 {"status":"ok","checks":{...}}` / `503 degraded` when PG or Chroma is down |
| `GET /api/repositories` | open | List repositories + sync status |
| `POST /api/repositories/onboard` | `X-API-Key` | Register a repo, enqueue backfill |
| `POST /api/repositories/{id}/resync` | `X-API-Key` | Re-enqueue backfill |
| `POST /api/query` | `X-API-Key` | RAG question → `{answer, references[]}` with commit/file citations |

Auth is enabled only when `KYRO_API_KEY` is set (constant-time compare;
dev mode without it). The browser never holds the key — the Next.js proxy
injects it server-side.

Query gating: `409` SYNCING/SYNC_FAILED, `403` ACCESS_REVOKED, `404` unknown
repo, `503` retrieval failure, `502` LLM failure — messages surfaced verbatim.

## Development

```powershell
# Backend (Python 3.13 venv in backend/.venv)
cd backend
python -m pip install -r requirements.txt
python -m pytest tests/ -q          # 76 tests
python -m ruff check app tests alembic
python -m pyright app tests alembic

# Frontend
cd frontend
npm ci
npm run lint
npm run build
```

CI runs the same gates on every push (`.github/workflows/ci.yml`).

## Secrets

- Root `.env` — runtime secrets (`GEMINI_API_KEY`, `KYRO_API_KEY`), gitignored.
- `.env.example` — committed template with HOST/Docker/PROD URL blocks.
- Docker-internal URLs are hard-coded in `app/docker-compose.yml`
  (`DATABASE_URL`, `CHROMA_URL`, `KAFKA_BOOTSTRAP_SERVERS`) and always
  override `.env`.
- n8n credentials live encrypted inside volume `n8n_data` and are never
  committed. GitHub App credentials (`GITHUB_APP_*`) are optional — without
  them private-repo ingestion fails visibly (FAILED events), it is never faked.

## Component docs

- [backend/README.md](backend/README.md) — API dev setup
- [frontend/README.md](frontend/README.md) — UI dev setup
- [n8n/README.md](n8n/README.md) — webhook → Kafka contract, fresh-deploy steps
- [kafka/README.md](kafka/README.md) — topic bootstrap
