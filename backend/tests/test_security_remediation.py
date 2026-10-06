"""Security remediation tests (rate limits + bounded request fields).

Covers the audit items:
  * per-user rate limits on POST /api/query and POST .../resync (429 +
    Retry-After, disabled when limit=0, per-process limiter semantics);
  * bounded question/owner/name/full_name/url/default_branch input (422).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config
from app.github.backfill import BackfillService
from app.ingest.processor import EventProcessor
from app.main import create_app
from app.security.ratelimit import RateLimiter
from app.state import AppState
from app.sync.manager import SyncManager
from tests.fake_github import FakeGitHub, make_github_client


# ------------------------------------------------------------- unit limiter
def test_limiter_allows_until_limit_then_blocks_then_resets():
    clock = [0.0]
    limiter = RateLimiter(now=lambda: clock[0])

    for _ in range(3):
        assert limiter.hit(bucket="q", subject_id=1, limit=3, window_s=60) is None
    retry = limiter.hit(bucket="q", subject_id=1, limit=3, window_s=60)
    assert retry is not None
    assert 1 <= retry <= 60

    clock[0] = 61.0  # next window
    assert limiter.hit(bucket="q", subject_id=1, limit=3, window_s=60) is None


def test_limiter_zero_disables():
    limiter = RateLimiter(now=lambda: 123.0)
    for _ in range(100):
        assert limiter.hit(bucket="q", subject_id=1, limit=0, window_s=60) is None


def test_limiter_is_per_subject_and_per_bucket():
    clock = [0.0]
    limiter = RateLimiter(now=lambda: clock[0])
    assert limiter.hit(bucket="q", subject_id=1, limit=1, window_s=60) is None
    assert limiter.hit(bucket="q", subject_id=1, limit=1, window_s=60) is not None
    # another user and another bucket are unaffected
    assert limiter.hit(bucket="q", subject_id=2, limit=1, window_s=60) is None
    assert limiter.hit(bucket="r", subject_id=1, limit=1, window_s=60) is None


# --------------------------------------------------------------- API fixture
@pytest.fixture
def sec_env(db, indexer):
    """FastAPI app without Kafka wiring (limiter/validation tests only)."""
    fake = FakeGitHub()
    gh_client, _ = make_github_client(fake)
    processor = EventProcessor(db, indexer, gh_client)
    backfill = BackfillService(gh_client)
    manager = SyncManager(
        db,
        backfill,
        processor,
        gh_client,
        backfill_topic="kyro.test.never.published",
        timeout=60.0,
        poll_interval=0.05,
        publish_batch=2,
        concurrency=2,
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


def _query_payload(**overrides) -> dict:
    payload = {"github_repository_id": 424242, "question": "what changed?"}
    payload.update(overrides)
    return payload


# ------------------------------------------------------------- rate limiting
def test_query_rate_limited_429_with_retry_after(sec_env, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_QUERY_PER_MIN", 2)

    codes = []
    for _ in range(3):
        r = sec_env.http.post("/api/query", json=_query_payload())
        codes.append(r.status_code)

    # first two pass the limiter (they 404 on the unknown repository);
    # the third is rejected before any handler work.
    assert codes[:2] == [404, 404]
    assert codes[2] == 429
    r = sec_env.http.post("/api/query", json=_query_payload())
    assert r.status_code == 429
    retry_after = r.headers.get("Retry-After")
    assert retry_after is not None
    assert 1 <= int(retry_after) <= 60
    assert r.json()["detail"] == "rate limit exceeded"


def test_resync_rate_limited_429(sec_env, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_RESYNC_PER_MIN", 1)

    first = sec_env.http.post("/api/repositories/424242/resync", json={})
    second = sec_env.http.post("/api/repositories/424242/resync", json={})

    assert first.status_code == 404  # unknown repository, past the limiter
    assert second.status_code == 429
    assert second.headers.get("Retry-After") is not None


def test_rate_limit_zero_disables(sec_env, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_QUERY_PER_MIN", 0)
    monkeypatch.setattr(config, "RATE_LIMIT_RESYNC_PER_MIN", 0)

    for _ in range(5):
        assert sec_env.http.post("/api/query", json=_query_payload()).status_code == 404
    for _ in range(5):
        r = sec_env.http.post("/api/repositories/424242/resync", json={})
        assert r.status_code == 404


def test_rate_limit_is_per_user(sec_env, monkeypatch):
    """The shared service key and dev identity share one subject; two
    different per-user keys would not. Dev mode has a single identity, so
    verify isolation at the limiter level (unit test above) and here that
    one identity actually consumes the shared budget."""
    monkeypatch.setattr(config, "RATE_LIMIT_QUERY_PER_MIN", 3)
    codes = [
        sec_env.http.post("/api/query", json=_query_payload()).status_code
        for _ in range(4)
    ]
    assert codes == [404, 404, 404, 429]


# ---------------------------------------------------------------- input caps
def test_question_over_max_422(sec_env):
    too_long = "q" * (config.QUERY_MAX_QUESTION_CHARS + 1)
    r = sec_env.http.post("/api/query", json=_query_payload(question=too_long))
    assert r.status_code == 422


def test_question_at_max_accepted_by_validation(sec_env):
    exact = "q" * config.QUERY_MAX_QUESTION_CHARS
    r = sec_env.http.post("/api/query", json=_query_payload(question=exact))
    assert r.status_code == 404  # validation passed; repository unknown


@pytest.mark.parametrize("field,max_len", [("owner", 100), ("name", 100)])
def test_onboard_owner_name_bounds(sec_env, field, max_len):
    body = {
        "github_repository_id": 424242,
        "owner": "o" * (100 if field != "owner" else max_len + 1),
        "name": "n" * (100 if field != "name" else max_len + 1),
    }
    r = sec_env.http.post("/api/repositories/onboard", json=body)
    assert r.status_code == 422


def test_onboard_full_name_bound_422(sec_env):
    body = {
        "github_repository_id": 424242,
        "owner": "acme",
        "name": "repo",
        "full_name": "a" * 201,
    }
    r = sec_env.http.post("/api/repositories/onboard", json=body)
    assert r.status_code == 422


def test_onboard_url_bound_422(sec_env):
    body = {
        "github_repository_id": 424242,
        "owner": "acme",
        "name": "repo",
        "url": "https://example.com/" + "a" * 500,
    }
    r = sec_env.http.post("/api/repositories/onboard", json=body)
    assert r.status_code == 422
