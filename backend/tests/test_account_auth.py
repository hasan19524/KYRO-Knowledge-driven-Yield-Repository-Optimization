"""Additive account login: register/login/logout/me + session identity.

Acceptance coverage for Phase 3b:

  * registration creates a user with a PBKDF2 password hash (never
    plaintext) and NO admin rights / API key / visible repositories
  * login answers a uniform 401 for unknown email, wrong password and
    deactivated accounts (no enumeration) and is pre-auth rate limited
  * sessions store only the SHA-256 of the opaque token; expiry is
    server-side; logout deletes the row (immediate invalidation)
  * a bearer session resolves to the same CurrentUser and enforces the
    existing ownership rules (cross-user access stays 404/empty)
  * an invalid/expired bearer is a TERMINAL 401 - never a fallback to
    X-API-Key auth or the development-mode identity
  * the X-API-Key path itself is unchanged
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import config
from app.api.auth import hash_session_token
from app.db.models import DEFAULT_USER_HANDLE, Repository, User, UserSession
from app.github.backfill import BackfillService
from app.ingest.processor import EventProcessor
from app.main import create_app
from app.security.passwords import hash_password, verify_password
from app.state import AppState
from app.sync.manager import SyncManager
from tests.fake_github import FakeGitHub, make_github_client

SERVICE_KEY = "svc-secret-key"


@pytest.fixture
def auth_env(db, indexer):
    """API wired to fake GitHub and real DB/Chroma (no Kafka)."""
    fake = FakeGitHub()
    gh_client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, gh_client)
    backfill = BackfillService(gh_client)
    manager = SyncManager(
        db,
        backfill,
        processor,
        gh_client,
        backfill_topic="kyro.test.unused.auth",
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


# ------------------------------------------------------------------ helpers
def _register(env, email="jane@example.com", password="correct-horse-1", name=None):
    body = {"email": email, "password": password}
    if name is not None:
        body["name"] = name
    r = env.http.post("/api/auth/register", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _bearer(session: dict) -> dict:
    return {"Authorization": f"Bearer {session['token']}"}


def _seed_repo(env, gid: int, owner_user_id: int | None) -> int:
    with env.db() as session, session.begin():
        repo = Repository(
            github_repository_id=gid,
            name="demo",
            full_name="org/demo",
            owner="org",
            default_branch="main",
            status="READY",
            owner_user_id=owner_user_id,
        )
        session.add(repo)
        session.flush()
        return repo.id


def _default_user_id(env) -> int:
    """The default identity (created on demand, like auth.py does)."""
    with env.db() as session:
        row = session.scalar(select(User).where(User.handle == DEFAULT_USER_HANDLE))
        if row is not None:
            return row.id
    with env.db() as session, session.begin():
        row = User(handle=DEFAULT_USER_HANDLE, is_active=True)
        session.add(row)
        session.flush()
        return row.id


# ----------------------------------------------------------- password units
def test_password_hash_roundtrip_and_fail_closed():
    stored = hash_password("correct-horse-1")
    assert stored.startswith("pbkdf2_sha256$")
    assert "correct-horse-1" not in stored
    assert verify_password("correct-horse-1", stored)
    assert not verify_password("wrong-password", stored)
    assert not verify_password("correct-horse-1", "garbage")
    assert not verify_password("correct-horse-1", "pbkdf2_sha256$x$zz$zz")
    # Salted: the same password hashes differently every time.
    assert hash_password("correct-horse-1") != stored


# ---------------------------------------------------------------- register
def test_register_creates_session_and_works_on_me(auth_env):
    sess = _register(auth_env, name="Hasan Ali")
    assert sess["token"].startswith("kyro_sess_")
    assert sess["token_type"] == "bearer"
    assert sess["user"]["email"] == "jane@example.com"
    assert sess["user"]["handle"] == "hasan-ali"

    me = auth_env.http.get("/api/auth/me", headers=_bearer(sess))
    assert me.status_code == 200, me.text
    assert me.json() == sess["user"]


def test_register_stores_only_hashes(auth_env):
    sess = _register(auth_env)
    with auth_env.db() as session:
        user = session.scalar(select(User).where(User.email == "jane@example.com"))
        assert user is not None
        assert user.password_hash is not None
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert "correct-horse-1" not in user.password_hash
        assert user.api_key_hash is None  # no API key handed out at signup
        row = session.scalar(select(UserSession).where(UserSession.user_id == user.id))
        assert row is not None
        # Only the SHA-256 of the token is stored - never the token itself.
        assert row.token_hash == hashlib.sha256(sess["token"].encode()).hexdigest()
        assert row.token_hash == hash_session_token(sess["token"])
        assert len(row.token_hash) == 64


def test_register_normalizes_email_and_rejects_duplicates(auth_env):
    first = _register(auth_env, email="  Jane@Example.COM ")
    again = auth_env.http.post(
        "/api/auth/register",
        json={"email": "jane@example.com", "password": "another-pass-1"},
    )
    assert again.status_code == 409
    assert first["user"]["email"] == "jane@example.com"


def test_register_handle_collisions_get_distinct_handles(auth_env):
    a = _register(auth_env, email="jane1@example.com", name="Jane")
    b = _register(auth_env, email="jane2@example.com", name="Jane")
    assert a["user"]["handle"] != b["user"]["handle"]
    assert a["user"]["handle"].startswith("jane")
    assert b["user"]["handle"].startswith("jane")


@pytest.mark.parametrize(
    "body",
    [
        {"email": "nope", "password": "long-enough-1"},
        {"email": "a@b.co", "password": "short"},  # < 8 chars
        {"email": "a@b.co", "password": "x" * 129},  # > 128 chars
        {"email": "", "password": "long-enough-1"},
    ],
)
def test_register_validation_rejected(auth_env, body):
    r = auth_env.http.post("/api/auth/register", json=body)
    assert r.status_code == 422


# ------------------------------------------------------------------- login
def test_login_success_and_identity(auth_env):
    created = _register(auth_env)
    r = auth_env.http.post(
        "/api/auth/login",
        json={"email": "JANE@example.com", "password": "correct-horse-1"},
    )
    assert r.status_code == 200, r.text
    sess = r.json()
    assert sess["user"]["id"] == created["user"]["id"]
    me = auth_env.http.get("/api/auth/me", headers=_bearer(sess))
    assert me.status_code == 200


@pytest.mark.parametrize(
    "email,password",
    [
        ("jane@example.com", "wrong-password-1"),  # wrong password
        ("nobody@example.com", "correct-horse-1"),  # unknown email
        ("jane@example.com", "short"),  # short password: 401, not 422
    ],
)
def test_login_failures_are_uniform_401(auth_env, email, password):
    _register(auth_env)
    r = auth_env.http.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid email or password"


def test_login_rate_limited_per_email(auth_env, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_LOGIN_PER_MIN", 3)
    _register(auth_env)
    codes = []
    for _ in range(4):
        r = auth_env.http.post(
            "/api/auth/login",
            json={"email": "jane@example.com", "password": "wrong-password-1"},
        )
        codes.append(r.status_code)
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429
    # A different email keeps its own budget.
    other = auth_env.http.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": "whatever-pass"},
    )
    assert other.status_code == 401


# ----------------------------------------------------- sessions lifecycle
def test_logout_invalidates_session_server_side(auth_env):
    sess = _register(auth_env)
    assert auth_env.http.get("/api/auth/me", headers=_bearer(sess)).status_code == 200

    out = auth_env.http.post("/api/auth/logout", headers=_bearer(sess))
    assert out.status_code == 204, out.text

    after = auth_env.http.get("/api/auth/me", headers=_bearer(sess))
    assert after.status_code == 401
    with auth_env.db() as session:
        rows = session.scalars(select(UserSession)).all()
        assert rows == []  # the row is gone, not merely flagged
    # Repeating logout is a clean 401 (already logged out).
    assert (
        auth_env.http.post("/api/auth/logout", headers=_bearer(sess)).status_code == 401
    )


def test_expired_session_rejected_server_side(auth_env):
    sess = _register(auth_env)
    with auth_env.db() as session, session.begin():
        row = session.scalar(select(UserSession))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    assert auth_env.http.get("/api/auth/me", headers=_bearer(sess)).status_code == 401


def test_me_and_logout_require_a_session(auth_env):
    assert auth_env.http.get("/api/auth/me").status_code == 401
    assert auth_env.http.post("/api/auth/logout").status_code == 401
    assert (
        auth_env.http.get(
            "/api/auth/me", headers={"Authorization": "Bearer kyro_sess_bogus"}
        ).status_code
        == 401
    )
    # An API key is NOT a session.
    assert (
        auth_env.http.get(
            "/api/auth/me", headers={"X-API-Key": "whatever-key"}
        ).status_code
        == 401
    )


def test_deactivated_user_cannot_login_or_use_sessions(auth_env, monkeypatch):
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    sess = _register(auth_env)
    admin = {"X-API-Key": SERVICE_KEY}
    r = auth_env.http.post(f"/api/users/{sess['user']['id']}/deactivate", headers=admin)
    assert r.status_code == 200

    login = auth_env.http.post(
        "/api/auth/login",
        json={"email": "jane@example.com", "password": "correct-horse-1"},
    )
    assert login.status_code == 401  # uniform failure, same message

    me = auth_env.http.get("/api/auth/me", headers=_bearer(sess))
    assert me.status_code == 401  # existing session dies with the account


# ------------------------------------------------- terminal bearer failures
def test_invalid_bearer_never_falls_back_to_api_key(auth_env, monkeypatch):
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    headers = {
        "Authorization": "Bearer kyro_sess_totally-bogus",
        "X-API-Key": SERVICE_KEY,  # valid shared key alongside
    }
    r = auth_env.http.get("/api/repositories", headers=headers)
    assert r.status_code == 401  # terminal: no fallback to the shared key


def test_expired_bearer_never_falls_back_to_dev_mode(auth_env):
    # KYRO_API_KEY unset => dev mode, but a bad bearer must still 401.
    sess = _register(auth_env)
    with auth_env.db() as session, session.begin():
        row = session.scalar(select(UserSession))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    r = auth_env.http.get("/api/repositories", headers=_bearer(sess))
    assert r.status_code == 401


def test_valid_session_wins_over_shared_key(auth_env, monkeypatch):
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    sess = _register(auth_env)
    unowned_gid = 880001
    _seed_repo(auth_env, unowned_gid, owner_user_id=None)  # default's repo

    both = {
        "Authorization": f"Bearer {sess['token']}",
        "X-API-Key": SERVICE_KEY,
    }
    r = auth_env.http.get("/api/repositories", headers=both)
    assert r.status_code == 200
    assert r.json() == []  # the session user is NOT the default identity


# --------------------------------------------- sessions vs ownership rules
def test_session_identity_enforces_ownership(auth_env):
    sess = _register(auth_env)
    other_gid, unowned_gid = 880101, 880102
    with auth_env.db() as session, session.begin():
        other = User(handle="other-user", is_active=True)
        session.add(other)
        session.flush()
        other_pk = other.id
    _seed_repo(auth_env, other_gid, owner_user_id=other_pk)
    _seed_repo(auth_env, unowned_gid, owner_user_id=None)

    r = auth_env.http.get("/api/repositories", headers=_bearer(sess))
    assert r.status_code == 200
    assert r.json() == []  # neither owned nor unowned repos are visible
    detail = auth_env.http.get(f"/api/repositories/{other_gid}", headers=_bearer(sess))
    assert detail.status_code == 404  # no existence leak


def test_new_account_has_no_admin_rights(auth_env, monkeypatch):
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    sess = _register(auth_env)
    r = auth_env.http.get("/api/users", headers=_bearer(sess))
    assert r.status_code == 401  # bearer sessions never grant admin


def test_default_identity_still_works_with_shared_key(auth_env, monkeypatch):
    """Regression: the shared-key (proxy) path is untouched by sessions."""
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    gid = 880201
    _seed_repo(auth_env, gid, owner_user_id=_default_user_id(auth_env))
    r = auth_env.http.get("/api/repositories", headers={"X-API-Key": SERVICE_KEY})
    assert r.status_code == 200
    assert [snap["github_repository_id"] for snap in r.json()] == [gid]


def test_user_sessions_schema_matches_model(auth_env):
    """The migrated schema carries the additive columns/table."""
    with auth_env.db() as session:
        cols = session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name IN ('email', 'password_hash')"
            )
        ).all()
        assert {c[0] for c in cols} == {"email", "password_hash"}
        tables = session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'user_sessions'"
            )
        ).all()
        assert tables
