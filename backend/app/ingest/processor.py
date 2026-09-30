"""Event processing pipeline (validate -> idempotency -> persist -> index).

Phase boundaries (each individually durable):

  1. PostgreSQL tx: ingestion_events row + repository/commits/files/
     commit_files written atomically (pg_status=done on commit).
  2. ChromaDB upsert (deterministic ids -> idempotent).
  3. Mark event processed (index_status=done) -> caller may commit offset.

Live events for repositories that are not READY are DEFERRED: durably parked
in ingestion_events (status=deferred) and their Kafka offset committed, so
they can never overtake backfill for that repository AND cannot block other
repositories sharing the partition. The sync manager flushes the parked rows
in arrival order once backfill catches up.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Commit,
    CommitFile,
    EventKind,
    EventStatus,
    File,
    IngestionEvent,
    PhaseStatus,
    Repository,
    RepositoryStatus,
)
from app.github.client import (
    GitHubAuthError,
    GitHubClient,
    GitHubCredentialsMissing,
    GitHubError,
)
from app.ingest.content import ContentResolutionError, ContentResolver
from app.ingest.indexer import ChromaIndexer, IndexError_, QueryHit
from app.ingest.persistence import IndexItem, apply_payload, resolve_repository
from app.schemas.events import EventValidationError, IngestionEventPayload, parse_event

log = logging.getLogger("kyro.processor")


class HandleOutcome(enum.StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    DEFERRED = "deferred"
    INVALID = "invalid"
    RETRY = "retry"
    FAILED = "failed"


class IngestError(RuntimeError):
    """Base class for processing failures carrying a structured reason."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class TransientIngestError(IngestError):
    """Retryable (PostgreSQL/Chroma/GitHub transient)."""


class PermanentIngestError(IngestError):
    """Not retryable within this session (still no offset commit)."""


