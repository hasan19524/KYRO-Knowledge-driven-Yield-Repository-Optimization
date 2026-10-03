"""User authentication, user management, and multi-repository isolation.

Acceptance coverage for this milestone:

  * users table + repositories.owner_user_id FK (schema, migration safety)
  * per-user API keys: issued once, stored only as SHA-256, rotatable
  * identity resolution: shared KYRO_API_KEY -> legacy `default` identity,
    per-user key -> that user; invalid/missing/deactivated credentials
    rejected (fail-closed) whenever a service key is configured
  * ownership checked server-side on list/detail/onboard/resync/query;
    cross-user access rejected in both directions with 404 (no existence
    leak); client-supplied user ids ignored (never trusted)
  * ingestion never assigns ownership from event payloads; unowned rows
    stay ownerless (quarantined) and live events keep using the existing
    deferral mechanism
  * Chroma keys preserved (repository_id/commit_id/file_id/commit_sha/path)
    and traceable to the owning user through PostgreSQL; reindex idempotent
  * migration upgrade/downgrade preserves repository data
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from app import config
from app.api.auth import hash_api_key
from app.db.models import (
    DEFAULT_USER_HANDLE,
    Commit,
    CommitFile,
    File,
    Repository,
    RepositoryStatus,
    User,
)
from app.github.backfill import BackfillService
from app.ingest.persistence import IndexItem
from app.ingest.processor import EventProcessor
from app.main import create_app
from app.state import AppState
from app.sync.manager import SyncManager
from tests.conftest import (
    ADMIN_DB_URL,
    apply_event,
    build_backfill_events,
    live_event,
    live_event_for_head,
)
from tests.fake_github import FakeGitHub, make_github_client

GID_A1 = 910011
GID_A2 = 910012
GID_B1 = 910021
GID_A3 = 910031
GID_A4 = 910032
FAKE_GID = 1395956448  # the FakeGitHub repository id
SERVICE_KEY = "svc-secret-key"


@pytest.fixture
def owner_env(db, indexer):
    """API + processor wired to fake GitHub and real DB/Chroma (no Kafka)."""
    fake = FakeGitHub()
    gh_client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, gh_client)
    backfill = BackfillService(gh_client)
    manager = SyncManager(
        db,
        backfill,
        processor,
        gh_client,
        backfill_topic="kyro.test.unused.owner",
        timeout=5.0,
        poll_interval=0.05,
        publish_batch=2,
        concurrency=1,
    )
    prompts: list[str] = []

    def fake_llm(prompt: str) -> str:
        prompts.append(prompt)
        return "SYNTHETIC ANSWER"

    state = AppState(
        session_factory=db,
        indexer=indexer,
        github_client=gh_client,
        processor=processor,
        backfill=backfill,
        sync_manager=manager,
        llm=fake_llm,
    )
    app = create_app(state)
    with TestClient(app) as http:
        yield SimpleNamespace(
            http=http,
            state=state,
            manager=manager,
            processor=processor,
            db=db,
            indexer=indexer,
            fake=fake,
            prompts=prompts,
        )


# ------------------------------------------------------------------ helpers
def _create_user(env, handle: str) -> dict:
    r = env.http.post("/api/users", json={"handle": handle})
    assert r.status_code == 201, r.text
    return r.json()


def _hdr(user: dict) -> dict:
    return {"X-API-Key": user["api_key"]}


def _seed(
    env,
    gid: int,
    *,
    owner_user_id: int | None,
    status: str = RepositoryStatus.READY.value,
    name: str = "demo",
    owner: str = "org",
) -> int:
    """Insert a repository row directly; returns its primary key."""
    with env.db() as session, session.begin():
        repo = Repository(
            github_repository_id=gid,
            name=name,
            full_name=f"{owner}/{name}",
            owner=owner,
            default_branch="main",
            status=status,
            owner_user_id=owner_user_id,
        )
        session.add(repo)
        session.flush()
        return repo.id


def _repo(env, gid: int) -> Repository | None:
    with env.db() as session:
        return session.scalar(
            select(Repository).where(Repository.github_repository_id == gid)
        )


def _default_user_id(env) -> int:
    with env.db() as session:
        row = session.scalar(select(User).where(User.handle == DEFAULT_USER_HANDLE))
        assert row is not None, "default user must exist"
        return row.id


def _add_change_rows(env, repo_pk: int, *, sha: str, path: str) -> None:
    """Real Commit/File/CommitFile rows so query enrichment can join them."""
    now = datetime.now(UTC)
    with env.db() as session, session.begin():
        commit = Commit(
            repository_id=repo_pk,
            github_commit_sha=sha,
            message=f"change touching {path}",
            committed_at=now,
        )
        session.add(commit)
        session.flush()
        file_row = File(repository_id=repo_pk, path=path)
        session.add(file_row)
        session.flush()
        session.add(
            CommitFile(
                commit_id=commit.id,
                file_id=file_row.id,
                status="modified",
                additions=1,
                deletions=1,
                changes=2,
                patch=f"-old\n+new in {path}",
            )
        )


def _index_change(env, repo_pk: int, *, gid: int, sha: str, path: str) -> IndexItem:
    with env.db() as session:
        commit_id = session.scalar(
            select(Commit.id).where(
                Commit.repository_id == repo_pk, Commit.github_commit_sha == sha
            )
        )
        file_id = session.scalar(
            select(File.id).where(File.repository_id == repo_pk, File.path == path)
        )
    assert commit_id is not None and file_id is not None
    item = IndexItem(
        repository_pk=repo_pk,
        github_repository_id=gid,
        commit_pk=int(commit_id),
        commit_sha=sha,
        file_pk=int(file_id),
        path=path,
        status="modified",
        patch=f"-old\n+new in {path}",
        commit_message=f"change touching {path}",
        committed_at=datetime.now(UTC),
        additions=1,
        deletions=1,
    )
    env.indexer.index_event([item])
    return item


# ---------------------------------------------------- schema + migration (1, 18)
def test_users_schema_owner_fk_and_default_identity(owner_env):
    env = owner_env
    with env.db() as session:
        cols = {
            r[0]
            for r in session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users'"
                )
            )
        }
        assert {
            "id",
            "handle",
            "api_key_hash",
            "is_active",
            "created_at",
            "updated_at",
        } <= cols
        fks = session.execute(
            text(
                "SELECT conname, confdeltype FROM pg_constraint "
                "WHERE conrelid = 'repositories'::regclass AND contype = 'f'"
            )
        ).all()
        owner_fks = [row for row in fks if "owner_user_id" in row[0]]
        assert owner_fks, "repositories.owner_user_id must have an FK"
        # RESTRICT: deleting an owner must never silently orphan repositories.
        assert any(row[1] == "r" for row in owner_fks), "FK must be RESTRICT"

    # The legacy identity materializes on first use (seeded by migration in
    # real deployments, recreated on demand after test truncation).
    env.http.get("/api/repositories")
    default_id = _default_user_id(env)
    assert default_id > 0


def test_db_level_fk_restrict_blocks_deleting_owner(owner_env):
    env = owner_env
    with env.db() as session, session.begin():
        victim = User(handle="victim", is_active=True)
        session.add(victim)
        session.flush()
        session.add(
            Repository(
                github_repository_id=910099,
                name="guarded",
                full_name="org/guarded",
                owner="org",
                status=RepositoryStatus.READY.value,
                owner_user_id=victim.id,
            )
        )
        victim_pk = victim.id

    with env.db() as session:
        repo_pk = session.scalar(
            select(Repository.id).where(Repository.github_repository_id == 910099)
        )
        assert repo_pk is not None

    # ORM delete path: passive relationship -> the database itself refuses.
    with env.db() as session, pytest.raises(IntegrityError), session.begin():
        row = session.get(User, victim_pk)
        assert row is not None
        session.delete(row)

    with env.db() as session:
        assert session.get(User, victim_pk) is not None
        repo = session.get(Repository, repo_pk)
        assert repo is not None
        assert repo.owner_user_id == victim_pk  # ownership preserved


def test_migration_upgrade_downgrade_preserves_repository_data():
    """Full alembic cycle on an isolated database (non-destructive claim)."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mig_url = "postgresql+psycopg://kyro:kyro@localhost:5433/kyro_mig_check"
    admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            try:
                conn.execute(text("DROP DATABASE IF EXISTS kyro_mig_check"))
            except Exception:
                conn.execute(
                    text("DROP DATABASE IF EXISTS kyro_mig_check WITH (FORCE)")
                )
            conn.execute(text("CREATE DATABASE kyro_mig_check"))
        admin.dispose()

        env = dict(os.environ)
        env["DATABASE_URL"] = mig_url

        def alembic(*args: str) -> None:
            proc = subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=backend_dir,
                env=env,
                capture_output=True,
                text=True,
            )
            assert proc.returncode == 0, proc.stdout + proc.stderr

        alembic("upgrade", "head")

        probe = create_engine(mig_url)
        with probe.begin() as conn:
            default_id = conn.execute(
                text("SELECT id FROM users WHERE handle = 'default'")
            ).scalar()
            assert default_id is not None
            conn.execute(
                text(
                    "INSERT INTO repositories (github_repository_id, name, "
                    "full_name, owner, is_private, status, created_at, "
                    "updated_at) VALUES (424242, 'keepme', 'org/keepme', "
                    "'org', false, 'READY', now(), now())"
                )
            )
        # downgrade one revision, then upgrade again: data must survive.
        alembic("downgrade", "-1")
        alembic("upgrade", "head")

        with probe.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT name, full_name, owner, owner_user_id FROM "
                    "repositories WHERE github_repository_id = 424242"
                )
            ).one()
            assert row.name == "keepme"
            assert row.full_name == "org/keepme"
            assert row.owner == "org"
            # re-backfilled to the legacy identity after the cycle
            default_after = conn.execute(
                text("SELECT id FROM users WHERE handle = 'default'")
            ).scalar()
            assert row.owner_user_id == default_after
        probe.dispose()
    finally:
        admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            try:
                conn.execute(text("DROP DATABASE IF EXISTS kyro_mig_check"))
            except Exception:
                conn.execute(
                    text("DROP DATABASE IF EXISTS kyro_mig_check WITH (FORCE)")
                )
        admin.dispose()


