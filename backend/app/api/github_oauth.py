"""GitHub App OAuth: "Sign in with GitHub" (additive third identity kind).

Flow (one-click redirect, GitHub App user authorization):

  GET /api/auth/github/start
      -> 302 to GitHub's authorize URL. `state` is a stateless signed
         blob (HMAC-SHA256 over {exp, nonce} keyed by the client secret):
         unforgeable, expires in 10 min, needs no server-side storage.
  GET /api/auth/github/callback?code=...&state=...
      -> validates state, exchanges the code server-side (the client
         secret never leaves the backend), reads the user's identity,
         links or creates the KYRO account, creates a login session and
         answers 302 -> /app with the session cookie set. The OAuth
         access token is used ONCE for identity and NEVER stored.

Account resolution (fail-closed, no enumeration):

  1. users.github_id match           -> sign in as that user
  2. else GitHub email match on
     users.email (verified primary)  -> LINK: attach github_id/login
  3. else create new user            -> handle derived from the login
  deactivated account                -> redirect to /login?error=github

The Next.js proxy forwards these two GETs verbatim (Location + Set-Cookie
passthrough) and injects X-Kyro-Self-Origin so the redirect_uri matches
the origin the browser actually used (GitHub requires an exact match
against the registered callback URLs).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import config
from app.api.account import _check_rate, _derive_handle, _unique_handle
from app.api.auth import CurrentUser, create_session, get_state, require_session
from app.db.models import Repository, User
from app.github.auth import GitHubAppAuth, GitHubAuthError, GitHubCredentialsMissing
from app.state import AppState

log = logging.getLogger("kyro.api.github_oauth")

auth_router = APIRouter(prefix="/api/auth/github", tags=["auth-github"])
repos_router = APIRouter(prefix="/api/github", tags=["github"])

# Set by the proxy per-request (public origin the browser used).
_SELF_ORIGIN_HEADER = "X-Kyro-Self-Origin"
_STATE_TTL_S = 600
_CALLBACK_PATH = "/backend/api/auth/github/callback"
_SESSION_COOKIE = "kyro_session"
# Matches the Next.js proxy's session cookie (7 days).
_SESSION_MAX_AGE_S = 7 * 24 * 60 * 60


# --------------------------------------------------------------- state blob
def _state_key() -> bytes:
    return hashlib.sha256(config.GITHUB_CLIENT_SECRET.encode("utf-8")).digest()


def _sign_state(payload: dict[str, Any]) -> str:
    blob = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(_state_key(), blob.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{blob}.{sig}"


def _verify_state(state: str) -> bool:
    try:
        blob, sig = state.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(_state_key(), blob.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        padding = "=" * (-len(blob) % 4)
        payload = json.loads(base64.urlsafe_b64decode(blob + padding))
    except (ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    exp = payload.get("exp")
    return isinstance(exp, (int, float)) and exp > time.time()


def _public_origin(request: Request) -> str:
    origin = (
        request.headers.get(_SELF_ORIGIN_HEADER) or config.KYRO_PUBLIC_URL
    ).rstrip("/")
    if not origin.startswith(("http://", "https://")):
        raise HTTPException(status_code=503, detail="public origin not configured")
    return origin


# ---------------------------------------------------- GitHub HTTP seams
# (module-level so tests can monkeypatch without touching the routes)
def _exchange_code(code: str, redirect_uri: str) -> str:
    """One-shot code -> user access token exchange (server-side only)."""
    with httpx.Client(
        base_url=config.GITHUB_WEB_BASE_URL, timeout=config.GITHUB_TIMEOUT_S
    ) as client:
        resp = client.post(
            "/login/oauth/access_token",
            data={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise GitHubAuthError(f"token exchange failed (HTTP {resp.status_code})")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        # Never log response bodies here - they can echo secrets.
        raise GitHubAuthError(
            f"token exchange rejected: {data.get('error', 'unknown')}"
        )
    return str(token)


def _fetch_identity(access_token: str) -> dict[str, Any]:
    """Read {id, login, email} once; the token is discarded afterwards."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(
        base_url=config.GITHUB_API_BASE_URL, timeout=config.GITHUB_TIMEOUT_S
    ) as client:
        resp = client.get("/user", headers=headers)
        if resp.status_code != 200:
            raise GitHubAuthError(f"/user failed (HTTP {resp.status_code})")
        user = resp.json()
        email = (user.get("email") or "").strip().lower() or None
        if email is None:
            # Primary verified email (needs the user:email scope we request).
            emails = client.get("/user/emails", headers=headers)
            if emails.status_code == 200:
                for entry in emails.json():
                    if entry.get("primary") and entry.get("verified"):
                        email = (entry.get("email") or "").strip().lower() or None
                        break
    gh_id = user.get("id")
    login = user.get("login")
    if not isinstance(gh_id, int) or not login:
        raise GitHubAuthError("identity payload missing id/login")
    return {"id": gh_id, "login": str(login), "email": email}


