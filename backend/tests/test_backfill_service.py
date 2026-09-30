"""BackfillService tests (§8, §14): full history, pagination, ordering,
deterministic ids, boundaries, and GitHub failure classification."""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.github.auth import GitHubAuthError
from app.github.backfill import BackfillService
from app.github.client import GitHubRateLimited, GitHubUnavailable
from tests.fake_github import FakeGitHub, make_github_client


def _service(fake: FakeGitHub, **client_kwargs) -> tuple[BackfillService, FakeGitHub]:
    client, _ = make_github_client(fake, **client_kwargs)
    return BackfillService(client, detail_concurrency=2), fake


def _repo_block(fake: FakeGitHub) -> dict:
    return {
        "github_id": 1395956448,
        "name": fake.name,
        "full_name": f"{fake.owner}/{fake.name}",
        "owner": fake.owner,
        "private": fake.private,
        "default_branch": fake.default_branch,
        "url": f"https://github.com/{fake.owner}/{fake.name}",
    }


def _events(service, fake, **kwargs) -> list[dict]:
    return [
        event
        for _, event in service.build_events(
            fake.owner,
            fake.name,
            repository=_repo_block(fake),
            branch=fake.default_branch or "main",
            installation_id=fake.installation_id,
            target_sha=fake.head,
            **kwargs,
        )
    ]


def test_full_history_with_pagination_is_chronological():
    """5 commits, 2 per page -> Link pagination; events parents-first."""
    fake = FakeGitHub()
    fake.per_page_cap = 2
    shas = [fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(5)]
    service, fake = _service(fake)

    events = _events(service, fake)
    assert [e["push"]["after"] for e in events] == shas  # oldest -> newest
    assert [e["backfill"]["sequence"] for e in events] == [0, 1, 2, 3, 4]
    for prev, cur in pairwise(events):
        assert cur["push"]["before"] == prev["push"]["after"]
    # pagination actually exercised more than one page (5 commits @ 2/page)
    commits_list_calls = [r for r in fake.requests if r.endswith("/commits")]
    assert len(commits_list_calls) >= 3


def test_first_commit_event_shape():
    """§8: before=null, is_initial_commit, every change status=added."""
    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n", "b.py": "2\n"})
    service, fake = _service(fake)
    (event,) = _events(service, fake)

    assert event["push"]["before"] is None
    assert event["push"]["created"] is True
    assert event["backfill"]["is_initial_commit"] is True
    assert event["backfill"]["parent_sha"] is None
    assert all(c["status"] == "added" for c in event["changes"])
    commit = event["commits"][0]
    assert sorted(commit["added"]) == ["a.py", "b.py"]
    assert commit["modified"] == [] and commit["removed"] == []
    assert event["event"]["id"] == f"backfill:1395956448:{event['push']['after']}"
    assert event["event"]["classification"] == "initial_backfill"
    assert event["backfill"]["sync_target_commit"] == fake.head


def test_stop_sha_publishes_only_unpublished_range():
    """§14: stop at the already-published boundary (exclusive)."""
    fake = FakeGitHub()
    shas = [fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(5)]
    service, fake = _service(fake)

    events = _events(service, fake, stop_sha=shas[1])
    assert [e["push"]["after"] for e in events] == shas[2:]
    assert events[0]["push"]["before"] == shas[1]  # boundary preserved


def test_deterministic_event_ids_on_republish():
    fake = FakeGitHub()
    for i in range(3):
        fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"})
    service, fake = _service(fake)

    first = [e["event"]["id"] for e in _events(service, fake)]
    second = [e["event"]["id"] for e in _events(service, fake)]
    assert first == second
    assert len(set(first)) == 3


def test_rate_limit_recovers_within_cap():
    """Transient 403 rate-limits are retried (bounded) and succeed."""
    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n"})
    fake.rate_limited_remaining = 2
    service, fake = _service(fake)

    events = _events(service, fake)
    assert len(events) == 1


def test_rate_limit_above_cap_raises():
    """Wait exceeding the configured cap -> GitHubRateLimited (no endless loop)."""
    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n"})
    fake.rate_limited_remaining = 5
    service, fake = _service(fake, rate_limit_max_wait_s=0.0)

    with pytest.raises(GitHubRateLimited):
        _events(service, fake)


def test_access_revoked_raises_auth_error():
    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n"})
    fake.auth_mode = "revoked"
    service, fake = _service(fake)

    with pytest.raises(GitHubAuthError):
        _events(service, fake)


def test_server_errors_retried_then_succeed():
    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n"})
    fake.fail_route["GET /repos"] = 2  # two 500s, then healthy
    service, fake = _service(fake)

    assert len(_events(service, fake)) == 1


def test_server_errors_exhaust_retries():
    fake = FakeGitHub()
    fake.push("init", {"a.py": "1\n"})
    fake.fail_route["GET /repos"] = 99
    service, fake = _service(fake, max_retries=1)

    with pytest.raises(GitHubUnavailable):
        _events(service, fake)


def test_renames_become_renamed_changes_with_previous_path():
    fake = FakeGitHub()
    fake.push("init", {"old.py": "X = 1\n"})
    fake.push(
        "rename",
        {"new.py": "X = 1\n"},
        renames={"new.py": "old.py"},
    )
    service, fake = _service(fake)
    events = _events(service, fake)

    renamed = events[1]["changes"][0]
    assert renamed["status"] == "renamed"
    assert renamed["previous_path"] == "old.py"
    assert renamed["path"] == "new.py"
    # commit block classification puts the rename target into `modified`
    assert events[1]["commits"][0]["modified"] == ["new.py"]
