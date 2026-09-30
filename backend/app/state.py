"""Application state container (shared singletons for API + supervisor)."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app import config, gemini_service
from app.db import get_session_factory
from app.github.auth import GitHubAppAuth
from app.github.backfill import BackfillService
from app.github.client import GitHubClient
from app.ingest.indexer import ChromaIndexer
from app.ingest.processor import EventProcessor
from app.sync.manager import SyncManager

log = logging.getLogger("kyro.state")


@dataclass
class AppState:
    session_factory: sessionmaker[Session]
    indexer: ChromaIndexer
    github_client: GitHubClient
    processor: EventProcessor
    backfill: BackfillService
    sync_manager: SyncManager
    llm: Callable[[str], str]

    def shutdown(self) -> None:
        self.sync_manager.shutdown(wait=False)
        with contextlib.suppress(Exception):
            self.github_client.close()


def build_state(
    *,
    session_factory: sessionmaker[Session] | None = None,
    indexer: ChromaIndexer | None = None,
    github_client: GitHubClient | None = None,
    llm: Callable[[str], str] | None = None,
) -> AppState:
    """Assemble the production wiring. Tests inject their own components."""
    sf = session_factory or get_session_factory()
    gh = github_client or GitHubClient(GitHubAppAuth())
    idx = indexer or ChromaIndexer()
    processor = EventProcessor(sf, idx, gh)
    backfill = BackfillService(gh)
    manager = SyncManager(sf, backfill, processor, gh)
    return AppState(
        session_factory=sf,
        indexer=idx,
        github_client=gh,
        processor=processor,
        backfill=backfill,
        sync_manager=manager,
        llm=llm or gemini_service.chat,
    )


__all__ = ["AppState", "build_state", "config"]
