"""ChromaDB semantic index (NOT the source of truth).

Every item carries PostgreSQL primary keys (repository_id / commit_id /
file_id) as metadata so the index is deterministically bridgeable back to the
authoritative rows and can be rebuilt from PostgreSQL at any time.

Document IDs are deterministic (repository_pk:commit_sha:path) so indexing is
idempotent: re-running after a retry overwrites instead of duplicating.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app import config
from app.ingest.persistence import IndexItem

if TYPE_CHECKING:
    from chromadb.api.types import Metadata

log = logging.getLogger("kyro.indexer")


class IndexError_(RuntimeError):
    """ChromaDB indexing failure (keeps the event retryable)."""


@dataclass
class QueryHit:
    document: str
    metadata: dict
    distance: float | None = None


def build_doc_id(item: IndexItem) -> str:
    return f"{item.repository_pk}:{item.commit_sha}:{item.path}"


def build_document(item: IndexItem) -> str:
    header = f"repository={item.commit_sha[:12]} file={item.path} status={item.status}"
    msg = (item.commit_message or "").strip()
    patch = (item.patch or "").strip()
    parts = [f"Commit: {msg}" if msg else "", header]
    if patch:
        parts.append(f"Diff:\n{patch}")
    return "\n\n".join(p for p in parts if p)


class ChromaIndexer:
    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
        client=None,
    ) -> None:
        self.url = url or config.CHROMA_URL
        self.collection_name = collection_name or config.CHROMA_COLLECTION
        if client is not None:
            self._client = client
        else:
            import chromadb

            self._client = chromadb.HttpClient(
                host=_host_of(self.url), port=_port_of(self.url)
            )
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def index_event(self, items: list[IndexItem]) -> int:
        """Upsert semantic chunks for one event's changes. Idempotent."""
        if not items:
            return 0
        ids = [build_doc_id(i) for i in items]
        documents = [build_document(i) for i in items]
        metadatas = [_metadata(i) for i in items]
        try:
            # Batched upsert keeps payload sizes bounded for large pushes.
            step = 100
            for start in range(0, len(ids), step):
                self.collection.upsert(
                    ids=ids[start : start + step],
                    documents=documents[start : start + step],
                    metadatas=metadatas[start : start + step],
                )
        except Exception as exc:  # chroma client raises its own error types
            raise IndexError_(f"chroma upsert failed: {exc}") from exc
        log.info(
            "chroma_indexed count=%d collection=%s", len(ids), self.collection_name
        )
        return len(ids)

    def count(self) -> int:
        try:
            return int(self.collection.count())
        except Exception as exc:
            raise IndexError_(f"chroma count failed: {exc}") from exc

    def search(
        self,
        query: str,
        *,
        repository_pk: int,
        n_results: int = 8,
    ) -> list[QueryHit]:
        try:
            res = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"repository_id": repository_pk},
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise IndexError_(f"chroma query failed: {exc}") from exc
        hits: list[QueryHit] = []
        for docs, metas, dists in zip(
            res.get("documents") or [],
            res.get("metadatas") or [],
            res.get("distances") or [],
            strict=True,
        ):
            for doc, meta, dist in zip(docs, metas, dists, strict=True):
                hits.append(
                    QueryHit(document=doc, metadata=dict(meta or {}), distance=dist)
                )
        return hits

    def reset(self) -> None:
        """Test helper: drop and recreate the collection (local/dev only)."""
        with contextlib.suppress(Exception):
            self._client.delete_collection(self.collection_name)
        self._collection = None


def _metadata(item: IndexItem) -> Metadata:
    meta = {
        # Deterministic bridge to PostgreSQL (locked requirement).
        "repository_id": item.repository_pk,
        "commit_id": item.commit_pk,
        "file_id": item.file_pk,
        "github_repository_id": item.github_repository_id,
        "commit_sha": item.commit_sha,
        "path": item.path,
        "status": item.status,
    }
    if item.committed_at is not None:
        meta["committed_at"] = item.committed_at.isoformat()
    if item.additions:
        meta["additions"] = item.additions
    if item.deletions:
        meta["deletions"] = item.deletions
    return meta


def _host_of(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.hostname or "localhost"


def _port_of(url: str) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.port or (443 if parsed.scheme == "https" else 80)
