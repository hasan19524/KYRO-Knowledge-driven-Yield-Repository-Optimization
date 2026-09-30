import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import gemini_service
from app.api.repositories import router as repositories_router
from app.state import AppState, build_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from app import config  # noqa: E402  (after logging config)


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    class ChatRequest(BaseModel):
        message: str

    class ChatResponse(BaseModel):
        response: str

    @app.post("/api/chat", response_model=ChatResponse)
    def chat_endpoint(request: ChatRequest):
        if not request.message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        try:
            reply = gemini_service.chat(request.message)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Gemini API error: {exc}"
            ) from exc

        return ChatResponse(response=reply)

    app.include_router(repositories_router)
    return app


app = create_app()