# ------------------------------------------------------------- user mgmt (1, 2, 11, 17)
def test_create_user_issues_key_once_and_stores_only_hash(owner_env):
    env = owner_env
    created = env.http.post("/api/users", json={"handle": "  Alice  "})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["handle"] == "alice"  # normalized
    assert body["is_active"] is True
    assert body["has_api_key"] is True
    assert body["api_key"].startswith("kyro_")
    assert set(body) == {
        "id",
        "handle",
        "is_active",
        "has_api_key",
        "api_key",
    }

    # stored value is the SHA-256, never the plaintext key
    with env.db() as session:
        row = session.get(User, body["id"])
        assert row is not None
        assert row.api_key_hash == hash_api_key(body["api_key"])
        assert row.api_key_hash != body["api_key"]

    # listing never leaks keys
    listing = env.http.get("/api/users")
    assert listing.status_code == 200
    handles = {u["handle"] for u in listing.json()}
    assert {DEFAULT_USER_HANDLE, "alice"} <= handles
    for item in listing.json():
        assert "api_key" not in item

    # duplicates and reserved handles rejected
    assert env.http.post("/api/users", json={"handle": "ALICE"}).status_code == 409
    assert (
        env.http.post("/api/users", json={"handle": DEFAULT_USER_HANDLE}).status_code
        == 409
    )
    assert env.http.post("/api/users", json={"handle": "ab"}).status_code == 422
    assert env.http.post("/api/users", json={"handle": "x" * 40}).status_code == 422
    assert env.http.post("/api/users", json={"handle": "!!bad!!"}).status_code == 422


