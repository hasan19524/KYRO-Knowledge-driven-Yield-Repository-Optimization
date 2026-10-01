"""Repository onboarding/status API + gated query endpoint.

Query gating (locked §13 / §76 CASE 6):
  SYNCING        -> 409 "Repository synchronization is in progress. ..."
  SYNC_FAILED    -> 409 (knowledge may be incomplete; requires re-sync)
  ACCESS_REVOKED -> 403 (re-authorize the KYRO GitHub App)
  READY          -> ChromaDB retrieval -> ranking/filtering -> PostgreSQL
                    enrichment -> context assembly -> LLM answer
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_

from app import config
from app.api.auth import require_api_key
from app.db.models import Commit, CommitFile, File, Repository, RepositoryStatus
from app.ingest.indexer import IndexError_
from app.state import AppState

log = logging.getLogger("kyro.api")

router = APIRouter(prefix="/api", tags=["repositories"])

SYNCING_MESSAGE = (
    "Repository synchronization is in progress. "
    "Please wait until synchronization is complete."
)
SYNC_FAILED_MESSAGE = (
    "Repository synchronization failed; repository knowledge may be "
    "incomplete. Trigger a re-sync before querying."
)
ACCESS_REVOKED_MESSAGE = (
    "KYRO no longer has GitHub access to this repository. "
    "Re-authorize the KYRO GitHub App to restore access."
)


def get_state(request: Request) -> AppState:
    return request.app.state.kyro


# ------------------------------------------------------------------ schemas
class OnboardRequest(BaseModel):
    github_repository_id: int = Field(gt=0)
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    full_name: str | None = None
    installation_id: int | None = None
    default_branch: str | None = None
    private: bool = False
    url: str | None = None


class ResyncRequest(BaseModel):
    full: bool = False


class QueryRequest(BaseModel):
    github_repository_id: int = Field(gt=0)
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)


class Reference(BaseModel):
    commit_sha: str | None = None
    commit_message: str | None = None
    committed_at: str | None = None
    author: str | None = None
    path: str | None = None
    status: str | None = None
    additions: int = 0
    deletions: int = 0
    similarity_distance: float | None = None


class QueryResponse(BaseModel):
    status: str
    repository: str
    question: str
    answer: str
    references: list[Reference]
    chunks_considered: int


# ----------------------------------------------------------- repo endpoints
@router.post("/repositories/onboard", status_code=202)
def onboard(
    body: OnboardRequest,
    state: AppState = Depends(get_state),
    _: None = Depends(require_api_key),
) -> dict:
    return state.sync_manager.onboard(
        github_repository_id=body.github_repository_id,
        owner=body.owner,
        name=body.name,
        full_name=body.full_name,
        installation_id=body.installation_id,
        default_branch=body.default_branch,
        private=body.private,
        url=body.url,
        run=True,
    )


@router.get("/repositories")
def list_repositories(state: AppState = Depends(get_state)) -> list[dict]:
    return state.sync_manager.list_snapshots()


@router.get("/repositories/{github_repository_id}")
def get_repository(
    github_repository_id: int, state: AppState = Depends(get_state)
) -> dict:
    snap = state.sync_manager.snapshot(github_repository_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="repository not found")
    return snap


@router.post("/repositories/{github_repository_id}/resync", status_code=202)
def resync(
    github_repository_id: int,
    body: ResyncRequest | None = None,
    state: AppState = Depends(get_state),
    _: None = Depends(require_api_key),
) -> dict:
    snap = state.sync_manager.resync(
        github_repository_id, full=bool(body and body.full), run=True
    )
    if snap is None:
        raise HTTPException(status_code=404, detail="repository not found")
    return snap


# ------------------------------------------------------------------- query
@router.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    state: AppState = Depends(get_state),
    _: None = Depends(require_api_key),
) -> QueryResponse:
    session_factory = state.session_factory
    with session_factory() as session:
        repo = session.scalar(
            select(Repository).where(
                Repository.github_repository_id == body.github_repository_id
            )
        )
        if repo is None:
            raise HTTPException(status_code=404, detail="repository not found")

        if repo.status == RepositoryStatus.SYNCING.value:
            raise HTTPException(
                status_code=409,
                detail={"status": repo.status, "message": SYNCING_MESSAGE},
            )
        if repo.status == RepositoryStatus.SYNC_FAILED.value:
            raise HTTPException(
                status_code=409,
                detail={"status": repo.status, "message": SYNC_FAILED_MESSAGE},
            )
        if repo.status == RepositoryStatus.ACCESS_REVOKED.value:
            raise HTTPException(
                status_code=403,
                detail={"status": repo.status, "message": ACCESS_REVOKED_MESSAGE},
            )
        repo_pk = repo.id
        repo_full_name = repo.full_name

    # --- ChromaDB semantic retrieval (candidates carry PG references) ------
    top_k = body.top_k or config.QUERY_TOP_K
    try:
        hits = state.indexer.search(
            body.question, repository_pk=repo_pk, n_results=top_k
        )
    except IndexError_ as exc:
        log.error(
            "query_chroma_failed repository_id=%d error=%s",
            body.github_repository_id,
            str(exc)[:200],
        )
        raise HTTPException(
            status_code=503,
            detail="semantic index temporarily unavailable; retry shortly",
        ) from exc

    # --- ranking / filtering: similarity order, complete metadata only ----
    ranked = [
        h
        for h in sorted(hits, key=lambda h: (h.distance is None, h.distance))
        if h.metadata.get("commit_id") is not None
        and h.metadata.get("file_id") is not None
    ][:top_k]

    # --- PostgreSQL enrichment (single batched query, no N+1) -------------
    pairs = [(int(h.metadata["commit_id"]), int(h.metadata["file_id"])) for h in ranked]
    enriched: dict[tuple[int, int], tuple[Commit, CommitFile, File]] = {}
    if pairs:
        with session_factory() as session:
            rows = session.execute(
                select(Commit, CommitFile, File)
                .join(CommitFile, CommitFile.commit_id == Commit.id)
                .join(File, File.id == CommitFile.file_id)
                .where(
                    Commit.repository_id == repo_pk,
                    tuple_(Commit.id, CommitFile.file_id).in_(pairs),
                )
            ).all()
            for commit, commit_file, file_row in rows:
                enriched[(commit.id, commit_file.file_id)] = (
                    commit,
                    commit_file,
                    file_row,
                )

    # --- context assembly (bounded; only relevant context reaches the LLM)
    references: list[Reference] = []
    context_parts: list[str] = []
    used = 0
    for hit in ranked:
        key = (int(hit.metadata["commit_id"]), int(hit.metadata["file_id"]))
        bundle = enriched.get(key)
        if bundle is None:
            continue
        commit, commit_file, file_row = bundle
        ref = Reference(
            commit_sha=commit.github_commit_sha,
            commit_message=commit.message,
            committed_at=commit.committed_at.isoformat()
            if commit.committed_at
            else None,
            author=commit.author_name,
            path=file_row.path,
            status=commit_file.status,
            additions=commit_file.additions,
            deletions=commit_file.deletions,
            similarity_distance=hit.distance,
        )
        references.append(ref)

        patch = (commit_file.patch or "").strip()
        if len(patch) > config.QUERY_PATCH_MAX_CHARS:
            patch = patch[: config.QUERY_PATCH_MAX_CHARS] + "\n... [truncated]"
        block = (
            f"commit {commit.github_commit_sha[:12]} "
            f"({commit.committed_at.date().isoformat() if commit.committed_at else 'unknown date'}) "
            f"by {commit.author_name or 'unknown'}: "
            f"{(commit.message or '').strip()[:200]}\n"
            f"file: {file_row.path} [{commit_file.status}] "
            f"+{commit_file.additions} -{commit_file.deletions}\n"
        )
        if patch:
            block += f"diff:\n{patch}"
        if used + len(block) > config.QUERY_CONTEXT_MAX_CHARS:
            break
        context_parts.append(block)
        used += len(block)

    if not context_parts:
        # READY but no semantic chunks yet (e.g. empty index): still answer
        # honestly without dumping anything unrelated into the LLM.
        context = "No indexed changes matched this question for this repository."
    else:
        context = "\n\n".join(context_parts)

    prompt = (
        "You are KYRO, a repository intelligence assistant. Answer the user's "
        "question using ONLY the repository context below. If the context is "
        "insufficient, say so explicitly. Be concise and cite commit shas and "
        "file paths from the context when relevant.\n\n"
        f"Repository: {repo_full_name}\n\n"
        f"Repository context:\n{context}\n\n"
        f"Question: {body.question}"
    )
    try:
        answer = state.llm(prompt)
    except Exception as exc:
        log.error(
            "query_llm_failed repository_id=%d error=%s",
            body.github_repository_id,
            str(exc)[:200],
        )
        raise HTTPException(
            status_code=502, detail=f"LLM gateway error: {exc}"
        ) from exc

    return QueryResponse(
        status=RepositoryStatus.READY.value,
        repository=repo_full_name,
        question=body.question,
        answer=answer,
        references=references,
        chunks_considered=len(hits),
    )


__all__ = ["SYNCING_MESSAGE", "get_state", "router"]
