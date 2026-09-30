"""Query gating + repository API tests (§13/§76 CASE 6, §44, §56).

Covers the locked four-state query gate:
  SYNCING        -> 409 with in-progress message
  SYNC_FAILED    -> 409 with re-sync message
  ACCESS_REVOKED -> 403 with re-authorize message
  READY          -> Chroma retrieval -> PG enrichment -> LLM answer
plus the onboarding/list/status/resync endpoints and validation errors.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.repositories import (
    ACCESS_REVOKED_MESSAGE,
    SYNC_FAILED_MESSAGE,
    SYNCING_MESSAGE,
)
from app.db.models import Repository, RepositoryStatus
from app.github.backfill import BackfillService
from app.ingest.indexer import IndexError_
from app.ingest.processor import EventProcessor
from app.main import create_app
from app.state import AppState
from app.sync.manager import SyncManager
from tests.conftest import apply_event, build_backfill_events, wait_for
from tests.fake_github import FakeGitHub, make_github_client

GID = 1395956448


@pytest.fixture
def api_env(db, indexer, kafka_topics, worker_factory):
    """FastAPI app wired to the fake GitHub, real DB/Chroma, and test topics."""
    fake = FakeGitHub()
    gh_client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, gh_client)
    backfill = BackfillService(gh_client)
    manager = SyncManager(
        db,
        backfill,
        processor,
        gh_client,
        backfill_topic=kafka_topics.backfill,
        timeout=60.0,
        poll_interval=0.05,
        publish_batch=2,
        concurrency=2,
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
    harness = worker_factory(
        topics=[kafka_topics.backfill, kafka_topics.live],
        fake=fake,
        processor=processor,
    )
    with TestClient(app) as http:
        yield SimpleNamespace(
            app=app,
            http=http,
            state=state,
            fake=fake,
            processor=processor,
            manager=manager,
            harness=harness,
            prompts=prompts,
            db=db,
            indexer=indexer,
            topics=kafka_topics,
        )


def _seed_repo(db, status: str, *, gid: int = GID) -> None:
    with db() as session, session.begin():
        session.add(
            Repository(
                github_repository_id=gid,
                name="kyro-demo",
                full_name="acme/kyro-demo",
                owner="acme",
                default_branch="main",
                status=status,
            )
        )


def _set_status(db, status: str, *, gid: int = GID) -> None:
    with db() as session, session.begin():
        repo = session.scalar(
            select(Repository).where(Repository.github_repository_id == gid)
        )
        assert repo is not None, "repository row must exist before status change"
        repo.status = status


# ------------------------------------------------------- query state gating
def test_query_unknown_repository_404(api_env):
    r = api_env.http.post(
        "/api/query", json={"github_repository_id": 999_999_999, "question": "q"}
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "repository not found"


def test_query_syncing_returns_409(api_env):
    _seed_repo(api_env.db, RepositoryStatus.SYNCING.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": "how?"}
    )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["status"] == RepositoryStatus.SYNCING.value
    assert detail["message"] == SYNCING_MESSAGE
    assert api_env.prompts == []  # LLM never consulted while gating


def test_query_sync_failed_returns_409(api_env):
    _seed_repo(api_env.db, RepositoryStatus.SYNC_FAILED.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": "how?"}
    )

    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["status"] == RepositoryStatus.SYNC_FAILED.value
    assert detail["message"] == SYNC_FAILED_MESSAGE
    assert api_env.prompts == []


def test_query_access_revoked_returns_403(api_env):
    _seed_repo(api_env.db, RepositoryStatus.ACCESS_REVOKED.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": "how?"}
    )

    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["status"] == RepositoryStatus.ACCESS_REVOKED.value
    assert detail["message"] == ACCESS_REVOKED_MESSAGE
    assert api_env.prompts == []


def test_query_rejects_empty_question(api_env):
    _seed_repo(api_env.db, RepositoryStatus.READY.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": ""}
    )

    assert r.status_code == 422


# ------------------------------------------------------------ READY answer
def test_query_ready_returns_answer_with_references(api_env):
    """READY: retrieval -> enrichment -> bounded context -> synthetic LLM."""
    env = api_env
    env.fake.push(
        "feat: token check",
        {"auth.py": "def check(token):\n    return bool(token)\n"},
    )
    for i, evt in enumerate(build_backfill_events(env.fake)):
        assert apply_event(env.processor, evt, offset=i).value == "processed"
    _set_status(env.db, RepositoryStatus.READY.value)

    r = env.http.post(
        "/api/query",
        json={"github_repository_id": GID, "question": "How does auth check work?"},
    )

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == RepositoryStatus.READY.value
    assert data["repository"] == "acme/kyro-demo"
    assert data["question"] == "How does auth check work?"
    assert data["answer"] == "SYNTHETIC ANSWER"
    assert data["chunks_considered"] >= 1

    refs = data["references"]
    assert refs, "indexed commit/file must be surfaced as references"
    assert refs[0]["path"] == "auth.py"
    assert refs[0]["commit_sha"] == env.fake.head
    assert refs[0]["similarity_distance"] is not None

    # Only relevant context reached the LLM prompt.
    assert env.prompts, "LLM must be invoked exactly once"
    prompt = env.prompts[-1]
    assert "auth.py" in prompt
    assert "Repository: acme/kyro-demo" in prompt
    assert "How does auth check work?" in prompt


def test_query_ready_with_empty_index_still_answers(api_env):
    """READY but no indexed chunks: honest answer, no fabricated references."""
    _seed_repo(api_env.db, RepositoryStatus.READY.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": "anything?"}
    )

    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "SYNTHETIC ANSWER"
    assert data["references"] == []
    assert data["chunks_considered"] == 0
    assert "No indexed changes matched" in api_env.prompts[-1]


def test_query_chroma_failure_returns_503(api_env):
    class BrokenIndexer:
        def search(self, *args, **kwargs):
            raise IndexError_("chroma query failed: connection refused")

    api_env.state.indexer = BrokenIndexer()
    _seed_repo(api_env.db, RepositoryStatus.READY.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": "q"}
    )

    assert r.status_code == 503
    assert "semantic index temporarily unavailable" in r.json()["detail"]
    assert api_env.prompts == []


def test_query_llm_failure_returns_502(api_env):
    def boom(prompt: str) -> str:
        raise RuntimeError("gateway down")

    api_env.state.llm = boom
    _seed_repo(api_env.db, RepositoryStatus.READY.value)

    r = api_env.http.post(
        "/api/query", json={"github_repository_id": GID, "question": "q"}
    )

    assert r.status_code == 502
    assert "LLM gateway error" in r.json()["detail"]


# ----------------------------------------------------- full API sync flow
def test_onboard_sync_then_query_flow(api_env):
    """POST onboard -> worker applies -> READY -> query -> resync -> READY."""
    env = api_env
    env.fake.push(
        "feat: token check",
        {"auth.py": "def check(token):\n    return bool(token)\n"},
    )
    env.fake.push("chore: helper", {"util.py": "def helper():\n    return 1\n"})

    r = env.http.post(
        "/api/repositories/onboard",
        json={
            "github_repository_id": GID,
            "owner": env.fake.owner,
            "name": env.fake.name,
            "installation_id": env.fake.installation_id,
            "default_branch": "main",
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["github_repository_id"] == GID
    assert body["status"] == RepositoryStatus.SYNCING.value

    def _ready():
        return (
            env.http.get(f"/api/repositories/{GID}").json()["status"]
            == RepositoryStatus.READY.value
        )

    env.harness.start()
    try:
        assert wait_for(_ready, timeout=60), "sync must reach READY"

        listed = env.http.get("/api/repositories")
        assert listed.status_code == 200
        assert [x["github_repository_id"] for x in listed.json()] == [GID]

        snap = env.http.get(f"/api/repositories/{GID}").json()
        assert snap["status"] == RepositoryStatus.READY.value
        assert snap["synced_through_commit"] == env.fake.head
        assert snap["backfill_published_through_commit"] == env.fake.head
        assert snap["deferred_events"] == 0
        assert snap["last_error"] is None
        assert snap["sync_completed_at"] is not None

        q = env.http.post(
            "/api/query",
            json={"github_repository_id": GID, "question": "How does auth work?"},
        )
        assert q.status_code == 200
        qdata = q.json()
        assert qdata["status"] == RepositoryStatus.READY.value
        assert qdata["answer"] == "SYNTHETIC ANSWER"
        assert {ref["path"] for ref in qdata["references"]} & {"auth.py", "util.py"}

        # Resync after a new push: only the new range is published.
        env.fake.push(
            "fix: tighten check", {"auth.py": "def check(t):\n    return bool(t)\n"}
        )
        r = env.http.post(f"/api/repositories/{GID}/resync", json={"full": False})
        assert r.status_code == 202
        assert r.json()["status"] == RepositoryStatus.SYNCING.value

        def _resynced():
            s = env.http.get(f"/api/repositories/{GID}").json()
            return (
                s["status"] == RepositoryStatus.READY.value
                and s["synced_through_commit"] == env.fake.head
            )

        assert wait_for(_resynced, timeout=60), "resync must reach READY again"
    finally:
        env.harness.stop()


def test_repository_endpoints_and_validation(api_env):
    env = api_env
    _seed_repo(env.db, RepositoryStatus.READY.value)

    # list + get
    listed = env.http.get("/api/repositories")
    assert listed.status_code == 200
    assert listed.json()[0]["github_repository_id"] == GID
    got = env.http.get(f"/api/repositories/{GID}")
    assert got.status_code == 200
    assert got.json()["status"] == RepositoryStatus.READY.value

    # unknown ids
    assert env.http.get("/api/repositories/123456789").status_code == 404
    assert (
        env.http.post("/api/repositories/123456789/resync", json={}).status_code == 404
    )

    # onboard payload validation
    bad = env.http.post("/api/repositories/onboard", json={"owner": "acme"})
    assert bad.status_code == 422
    bad = env.http.post(
        "/api/repositories/onboard",
        json={"github_repository_id": 0, "owner": "acme", "name": "x"},
    )
    assert bad.status_code == 422


def test_onboard_missing_fields_returns_422(api_env):
    r = api_env.http.post("/api/repositories/onboard", json={})
    assert r.status_code == 422
    assert api_env.manager.pending_sync_ids() == []
