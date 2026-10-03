"""User management API (admin-guarded).

Lifecycle: create -> list/detail -> rotate key -> deactivate/reactivate ->
delete. API keys are hashed (SHA-256) before storage and returned exactly
once, at issue or rotation. Only the shared service key (KYRO_API_KEY)
grants access in production; with the key unset the guard is open, matching
the API's development mode. The legacy `default` user is protected from
deactivation and deletion.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.auth import (
    CurrentUser,
    generate_api_key,
    get_state,
    hash_api_key,
    require_admin,
)
from app.db.models import DEFAULT_USER_HANDLE, Repository, User
from app.state import AppState

log = logging.getLogger("kyro.api.users")

router = APIRouter(prefix="/api/users", tags=["users"])

_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")


# ------------------------------------------------------------------ schemas
class CreateUserRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=32)


class UserView(BaseModel):
    id: int
    handle: str
    is_active: bool
    has_api_key: bool
    created_at: str | None = None


class IssuedKey(BaseModel):
    id: int
    handle: str
    api_key: str


def _view(user: User) -> UserView:
    return UserView(
        id=user.id,
        handle=user.handle,
        is_active=user.is_active,
        has_api_key=user.api_key_hash is not None,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


def _get_or_404(state: AppState, user_id: int) -> User:
    with state.session_factory() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        session.expunge(user)
        return user


def _guard_not_default(user: User, action: str) -> None:
    if user.handle == DEFAULT_USER_HANDLE:
        raise HTTPException(
            status_code=409,
            detail=f"the legacy '{DEFAULT_USER_HANDLE}' user cannot be {action}",
        )


# ------------------------------------------------------------------ routes
@router.post("", status_code=201)
def create_user(
    body: CreateUserRequest,
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> dict:
    handle = body.handle.strip().lower()
    if not _HANDLE_RE.match(handle):
        raise HTTPException(
            status_code=422,
            detail="handle must be 3-32 chars: lowercase letters, digits, "
            "'_' or '-', starting with a letter or digit",
        )
    if handle == DEFAULT_USER_HANDLE:
        raise HTTPException(
            status_code=409,
            detail=f"handle '{DEFAULT_USER_HANDLE}' is reserved",
        )
    api_key = generate_api_key()
    with state.session_factory() as session, session.begin():
        exists = session.scalar(select(User).where(User.handle == handle))
        if exists is not None:
            raise HTTPException(status_code=409, detail="handle already exists")
        user = User(handle=handle, api_key_hash=hash_api_key(api_key), is_active=True)
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="handle already exists"
            ) from exc
        log.info("user_created user_id=%d handle=%s", user.id, handle)
        return {
            "id": user.id,
            "handle": user.handle,
            "is_active": user.is_active,
            "has_api_key": True,
            "api_key": api_key,  # plaintext: shown once, only the hash is kept
        }


@router.get("")
def list_users(
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> list[UserView]:
    with state.session_factory() as session:
        users = session.scalars(select(User).order_by(User.id)).all()
        return [_view(u) for u in users]


@router.get("/{user_id}")
def get_user(
    user_id: int,
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> UserView:
    return _view(_get_or_404(state, user_id))


@router.post("/{user_id}/rotate-key")
def rotate_key(
    user_id: int,
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> IssuedKey:
    user = _get_or_404(state, user_id)
    if user.handle == DEFAULT_USER_HANDLE:
        raise HTTPException(
            status_code=409,
            detail="the legacy default user authenticates via the shared "
            "service key and has no rotatable API key",
        )
    api_key = generate_api_key()
    with state.session_factory() as session, session.begin():
        row = session.get(User, user_id)
        if row is None:  # pragma: no cover - deleted concurrently
            raise HTTPException(status_code=404, detail="user not found")
        row.api_key_hash = hash_api_key(api_key)
        log.info("user_key_rotated user_id=%d handle=%s", row.id, row.handle)
        return IssuedKey(id=row.id, handle=row.handle, api_key=api_key)


@router.post("/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> UserView:
    user = _get_or_404(state, user_id)
    _guard_not_default(user, "deactivated")
    with state.session_factory() as session, session.begin():
        row = session.get(User, user_id)
        if row is None:  # pragma: no cover - deleted concurrently
            raise HTTPException(status_code=404, detail="user not found")
        row.is_active = False
        log.info("user_deactivated user_id=%d handle=%s", row.id, row.handle)
        return _view(row)


@router.post("/{user_id}/reactivate")
def reactivate_user(
    user_id: int,
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> UserView:
    user = _get_or_404(state, user_id)
    _guard_not_default(user, "reactivated")
    with state.session_factory() as session, session.begin():
        row = session.get(User, user_id)
        if row is None:  # pragma: no cover - deleted concurrently
            raise HTTPException(status_code=404, detail="user not found")
        row.is_active = True
        log.info("user_reactivated user_id=%d handle=%s", row.id, row.handle)
        return _view(row)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    state: AppState = Depends(get_state),
    _: CurrentUser = Depends(require_admin),
) -> None:
    user = _get_or_404(state, user_id)
    _guard_not_default(user, "deleted")
    with state.session_factory() as session, session.begin():
        owned = session.scalar(
            select(func.count())
            .select_from(Repository)
            .where(Repository.owner_user_id == user_id)
        )
        if owned:
            # Fail-closed: never orphan or silently reassign repositories.
            raise HTTPException(
                status_code=409,
                detail=f"user still owns {int(owned or 0)} repositories",
            )
        row = session.get(User, user_id)
        if row is None:  # pragma: no cover - deleted concurrently
            raise HTTPException(status_code=404, detail="user not found")
        session.delete(row)
        log.info("user_deleted user_id=%d handle=%s", user.id, user.handle)


__all__ = ["router"]
