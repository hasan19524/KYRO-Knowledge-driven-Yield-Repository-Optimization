"""Additive account login API (register / login / logout / me).

Design constraints (integration plan Phase 3b):

* purely additive — the X-API-Key auth path and all ownership checks are
  untouched; these endpoints resolve sessions to the same `CurrentUser`
* only PBKDF2 password hashes and SHA-256 session-token hashes are stored
* session tokens are returned in the JSON body exactly once; the Next.js
  proxy is expected to hand them to the browser as an httpOnly
  `kyro_session` cookie and forward them back as `Authorization: Bearer`
* new accounts get no admin rights, no API key, and see no repositories
  they do not own (fail-closed)
* login answers a uniform 401 for unknown email / wrong password /
  deactivated account (no account enumeration); pre-auth rate limiting is
  keyed on the normalized email
"""

from __future__ import annotations

import hashlib
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import config
from app.api.auth import (
    CurrentUser,
    bearer_token,
    create_session,
    get_state,
    hash_session_token,
    require_session,
)
from app.db.models import DEFAULT_USER_HANDLE, User, UserSession
from app.security.passwords import hash_password, verify_password
from app.state import AppState

log = logging.getLogger("kyro.api.account")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")

INVALID_CREDENTIALS = "invalid email or password"


# ------------------------------------------------------------------ schemas
class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    # Short passwords get the uniform 401, not a validation error, so the
    # response shape reveals nothing about account existence.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AccountUser(BaseModel):
    id: int
    handle: str
    email: str | None
    # Set when the account was created/linked via "Sign in with GitHub".
    github_login: str | None = None


class AuthSession(BaseModel):
    token: str
    token_type: str = "bearer"
    user: AccountUser


# ------------------------------------------------------------------ helpers
def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _email_subject(email: str) -> int:
    """Deterministic per-email subject for the in-memory rate limiter."""
    digest = hashlib.sha256(email.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _check_rate(state: AppState, bucket: str, setting: str, email: str) -> None:
    limit = int(getattr(config, setting, 0))
    retry_after = state.rate_limiter.hit(
        bucket=bucket, subject_id=_email_subject(email), limit=limit, window_s=60
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def _derive_handle(name: str | None, email: str) -> str:
    base = (name or email.split("@", 1)[0]).strip().lower()
    base = re.sub(r"[^a-z0-9_-]+", "-", base).strip("-_")
    if not base or not base[0].isalnum():
        base = f"u{base}".strip("-_")
    base = base[:23].strip("-_") or "user"  # room for a "-xxxxxxxx" suffix <= 32
    if len(base) < 3:
        base = f"{base}user"
    return base


def _unique_handle(session, base: str) -> str:
    candidate = base
    for _ in range(8):
        taken = session.scalar(select(User.handle).where(User.handle == candidate))
        if taken is None and candidate != DEFAULT_USER_HANDLE:
            return candidate
        candidate = f"{base}-{hashlib.sha256(candidate.encode()).hexdigest()[:4]}"
    return f"{base}-{hashlib.sha256(candidate.encode()).hexdigest()[:8]}"


def _view(user: User) -> AccountUser:
    return AccountUser(
        id=user.id,
        handle=user.handle,
        email=user.email,
        github_login=user.github_login,
    )


# -------------------------------------------------------------------- routes
@router.post("/register", status_code=201, response_model=AuthSession)
def register(
    body: RegisterRequest,
    state: AppState = Depends(get_state),
) -> AuthSession:
    email = _normalize_email(body.email)
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(status_code=422, detail="invalid email address")
    _check_rate(state, "auth_register", "RATE_LIMIT_REGISTER_PER_MIN", email)

    password_hash = hash_password(body.password)
    try:
        with state.session_factory() as session, session.begin():
            exists = session.scalar(select(User).where(User.email == email))
            if exists is not None:
                raise HTTPException(status_code=409, detail="email already registered")
            user = User(
                handle=_unique_handle(session, _derive_handle(body.name, email)),
                email=email,
                password_hash=password_hash,
                is_active=True,
            )
            session.add(user)
            session.flush()
            user_id = user.id
            view = _view(user)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="email already registered") from exc

    token = create_session(state.session_factory, user_id)
    log.info("account_registered user_id=%d", user_id)
    return AuthSession(token=token, user=view)


@router.post("/login", response_model=AuthSession)
def login(
    body: LoginRequest,
    state: AppState = Depends(get_state),
) -> AuthSession:
    email = _normalize_email(body.email)
    _check_rate(state, "auth_login", "RATE_LIMIT_LOGIN_PER_MIN", email)

    with state.session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        # Uniform failure for unknown email / bad password / deactivated:
        # the response reveals nothing about which one it was.
        if (
            user is None
            or user.password_hash is None
            or not user.is_active
            or not verify_password(body.password, user.password_hash)
        ):
            raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
        user_id = user.id
        view = _view(user)

    token = create_session(state.session_factory, user_id)
    log.info("account_login user_id=%d", user_id)
    return AuthSession(token=token, user=view)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    state: AppState = Depends(get_state),
    _user: CurrentUser = Depends(require_session),
) -> None:
    # require_session already validated this bearer token; delete its row -
    # that IS the server-side invalidation (the browser cookie is cleared
    # by the Next.js proxy layer).
    token = bearer_token(request.headers.get("Authorization"))
    assert token is not None  # require_session would have 401'd otherwise
    with state.session_factory() as session, session.begin():
        row = session.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(token)
            )
        )
        if row is not None:
            session.delete(row)
    log.info("account_logout user_id=%d", _user.id)


@router.get("/me", response_model=AccountUser)
def me(
    state: AppState = Depends(get_state),
    user: CurrentUser = Depends(require_session),
) -> AccountUser:
    with state.session_factory() as session:
        row = session.get(User, user.id)
        if row is None:  # pragma: no cover - session validated moments ago
            raise HTTPException(status_code=401, detail="invalid or expired session")
        return _view(row)


__all__ = ["router"]
