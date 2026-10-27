import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
# models/gemini-2.0-flash was retired upstream (404); override via env when
# Google rotates model versions again.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# --- LLM provider fallback chain --------------------------------------------
# Query answers try providers in this order (comma-separated); the first
# success wins, any failure falls through to the next (see app/llm_chain.py).
# Ingestion never uses an LLM.
LLM_PROVIDER_ORDER: list[str] = [
    p.strip()
    for p in os.getenv("LLM_PROVIDER_ORDER", "opencode,nvidia,openrouter,gemini").split(
        ","
    )
    if p.strip()
]
# Per-attempt budget: each HTTP provider gets one bounded request.
LLM_HTTP_TIMEOUT_S: float = _float("LLM_HTTP_TIMEOUT_S", 60.0)
# OpenCode Zen (Console, OpenAI-compatible inference endpoint). The slot is
# key-gated: without OPENCODE_API_KEY the chain skips opencode entirely
# (the free zen tier refuses external HTTP callers — no workaround).
OPENCODE_API_KEY: str = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_BASE_URL: str = os.getenv(
    "OPENCODE_BASE_URL", "https://opencode.ai/inference/v1"
).rstrip("/")
OPENCODE_MODEL: str = os.getenv("OPENCODE_MODEL", "mimo-v2.6-flash-free")
# NVIDIA NIM (OpenAI-compatible).
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL: str = os.getenv(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
).rstrip("/")
NVIDIA_MODEL: str = os.getenv("NVIDIA_MODEL", "z-ai/glm-5.3-flash")
# OpenRouter (OpenAI-compatible).
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.8-omni-flash")

# --- API authentication ----------------------------------------------------
# Shared secret required (as X-API-Key) on mutation and query endpoints.
# Unset => authentication disabled (local development only). Production must
# set it in .env; the Next.js proxy injects it server-side so the browser
# never sees the value.
KYRO_API_KEY: str = os.getenv("KYRO_API_KEY", "")

# --- Security surface (audit remediation) ----------------------------------
# Interactive API docs (/docs, /redoc) and the OpenAPI schema:
#   auto (default) = enabled only in development (KYRO_API_KEY unset);
#   on / off       = explicit override either way.
KYRO_DOCS: str = os.getenv("KYRO_DOCS", "auto").strip().lower()
# Allowed browser origins for CORS (comma-separated). Local frontend only by
# default; production sets the deployed frontend origin(s).
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# --- Data stores -----------------------------------------------------------
# NOTE: host port 5432 belongs to an existing native PostgreSQL that KYRO does
# not own; KYRO's own cluster publishes on 5433 (see infra/docker-compose.yml).
# Host-side defaults use 127.0.0.1 instead of "localhost": "localhost" resolves
# IPv6-first (::1) on Windows and mishandled ::1 connects stall libpq for the
# full connect_timeout. Docker/container runs always override via env
# (app/docker-compose.yml), so only host-run defaults are affected.
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://kyro:kyro@127.0.0.1:5433/kyro"
)
CHROMA_URL: str = os.getenv("CHROMA_URL", "http://127.0.0.1:8100")
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "kyro_changes")

# --- Kafka -----------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
LIVE_TOPIC: str = "kyro.github.push"
BACKFILL_TOPIC: str = "kyro.github.backfill"
CONSUMER_GROUP: str = "kyro-ingestion-workers"
KAFKA_PARTITIONS: int = _int("KAFKA_PARTITIONS", 5)
KAFKA_RETENTION_MS: int = 7 * 24 * 60 * 60 * 1000  # 7 days (locked)
KAFKA_MIN_INSYNC_REPLICAS: int = _int("KAFKA_MIN_INSYNC_REPLICAS", 1)

# --- Worker ----------------------------------------------------------------
WORKER_CONCURRENCY: int = _int("WORKER_CONCURRENCY", 2)
WORKER_POLL_TIMEOUT_MS: int = _int("WORKER_POLL_TIMEOUT_MS", 2000)
MAX_EVENT_ATTEMPTS: int = _int("MAX_EVENT_ATTEMPTS", 5)
EVENT_RETRY_BASE_DELAY_S: float = _float("EVENT_RETRY_BASE_DELAY_S", 0.5)
EVENT_RETRY_MAX_DELAY_S: float = _float("EVENT_RETRY_MAX_DELAY_S", 4.0)

# --- GitHub App ------------------------------------------------------------
GITHUB_API_BASE_URL: str = os.getenv(
    "GITHUB_API_BASE_URL", "https://api.github.com"
).rstrip("/")
GITHUB_APP_ID: str = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY: str = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
GITHUB_APP_PRIVATE_KEY_PATH: str = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "")
GITHUB_APP_INSTALLATION_ID: str = os.getenv("GITHUB_APP_INSTALLATION_ID", "")