def test_user_lifecycle_rotate_deactivate_delete(owner_env, monkeypatch):
    env = owner_env
    bob = _create_user(env, "bob")
    bob_id, old_key = bob["id"], bob["api_key"]

    rotated = env.http.post(f"/api/users/{bob_id}/rotate-key")
    assert rotated.status_code == 200, rotated.text
    new_key = rotated.json()["api_key"]
    assert new_key != old_key
    with env.db() as session:
        row = session.get(User, bob_id)
        assert row is not None
        assert row.api_key_hash == hash_api_key(new_key)

    # production-like: the shared service key is now required
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    admin = {"X-API-Key": SERVICE_KEY}

    assert env.http.get("/api/repositories").status_code == 401
    assert (
        env.http.get("/api/repositories", headers={"X-API-Key": old_key}).status_code
        == 401
    )  # rotated away
    assert (
        env.http.get("/api/repositories", headers={"X-API-Key": new_key}).status_code
        == 200
    )

    # per-user keys never grant user management
    assert (
        env.http.post(
            "/api/users", json={"handle": "eve"}, headers={"X-API-Key": new_key}
        ).status_code
        == 401
    )

    # deactivate -> key rejected everywhere
    deact = env.http.post(f"/api/users/{bob_id}/deactivate", headers=admin)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False
    assert (
        env.http.get("/api/repositories", headers={"X-API-Key": new_key}).status_code
        == 401
    )

    react = env.http.post(f"/api/users/{bob_id}/reactivate", headers=admin)
    assert react.status_code == 200
    assert (
        env.http.get("/api/repositories", headers={"X-API-Key": new_key}).status_code
        == 200
    )

    # the legacy default identity is protected
    default_id = next(
        u["id"]
        for u in env.http.get("/api/users", headers=admin).json()
        if u["handle"] == DEFAULT_USER_HANDLE
    )
    assert (
        env.http.post(f"/api/users/{default_id}/deactivate", headers=admin).status_code
        == 409
    )
    assert env.http.delete(f"/api/users/{default_id}", headers=admin).status_code == 409

    # delete blocked while the user owns repositories, allowed afterwards
    _seed(env, 910091, owner_user_id=bob_id)
    assert env.http.delete(f"/api/users/{bob_id}", headers=admin).status_code == 409
    with env.db() as session, session.begin():
        repo = session.scalar(
            select(Repository).where(Repository.github_repository_id == 910091)
        )
        assert repo is not None
        session.delete(repo)
    assert env.http.delete(f"/api/users/{bob_id}", headers=admin).status_code == 204
    assert env.http.get(f"/api/users/{bob_id}", headers=admin).status_code == 404
    assert (
        env.http.get("/api/repositories", headers={"X-API-Key": new_key}).status_code
        == 401
    )


