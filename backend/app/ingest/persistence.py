"""PostgreSQL persistence for ingestion events (source of truth).

All writes are idempotent:
  * commits  upserted on (repository_id, github_commit_sha)
  * files    upserted on (repository_id, path)
  * commit_files upserted on (commit_id, file_id)
  * files.current_content updated only when the incoming commit is not older
    than the current basis (out-of-order guards for deferred live events)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Commit,
    CommitFile,
    File,
    GithubInstallation,
    Repository,
    RepositoryStatus,
)
from app.ingest.content import ContentResolver
from app.schemas.events import ChangeBlock, CommitBlock, IngestionEventPayload

log = logging.getLogger("kyro.persistence")

STATUS_MAP = {
    "added": "added",
    "modified": "modified",
    "changed": "modified",
    "removed": "deleted",
    "deleted": "deleted",
    "renamed": "renamed",
    "copied": "copied",
    "unchanged": "unchanged",
}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _norm_status(status: str) -> str:
    return STATUS_MAP.get(status, status or "modified")


@dataclass
class IndexItem:
    repository_pk: int
    github_repository_id: int
    commit_pk: int
    commit_sha: str
    file_pk: int
    path: str
    status: str
    patch: str | None
    commit_message: str | None
    committed_at: datetime | None
    additions: int
    deletions: int


@dataclass
class ApplyResult:
    repository: Repository
    index_items: list[IndexItem] = field(default_factory=list)


def resolve_repository(
    session: Session, payload: IngestionEventPayload, *, lock: bool = True
) -> Repository:
    """Get-or-create the repository row; NEVER changes synchronization status.

    Ownership invariant (multi-user isolation): this function NEVER reads or
    writes `owner_user_id` from event data. For an existing row the KYRO
    owner is whatever PostgreSQL already records; a row created here stays
    unowned (owner_user_id IS NULL) until the onboarding API claims it -
    event payloads carry no trusted user identity and must never assign one.
    """
    q = select(Repository).where(
        Repository.github_repository_id == payload.repository.github_id
    )
    if lock:
        q = q.with_for_update()
    repo = session.scalar(q)
    rb = payload.repository
    installation_id = payload.installation.github_installation_id

    if repo is None:
        repo = Repository(
            github_repository_id=rb.github_id,
            name=rb.name,
            full_name=rb.full_name,
            owner=rb.owner,
            is_private=rb.private,
            default_branch=rb.default_branch,
            url=rb.url,
            github_installation_id=installation_id,
            status=RepositoryStatus.SYNCING.value,
            sync_started_at=datetime.now(UTC),
        )
        session.add(repo)
        session.flush()
        log.info(
            "repository_created repository_id=%d github_repository_id=%d",
            repo.id,
            rb.github_id,
        )
    else:
        repo.name = rb.name
        repo.full_name = rb.full_name
        repo.owner = rb.owner
        repo.is_private = rb.private
        if rb.default_branch:
            repo.default_branch = rb.default_branch
        if rb.url:
            repo.url = rb.url
        if installation_id is not None:
            repo.github_installation_id = installation_id

    if installation_id is not None:
        inst = session.scalar(
            select(GithubInstallation)
            .where(GithubInstallation.github_installation_id == installation_id)
            .with_for_update()
        )
        if inst is None:
            session.add(GithubInstallation(github_installation_id=installation_id))
    session.flush()
    return repo


def _upsert_commit(
    session: Session,
    repo: Repository,
    cb: CommitBlock,
    parent_sha: str | None,
) -> tuple[Commit, bool]:
    existing = session.scalar(
        select(Commit).where(
            Commit.repository_id == repo.id,
            Commit.github_commit_sha == cb.sha,
        )
    )
    if existing is not None:
        if existing.message is None and cb.message:
            existing.message = cb.message
        if existing.committed_at is None and cb.timestamp:
            existing.committed_at = _parse_ts(cb.timestamp)
        if existing.parent_sha is None and parent_sha:
            existing.parent_sha = parent_sha
        if existing.author_name is None and cb.author.name:
            existing.author_name = cb.author.name
            existing.author_email = cb.author.email
        if existing.committer_name is None and cb.committer.name:
            existing.committer_name = cb.committer.name
            existing.committer_email = cb.committer.email
        return existing, False

    commit = Commit(
        repository_id=repo.id,
        github_commit_sha=cb.sha,
        parent_sha=parent_sha,
        author_name=cb.author.name,
        author_email=cb.author.email,
        author_username=cb.author.username,
        committer_name=cb.committer.name,
        committer_email=cb.committer.email,
        committer_username=cb.committer.username,
        message=cb.message,
        committed_at=_parse_ts(cb.timestamp),
    )
    session.add(commit)
    session.flush()
    return commit, True


def _upsert_file(session: Session, repo: Repository, path: str) -> File:
    existing = session.scalar(
        select(File).where(File.repository_id == repo.id, File.path == path)
    )
    if existing is not None:
        return existing
    f = File(repository_id=repo.id, path=path)
    session.add(f)
    session.flush()
    return f


@dataclass
class Attribution:
    commit: CommitBlock
    path: str
    status: str
    change: ChangeBlock | None


def _attribute(payload: IngestionEventPayload) -> list[Attribution]:
    """Map changes to the commits that carried them.

    Backfill events carry exactly one commit and its own change list. Live
    events carry the push's commit lists (added/modified/removed) plus the
    compare-level change list; attribution uses the commit lists and any
    leftover compare changes attach to the push head commit so nothing is
    silently dropped.
    """
    changes_by_path = {c.path: c for c in payload.changes}
    attributions: list[Attribution] = []
    claimed: set[str] = set()

    if payload.is_backfill or len(payload.commits) <= 1:
        commit = payload.commits[0] if payload.commits else None
        if commit is not None:
            for ch in payload.changes:
                attributions.append(
                    Attribution(commit, ch.path, _norm_status(ch.status), ch)
                )
                claimed.add(ch.path)
            # commit list paths not present in compare results (truncated)
            for path in commit.added:
                if path not in claimed:
                    attributions.append(Attribution(commit, path, "added", None))
                    claimed.add(path)
            for path in commit.modified:
                if path not in claimed:
                    attributions.append(Attribution(commit, path, "modified", None))
                    claimed.add(path)
            for path in commit.removed:
                if path not in claimed:
                    attributions.append(Attribution(commit, path, "deleted", None))
                    claimed.add(path)
        else:
            attributions.extend(
                Attribution(
                    _orphan_commit(payload), ch.path, _norm_status(ch.status), ch
                )
                for ch in payload.changes
            )
        return attributions

    for cb in payload.commits:
        for path in cb.added:
            ch = changes_by_path.get(path)
            attributions.append(Attribution(cb, path, "added", ch))
            claimed.add(path)
        for path in cb.modified:
            ch = changes_by_path.get(path)
            status = _norm_status(ch.status) if ch else "modified"
            attributions.append(Attribution(cb, path, status, ch))
            claimed.add(path)
        for path in cb.removed:
            ch = changes_by_path.get(path)
            status = _norm_status(ch.status) if ch else "deleted"
            attributions.append(Attribution(cb, path, status, ch))
            claimed.add(path)

    head = next(
        (c for c in payload.commits if c.sha == payload.push.after),
        payload.commits[-1] if payload.commits else None,
    )
    if head is not None:
        for ch in payload.changes:
            if ch.path not in claimed:
                attributions.append(
                    Attribution(head, ch.path, _norm_status(ch.status), ch)
                )
                claimed.add(ch.path)
    return attributions


def _orphan_commit(payload: IngestionEventPayload) -> CommitBlock:
    return CommitBlock(sha=payload.push.after or "unknown")


def _guard_time(payload: IngestionEventPayload) -> datetime:
    after = payload.push.after
    for cb in payload.commits:
        if cb.sha == after and cb.timestamp:
            ts = _parse_ts(cb.timestamp)
            if ts:
                return ts
    times = [t for t in (_parse_ts(cb.timestamp) for cb in payload.commits) if t]
    return max(times) if times else datetime.now(UTC)


def _parent_for(payload: IngestionEventPayload, cb: CommitBlock) -> str | None:
    if payload.backfill is not None and cb.sha == payload.push.after:
        return payload.backfill.parent_sha
    if cb.sha == payload.push.after and payload.push.before:
        before = payload.push.before
        if before and set(before) != {"0"}:
            return before
    return None


def apply_payload(
    session: Session,
    payload: IngestionEventPayload,
    *,
    resolver: ContentResolver | None,
    update_current: bool = True,
    lock: bool = True,
) -> ApplyResult:
    repo = resolve_repository(session, payload, lock=lock)
    guard_at = _guard_time(payload)

    # Commits first so commit_files can reference their ids.
    commit_ids: dict[str, int] = {}
    commit_blocks: dict[str, CommitBlock] = {}
    for cb in payload.commits:
        commit, _ = _upsert_commit(session, repo, cb, _parent_for(payload, cb))
        commit_ids[cb.sha] = commit.id
        commit_blocks[cb.sha] = cb

    attributions = _attribute(payload)
    result = ApplyResult(repository=repo)
    ref = payload.push.after or ""

    for attr in attributions:
        file_row = _upsert_file(session, repo, attr.path)

        content_to_set: str | object | None
        blob_to_set: str | None = None
        if attr.status == "deleted":
            content_to_set = None if update_current else _UNSET
            blob_to_set = attr.change.sha if attr.change else None
        elif update_current and resolver is not None and ref:
            known = file_row.current_content
            resolved = resolver.resolve(
                path=attr.path,
                status=attr.status,
                patch=attr.change.patch if attr.change else None,
                expected_blob_sha=attr.change.sha if attr.change else None,
                ref=ref,
                known_content=known,
            )
            content_to_set = resolved.content
            blob_to_set = resolved.blob_sha
        else:
            content_to_set = _UNSET

        _apply_file_state(
            file_row,
            content=content_to_set,
            blob_sha=blob_to_set,
            guard_at=guard_at,
            commit_sha=ref or None,
        )

        # Renames must also retire the previous path.
        if attr.change is not None and attr.change.previous_path:
            old = _upsert_file(session, repo, attr.change.previous_path)
            _apply_file_state(
                old,
                content=None,
                blob_sha=None,
                guard_at=guard_at,
                commit_sha=ref or None,
            )
            old_commit = commit_blocks.get(attr.commit.sha)
            if old_commit is None:
                old_commit = attr.commit
            _upsert_commit_file(
                session,
                commit_ids[attr.commit.sha],
                old.id,
                status="deleted",
                additions=0,
                deletions=0,
                changes=0,
                patch=None,
                previous_path=None,
            )
            result.index_items.append(
                IndexItem(
                    repository_pk=repo.id,
                    github_repository_id=repo.github_repository_id,
                    commit_pk=commit_ids[attr.commit.sha],
                    commit_sha=attr.commit.sha,
                    file_pk=old.id,
                    path=attr.change.previous_path,
                    status="deleted",
                    patch=None,
                    commit_message=old_commit.message,
                    committed_at=_parse_ts(old_commit.timestamp),
                    additions=0,
                    deletions=0,
                )
            )

        _upsert_commit_file(
            session,
            commit_ids[attr.commit.sha],
            file_row.id,
            status=attr.status,
            additions=attr.change.additions if attr.change else 0,
            deletions=attr.change.deletions if attr.change else 0,
            changes=attr.change.changes if attr.change else 0,
            patch=attr.change.patch if attr.change else None,
            previous_path=attr.change.previous_path if attr.change else None,
        )
        cb_default: CommitBlock = attr.commit
        cb_found = commit_blocks.get(attr.commit.sha)
        cb: CommitBlock = cb_found if cb_found is not None else cb_default
        result.index_items.append(
            IndexItem(
                repository_pk=repo.id,
                github_repository_id=repo.github_repository_id,
                commit_pk=commit_ids[attr.commit.sha],
                commit_sha=attr.commit.sha,
                file_pk=file_row.id,
                path=attr.path,
                status=attr.status,
                patch=attr.change.patch if attr.change else None,
                commit_message=cb.message,
                committed_at=_parse_ts(cb.timestamp),
                additions=attr.change.additions if attr.change else 0,
                deletions=attr.change.deletions if attr.change else 0,
            )
        )

    # Backfill progress: this event's commit is now synchronized.
    if payload.is_backfill and payload.push.after:
        repo.synced_through_commit = payload.push.after

    session.flush()
    return result


class _Unset:
    def __repr__(self) -> str:  # pragma: no cover
        return "<UNSET>"


_UNSET = _Unset()


def _apply_file_state(
    file_row: File,
    *,
    content: str | _Unset | None,
    blob_sha: str | None,
    guard_at: datetime,
    commit_sha: str | None,
) -> None:
    if not isinstance(content, _Unset):
        basis = file_row.current_content_commit_at
        # Out-of-order guard: never let an older commit overwrite a newer
        # current_content (deferred live events flush after backfill).
        if basis is None or guard_at >= basis:
            file_row.current_content = content
            file_row.current_content_commit_sha = commit_sha
            file_row.current_content_commit_at = guard_at
            file_row.is_deleted = content is None
            if blob_sha:
                file_row.blob_sha = blob_sha


def _upsert_commit_file(
    session: Session,
    commit_id: int,
    file_id: int,
    *,
    status: str,
    additions: int,
    deletions: int,
    changes: int,
    patch: str | None,
    previous_path: str | None,
) -> CommitFile:
    existing = session.scalar(
        select(CommitFile).where(
            CommitFile.commit_id == commit_id, CommitFile.file_id == file_id
        )
    )
    if existing is not None:
        existing.status = status
        existing.additions = additions
        existing.deletions = deletions
        existing.changes = changes
        if patch is not None:
            existing.patch = patch
        if previous_path is not None:
            existing.previous_path = previous_path
        return existing
    row = CommitFile(
        commit_id=commit_id,
        file_id=file_id,
        status=status,
        additions=additions,
        deletions=deletions,
        changes=changes,
        patch=patch,
        previous_path=previous_path,
    )
    session.add(row)
    session.flush()
    return row