def _fetch_installation_repositories() -> list[dict[str, Any]]:
    """Repos visible to the GitHub App installation (server-side token)."""
    installation_id = (config.GITHUB_APP_INSTALLATION_ID or "").strip()
    if not installation_id.isdigit():
        raise GitHubCredentialsMissing("GITHUB_APP_INSTALLATION_ID is not set")
    token = GitHubAppAuth().installation_token(int(installation_id))
    with httpx.Client(
        base_url=config.GITHUB_API_BASE_URL, timeout=config.GITHUB_TIMEOUT_S
    ) as client:
        resp = client.get(
            "/installation/repositories",
            params={"per_page": 100},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if resp.status_code != 200:
        raise GitHubAuthError(f"listing repositories failed (HTTP {resp.status_code})")
    return list(resp.json().get("repositories", []))


# ------------------------------------------------------------- OAuth routes
@auth_router.get("/start")
def start(request: Request) -> RedirectResponse:
    if not config.GITHUB_CLIENT_ID or not config.GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="github sign-in is not configured")
    state: AppState = get_state(request)
    _check_rate(state, "auth_github_start", "RATE_LIMIT_LOGIN_PER_MIN", "github-oauth")

    redirect_uri = f"{_public_origin(request)}{_CALLBACK_PATH}"
    blob = _sign_state({"exp": int(time.time()) + _STATE_TTL_S})
    params = urlencode(
        {
            "client_id": config.GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "state": blob,
            "scope": "read:user user:email",
            "allow_signup": "false",
        }
    )
    log.info("github_oauth_start")
    return RedirectResponse(
        f"{config.GITHUB_WEB_BASE_URL}/login/oauth/authorize?{params}", status_code=302
    )


@auth_router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    fail = RedirectResponse("/login?error=github", status_code=302)
    if not code or not state or not _verify_state(state):
        log.warning("github_oauth_callback rejected (state/code)")
        return fail

    st: AppState = get_state(request)
    _check_rate(st, "auth_github_callback", "RATE_LIMIT_LOGIN_PER_MIN", "github-oauth")

    try:
        access_token = _exchange_code(
            code, f"{_public_origin(request)}{_CALLBACK_PATH}"
        )
        identity = _fetch_identity(access_token)
    except (GitHubAuthError, httpx.HTTPError) as exc:
        log.warning("github_oauth_exchange_failed error=%s", exc)
        return fail

    try:
        with st.session_factory() as session, session.begin():
            user = session.scalar(select(User).where(User.github_id == identity["id"]))
            if user is None and identity["email"]:
                user = session.scalar(
                    select(User).where(User.email == identity["email"])
                )
                if user is not None:
                    # Link the GitHub identity to the existing account.
                    user.github_id = identity["id"]
                    user.github_login = identity["login"]
            if user is None:
                user = User(
                    handle=_unique_handle(
                        session,
                        _derive_handle(
                            identity["login"],
                            identity["email"]
                            or f"{identity['login']}@users.noreply.github.com",
                        ),
                    ),
                    email=identity["email"],
                    github_id=identity["id"],
                    github_login=identity["login"],
                    is_active=True,
                )
                session.add(user)
                session.flush()
            if not user.is_active:
                log.warning("github_oauth_deactivated user_id=%d", user.id)
                return fail
            user_id = user.id
    except IntegrityError:
        # Unique github_id race (two callbacks at once): treat as failure;
        # the retry finds the row created by the winner.
        log.warning("github_oauth_race user_id unknown")
        return fail

    token = create_session(st.session_factory, user_id)
    log.info("github_oauth_login user_id=%d", user_id)
    resp = RedirectResponse("/app", status_code=302)
    resp.set_cookie(
        _SESSION_COOKIE,
        token,
        max_age=_SESSION_MAX_AGE_S,
        httponly=True,
        samesite="lax",
        secure=_public_origin(request).startswith("https://"),
        path="/",
    )
    return resp


# ----------------------------------------------------------- repo listing
class RepoOption(BaseModel):
    github_repository_id: int
    full_name: str
    name: str
    owner: str
    private: bool
    default_branch: str | None
    url: str | None
    onboarded: bool
    status: str | None


@repos_router.get("/repos", response_model=list[RepoOption])
def list_repos(
    st: AppState = Depends(get_state),
    user: CurrentUser = Depends(require_session),
) -> list[RepoOption]:
    """The user's GitHub repos (installation token) + KYRO onboarding state."""
    try:
        repos = _fetch_installation_repositories()
    except (GitHubAuthError, GitHubCredentialsMissing, httpx.HTTPError) as exc:
        log.warning("github_repo_list_failed error=%s", exc)
        raise HTTPException(status_code=502, detail="github is unreachable") from exc

    gh_ids = [int(r["id"]) for r in repos if r.get("id")]
    local: dict[int, Repository] = {}
    if gh_ids:
        with st.session_factory() as session:
            rows = session.scalars(
                select(Repository).where(Repository.github_repository_id.in_(gh_ids))
            ).all()
            local = {r.github_repository_id: r for r in rows}

    options: list[RepoOption] = []
    for repo in repos:
        gh_id = int(repo["id"])
        row = local.get(gh_id)
        full_name = str(repo.get("full_name") or repo.get("name") or "")
        options.append(
            RepoOption(
                github_repository_id=gh_id,
                full_name=full_name,
                name=str(repo.get("name") or full_name),
                owner=str(
                    repo.get("owner", {}).get("login") or full_name.split("/")[0]
                ),
                private=bool(repo.get("private")),
                default_branch=repo.get("default_branch"),
                url=repo.get("html_url"),
                # "onboarded" = the repo already exists in KYRO (any
                # identity); the picker then shows its sync status instead
                # of a Connect button. This deliberately does NOT filter by
                # ownership: the list is the GitHub App installation's own
                # visibility (the signed-in user's own repos) joined with
                # KYRO state — no cross-user leak. may_access still governs
                # query/resync on repos owned by another identity.
                onboarded=row is not None,
                status=row.status if row is not None else None,
            )
        )
    return options


__all__ = ["auth_router", "repos_router"]