def test_admin_guard_and_invalid_credentials(owner_env, monkeypatch):
    env = owner_env
    alice = _create_user(env, "alice")  # dev mode: admin open for creation

    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    admin = {"X-API-Key": SERVICE_KEY}

    # missing / wrong credentials on every guarded surface
    assert env.http.get("/api/users").status_code == 401
    assert env.http.post("/api/users", json={"handle": "mallory"}).status_code == 401
    assert env.http.get("/api/users", headers={"X-API-Key": "wrong"}).status_code == 401
    assert (
        env.http.get(
            "/api/repositories", headers={"X-API-Key": alice["api_key"]}
        ).status_code
        == 200
    )  # valid user key still authenticates

    # no side effects from the rejected attempts above
    with env.db() as session:
        handles = set(session.scalars(select(User.handle)).all())
        assert "mallory" not in handles  # rejected attempts created nothing

    # shared key = admin: the legitimate attempt now succeeds
    assert (
        env.http.post(
            "/api/users", json={"handle": "mallory"}, headers=admin
        ).status_code
        == 201
    )
    with env.db() as session:
        handles = set(session.scalars(select(User.handle)).all())
        assert "mallory" in handles


def test_deactivated_user_rejected_even_in_dev_mode(owner_env):
    env = owner_env
    carol = _create_user(env, "carol")
    assert env.http.post(f"/api/users/{carol['id']}/deactivate").status_code == 200
    # dev mode (no service key): an unknown/stale credential stays open, but
    # a key that resolves to a deactivated account is fail-closed.
    r = env.http.get("/api/repositories", headers=_hdr(carol))
    assert r.status_code == 401


def test_dev_mode_without_credentials_stays_open(owner_env):
    """KYRO_API_KEY unset: legacy development behavior preserved."""
    env = owner_env
    assert config.KYRO_API_KEY == ""
    r = env.http.get("/api/repositories")
    assert r.status_code == 200
    assert r.json() == []


