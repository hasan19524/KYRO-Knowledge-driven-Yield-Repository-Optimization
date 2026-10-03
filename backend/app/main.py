import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.repositories import router as repositories_router
from app.api.users import router as users_router
from app.state import AppState, build_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app import config  # noqa: E402  (after logging config)

log = logging.getLogger("kyro.main")


def _check_postgres(state: AppState) -> str:
    try:
        with state.session_factory() as session:
            session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _check_chroma(state: AppState) -> str:
    try:
        ping = getattr(state.indexer, "ping", None)
        if callable(ping):
            ping()
        else:
            state.indexer.count()
        return "ok"
    except Exception:
        return "error"


def create_app(state: AppState | None = None) -> FastAPI:
    """Build the FastAPI app.

    state=None (production) wires the real components at startup and starts
    the sync supervisor (crash recovery for interrupted SYNCING runs).
    Tests pass a pre-built state; the supervisor only starts when enabled in
    config.
    """
    supplied = state

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        auto_built = supplied is None
        app_state = supplied if supplied is not None else build_state()
        app.state.kyro = app_state
        supervisor = None
        # Supervisor only runs for the production (self-built) wiring so
        # injected test states never spawn background sync threads.
        if auto_built and config.SYNC_SUPERVISOR_ENABLED:
            from app.sync.supervisor import SyncSupervisor

            supervisor = SyncSupervisor(app_state.sync_manager)
            supervisor.start()
        try:
            yield
        finally:
            if supervisor is not None:
                supervisor.stop()
                supervisor.join(timeout=5)
            app_state.shutdown()

    app = FastAPI(title="KYRO Backend", version="0.1.0", lifespan=lifespan)

    if not config.KYRO_API_KEY:
        log.warning(
            "KYRO_API_KEY is not set; requests are unauthenticated and act "
            "as the legacy 'default' user (development mode only)"
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check(request: Request) -> JSONResponse:
        """Honest readiness: 503 until every query-path dependency answers."""
        state: AppState | None = getattr(request.app.state, "kyro", None)
        if state is None:
            return JSONResponse(
                status_code=503,
                content={"status": "starting", "checks": {}},
            )
        checks = {
            "postgres": _check_postgres(state),
            "chroma": _check_chroma(state),
        }
        ready = all(v == "ok" for v in checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ok" if ready else "degraded", "checks": checks},
        )

    app.include_router(repositories_router)
    app.include_router(users_router)
    return app


app = create_app()
