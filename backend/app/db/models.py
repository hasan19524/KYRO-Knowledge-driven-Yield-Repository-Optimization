"""KYRO PostgreSQL data model.

PostgreSQL is the authoritative source of truth (locked architecture).
ChromaDB only ever holds a rebuildable semantic index that references the
primary keys defined here (repository_id / commit_id / file_id).
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class RepositoryStatus(enum.StrEnum):
    SYNCING = "SYNCING"
    READY = "READY"
    SYNC_FAILED = "SYNC_FAILED"
    ACCESS_REVOKED = "ACCESS_REVOKED"


class EventKind(enum.StrEnum):
    LIVE = "live"
    BACKFILL = "backfill"


class EventStatus(enum.StrEnum):
    PROCESSING = "processing"
    DEFERRED = "deferred"
    PROCESSED = "processed"
    FAILED = "failed"
    INVALID = "invalid"


class PhaseStatus(enum.StrEnum):
    PENDING = "pending"
    DONE = "done"


# Identity of the legacy/shared-key tenant (config.KYRO_API_KEY, seeded by
# the ownership migration). Every repository that existed before per-user
# ownership was introduced belongs to this user.
DEFAULT_USER_HANDLE = "default"


class GithubInstallation(Base):
    __tablename__ = "github_installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_installation_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    account_login: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base):
    """KYRO user account.

    Authentication is by API key only: `api_key_hash` stores the SHA-256 of
    the key (plaintext returned exactly once at issue/rotation). The shared
    service key (config.KYRO_API_KEY) maps to the `default` user instead of
    a stored key, so the Next.js proxy keeps working unchanged.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    handle: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    api_key_hash: Mapped[str | None] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    repositories: Mapped[list[Repository]] = relationship(
        back_populates="owner_user",
        # Let the database enforce ON DELETE RESTRICT: never silently null
        # out ownership by deleting a user who still owns repositories.
        passive_deletes=True,
    )


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # GitHub repository ID is the canonical EXTERNAL identity (locked rule).
    # It identifies the repository, NEVER the user that owns it in KYRO.
    github_repository_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    # KYRO ownership: which user may see/operate this repository. Nullable
    # only for rows created by the ingestion worker before (or without) an
    # onboarding claim; unowned rows are invisible to per-user identities.
    # Never written from Kafka event payloads - only the onboarding API and
    # the ownership migration set it.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_branch: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    github_installation_id: Mapped[int | None] = mapped_column(BigInteger)

    # Synchronization state machine (locked states).
    status: Mapped[str] = mapped_column(
        Text, default=RepositoryStatus.SYNCING.value, nullable=False, index=True
    )
    sync_target_commit: Mapped[str | None] = mapped_column(Text)
    synced_through_commit: Mapped[str | None] = mapped_column(Text)
    backfill_published_through_commit: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    commits: Mapped[list[Commit]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    files: Mapped[list[File]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    owner_user: Mapped[User | None] = relationship(back_populates="repositories")


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "github_commit_sha", name="uq_commits_repo_sha"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    # Single-parent relationship: merge commits keep the first parent here
    # (the backfill chain follows first-parent chronological order).
    parent_sha: Mapped[str | None] = mapped_column(Text)
    author_name: Mapped[str | None] = mapped_column(Text)
    author_email: Mapped[str | None] = mapped_column(Text)
    author_username: Mapped[str | None] = mapped_column(Text)
    committer_name: Mapped[str | None] = mapped_column(Text)
    committer_email: Mapped[str | None] = mapped_column(Text)
    committer_username: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    repository: Mapped[Repository] = relationship(back_populates="commits")
    commit_files: Mapped[list[CommitFile]] = relationship(
        back_populates="commit", cascade="all, delete-orphan"
    )


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_files_repo_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    # CURRENT authoritative content (kept current; history lives in commit_files).
    current_content: Mapped[str | None] = mapped_column(Text)
    current_content_commit_sha: Mapped[str | None] = mapped_column(Text)
    current_content_commit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    blob_sha: Mapped[str | None] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    repository: Mapped[Repository] = relationship(back_populates="files")


class CommitFile(Base):
    __tablename__ = "commit_files"
    __table_args__ = (
        UniqueConstraint("commit_id", "file_id", name="uq_commit_files_commit_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commit_id: Mapped[int] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # added | modified | deleted | renamed | copied | changed | unchanged
    status: Mapped[str] = mapped_column(Text, nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    patch: Mapped[str | None] = mapped_column(Text)
    previous_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    commit: Mapped[Commit] = relationship(back_populates="commit_files")
    file: Mapped[File] = relationship()


class IngestionEvent(Base):
    """Durable idempotency + per-phase processing state for Kafka events.

    - event_id unique  -> at-least-once duplicate detection (SKIP_DUPLICATE)
    - pg_status        -> phase 1 (authoritative persistence) done/not
    - index_status     -> phase 2 (ChromaDB) done/not -> retry indexing after
                          redelivery without re-applying PostgreSQL data
    - status=deferred  -> live event parked while its repository is SYNCING so
                          it cannot overtake backfill and does not block the
                          partition (offset committed once durably parked)
    """

    __tablename__ = "ingestion_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_ingestion_events_event_id"),
        Index("ix_ingestion_events_repo_status", "repository_github_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text)
    partition: Mapped[int | None] = mapped_column(Integer)
    offset: Mapped[int | None] = mapped_column(BigInteger)
    repository_github_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(
        Text, default=EventKind.LIVE.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, default=EventStatus.PROCESSING.value, nullable=False, index=True
    )
    pg_status: Mapped[str] = mapped_column(
        Text, default=PhaseStatus.PENDING.value, nullable=False
    )
    index_status: Mapped[str] = mapped_column(
        Text, default=PhaseStatus.PENDING.value, nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