# --- GitHub App OAuth (user sign-in, additive) ------------------------------
# client_id is the App's OAuth Client ID (shown on the GitHub App page;
# distinct from GITHUB_APP_ID). secret = "Client secrets" section.
GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
# Web (HTML) origin for the authorize/token endpoints (not api.github.com).
GITHUB_WEB_BASE_URL: str = os.getenv(
    "GITHUB_WEB_BASE_URL", "https://github.com"
).rstrip("/")
# Public origin of the frontend OAuth bounces through (tunnel URL or
# http://127.0.0.1:3001). Normally supplied per-request by the Next.js
# proxy (X-Kyro-Self-Origin); this env is the manual fallback.
KYRO_PUBLIC_URL: str = os.getenv("KYRO_PUBLIC_URL", "").rstrip("/")

GITHUB_TIMEOUT_S: float = _float("GITHUB_TIMEOUT_S", 30.0)
GITHUB_MAX_RETRIES: int = _int("GITHUB_MAX_RETRIES", 5)
GITHUB_DETAIL_CONCURRENCY: int = _int("GITHUB_DETAIL_CONCURRENCY", 4)
GITHUB_RATE_LIMIT_MAX_WAIT_S: float = _float("GITHUB_RATE_LIMIT_MAX_WAIT_S", 60.0)

# --- Synchronization -------------------------------------------------------
SYNC_POLL_INTERVAL_S: float = _float("SYNC_POLL_INTERVAL_S", 0.25)
SYNC_TIMEOUT_S: float = _float("SYNC_TIMEOUT_S", 300.0)
# Bounded number of repositories synchronized concurrently (internal parameter).
SYNC_CONCURRENCY: int = _int("SYNC_CONCURRENCY", 2)
# Backfill events published/flushed per durability batch before the published
# boundary is advanced in PostgreSQL (bounded Kafka messages + safe resume).
SYNC_PUBLISH_BATCH: int = _int("SYNC_PUBLISH_BATCH", 50)
# Supervisor loop (crash recovery of interrupted SYNCING runs).
SYNC_SUPERVISOR_ENABLED: bool = os.getenv("SYNC_SUPERVISOR_ENABLED", "1") != "0"
SYNC_SUPERVISOR_INTERVAL_S: float = _float("SYNC_SUPERVISOR_INTERVAL_S", 5.0)

# --- Query ------------------------------------------------------------------
QUERY_TOP_K: int = _int("QUERY_TOP_K", 8)
QUERY_CONTEXT_MAX_CHARS: int = _int("QUERY_CONTEXT_MAX_CHARS", 6000)
QUERY_PATCH_MAX_CHARS: int = _int("QUERY_PATCH_MAX_CHARS", 1500)
# Retrieval quality (ported from Maaz's RAG deliverable, Phase 3a):
# over-fetch factor applied to top-K at the Chroma call so duplicate
# copies of a chunk cannot crowd distinct chunks out of the window before
# de-duplication, and a cosine similarity floor (similarity = 1 -
# distance; verified against this cluster) that keeps obviously-unrelated
# noise out of the LLM context.
QUERY_RETRIEVAL_OVERFETCH: int = max(1, _int("QUERY_RETRIEVAL_OVERFETCH", 4))
QUERY_SIMILARITY_THRESHOLD: float = _float("QUERY_SIMILARITY_THRESHOLD", 0.1)

# --- Abuse controls (security audit remediation) ---------------------------
# Per-user fixed-window rate limits (requests per minute, 0 disables).
# Enforced in-process per API worker; see app/security/ratelimit.py.
RATE_LIMIT_QUERY_PER_MIN: int = _int("RATE_LIMIT_QUERY_PER_MIN", 60)
RATE_LIMIT_RESYNC_PER_MIN: int = _int("RATE_LIMIT_RESYNC_PER_MIN", 10)
# Upper bound on question length (LLM cost control; enforced by request
# validation with 422 before the handler runs).
QUERY_MAX_QUESTION_CHARS: int = _int("QUERY_MAX_QUESTION_CHARS", 2000)

# --- Account login (additive sessions) -------------------------------------
# Server-side session lifetime; expiry is enforced on every request and
# the session row can be deleted early (logout) at any time.
AUTH_SESSION_TTL_HOURS: int = _int("AUTH_SESSION_TTL_HOURS", 168)
# Pre-auth fixed-window limits keyed on the normalized email (0 disables).
RATE_LIMIT_REGISTER_PER_MIN: int = _int("RATE_LIMIT_REGISTER_PER_MIN", 10)
RATE_LIMIT_LOGIN_PER_MIN: int = _int("RATE_LIMIT_LOGIN_PER_MIN", 10)
