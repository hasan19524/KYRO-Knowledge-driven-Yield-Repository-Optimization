"""GitHubClient tests: pagination, error classification, content fetching."""

from __future__ import annotations

import pytest

from app.github.auth import GitHubAuthError
from app.github.client import (
    GitHubClient,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
)
from tests.fake_github import FakeGitHub, make_github_client


def test_iter_commits_paginates_newest_first():
    fake = FakeGitHub()
    shas = [fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(5)]
    fake.per_page_cap = 2
    client, _ = make_github_client(fake)

    got = [
        item["sha"]
        for item in client.iter_commits(
            fake.owner, fake.name, sha="main", installation_id=fake.installation_id
        )
    ]
    assert got == list(reversed(shas))  # GitHub order: newest first


def test_iter_commits_stop_sha_halts_early():
    fake = FakeGitHub()
    shas = [fake.push(f"c{i}", {f"f{i}.py": f"{i}\n"}) for i in range(5)]
    client, _ = make_github_client(fake)

    got = [
        item["sha"]
        for item in client.iter_commits(
            fake.owner,
            fake.name,
            sha="main",
            installation_id=fake.installation_id,
            stop_sha=shas[3],
        )
    ]
    assert got[:2] == [shas[4], shas[3]]
    assert shas[2] not in got  # stopped at the boundary


def test_404_is_github_not_found():
    fake = FakeGitHub()
    client, _ = make_github_client(fake)
    with pytest.raises(GitHubNotFound):
        client.get_repository("nope", "missing", fake.installation_id)
    assert "GET /repos/nope/missing" in fake.requests


def test_401_is_auth_error():
    fake = FakeGitHub()
    fake.auth_mode = "revoked"
    client, _ = make_github_client(fake)
    with pytest.raises(GitHubAuthError):
        client.get_repository(fake.owner, fake.name, fake.installation_id)


def test_5xx_exhaustion_is_unavailable():
    fake = FakeGitHub()
    fake.fail_route["GET /repos"] = 99
    client, _ = make_github_client(fake, max_retries=1)
    with pytest.raises(GitHubUnavailable):
        client.get_repository(fake.owner, fake.name, fake.installation_id)
    # retries actually happened (initial + max_retries)
    assert sum(1 for r in fake.requests if r.startswith("GET /repos/")) >= 2


def test_rate_limit_above_cap_is_rate_limited():
    fake = FakeGitHub()
    fake.rate_limited_remaining = 5
    client, _ = make_github_client(fake, rate_limit_max_wait_s=0.0)
    with pytest.raises(GitHubRateLimited):
        client.get_repository(fake.owner, fake.name, fake.installation_id)


def test_get_file_content_decodes_blob():
    fake = FakeGitHub()
    sha = fake.push("init", {"a.py": "hello = 1\n"})
    client, _ = make_github_client(fake)

    content, blob_sha = client.get_file_content(
        fake.owner, fake.name, "a.py", sha, fake.installation_id
    )
    assert content == "hello = 1\n"
    assert blob_sha  # non-empty git blob sha


def test_get_file_content_missing_path_raises_not_found():
    fake = FakeGitHub()
    sha = fake.push("init", {"a.py": "1\n"})
    client, _ = make_github_client(fake)
    with pytest.raises(GitHubNotFound):
        client.get_file_content(
            fake.owner, fake.name, "nope.py", sha, fake.installation_id
        )


def test_next_page_parses_link_header():
    import httpx

    resp = httpx.Response(
        200,
        headers={
            "link": '<https://api.github.com/x?page=3>; rel="next", '
            '<https://api.github.com/x?page=1>; rel="first"'
        },
    )
    assert GitHubClient._next_page(resp) == 3

    resp = httpx.Response(
        200, headers={"link": '<https://api.github.com/x?page=1>; rel="prev"'}
    )
    assert GitHubClient._next_page(resp) is None
