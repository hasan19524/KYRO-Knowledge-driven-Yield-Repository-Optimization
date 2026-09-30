"""KYRO ingestion event contract.

Live events (produced by n8n into `kyro.github.push`) follow the existing
pipeline contract and are NOT modified by this codebase. Backfill events
(produced into `kyro.github.backfill`) reuse the same core structure and add
an explicit `event.classification` + `backfill` block so the worker can
distinguish LIVE PUSH from INITIAL BACKFILL (locked requirement).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

CLASSIFICATION_LIVE = "live_push"
CLASSIFICATION_BACKFILL = "initial_backfill"


class EventBlock(BaseModel):
    id: str = Field(min_length=1)
    type: str = "push"
    received_at: str | None = None
    classification: str = CLASSIFICATION_LIVE

    @field_validator("id")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("event.id must be non-empty")
        return v


class InstallationBlock(BaseModel):
    github_installation_id: int | None = None


class RepositoryBlock(BaseModel):
    github_id: int
    name: str
    full_name: str
    owner: str
    private: bool = False
    default_branch: str | None = None
    url: str | None = None


class ActorBlock(BaseModel):
    github_id: int | None = None
    username: str | None = None
    name: str | None = None
    email: str | None = None


class PushBlock(BaseModel):
    ref: str | None = None
    branch: str | None = None
    before: str | None = None
    after: str | None = None
    forced: bool = False
    created: bool = False
    deleted: bool = False


class PersonBlock(BaseModel):
    name: str | None = None
    email: str | None = None
    username: str | None = None


class CommitBlock(BaseModel):
    sha: str = Field(min_length=1)
    message: str | None = None
    timestamp: str | None = None
    author: PersonBlock = Field(default_factory=PersonBlock)
    committer: PersonBlock = Field(default_factory=PersonBlock)
    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class ChangeBlock(BaseModel):
    path: str = Field(min_length=1)
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    sha: str | None = None
    patch: str | None = None
    # Only produced by the backfill generator today; the existing n8n live
    # mapping does not carry previous_filename (see final report).
    previous_path: str | None = None


class BackfillBlock(BaseModel):
    sequence: int = 0
    is_initial_commit: bool = False
    parent_sha: str | None = None
    sync_target_commit: str | None = None


class IngestionEventPayload(BaseModel):
    event: EventBlock
    installation: InstallationBlock = Field(default_factory=InstallationBlock)
    repository: RepositoryBlock
    actor: ActorBlock = Field(default_factory=ActorBlock)
    push: PushBlock = Field(default_factory=PushBlock)
    commits: list[CommitBlock] = Field(default_factory=list)
    changes: list[ChangeBlock] = Field(default_factory=list)
    backfill: BackfillBlock | None = None

    @property
    def is_backfill(self) -> bool:
        return (
            self.backfill is not None
            or self.event.classification == CLASSIFICATION_BACKFILL
        )

    def model_post_init(self, __context: Any) -> None:
        has_block = self.backfill is not None
        classified = self.event.classification == CLASSIFICATION_BACKFILL
        if has_block != classified:
            raise ValueError(
                "backfill block and event.classification=initial_backfill "
                "must be present together"
            )


class EventValidationError(ValueError):
    """Raised when a Kafka payload does not satisfy the event contract."""


def parse_event(raw: bytes | str | dict[str, Any]) -> IngestionEventPayload:
    import json

    if isinstance(raw, (bytes, str)):
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise EventValidationError(f"payload is not valid JSON: {exc}") from exc
    else:
        data = raw
    try:
        return IngestionEventPayload.model_validate(data)
    except Exception as exc:  # pydantic wraps everything
        raise EventValidationError(str(exc)) from exc
