"""Sign in with GitHub: state signing, callback identity, repo picker.

Acceptance coverage for the GitHub App OAuth flow:

  * state is a signed, expiring blob: tampering or expiry is rejected
    (CSRF defense; the client secret never leaves the backend)
  * /start answers the GitHub authorize URL with the exact redirect_uri
    derived from the browser's origin (X-Kyro-Self-Origin) and 503 when
    OAuth is not configured
  * /callback: bad state -> redirect to /login?error=github (no account
    touched); good state + GitHub identity -> user created/link-ed, a
    session cookie is set, and the OAuth access token is never persisted
  * GitHub email match LINKS the identity to the existing email/password
    account instead of creating a duplicate (single-account promise)
  * /api/github/repos requires a session and joins GitHub's installation
    repository list with KYRO onboarding state (fail closed on GitHub
    errors: 502, never a fabricated list)
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config
from app.api import github_oauth
from app.db.models import Repository, User
from app.github.backfill import BackfillService
from app.ingest.processor import EventProcessor
from app.main import create_app
from app.state import AppState
from app.sync.manager import SyncManager
from tests.fake_github import FakeGitHub, make_github_client

SERVICE_KEY = "svc-secret-key"

# The proxy injects this per-request; tests stand in for a browser origin.
ORIGIN = "http://testserver"
START_HEADERS = {"X-Kyro-Self-Origin": ORIGIN}


@pytest.fixture
def oauth_env(db, indexer, monkeypatch):
    """API with OAuth configured; GitHub HTTP seams monkeypatched."""
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "test-client-secret")
    fake = FakeGitHub()
    gh_client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, gh_client)
    backfill = BackfillService(gh_client)
    manager = SyncManager(
        db,
        backfill,
        processor,
        gh_client,
        backfill_topic="kyro.test.unused.oauth",
        timeout=5.0,
        poll_interval=0.05,
        publish_batch=2,
        concurrency=1,
    )
    state = AppState(
        session_factory=db,
        indexer=indexer,
        github_client=gh_client,
        processor=processor,
        backfill=backfill,
        sync_manager=manager,
        llm=lambda prompt: "SYNTHETIC ANSWER",
    )
    app = create_app(state)
    with TestClient(app) as http:
        yield SimpleNamespace(http=http, state=state, db=db)


def _sign(payload: dict) -> str:
    return github_oauth._sign_state(payload)


def _valid_state() -> str:
    return _sign({"exp": int(time.time()) + 300})


def _patch_identity(monkeypatch, gh_id=777, login="octo", email=None):
    monkeypatch.setattr(
        github_oauth, "_exchange_code", lambda code, redirect_uri: "fake-oauth-token"
    )
    monkeypatch.setattr(
        github_oauth,
        "_fetch_identity",
        lambda token: {"id": gh_id, "login": login, "email": email},
    )


# ------------------------------------------------------------- state signing
def test_state_roundtrip_and_tamper_rejected():
    state = _valid_state()
    assert github_oauth._verify_state(state) is True
    blob, _sig = state.rsplit(".", 1)
    assert github_oauth._verify_state(f"{blob}.{'0' * 64}") is False
    assert github_oauth._verify_state("not-a-state") is False
    assert github_oauth._verify_state("") is False


def test_state_expiry_rejected():
    expired = _sign({"exp": int(time.time()) - 1})
    assert github_oauth._verify_state(expired) is False


def test_state_signature_binds_to_client_secret(monkeypatch):
    state = _valid_state()
    monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "rotated-secret")
    # A state minted under the old secret must not verify after rotation.
    assert github_oauth._verify_state(state) is False


# ------------------------------------------------------------------- /start
def test_start_redirects_to_github_authorize(oauth_env, monkeypatch):
    r = oauth_env.http.get(
        "/api/auth/github/start", headers=START_HEADERS, follow_redirects=False
    )
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=test-client-id" in location
    # redirect_uri is built from the browser origin the proxy reported
    # (urlencode escapes every reserved char, ':' included).
    assert (
        "redirect_uri=http%3A%2F%2Ftestserver%2Fbackend%2Fapi%2Fauth%2Fgithub%2Fcallback"
        in location
    )
    assert "state=" in location
    assert "scope=read%3Auser+user%3Aemail" in location


def test_start_503_when_oauth_not_configured(oauth_env, monkeypatch):
    monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "")
    r = oauth_env.http.get(
        "/api/auth/github/start", headers=START_HEADERS, follow_redirects=False
    )
    assert r.status_code == 503


# ----------------------------------------------------------------/callback
def _callback(env, state: str | None, code: str | None = "authcode"):
    params: dict[str, str] = {}
    if state is not None:
        params["state"] = state
    if code is not None:
        params["code"] = code
    return env.http.get(
        "/api/auth/github/callback",
        params=params,
        headers=START_HEADERS,
        follow_redirects=False,
    )


def test_callback_rejects_missing_or_tampered_state(oauth_env, monkeypatch):
    _patch_identity(monkeypatch)
    for state in (None, "forged.state", _valid_state() + "x"):
        r = _callback(oauth_env, state=state)
        assert r.status_code == 302
        assert r.headers["location"].startswith("/login?error=github")
    # No user was created by any of the rejected attempts.
    with oauth_env.db() as session:
        assert session.scalar(select(User).limit(1)) is None


def test_callback_creates_user_and_sets_session_cookie(oauth_env, monkeypatch):
    _patch_identity(monkeypatch, gh_id=4242, login="octo-cat", email=None)
    r = _callback(oauth_env, state=_valid_state())
    assert r.status_code == 302
    assert r.headers["location"] == "/app"
    token = r.cookies.get("kyro_session")
    assert token, "session cookie must be set on the callback redirect"

    with oauth_env.db() as session:
        user = session.scalar(select(User).where(User.github_id == 4242))
        assert user is not None
        assert user.github_login == "octo-cat"
        assert user.email is None  # GitHub email was private
    # The session cookie resolves to the new identity on /me.
    me = oauth_env.http.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["github_login"] == "octo-cat"


def test_callback_links_github_identity_to_existing_email_account(
    oauth_env, monkeypatch
):
    # Existing email/password account (the "no duplicates" promise).
    created = oauth_env.http.post(
        "/api/auth/register",
        json={"email": "jane@example.com", "password": "correct-horse-1"},
    )
    assert created.status_code == 201
    original_id = created.json()["user"]["id"]

    _patch_identity(monkeypatch, gh_id=9001, login="janegh", email="jane@example.com")
    r = _callback(oauth_env, state=_valid_state())
    assert r.status_code == 302
    token = r.cookies.get("kyro_session")

    with oauth_env.db() as session:
        rows = session.scalars(select(User)).all()
        assert len(rows) == 1, "email match must LINK, not duplicate"
        user = rows[0]
        assert user.id == original_id
        assert user.github_id == 9001
        assert user.github_login == "janegh"
    me = oauth_env.http.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.json()["id"] == original_id


def test_callback_second_signin_reuses_same_user(oauth_env, monkeypatch):
    _patch_identity(monkeypatch, gh_id=555, login="reuser", email=None)
    first = _callback(oauth_env, state=_valid_state())
    second = _callback(oauth_env, state=_valid_state())
    assert first.status_code == second.status_code == 302
    with oauth_env.db() as session:
        rows = session.scalars(select(User).where(User.github_id == 555)).all()
        assert len(rows) == 1


def test_callback_rate_limited_subject(oauth_env, monkeypatch):
    # The rate limiter shares the login bucket; hammering /callback trips it.
    _patch_identity(monkeypatch)
    from app import config as cfg

    monkeypatch.setattr(cfg, "RATE_LIMIT_LOGIN_PER_MIN", 2)
    hits = 0
    for _ in range(5):
        r = _callback(oauth_env, state=_valid_state())
        if r.status_code == 429:
            hits += 1
    assert hits >= 1, "repeated callback attempts must hit the rate limit"


def test_callback_deactivated_user_is_rejected(oauth_env, monkeypatch):
    _patch_identity(monkeypatch, gh_id=1212, login="gone", email=None)
    # First sign-in creates the account; deactivate it; second sign-in fails.
    assert _callback(oauth_env, state=_valid_state()).status_code == 302
    with oauth_env.db() as session, session.begin():
        user = session.scalar(select(User).where(User.github_id == 1212))
        user.is_active = False
    r = _callback(oauth_env, state=_valid_state())
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login?error=github")


# --------------------------------------------------------------- /api/github/repos
def test_repos_requires_a_session(oauth_env, monkeypatch):
    monkeypatch.setattr(github_oauth, "_fetch_installation_repositories", lambda: [])
    r = oauth_env.http.get("/api/github/repos")
    assert r.status_code == 401


def _sign_in_via_github(env, monkeypatch, gh_id=1, login="u") -> str:
    _patch_identity(monkeypatch, gh_id=gh_id, login=login, email=None)
    r = _callback(env, state=_valid_state())
    assert r.status_code == 302
    return r.cookies.get("kyro_session")


def test_repos_lists_github_repos_with_onboarded_state(oauth_env, monkeypatch):
    token = _sign_in_via_github(oauth_env, monkeypatch)
    monkeypatch.setattr(
        github_oauth,
        "_fetch_installation_repositories",
        lambda: [
            {
                "id": 111,
                "full_name": "hasan/acumen",
                "name": "acumen",
                "owner": {"login": "hasan"},
                "private": False,
                "default_branch": "main",
                "html_url": "https://github.com/hasan/acumen",
            },
            {
                "id": 222,
                "full_name": "hasan/fresh",
                "name": "fresh",
                "owner": {"login": "hasan"},
                "private": True,
                "default_branch": "master",
                "html_url": "https://github.com/hasan/fresh",
            },
        ],
    )
    # One of them is already onboarded in KYRO.
    with oauth_env.db() as session, session.begin():
        session.add(
            Repository(
                github_repository_id=111,
                name="acumen",
                full_name="hasan/acumen",
                owner="hasan",
                default_branch="main",
                status="READY",
            )
        )

    r = oauth_env.http.get(
        "/api/github/repos", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    items = {item["github_repository_id"]: item for item in r.json()}
    assert items[111]["onboarded"] is True
    assert items[111]["status"] == "READY"
    assert items[222]["onboarded"] is False
    assert items[222]["status"] is None
    assert items[222]["private"] is True


def test_repos_github_failure_is_502_not_fake_list(oauth_env, monkeypatch):
    from app.github.auth import GitHubAuthError

    token = _sign_in_via_github(oauth_env, monkeypatch, gh_id=2, login="u2")

    def _boom():
        raise GitHubAuthError("installation token rejected")

    monkeypatch.setattr(github_oauth, "_fetch_installation_repositories", _boom)
    r = oauth_env.http.get(
        "/api/github/repos", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 502
