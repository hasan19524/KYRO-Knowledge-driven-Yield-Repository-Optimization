"""User identity + admin authentication (X-API-Key).

Two credential kinds share the X-API-Key header; identity is ALWAYS derived
server-side from the credential, never from a client-supplied user id:

  * shared service key (config.KYRO_API_KEY) -> the legacy `default`
    identity. This is what the Next.js proxy injects server-side, so the
    existing frontend keeps working without changes.
  * per-user API key (users.api_key_hash, SHA-256 of the key) -> that
    user's identity, used for multi-user isolation.

Unset KYRO_API_KEY => local development mode: requests without a per-user
key act as the `default` identity (same open behavior as before). A
per-user key still resolves when presented, and a key belonging to a
deactivated user is always rejected (fail-closed).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.db.models import DEFAULT_USER_HANDLE, Repository, User


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated identity for one request."""

    id: int
    handle: str
    is_default: bool


def get_state(request: Request):
    """FastAPI dependency: the application state attached at startup."""
    return request.app.state.kyro


def hash_api_key(key: str) -> str:
    """SHA-256 of an API key (only the hash is ever stored)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Fresh per-user API key (returned to the caller exactly once)."""
    return f"kyro_{secrets.token_hex(24)}"


def _as_current(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        handle=user.handle,
        is_default=user.handle == DEFAULT_USER_HANDLE,
    )


def _default_user(session_factory: sessionmaker[Session]) -> CurrentUser:
    """Resolve (creating on demand) the legacy `default` identity."""
    with session_factory() as session, session.begin():
        user = session.scalar(select(User).where(User.handle == DEFAULT_USER_HANDLE))
        if user is not None:
            return _as_current(user)
    # Rare: the migration seed row is missing (fresh/undeveloped DB).
    try:
        with session_factory() as session, session.begin():
            user = User(handle=DEFAULT_USER_HANDLE, is_active=True)
            session.add(user)
            session.flush()
            return _as_current(user)
    except IntegrityError:
        with session_factory() as session:
            raced = session.scalar(
                select(User).where(User.handle == DEFAULT_USER_HANDLE)
            )
            if raced is None:
                raise
            return _as_current(raced)


def _user_by_key(
    session_factory: sessionmaker[Session], key: str
) -> tuple[CurrentUser, bool] | None:
    """Look up a user by API key hash -> (identity, is_active) or None."""
    with session_factory() as session:
        user = session.scalar(
            select(User).where(User.api_key_hash == hash_api_key(key))
        )
        if user is None:
            return None
        return _as_current(user), user.is_active


def require_user(
    request: Request, x_api_key: str | None = Header(default=None)
) -> CurrentUser:
    """Resolve the requesting user's identity from the X-API-Key header."""
    session_factory = get_state(request).session_factory
    expected = config.KYRO_API_KEY

    if expected:
        # Shared service key => legacy identity (proxy / operators).
        if x_api_key is not None and secrets.compare_digest(x_api_key, expected):
            return _default_user(session_factory)
    elif x_api_key is None:
        # Development mode without any credential => legacy behavior.
        return _default_user(session_factory)

    if x_api_key:
        found = _user_by_key(session_factory, x_api_key)
        if found is not None:
            user, is_active = found
            if not is_active:
                raise HTTPException(
                    status_code=401, detail="invalid or missing API key"
                )
            return user

    if expected:
        # Production: any other credential (garbage, unknown, or the shared
        # key in dev-only setups) is rejected before reaching a handler.
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    # Development mode with an unrecognized header: stay open (before this
    # milestone every endpoint behaved that way when no key was configured).
    return _default_user(session_factory)


def require_admin(
    request: Request, x_api_key: str | None = Header(default=None)
) -> CurrentUser:
    """Guard for user-management endpoints.

    Only the shared service key grants admin rights in production; per-user
    keys never do. With KYRO_API_KEY unset (local development) the guard is
    open, matching the rest of the API's development-mode behavior.
    """
    expected = config.KYRO_API_KEY
    if not expected:
        return _default_user(get_state(request).session_factory)
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="admin credentials required")
    return _default_user(get_state(request).session_factory)


def may_access(repo: Repository, user: CurrentUser | None) -> bool:
    """Server-side ownership rule for repository operations.

    * internal/system callers (user=None) see everything;
    * repositories with an owner are visible only to that owner;
    * unowned rows (created by ingestion without an onboarding claim) are
      visible only to the legacy `default` identity - per-user identities
      are locked out (fail-closed) until someone claims the repository.
    """
    if user is None:
        return True
    if repo.owner_user_id is None:
        return user.is_default
    return repo.owner_user_id == user.id


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Legacy raw gate kept for endpoints that need the key but no identity.

    Unset KYRO_API_KEY => authentication disabled (local development only).
    """
    expected = config.KYRO_API_KEY
    if not expected:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


__all__ = [
    "CurrentUser",
    "generate_api_key",
    "get_state",
    "hash_api_key",
    "may_access",
    "require_admin",
    "require_api_key",
    "require_user",
]
