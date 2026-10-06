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
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://kyro:kyro@localhost:5433/kyro"
)
CHROMA_URL: str = os.getenv("CHROMA_URL", "http://localhost:8100")
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "kyro_changes")

# --- Kafka -----------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
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

# --- Abuse controls (security audit remediation) ---------------------------
# Per-user fixed-window rate limits (requests per minute, 0 disables).
# Enforced in-process per API worker; see app/security/ratelimit.py.
RATE_LIMIT_QUERY_PER_MIN: int = _int("RATE_LIMIT_QUERY_PER_MIN", 60)
RATE_LIMIT_RESYNC_PER_MIN: int = _int("RATE_LIMIT_RESYNC_PER_MIN", 10)
# Upper bound on question length (LLM cost control; enforced by request
# validation with 422 before the handler runs).
QUERY_MAX_QUESTION_CHARS: int = _int("QUERY_MAX_QUESTION_CHARS", 2000)