# ------------------------------------------------- isolation + scoping (3, 4, 5, 9)
def test_one_user_owns_multiple_repositories(owner_env):
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")

    r1 = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": GID_A1,
            "owner": "org",
            "name": "repo-one",
            "default_branch": "main",
        },
        headers=_hdr(alice),
    )
    assert r1.status_code == 202, r1.text
    r2 = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": GID_A2,
            "owner": "org",
            "name": "repo-two",
            "default_branch": "main",
        },
        headers=_hdr(alice),
    )
    assert r2.status_code == 202, r2.text

    repo1, repo2 = _repo(env, GID_A1), _repo(env, GID_A2)
    assert repo1 is not None and repo1.owner_user_id == alice["id"]
    assert repo2 is not None and repo2.owner_user_id == alice["id"]

    alice_list = env.http.get("/api/repositories", headers=_hdr(alice))
    assert {x["github_repository_id"] for x in alice_list.json()} == {
        GID_A1,
        GID_A2,
    }
    bob_list = env.http.get("/api/repositories", headers=_hdr(bob))
    assert bob_list.json() == []

    # detail works for the owner
    assert (
        env.http.get(f"/api/repositories/{GID_A1}", headers=_hdr(alice)).status_code
        == 200
    )
    # ... and is invisible to the other user
    assert (
        env.http.get(f"/api/repositories/{GID_A1}", headers=_hdr(bob)).status_code
        == 404
    )


def test_cross_user_access_rejected_both_directions(owner_env):
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")
    pk_a = _seed(env, GID_A3, owner_user_id=alice["id"], name="alice-repo")
    pk_b = _seed(env, GID_B1, owner_user_id=bob["id"], name="bob-repo")
    assert pk_a != pk_b

    for viewer, foreign_gid in ((alice, GID_B1), (bob, GID_A3)):
        h = _hdr(viewer)
        # detail
        assert (
            env.http.get(f"/api/repositories/{foreign_gid}", headers=h).status_code
            == 404
        )
        # resync
        assert (
            env.http.post(
                f"/api/repositories/{foreign_gid}/resync", json={}, headers=h
            ).status_code
            == 404
        )
        # query (ownership checked before any status/retrieval/LLM work)
        before = len(env.prompts)
        q = env.http.post(
            "/api/query",
            json={"github_repository_id": foreign_gid, "question": "secret?"},
            headers=h,
        )
        assert q.status_code == 404
        assert len(env.prompts) == before  # LLM never consulted
        # list never contains the foreign repository
        gids = {
            x["github_repository_id"]
            for x in env.http.get("/api/repositories", headers=h).json()
        }
        assert foreign_gid not in gids

    # owners still see their own repositories
    assert (
        env.http.get(f"/api/repositories/{GID_A3}", headers=_hdr(alice)).status_code
        == 200
    )
    assert (
        env.http.get(f"/api/repositories/{GID_B1}", headers=_hdr(bob)).status_code
        == 200
    )
    # and can query their own (READY, empty index => honest answer)
    own = env.http.post(
        "/api/query",
        json={"github_repository_id": GID_A3, "question": "how?"},
        headers=_hdr(alice),
    )
    assert own.status_code == 200
    assert own.json()["answer"] == "SYNTHETIC ANSWER"


def test_onboard_conflict_and_re_onboard(owner_env):
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")
    payload = {
        "github_repository_id": GID_B1,
        "owner": "org",
        "name": "shared",
        "default_branch": "main",
    }
    first = env.http.post(
        "/api/repositories/onboard", json=payload, headers=_hdr(alice)
    )
    assert first.status_code == 202, first.text

    conflict = env.http.post(
        "/api/repositories/onboard", json=payload, headers=_hdr(bob)
    )
    assert conflict.status_code == 409
    assert "another user" in conflict.json()["detail"]

    # ownership unchanged by the rejected attempt
    repo = _repo(env, GID_B1)
    assert repo is not None and repo.owner_user_id == alice["id"]

    # the actual owner may re-onboard (resync semantics)
    again = env.http.post(
        "/api/repositories/onboard", json=payload, headers=_hdr(alice)
    )
    assert again.status_code == 202
    repo = _repo(env, GID_B1)
    assert repo is not None and repo.owner_user_id == alice["id"]


