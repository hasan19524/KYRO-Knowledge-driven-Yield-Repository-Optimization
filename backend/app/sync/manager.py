"""Repository synchronization state machine (onboard -> backfill -> READY).

Locked behavior implemented here (master prompt §10-§16, §39, §56, §62):

  * repository enters SYNCING on onboarding (or re-sync)
  * entire reachable history is published to `kyro.github.backfill`
    (one delta event per commit, chronological, batched + flushed before the
    published boundary is advanced in PostgreSQL)
  * the run waits until the ingestion worker has applied every published
    event (synced_through_commit == target)
  * the branch head is re-read (race window §15/§62); if it moved the target
    is extended and the cycle repeats
  * parked (deferred) live events are flushed, then READY is committed under
    the repository row lock ONLY when: published == applied == latest head
    AND zero deferred events remain - so a live push can neither be lost nor
    overtake backfill, and the repo can never be READY prematurely
  * timeouts / auth failures move the repository to SYNC_FAILED /
    ACCESS_REVOKED (never stuck in SYNCING)

Concurrency model:
  * in-process guard + PostgreSQL advisory lock keyed on github_repository_id
    => one sync run per repository, while different repositories synchronize
    concurrently (bounded by SYNC_CONCURRENCY).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.db.models import (
    EventStatus,
    IngestionEvent,
    Repository,
    RepositoryStatus,
)
from app.github.auth import GitHubAuthError, GitHubCredentialsMissing
from app.github.backfill import BackfillService
from app.github.client import (
    GitHubClient,
    GitHubError,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
)
from app.ingest.processor import EventProcessor, TransientIngestError
from app.kafka.producer import BackfillDeliveryError, BackfillProducer

log = logging.getLogger("kyro.sync")


def _now() -> datetime:
    return datetime.now(UTC)


class SyncRunError(RuntimeError):
    """Terminal condition for one synchronization run."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        target_status: str | None = RepositoryStatus.SYNC_FAILED.value,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.target_status = target_status


class SyncTimeout(SyncRunError):
    def __init__(self, message: str) -> None:
        super().__init__(message, reason="timeout")


class SyncPublishError(SyncRunError):
    def __init__(self, message: str) -> None:
        super().__init__(message, reason="kafka_publish")


class SyncStatusChanged(SyncRunError):
    """Another actor changed the repository status mid-run; do not overwrite."""

    def __init__(self, status: str, message: str = "") -> None:
        super().__init__(
            message or f"repository status changed to {status}",
            reason="status_changed",
            target_status=None,
        )
        self.observed_status = status


class RepositoryOwnershipConflict(RuntimeError):
    """Onboarding attempted for a repository owned by a different user."""


def _visible(
    repo: Repository, owner_user_id: int | None, include_unowned: bool
) -> bool:
    """Ownership visibility rule (server-side, never client-supplied).

    owner_user_id=None => internal/system view (everything visible).
    Otherwise: owned rows only to their owner; unowned rows only when the
    caller explicitly allows them (legacy `default` identity).
    """
    if owner_user_id is None:
        return True
    if repo.owner_user_id is None:
        return include_unowned
    return repo.owner_user_id == owner_user_id


class SyncManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        backfill: BackfillService,
        processor: EventProcessor,
        github_client: GitHubClient,
        *,
        producer_factory: Callable[[], Any] | None = None,
        backfill_topic: str | None = None,
        poll_interval: float | None = None,
        timeout: float | None = None,
        publish_batch: int | None = None,
        concurrency: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.backfill = backfill
        self.processor = processor
        self.github = github_client
        self._producer_factory = producer_factory or (
            lambda: BackfillProducer(client_id=f"kyro-sync-{os.getpid()}")
        )
        self.backfill_topic = backfill_topic or config.BACKFILL_TOPIC
        self.poll_interval = (
            poll_interval if poll_interval is not None else config.SYNC_POLL_INTERVAL_S
        )
        self.timeout = timeout if timeout is not None else config.SYNC_TIMEOUT_S
        self.publish_batch = (
            publish_batch if publish_batch is not None else config.SYNC_PUBLISH_BATCH
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, concurrency or config.SYNC_CONCURRENCY),
            thread_name_prefix="kyro-sync",
        )
        self._active: set[int] = set()
        self._lock = threading.Lock()

    # ================================================================ public
    def onboard(
        self,
        *,
        github_repository_id: int,
        owner: str,
        name: str,
        full_name: str | None = None,
        installation_id: int | None = None,
        default_branch: str | None = None,
        private: bool = False,
        url: str | None = None,
        run: bool = True,
        owner_user_id: int | None = None,
    ) -> dict:
        """Create/refresh the repository row and mark it SYNCING (§44/§56).

        An existing row keeps its published boundary so an interrupted sync
        resumes instead of re-walking everything (events are idempotent
        either way).

        Ownership (owner_user_id): a new row is created for `owner_user_id`
        (None = internal/system caller); an unowned row is claimed by the
        caller; a row owned by someone else raises
        RepositoryOwnershipConflict - github_repository_id identifies the
        repository, never the user.
        """
        with self.session_factory() as session, session.begin():
            repo = session.scalar(
                select(Repository)
                .where(Repository.github_repository_id == github_repository_id)
                .with_for_update()
            )
            if repo is None:
                repo = Repository(
                    github_repository_id=github_repository_id,
                    name=name,
                    full_name=full_name or f"{owner}/{name}",
                    owner=owner,
                    is_private=private,
                    default_branch=default_branch,
                    url=url,
                    github_installation_id=installation_id,
                    status=RepositoryStatus.SYNCING.value,
                    sync_started_at=_now(),
                    owner_user_id=owner_user_id,
                )
                session.add(repo)
                log.info(
                    "repo_onboarded github_repository_id=%d owner=%s name=%s "
                    "owner_user_id=%s",
                    github_repository_id,
                    owner,
                    name,
                    owner_user_id,
                )
            else:
                # Ownership gate runs BEFORE any mutation so a rejected
                # onboarding leaves the repository completely untouched.
                if repo.owner_user_id is None:
                    if owner_user_id is not None:
                        # First claim of a row the ingestion worker created.
                        repo.owner_user_id = owner_user_id
                        log.info(
                            "repo_claimed github_repository_id=%d owner_user_id=%d",
                            github_repository_id,
                            owner_user_id,
                        )
                elif repo.owner_user_id != owner_user_id:
                    raise RepositoryOwnershipConflict(
                        f"repository {github_repository_id} is owned by another user"
                    )
                previous = repo.status
                repo.name = name
                repo.full_name = full_name or f"{owner}/{name}"
                repo.owner = owner
                repo.is_private = private
                if default_branch:
                    repo.default_branch = default_branch
                if url:
                    repo.url = url
                if installation_id is not None:
                    repo.github_installation_id = installation_id
                repo.status = RepositoryStatus.SYNCING.value
                repo.last_error = None
                repo.sync_started_at = _now()
                repo.sync_completed_at = None
                log.info(
                    "repo_resync_requested github_repository_id=%d previous_status=%s",
                    github_repository_id,
                    previous,
                )
        if run:
            self.trigger(github_repository_id)
        return self.snapshot(  # type: ignore[return-value]
            github_repository_id, owner_user_id=owner_user_id
        )

    def resync(
        self,
        github_repository_id: int,
        *,
        full: bool = False,
        run: bool = True,
        owner_user_id: int | None = None,
        include_unowned: bool = False,
    ) -> dict | None:
        """Re-run synchronization for an existing repository.

        full=True clears the published boundary so the entire history is
        re-published (recovery when buffered Kafka events expired).

        Visibility: returns None (like a missing row) when the repository
        is not visible to `owner_user_id`, so callers answer 404 without
        leaking existence. owner_user_id=None is the internal/system view.
        """
        with self.session_factory() as session, session.begin():
            repo = session.scalar(
                select(Repository)
                .where(Repository.github_repository_id == github_repository_id)
                .with_for_update()
            )
            if repo is None:
                return None
            if not _visible(repo, owner_user_id, include_unowned):
                return None
            previous = repo.status
            repo.status = RepositoryStatus.SYNCING.value
            repo.last_error = None
            repo.sync_started_at = _now()
            repo.sync_completed_at = None
            if full:
                repo.backfill_published_through_commit = None
            log.info(
                "repo_resync github_repository_id=%d previous_status=%s full=%s "
                "requested_by_user_id=%s",
                github_repository_id,
                previous,
                full,
                owner_user_id,
            )
        if run:
            self.trigger(github_repository_id)
        return self.snapshot(  # type: ignore[return-value]
            github_repository_id,
            owner_user_id=owner_user_id,
            include_unowned=include_unowned,
        )

    def run_sync(self, github_repository_id: int) -> str:
        """Blocking synchronization run. Returns the final repository status."""
        if not self._reserve(github_repository_id):
            return self._status_of(github_repository_id) or ""
        try:
            return self._run_reserved(github_repository_id)
        finally:
            self._release(github_repository_id)

    def trigger(self, github_repository_id: int) -> bool:
        """Start a background synchronization run (bounded concurrency)."""
        if not self._reserve(github_repository_id):
            return False

        def _job() -> None:
            try:
                self._run_reserved(github_repository_id)
            finally:
                self._release(github_repository_id)

        self._executor.submit(_job)
        return True

    def snapshot(
        self,
        github_repository_id: int,
        *,
        owner_user_id: int | None = None,
        include_unowned: bool = False,
    ) -> dict | None:
        """Status snapshot, visibility-scoped (None when not visible).

        owner_user_id=None is the internal/system view (no scoping) used by
        the sync supervisor and tests; API callers always pass the identity
        resolved from the credential, never a client-supplied id.
        """
        with self.session_factory() as session:
            repo = session.scalar(
                select(Repository).where(
                    Repository.github_repository_id == github_repository_id
                )
            )
            if repo is None:
                return None
            if not _visible(repo, owner_user_id, include_unowned):
                return None
            deferred = session.scalar(
                select(func.count())
                .select_from(IngestionEvent)
                .where(
                    IngestionEvent.repository_github_id == github_repository_id,
                    IngestionEvent.status == EventStatus.DEFERRED.value,
                )
            )
            return {
                "github_repository_id": repo.github_repository_id,
                "name": repo.name,
                "full_name": repo.full_name,
                "owner": repo.owner,
                "default_branch": repo.default_branch,
                "is_private": repo.is_private,
                "url": repo.url,
                "status": repo.status,
                "sync_target_commit": repo.sync_target_commit,
                "synced_through_commit": repo.synced_through_commit,
                "backfill_published_through_commit": (
                    repo.backfill_published_through_commit
                ),
                "deferred_events": int(deferred or 0),
                "last_error": repo.last_error,
                "sync_started_at": repo.sync_started_at.isoformat()
                if repo.sync_started_at
                else None,
                "sync_completed_at": repo.sync_completed_at.isoformat()
                if repo.sync_completed_at
                else None,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                "sync_running": self.is_active(github_repository_id),
            }

    def list_snapshots(
        self,
        *,
        owner_user_id: int | None = None,
        include_unowned: bool = False,
    ) -> list[dict]:
        """Visibility-scoped snapshots of every repository the caller may see."""
        with self.session_factory() as session:
            query = select(Repository.github_repository_id).order_by(Repository.id)
            if owner_user_id is not None:
                if include_unowned:
                    query = query.where(
                        or_(
                            Repository.owner_user_id == owner_user_id,
                            Repository.owner_user_id.is_(None),
                        )
                    )
                else:
                    query = query.where(Repository.owner_user_id == owner_user_id)
            ids = session.scalars(query).all()
        out: list[dict] = []
        for gid in ids:
            snap = self.snapshot(
                gid,
                owner_user_id=owner_user_id,
                include_unowned=include_unowned,
            )
            if snap:
                out.append(snap)
        return out

    def pending_sync_ids(self, limit: int = 50) -> list[int]:
        """Repositories left in SYNCING (crash recovery / supervisor input)."""
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(Repository.github_repository_id)
                    .where(Repository.status == RepositoryStatus.SYNCING.value)
                    .order_by(Repository.updated_at)
                    .limit(limit)
                ).all()
            )

    def is_active(self, github_repository_id: int) -> bool:
        with self._lock:
            return github_repository_id in self._active

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    # =============================================================== internal
    def _reserve(self, github_repository_id: int) -> bool:
        with self._lock:
            if github_repository_id in self._active:
                log.info(
                    "sync_already_running github_repository_id=%d",
                    github_repository_id,
                )
                return False
            self._active.add(github_repository_id)
            return True

    def _release(self, github_repository_id: int) -> None:
        with self._lock:
            self._active.discard(github_repository_id)

    def _run_reserved(self, github_repository_id: int) -> str:
        status = self._status_of(github_repository_id)
        if status is None:
            raise SyncRunError(
                f"repository {github_repository_id} not found", reason="not_found"
            )
        if status != RepositoryStatus.SYNCING.value:
            # Only SYNCING runs are executed; other states require an explicit
            # onboard/resync first (prevents accidental re-runs / overwrites).
            log.info(
                "sync_skipped github_repository_id=%d status=%s",
                github_repository_id,
                status,
            )
            return status

        try:
            with self._advisory_lock(github_repository_id) as acquired:
                if not acquired:
                    log.info(
                        "sync_busy_other_process github_repository_id=%d",
                        github_repository_id,
                    )
                    return self._status_of(github_repository_id) or status
                return self._run_locked(github_repository_id)
        except SyncStatusChanged as exc:
            log.warning(
                "sync_status_changed github_repository_id=%d status=%s",
                github_repository_id,
                exc.observed_status,
            )
            return exc.observed_status
        except SyncRunError as exc:
            self._mark_failed(github_repository_id, exc.target_status, str(exc))
            log.error(
                "sync_failed github_repository_id=%d reason=%s status=%s error=%s",
                github_repository_id,
                exc.reason,
                exc.target_status,
                str(exc)[:300],
            )
            return exc.target_status or self._status_of(github_repository_id) or ""
        except GitHubAuthError as exc:
            # GitHub rejected the App/installation identity -> access gone.
            self._mark_failed(
                github_repository_id,
                RepositoryStatus.ACCESS_REVOKED.value,
                str(exc),
            )
            log.error(
                "sync_access_revoked github_repository_id=%d error=%s",
                github_repository_id,
                str(exc)[:300],
            )
            return RepositoryStatus.ACCESS_REVOKED.value
        except GitHubCredentialsMissing as exc:
            # Configuration problem (not a revocation): visible SYNC_FAILED.
            self._mark_failed(
                github_repository_id, RepositoryStatus.SYNC_FAILED.value, str(exc)
            )
            log.error(
                "sync_credentials_missing github_repository_id=%d",
                github_repository_id,
            )
            return RepositoryStatus.SYNC_FAILED.value
        except GitHubNotFound as exc:
            # Repository/branch disappeared from GitHub (not transient).
            self._mark_failed(
                github_repository_id,
                RepositoryStatus.SYNC_FAILED.value,
                f"GitHub resource not found: {exc}",
            )
            log.error(
                "sync_not_found github_repository_id=%d error=%s",
                github_repository_id,
                str(exc)[:200],
            )
            return RepositoryStatus.SYNC_FAILED.value
        except GitHubError as exc:
            self._mark_failed(
                github_repository_id,
                RepositoryStatus.SYNC_FAILED.value,
                f"GitHub error: {exc}",
            )
            log.error(
                "sync_github_error github_repository_id=%d status=%s error=%s",
                github_repository_id,
                exc.status,
                str(exc)[:200],
            )
            return RepositoryStatus.SYNC_FAILED.value
        except Exception as exc:  # never silently swallow
            log.exception(
                "sync_unexpected_error github_repository_id=%d",
                github_repository_id,
            )
            self._mark_failed(
                github_repository_id,
                RepositoryStatus.SYNC_FAILED.value,
                f"unexpected: {exc}",
            )
            return RepositoryStatus.SYNC_FAILED.value

    # ------------------------------------------------------------------ core
    def _run_locked(self, github_repository_id: int) -> str:
        snap = self._repo_row(github_repository_id)
        if snap is None:
            raise SyncRunError("repository disappeared", reason="not_found")
        deadline = time.monotonic() + self.timeout
        status = self._catch_up(snap, deadline)
        log.info(
            "sync_completed github_repository_id=%d status=%s duration_budget_left=%.1fs",
            github_repository_id,
            status,
            max(0.0, deadline - time.monotonic()),
        )
        return status

    def _catch_up(self, repo: _RepoRow, deadline: float) -> str:
        github_id = repo.github_repository_id
        installation_id = repo.github_installation_id or (
            int(config.GITHUB_APP_INSTALLATION_ID)
            if config.GITHUB_APP_INSTALLATION_ID
            else None
        )
        owner, name = repo.owner, repo.name

        # Resolve default branch (and refresh metadata) when unknown.
        branch = repo.default_branch
        if not branch:
            info = self._gh_retry(
                deadline, self.github.get_repository, owner, name, installation_id
            )
            branch = info.get("default_branch")
            self._refresh_metadata(github_id, info)
            if not branch:
                # Repository with no commits yet: nothing to backfill.
                log.info("sync_empty_repository github_repository_id=%d", github_id)
                self.processor.flush_deferred(github_id)
                if self._try_finalize(github_id, None):
                    return RepositoryStatus.READY.value
                raise SyncStatusChanged(self._status_of(github_id) or "")

        while True:
            if time.monotonic() > deadline:
                raise SyncTimeout(
                    f"synchronization exceeded {self.timeout:.0f}s waiting for "
                    f"repository {github_id} to catch up"
                )

            head = self._gh_retry(
                deadline,
                self.github.get_branch_sha,
                owner,
                name,
                branch,
                installation_id,
            )
            current = self._repo_row(github_id)
            if current is None:
                raise SyncRunError("repository disappeared", reason="not_found")
            published = current.backfill_published_through_commit

            if current.sync_target_commit != head:
                self._set_target(github_id, head)

            if head != published:
                # Publish the unpublished range (bounded batches; boundary is
                # only advanced after a successful synchronous flush).
                published = self._publish_range(
                    repo, head, published, branch, installation_id, deadline
                )
                log.info(
                    "sync_range_published github_repository_id=%d target=%s published=%s",
                    github_id,
                    head[:12],
                    (published or "")[:12],
                )

            # Wait for the worker to apply every published event (§39.4).
            self._wait_applied(github_id, head, deadline)

            # Race window (§15/§62): re-read the head before finalizing.
            head2 = self._gh_retry(
                deadline,
                self.github.get_branch_sha,
                owner,
                name,
                branch,
                installation_id,
            )
            if head2 != head:
                log.info(
                    "sync_target_extended github_repository_id=%d from=%s to=%s",
                    github_id,
                    head[:12],
                    head2[:12],
                )
                continue

            # Flush parked live events before READY (§10/§39.5).
            try:
                flushed = self.processor.flush_deferred(github_id)
                if flushed:
                    log.info(
                        "sync_deferred_flushed github_repository_id=%d count=%d",
                        github_id,
                        flushed,
                    )
            except TransientIngestError as exc:
                log.warning(
                    "sync_deferred_flush_retry github_repository_id=%d error=%s",
                    github_id,
                    str(exc)[:200],
                )
                continue

            if self._try_finalize(github_id, head):
                return RepositoryStatus.READY.value

            # Finalize refused: a live event parked between flush and lock
            # (its push will show up on the next head read) or the status
            # changed underneath us.
            now_status = self._status_of(github_id)
            if now_status != RepositoryStatus.SYNCING.value:
                raise SyncStatusChanged(now_status or "")
            # loop: re-read head -> extend/publish/flush/finalize again

    # -------------------------------------------------------------- helpers
    def _publish_range(
        self,
        repo: _RepoRow,
        head: str,
        published: str | None,
        branch: str,
        installation_id: int | None,
        deadline: float,
    ) -> str:
        github_id = repo.github_repository_id
        repo_block = {
            "github_id": github_id,
            "name": repo.name,
            "full_name": repo.full_name,
            "owner": repo.owner,
            "private": repo.is_private,
            "default_branch": branch,
            "url": repo.url,
        }
        last = published
        while True:
            producer = self._producer_factory()
            buffered = 0
            boundary = last
            try:
                for meta, event in self.backfill.build_events(
                    owner=repo.owner,
                    name=repo.name,
                    repository=repo_block,
                    branch=branch,
                    installation_id=installation_id,
                    stop_sha=last,
                    target_sha=head,
                ):
                    producer.send(github_id, event, topic=self.backfill_topic)
                    boundary = meta.sha
                    buffered += 1
                    if buffered >= self.publish_batch:
                        producer.flush()
                        self._advance_boundary(github_id, boundary)
                        buffered = 0
                producer.flush()
                if boundary is None:
                    raise SyncRunError(
                        f"no commits found while publishing history for repo {github_id}",
                        reason="empty_history",
                    )
                if boundary != last:
                    self._advance_boundary(github_id, boundary)
                return boundary
            except (GitHubRateLimited, GitHubUnavailable, BackfillDeliveryError) as exc:
                # Transient: retry within the run deadline. Deterministic
                # event ids make any re-sent duplicates harmless downstream.
                if time.monotonic() > deadline:
                    if isinstance(exc, BackfillDeliveryError):
                        raise SyncPublishError(
                            f"backfill publish failed: {exc}"
                        ) from exc
                    raise SyncTimeout(
                        f"backfill publish kept failing until deadline: {exc}"
                    ) from exc
                log.warning(
                    "sync_publish_retry github_repository_id=%d error=%s",
                    github_id,
                    str(exc)[:200],
                )
                time.sleep(min(max(self.poll_interval, 0.5), 2.0))
            finally:
                producer.close()

    def _wait_applied(self, github_id: int, target: str, deadline: float) -> None:
        while True:
            with self.session_factory() as session:
                repo = session.scalar(
                    select(Repository).where(
                        Repository.github_repository_id == github_id
                    )
                )
                if repo is None:
                    raise SyncRunError("repository disappeared", reason="not_found")
                status = repo.status
                synced = repo.synced_through_commit
            if synced == target:
                return
            if status == RepositoryStatus.READY.value and synced == target:
                return
            if status in (
                RepositoryStatus.SYNC_FAILED.value,
                RepositoryStatus.ACCESS_REVOKED.value,
            ):
                # The worker recorded an unrecoverable event failure.
                raise SyncStatusChanged(status)
            if time.monotonic() > deadline:
                raise SyncTimeout(
                    f"timed out waiting for worker to apply through {target[:12]} "
                    f"(synced_through={str(synced)[:12] or 'none'})"
                )
            time.sleep(self.poll_interval)

    def _try_finalize(self, github_id: int, target: str | None) -> bool:
        """Atomically promote SYNCING -> READY (§15/§39/§62).

        Runs entirely under the repository row lock, which is the same lock
        the ingestion worker holds while it decides to defer a live event.
        Therefore at the moment READY is committed there are zero parked
        events, and any later live event observes READY and processes
        normally instead of parking.
        """
        with self.session_factory() as session, session.begin():
            repo = session.scalar(
                select(Repository)
                .where(Repository.github_repository_id == github_id)
                .with_for_update()
            )
            if repo is None:
                return False
            if repo.status != RepositoryStatus.SYNCING.value:
                return False
            if repo.backfill_published_through_commit != target:
                log.debug(
                    "finalize_refused_published github_repository_id=%d published=%s target=%s",
                    github_id,
                    repo.backfill_published_through_commit,
                    target,
                )
                return False
            if repo.synced_through_commit != target:
                log.debug(
                    "finalize_refused_synced github_repository_id=%d synced=%s target=%s",
                    github_id,
                    repo.synced_through_commit,
                    target,
                )
                return False
            deferred = session.scalar(
                select(func.count())
                .select_from(IngestionEvent)
                .where(
                    IngestionEvent.repository_github_id == github_id,
                    IngestionEvent.status == EventStatus.DEFERRED.value,
                )
            )
            if deferred:
                log.debug(
                    "finalize_refused_deferred github_repository_id=%d count=%d",
                    github_id,
                    deferred,
                )
                return False
            repo.status = RepositoryStatus.READY.value
            repo.sync_completed_at = _now()
            repo.last_error = None
            log.info(
                "repo_ready github_repository_id=%d synced_through=%s",
                github_id,
                str(target)[:12] or "none",
            )
            return True

    def _advance_boundary(self, github_id: int, sha: str) -> None:
        with self.session_factory() as session, session.begin():
            repo = session.scalar(
                select(Repository)
                .where(Repository.github_repository_id == github_id)
                .with_for_update()
            )
            if repo is not None:
                repo.backfill_published_through_commit = sha

    def _set_target(self, github_id: int, head: str) -> None:
        with self.session_factory() as session, session.begin():
            repo = session.scalar(
                select(Repository)
                .where(Repository.github_repository_id == github_id)
                .with_for_update()
            )
            if repo is not None:
                repo.sync_target_commit = head

    def _refresh_metadata(self, github_id: int, info: dict) -> None:
        with self.session_factory() as session, session.begin():
            repo = session.scalar(
                select(Repository)
                .where(Repository.github_repository_id == github_id)
                .with_for_update()
            )
            if repo is None:
                return
            if info.get("name"):
                repo.name = info["name"]
            if info.get("full_name"):
                repo.full_name = info["full_name"]
            if info.get("html_url"):
                repo.url = info["html_url"]
            if "private" in info:
                repo.is_private = bool(info.get("private"))
            if info.get("default_branch"):
                repo.default_branch = info["default_branch"]

    def _mark_failed(
        self, github_id: int, target_status: str | None, message: str
    ) -> None:
        if target_status is None:
            return
        try:
            with self.session_factory() as session, session.begin():
                repo = session.scalar(
                    select(Repository)
                    .where(Repository.github_repository_id == github_id)
                    .with_for_update()
                )
                if repo is None:
                    return
                # Only transition out of SYNCING; states set by other actors
                # (worker failures, access revocation) are preserved.
                if repo.status != RepositoryStatus.SYNCING.value:
                    return
                repo.status = target_status
                repo.last_error = message[:4000]
                if target_status == RepositoryStatus.ACCESS_REVOKED.value:
                    repo.sync_completed_at = None
        except Exception:
            log.exception(
                "sync_mark_failed_write_error github_repository_id=%d", github_id
            )

    def _gh_retry(self, deadline: float, fn, *args, **kwargs):
        """Call a GitHub API function, retrying transient errors until the
        run deadline (rate limits / 5xx / network). Auth errors propagate."""
        while True:
            try:
                return fn(*args, **kwargs)
            except (GitHubRateLimited, GitHubUnavailable) as exc:
                if time.monotonic() > deadline:
                    raise SyncTimeout(
                        f"GitHub kept failing until deadline: {exc}"
                    ) from exc
                log.warning(
                    "sync_github_retry fn=%s error=%s",
                    getattr(fn, "__name__", fn),
                    str(exc)[:200],
                )
                time.sleep(min(max(self.poll_interval, 0.5), 2.0))

    def _status_of(self, github_id: int) -> str | None:
        with self.session_factory() as session:
            return session.scalar(
                select(Repository.status).where(
                    Repository.github_repository_id == github_id
                )
            )

    def _repo_row(self, github_id: int) -> _RepoRow | None:
        with self.session_factory() as session:
            repo = session.scalar(
                select(Repository).where(Repository.github_repository_id == github_id)
            )
            if repo is None:
                return None
            return _RepoRow(
                github_repository_id=repo.github_repository_id,
                name=repo.name,
                full_name=repo.full_name,
                owner=repo.owner,
                is_private=repo.is_private,
                default_branch=repo.default_branch,
                url=repo.url,
                github_installation_id=repo.github_installation_id,
                sync_target_commit=repo.sync_target_commit,
                backfill_published_through_commit=(
                    repo.backfill_published_through_commit
                ),
            )

    @contextmanager
    def _advisory_lock(self, github_id: int) -> Iterator[bool]:
        """Cross-process mutual exclusion for one repository's sync run.

        Keyed on github_repository_id (fits signed bigint), so different
        repositories never block each other.
        """
        session = self.session_factory()
        try:
            conn = session.connection()
            row = conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": github_id}
            ).scalar()
            try:
                yield bool(row)
            finally:
                if row:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": github_id}
                    )
        finally:
            session.close()


class _RepoRow:
    """Detached snapshot of the repository fields the sync run needs."""

    __slots__ = (
        "backfill_published_through_commit",
        "default_branch",
        "full_name",
        "github_installation_id",
        "github_repository_id",
        "is_private",
        "name",
        "owner",
        "sync_target_commit",
        "url",
    )

    def __init__(
        self,
        *,
        github_repository_id: int,
        name: str,
        full_name: str,
        owner: str,
        is_private: bool,
        default_branch: str | None,
        url: str | None,
        github_installation_id: int | None,
        sync_target_commit: str | None,
        backfill_published_through_commit: str | None,
    ) -> None:
        self.github_repository_id = github_repository_id
        self.name = name
        self.full_name = full_name
        self.owner = owner
        self.is_private = is_private
        self.default_branch = default_branch
        self.url = url
        self.github_installation_id = github_installation_id
        self.sync_target_commit = sync_target_commit
        self.backfill_published_through_commit = backfill_published_through_commit


__all__ = [
    "RepositoryOwnershipConflict",
    "SyncManager",
    "SyncPublishError",
    "SyncRunError",
    "SyncStatusChanged",
    "SyncTimeout",
]