class EventProcessor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        indexer: ChromaIndexer,
        github_client: GitHubClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.indexer = indexer
        self.github_client = github_client

    # ------------------------------------------------------------------ API
    def handle_raw(
        self, raw: bytes, *, topic: str, partition: int, offset: int
    ) -> HandleOutcome:
        try:
            payload = parse_event(raw)
        except EventValidationError as exc:
            self._record_invalid(raw, topic, partition, offset, str(exc))
            log.error(
                "event_invalid topic=%s partition=%d offset=%d error=%s",
                topic,
                partition,
                offset,
                str(exc)[:200],
            )
            return HandleOutcome.INVALID

        try:
            return self._handle_payload(
                payload, topic=topic, partition=partition, offset=offset
            )
        except TransientIngestError as exc:
            log.warning(
                "event_retry topic=%s partition=%d offset=%d event_id=%s reason=%s error=%s",
                topic,
                partition,
                offset,
                payload.event.id,
                exc.reason,
                str(exc)[:200],
            )
            return HandleOutcome.RETRY
        except PermanentIngestError as exc:
            log.error(
                "event_permanent_failure topic=%s partition=%d offset=%d event_id=%s reason=%s error=%s",
                topic,
                partition,
                offset,
                payload.event.id,
                exc.reason,
                str(exc)[:200],
            )
            # The failing phase-1 tx rolled back, so no row exists yet:
            # durably record FAILED (event + repository SYNC_FAILED) BEFORE
            # the worker pauses the partition.
            self.mark_failure(raw, f"permanent_{exc.reason}: {exc}")
            return HandleOutcome.FAILED
        except Exception:  # unexpected bug -> retryable, never silent
            log.exception(
                "event_unexpected_error topic=%s partition=%d offset=%d event_id=%s",
                topic,
                partition,
                offset,
                payload.event.id,
            )
            return HandleOutcome.RETRY

    def mark_failure(self, raw: bytes, error: str) -> None:
        """Record an exhausted-retry/permanent failure durably.

        Creates the ingestion_events row when the failing transaction rolled
        back before ever committing one (phase-1 failures), so the failure is
        never silent. Also flips the repository to SYNC_FAILED so the query
        API stops answering from incomplete knowledge.
        """
        try:
            payload = parse_event(raw)
        except EventValidationError:
            return
        try:
            with self.session_factory() as session, session.begin():
                row = session.scalar(
                    select(IngestionEvent)
                    .where(IngestionEvent.event_id == payload.event.id)
                    .with_for_update()
                )
                if row is None:
                    row = IngestionEvent(
                        event_id=payload.event.id,
                        topic=None,
                        partition=None,
                        offset=None,
                        repository_github_id=payload.repository.github_id,
                        kind=(
                            EventKind.BACKFILL.value
                            if payload.is_backfill
                            else EventKind.LIVE.value
                        ),
                        status=EventStatus.FAILED.value,
                        payload=payload.model_dump(),
                        attempts=1,
                    )
                    session.add(row)
                row.status = EventStatus.FAILED.value
                row.error = error[:4000]
                row.updated_at = datetime.now(UTC)
                repo = resolve_repository(session, payload, lock=True)
                repo.last_error = error[:4000]
                # An unrecoverable event failure must not leave the repo
                # silently READY/SYNCING with incomplete knowledge.
                if repo.status in (
                    RepositoryStatus.SYNCING.value,
                    RepositoryStatus.READY.value,
                ):
                    repo.status = RepositoryStatus.SYNC_FAILED.value
                log.error(
                    "event_failed_persisted event_id=%s github_repository_id=%d error=%s",
                    payload.event.id,
                    payload.repository.github_id,
                    error[:200],
                )
        except Exception:
            log.exception("mark_failure_write_error event_id=%s", payload.event.id)

    # -------------------------------------------------------------- internals
    def _handle_payload(
        self,
        payload: IngestionEventPayload,
        *,
        topic: str,
        partition: int,
        offset: int,
    ) -> HandleOutcome:
        kind = EventKind.BACKFILL.value if payload.is_backfill else EventKind.LIVE.value
        index_items: list[IndexItem] | None = None

        with self.session_factory() as session, session.begin():
            row = session.scalar(
                select(IngestionEvent)
                .where(IngestionEvent.event_id == payload.event.id)
                .with_for_update()
            )
            if row is not None and row.status in (
                EventStatus.PROCESSED.value,
                EventStatus.DEFERRED.value,
                EventStatus.INVALID.value,
            ):
                log.info(
                    "skip_duplicate event_id=%s status=%s topic=%s partition=%d offset=%d",
                    row.event_id,
                    row.status,
                    topic,
                    partition,
                    offset,
                )
                return HandleOutcome.DUPLICATE

            if row is None:
                row = IngestionEvent(
                    event_id=payload.event.id,
                    topic=topic,
                    partition=partition,
                    offset=offset,
                    repository_github_id=payload.repository.github_id,
                    kind=kind,
                    status=EventStatus.PROCESSING.value,
                    payload=payload.model_dump(),
                    attempts=1,
                )
                session.add(row)
                session.flush()
            else:
                row.attempts += 1
                row.status = EventStatus.PROCESSING.value
                row.error = None

            repo = resolve_repository(session, payload, lock=True)
            row.repository_github_id = repo.github_repository_id

            # ---- deferral gate (live events during synchronization) --------
            if (
                kind == EventKind.LIVE.value
                and repo.status != RepositoryStatus.READY.value
            ):
                row.status = EventStatus.DEFERRED.value
                row.payload = payload.model_dump()
                log.info(
                    "event_deferred event_id=%s github_repository_id=%d repo_status=%s topic=%s partition=%d offset=%d",
                    row.event_id,
                    repo.github_repository_id,
                    repo.status,
                    topic,
                    partition,
                    offset,
                )
                return HandleOutcome.DEFERRED

            # ---- phase 1: authoritative PostgreSQL persistence -------------
            if row.pg_status != PhaseStatus.DONE.value:
                try:
                    update_current = (
                        kind == EventKind.LIVE.value
                        or repo.status != RepositoryStatus.READY.value
                    )
                    result = apply_payload(
                        session,
                        payload,
                        resolver=self._resolver_for(repo, payload),
                        update_current=update_current,
                        lock=True,
                    )
                except ContentResolutionError as exc:
                    raise TransientIngestError("content_resolution", str(exc)) from exc
                except GitHubCredentialsMissing as exc:
                    # Missing App credentials is a config problem: fail
                    # visibly (no offset commit) instead of retrying forever.
                    raise PermanentIngestError("github_credentials", str(exc)) from exc
                except GitHubAuthError as exc:
                    raise PermanentIngestError("github_auth", str(exc)) from exc
                except GitHubError as exc:
                    raise TransientIngestError("github_api", str(exc)) from exc
                except Exception as exc:
                    raise TransientIngestError("postgres", str(exc)) from exc

                index_items = result.index_items
                row.pg_status = PhaseStatus.DONE.value
                row.payload = payload.model_dump()
                # tx commits here: event row + authoritative data atomic
            else:
                index_items = self._rebuild_index_items(session, payload)
                row.payload = payload.model_dump()

        # ---- phase 2: ChromaDB semantic index -----------------------------
        try:
            self.indexer.index_event(index_items or [])
        except IndexError_ as exc:
            with self.session_factory() as session, session.begin():
                row = session.scalar(
                    select(IngestionEvent).where(
                        IngestionEvent.event_id == payload.event.id
                    )
                )
                if row is not None:
                    row.error = str(exc)[:4000]
            raise TransientIngestError("chroma_index", str(exc)) from exc

        # ---- phase 3: mark fully processed --------------------------------
        with self.session_factory() as session, session.begin():
            row = session.scalar(
                select(IngestionEvent)
                .where(IngestionEvent.event_id == payload.event.id)
                .with_for_update()
            )
            if row is not None:
                row.status = EventStatus.PROCESSED.value
                row.index_status = PhaseStatus.DONE.value
                row.error = None
                row.processed_at = datetime.now(UTC)

        log.info(
            "event_processed event_id=%s kind=%s github_repository_id=%d topic=%s partition=%d offset=%d indexed=%d",
            payload.event.id,
            kind,
            payload.repository.github_id,
            topic,
            partition,
            offset,
            len(index_items or []),
        )
        return HandleOutcome.PROCESSED

    # ------------------------------------------------------------- flush API
    def flush_deferred(self, github_repository_id: int) -> int:
        """Apply parked live events for a repository in arrival order.

        Called by the sync manager once backfill has caught up, before the
        repository may become READY. Each row moves deferred -> processed with
        the same two-phase durability as normal events.
        """
        applied = 0
        while True:
            raw_payload: dict | None = None
            with self.session_factory() as session, session.begin():
                repo = session.scalar(
                    select(Repository)
                    .where(Repository.github_repository_id == github_repository_id)
                    .with_for_update()
                )
                if repo is None:
                    return applied
                row = session.scalar(
                    select(IngestionEvent)
                    .where(
                        IngestionEvent.repository_github_id == github_repository_id,
                        IngestionEvent.status == EventStatus.DEFERRED.value,
                    )
                    .order_by(IngestionEvent.created_at, IngestionEvent.id)
                    .limit(1)
                    .with_for_update()
                )
                if row is None:
                    return applied
                # Duplicate the row content, release locks only after copy.
                raw_payload = dict(row.payload)
                event_id = row.event_id
                row.status = EventStatus.PROCESSING.value
                row.attempts += 1

            payload = parse_event(raw_payload)
            index_items: list[IndexItem]
            try:
                with self.session_factory() as session, session.begin():
                    repo = resolve_repository(session, payload, lock=True)
                    result = apply_payload(
                        session,
                        payload,
                        resolver=self._resolver_for(repo, payload),
                        update_current=True,
                        lock=True,
                    )
                    index_items = result.index_items
                    row = session.scalar(
                        select(IngestionEvent).where(
                            IngestionEvent.event_id == event_id
                        )
                    )
                    if row is not None:
                        row.pg_status = PhaseStatus.DONE.value
            except Exception as exc:
                with self.session_factory() as session, session.begin():
                    row = session.scalar(
                        select(IngestionEvent).where(
                            IngestionEvent.event_id == event_id
                        )
                    )
                    if row is not None:
                        row.status = EventStatus.DEFERRED.value
                        row.error = str(exc)[:4000]
                raise TransientIngestError("flush_apply", str(exc)) from exc

            try:
                self.indexer.index_event(index_items)
            except IndexError_ as exc:
                with self.session_factory() as session, session.begin():
                    row = session.scalar(
                        select(IngestionEvent).where(
                            IngestionEvent.event_id == event_id
                        )
                    )
                    if row is not None:
                        row.status = EventStatus.DEFERRED.value
                        row.error = str(exc)[:4000]
                raise TransientIngestError("flush_index", str(exc)) from exc

            with self.session_factory() as session, session.begin():
                row = session.scalar(
                    select(IngestionEvent)
                    .where(IngestionEvent.event_id == event_id)
                    .with_for_update()
                )
                if row is not None:
                    row.status = EventStatus.PROCESSED.value
                    row.index_status = PhaseStatus.DONE.value
                    row.processed_at = datetime.now(UTC)
            applied += 1
            log.info(
                "deferred_flushed event_id=%s github_repository_id=%d",
                event_id,
                github_repository_id,
            )

    def count_deferred(self, github_repository_id: int) -> int:
        with self.session_factory() as session:
            return len(
                session.scalars(
                    select(IngestionEvent).where(
                        IngestionEvent.repository_github_id == github_repository_id,
                        IngestionEvent.status == EventStatus.DEFERRED.value,
                    )
                ).all()
            )

    # ---------------------------------------------------------------- helpers
    def _resolver_for(
        self, repo: Repository, payload: IngestionEventPayload
    ) -> ContentResolver | None:
        if self.github_client is None:
            return None
        installation_id = (
            payload.installation.github_installation_id or repo.github_installation_id
        )
        return ContentResolver(
            self.github_client, repo.owner, repo.name, installation_id
        )

    def _record_invalid(
        self, raw: bytes, topic: str, partition: int, offset: int, error: str
    ) -> None:
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                data = {"_raw": raw.decode("utf-8", errors="replace")}
        except Exception:
            data = {"_raw": raw.decode("utf-8", errors="replace")}
        digest = hashlib.sha256(raw).hexdigest()[:32]
        try:
            with self.session_factory() as session, session.begin():
                exists = session.scalar(
                    select(IngestionEvent).where(
                        IngestionEvent.event_id == f"invalid:{digest}"
                    )
                )
                if exists is not None:
                    return
                session.add(
                    IngestionEvent(
                        event_id=f"invalid:{digest}",
                        topic=topic,
                        partition=partition,
                        offset=offset,
                        kind=EventKind.LIVE.value,
                        status=EventStatus.INVALID.value,
                        pg_status=PhaseStatus.PENDING.value,
                        index_status=PhaseStatus.PENDING.value,
                        payload=data,
                        error=error[:4000],
                    )
                )
        except Exception:
            log.exception("record_invalid_failed topic=%s offset=%d", topic, offset)

    def _rebuild_index_items(
        self, session: Session, payload: IngestionEventPayload
    ) -> list[IndexItem]:
        """Reconstruct index items from PostgreSQL after a phase-1-only
        success (Chroma failed earlier, offset never committed, event
        redelivered)."""
        shas = [cb.sha for cb in payload.commits] or (
            [payload.push.after] if payload.push.after else []
        )
        if not shas:
            return []
        repo = session.scalar(
            select(Repository).where(
                Repository.github_repository_id == payload.repository.github_id
            )
        )
        if repo is None:
            return []
        rows = session.execute(
            select(Commit, CommitFile, File)
            .join(CommitFile, CommitFile.commit_id == Commit.id)
            .join(File, File.id == CommitFile.file_id)
            .where(
                Commit.repository_id == repo.id,
                Commit.github_commit_sha.in_(shas),
            )
        ).all()
        return [
            IndexItem(
                repository_pk=repo.id,
                github_repository_id=repo.github_repository_id,
                commit_pk=commit.id,
                commit_sha=commit.github_commit_sha,
                file_pk=file_row.id,
                path=file_row.path,
                status=commit_file.status,
                patch=commit_file.patch,
                commit_message=commit.message,
                committed_at=commit.committed_at,
                additions=commit_file.additions,
                deletions=commit_file.deletions,
            )
            for commit, commit_file, file_row in rows
        ]


__all__ = [
    "EventProcessor",
    "HandleOutcome",
    "IngestError",
    "PermanentIngestError",
    "QueryHit",
    "TransientIngestError",
]