def test_client_supplied_user_id_is_ignored(owner_env):
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")

    forged = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": GID_A2,
            "owner": "org",
            "name": "forged",
            "default_branch": "main",
            # hostile extras: must be ignored, identity comes from the key
            "owner_user_id": bob["id"],
            "user_id": bob["id"],
            "owner_user": bob["id"],
        },
        headers=_hdr(alice),
    )
    assert forged.status_code == 202, forged.text
    repo = _repo(env, GID_A2)
    assert repo is not None
    assert repo.owner_user_id == alice["id"]  # authenticated identity wins

    # forged ownership in a query body changes nothing either
    _seed(env, GID_A3, owner_user_id=alice["id"])
    q = env.http.post(
        "/api/query",
        json={
            "github_repository_id": GID_A3,
            "question": "q?",
            "owner_user_id": bob["id"],
            "user_id": bob["id"],
        },
        headers=_hdr(bob),  # Bob, despite claiming Alice's id in the body
    )
    assert q.status_code == 404  # Bob does not own it


def test_query_returns_only_requested_repository_content(owner_env):
    """One user, two repositories: retrieval never crosses the boundary."""
    env = owner_env
    alice = _create_user(env, "alice")
    pk1 = _seed(env, GID_A3, owner_user_id=alice["id"], name="alpha")
    pk2 = _seed(env, GID_A4, owner_user_id=alice["id"], name="beta")
    sha1, sha2 = "a" * 40, "b" * 40
    _add_change_rows(env, pk1, sha=sha1, path="alpha.py")
    _add_change_rows(env, pk2, sha=sha2, path="beta.py")
    _index_change(env, pk1, gid=GID_A3, sha=sha1, path="alpha.py")
    _index_change(env, pk2, gid=GID_A4, sha=sha2, path="beta.py")

    q1 = env.http.post(
        "/api/query",
        json={"github_repository_id": GID_A3, "question": "show changes"},
        headers=_hdr(alice),
    )
    assert q1.status_code == 200
    data1 = q1.json()
    assert data1["chunks_considered"] >= 1
    assert data1["references"], "repo alpha must produce references"
    assert all(r["path"] == "alpha.py" for r in data1["references"])
    assert "alpha.py" in env.prompts[-1]
    assert "beta.py" not in env.prompts[-1]

    q2 = env.http.post(
        "/api/query",
        json={"github_repository_id": GID_A4, "question": "show changes"},
        headers=_hdr(alice),
    )
    assert q2.status_code == 200
    assert all(r["path"] == "beta.py" for r in q2.json()["references"])
    assert "beta.py" in env.prompts[-1]
    assert "alpha.py" not in env.prompts[-1]


# ------------------------------------------- ingestion ownership (6, 12, 13)
def test_worker_preserves_ownership_and_current_owner_wins(owner_env):
    """Events never change owner_user_id; the PG record is authoritative."""
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")

    env.fake.push("feat: one", {"alpha.py": "print('one')\n"})
    _seed(env, FAKE_GID, owner_user_id=alice["id"], owner="acme", name="kyro-demo")

    for i, evt in enumerate(build_backfill_events(env.fake)):
        assert apply_event(env.processor, evt, offset=i).value == "processed"

    repo = _repo(env, FAKE_GID)
    assert repo is not None
    assert repo.owner_user_id == alice["id"]  # untouched by backfill
    with env.db() as session:
        commits = session.scalars(
            select(Commit.id).where(Commit.repository_id == repo.id)
        ).all()
        assert commits, "worker must persist commits under the owner's repo"

    # ingestion events are linked through the repository, never a user id
    with env.db() as session:
        rows = session.execute(
            text(
                "SELECT repository_github_id FROM ingestion_events "
                "WHERE status = 'processed'"
            )
        ).all()
        assert rows and all(row[0] == FAKE_GID for row in rows)

    # ownership re-assigned between events (simulated admin change)
    with env.db() as session, session.begin():
        current = session.scalar(
            select(Repository).where(Repository.github_repository_id == FAKE_GID)
        )
        assert current is not None
        current.owner_user_id = bob["id"]

    env.fake.push("feat: two", {"beta.py": "print('two')\n"})
    live = live_event_for_head(env.fake, delivery_id="ownership-change-1")
    assert apply_event(env.processor, live, offset=99).value == "processed"

    repo = _repo(env, FAKE_GID)
    assert repo is not None
    assert repo.owner_user_id == bob["id"]  # event did NOT revert/claim owner
    assert repo.owner == "acme"  # GitHub org owner comes from payload (fine)

    # access follows the CURRENT owner
    assert (
        env.http.get(f"/api/repositories/{FAKE_GID}", headers=_hdr(bob)).status_code
        == 200
    )
    assert (
        env.http.get(f"/api/repositories/{FAKE_GID}", headers=_hdr(alice)).status_code
        == 404
    )


def test_events_never_assign_arbitrary_ownership(owner_env):
    """Unresolvable ownership: no guessed owner, existing deferral used."""
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")

    # (a) backfill for a repository nobody onboarded -> row created but
    #     OWNERLESS (payload carries no trusted user; nothing is guessed)
    fake = FakeGitHub()
    fake.push("feat: orphan", {"orphan.py": "x = 1\n"})
    for i, evt in enumerate(build_backfill_events(fake)):
        assert apply_event(env.processor, evt, offset=i).value == "processed"
    orphan = _repo(env, FAKE_GID)
    assert orphan is not None
    assert orphan.owner_user_id is None, "events must never assign an owner"

    # ownerless rows are quarantined from per-user identities
    assert (
        env.http.get(f"/api/repositories/{FAKE_GID}", headers=_hdr(alice)).status_code
        == 404
    )
    assert (
        env.http.get(f"/api/repositories/{FAKE_GID}", headers=_hdr(bob)).status_code
        == 404
    )

    # (b) live event for an unknown repository -> EXISTING deferral mechanism
    live = live_event(
        delivery_id="orphan-live-1",
        github_id=910999,
        owner="ghost",
        name="ghost-repo",
        commits=[],
        changes=[],
    )
    assert apply_event(env.processor, live, offset=7).value == "deferred"
    ghost = _repo(env, 910999)
    assert ghost is not None
    assert ghost.owner_user_id is None
    with env.db() as session:
        row_status = session.execute(
            text("SELECT status FROM ingestion_events WHERE event_id = 'orphan-live-1'")
        ).scalar()
    assert row_status == "deferred"

    # neither per-user identity can see the deferred/quarantined repository
    for user in (alice, bob):
        assert (
            env.http.get("/api/repositories/910999", headers=_hdr(user)).status_code
            == 404
        )
        gids = {
            x["github_repository_id"]
            for x in env.http.get("/api/repositories", headers=_hdr(user)).json()
        }
        assert FAKE_GID not in gids and 910999 not in gids


def test_unowned_repositories_are_claimable_by_first_onboard(owner_env):
    env = owner_env
    alice = _create_user(env, "alice")
    bob = _create_user(env, "bob")

    # ingestion created the row without an owner (as above)
    fake = FakeGitHub()
    fake.push("feat: claim me", {"claim.py": "y = 2\n"})
    for i, evt in enumerate(build_backfill_events(fake)):
        assert apply_event(env.processor, evt, offset=i).value == "processed"
    before_claim = _repo(env, FAKE_GID)
    assert before_claim is not None
    assert before_claim.owner_user_id is None

    # first authenticated onboarding claims it; the second user is rejected
    claim = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": FAKE_GID,
            "owner": "acme",
            "name": "kyro-demo",
            "default_branch": "main",
        },
        headers=_hdr(alice),
    )
    assert claim.status_code == 202, claim.text
    after_claim = _repo(env, FAKE_GID)
    assert after_claim is not None
    assert after_claim.owner_user_id == alice["id"]

    blocked = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": FAKE_GID,
            "owner": "acme",
            "name": "kyro-demo",
            "default_branch": "main",
        },
        headers=_hdr(bob),
    )
    assert blocked.status_code == 409
    final = _repo(env, FAKE_GID)
    assert final is not None
    assert final.owner_user_id == alice["id"]


# --------------------------------- vector keys + traceability (7, 10, 21)
def test_index_keys_preserved_and_traceable_to_owner(owner_env):
    env = owner_env
    alice = _create_user(env, "alice")
    repo_pk = _seed(env, GID_A3, owner_user_id=alice["id"], name="vector-repo")
    sha = "c" * 40
    path = "services/api/handler.py"
    _add_change_rows(env, repo_pk, sha=sha, path=path)
    item = _index_change(env, repo_pk, gid=GID_A3, sha=sha, path=path)

    # deterministic key format is unchanged (repository_pk:commit_sha:path)
    doc_id = f"{repo_pk}:{sha}:{path}"
    from app.ingest.indexer import build_doc_id

    assert build_doc_id(item) == doc_id

    got = env.indexer.collection.get(ids=[doc_id], include=["metadatas"])
    assert got["ids"] == [doc_id]
    meta = got["metadatas"][0]
    assert {
        "repository_id",
        "commit_id",
        "file_id",
        "github_repository_id",
        "commit_sha",
        "path",
        "status",
    } <= set(meta)
    assert meta["repository_id"] == repo_pk
    assert meta["commit_id"] == item.commit_pk
    assert meta["file_id"] == item.file_pk
    assert meta["commit_sha"] == sha
    assert meta["path"] == path

    # traceable to the user through PostgreSQL ownership
    owner_id = None
    with env.db() as session:
        owner_id = session.scalar(
            select(Repository.owner_user_id).where(Repository.id == repo_pk)
        )
    assert owner_id == alice["id"]

    # reindex/re-embed: idempotent, count unchanged, ownership still valid
    env.indexer.index_event([item])
    assert env.indexer.collection.get(ids=[doc_id])["ids"] == [doc_id]
    with env.db() as session:
        again = session.scalar(
            select(Repository.owner_user_id).where(
                Repository.id == int(meta["repository_id"])
            )
        )
    assert again == alice["id"]

    # answer generation unchanged: the owner still gets the indexed chunk
    q = env.http.post(
        "/api/query",
        json={"github_repository_id": GID_A3, "question": "what changed?"},
        headers=_hdr(alice),
    )
    assert q.status_code == 200
    assert q.json()["references"][0]["path"] == path
    assert path in env.prompts[-1]
    # and a different user is rejected before retrieval happens
    bob = _create_user(env, "bob")
    before = len(env.prompts)
    assert (
        env.http.post(
            "/api/query",
            json={"github_repository_id": GID_A3, "question": "what changed?"},
            headers=_hdr(bob),
        ).status_code
        == 404
    )
    assert len(env.prompts) == before


# ------------------------------------------------------- failure handling (19)
def test_auth_failures_leave_no_side_effects(owner_env, monkeypatch):
    env = owner_env
    alice = _create_user(env, "alice")
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)

    # rejected onboard creates nothing
    r = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": 910095,
            "owner": "org",
            "name": "never",
            "default_branch": "main",
        },
        headers={"X-API-Key": "nope"},
    )
    assert r.status_code == 401
    assert _repo(env, 910095) is None

    # rejected user creation creates nothing
    r = env.http.post(
        "/api/users", json={"handle": "ghost"}, headers={"X-API-Key": "nope"}
    )
    assert r.status_code == 401
    with env.db() as session:
        assert "ghost" not in set(session.scalars(select(User.handle)).all())

    # valid identity still works while the service key is enforced
    assert env.http.get("/api/repositories", headers=_hdr(alice)).status_code == 200


def test_shared_key_identity_sees_legacy_repositories(owner_env, monkeypatch):
    """The Next.js proxy path (shared key) keeps working unchanged."""
    env = owner_env

    # materialize the legacy identity (dev mode, no credential needed)
    assert env.http.get("/api/repositories").status_code == 200
    with env.db() as session:
        default_id = session.scalar(
            select(User.id).where(User.handle == DEFAULT_USER_HANDLE)
        )
        assert default_id is not None
    _seed(env, 910096, owner_user_id=default_id, name="legacy-repo")

    # now enforce the shared service key (production-like)
    monkeypatch.setattr(config, "KYRO_API_KEY", SERVICE_KEY)
    admin = {"X-API-Key": SERVICE_KEY}

    listed = env.http.get("/api/repositories", headers=admin)
    assert listed.status_code == 200
    assert {x["github_repository_id"] for x in listed.json()} == {910096}
    detail = env.http.get("/api/repositories/910096", headers=admin)
    assert detail.status_code == 200

    # health probe stays open for orchestrators (no repository data)
    assert env.http.get("/health").status_code in (200, 503)
