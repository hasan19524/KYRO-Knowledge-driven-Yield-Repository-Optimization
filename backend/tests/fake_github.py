"""In-process fake GitHub (REST) for tests.

Implements exactly the endpoints the KYRO backfill/ingestion stack uses:

  POST /app/installations/{id}/access_tokens
  GET  /repos/{owner}/{repo}
  GET  /repos/{owner}/{repo}/branches/{branch}
  GET  /repos/{owner}/{repo}/commits          (paginated, Link headers)
  GET  /repos/{owner}/{repo}/commits/{sha}    (detail with files + patches)
  GET  /repos/{owner}/{repo}/contents/{path}  (exact content at ref)

History is a simple append-only chain (each commit has one parent), which is
enough to model full chronological backfill, renames, adds, modifies and
deletes. Failures (auth revoked, 5xx, rate limits) are scriptable.
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.ingest.content import git_blob_sha


def _sha(*parts: Any) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _unified_patch(before: str | None, after: str) -> str | None:
    """GitHub-style patch body (starts at the @@ hunk header)."""
    import difflib

    before_lines = (before or "").split("\n")
    after_lines = after.split("\n")
    if before is not None and before_lines == after_lines:
        return None
    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="a",
            tofile="b",
            lineterm="",
            n=3,
        )
    )
    # Drop the ---/+++ file header lines; GitHub patches start at @@.
    body = [ln for ln in diff if not ln.startswith(("---", "+++"))]
    return "\n".join(body) if body else None


@dataclass
class FakeFileState:
    path: str
    content: str
    blob_sha: str


@dataclass
class FakeCommit:
    sha: str
    parents: list[str]
    message: str
    timestamp: str
    author_name: str
    author_email: str
    # path -> (status, previous_path, content_after, patch, additions, deletions)
    files: list[dict] = field(default_factory=list)


class FakeGitHub:
    def __init__(
        self,
        owner: str = "acme",
        name: str = "kyro-demo",
        *,
        installation_id: int = 791001,
        default_branch: str | None = "main",
        private: bool = False,
    ) -> None:
        self.owner = owner
        self.name = name
        self.installation_id = installation_id
        self.default_branch = default_branch
        self.private = private
        self.commits: list[FakeCommit] = []  # oldest first
        self.trees: dict[str, dict[str, str]] = {}  # commit sha -> path->content
        self.auth_mode = "ok"  # ok | revoked | rate_limited
        self.rate_limited_remaining = 0  # number of rate-limited replies to emit
        self.fail_route: dict[str, int] = {}  # route key -> #500s to serve first
        self.requests: list[str] = []  # method+path log (assertions)
        self.per_page_cap = 100

    # ------------------------------------------------------------- history
    @property
    def head(self) -> str | None:
        return self.commits[-1].sha if self.commits else None

    def push(
        self,
        message: str,
        files: dict[str, str | None],
        *,
        author: str = "Alice Dev",
        email: str = "alice@example.com",
        timestamp: datetime | None = None,
        renames: dict[str, str] | None = None,
    ) -> str:
        """Append a commit.

        files: path -> new content (None = delete)
        renames: new_path -> previous_path
        """
        parents = [self.commits[-1].sha] if self.commits else []
        sha = _sha("commit", len(self.commits), message, sorted(files.items()), parents)
        prev_tree = dict(self.trees[parents[0]]) if parents else {}
        tree = dict(prev_tree)
        file_entries: list[dict] = []

        for new_path, old_path in (renames or {}).items():
            content = files.get(new_path)
            if content is None:
                content = prev_tree.get(old_path, "")
            before = prev_tree.get(old_path)
            patch = _unified_patch(before, content)
            status = "renamed" if before is not None else "added"
            file_entries.append(
                {
                    "filename": new_path,
                    "previous_filename": old_path,
                    "status": status,
                    "patch": patch,
                    "content": content,
                }
            )
            tree.pop(old_path, None)
            tree[new_path] = content

        for path, content in files.items():
            if renames and path in renames:
                continue
            before = prev_tree.get(path)
            if content is None:
                if before is None:
                    continue  # deleting something never present: no-op
                file_entries.append(
                    {
                        "filename": path,
                        "status": "removed",
                        "patch": _unified_patch(before, ""),
                        "content": None,
                    }
                )
                tree.pop(path, None)
                continue
            patch = _unified_patch(before, content)
            file_entries.append(
                {
                    "filename": path,
                    "status": "added" if before is None else "modified",
                    "patch": patch,
                    "content": content,
                }
            )
            tree[path] = content

        detail_files = []
        for entry in file_entries:
            content = entry.pop("content")
            patch = entry["patch"]
            additions = (
                len(
                    [
                        line
                        for line in (patch or "").splitlines()
                        if line.startswith("+")
                    ]
                )
                if patch
                else (len(content.splitlines()) if content else 0)
            )
            deletions = (
                len(
                    [
                        line
                        for line in (patch or "").splitlines()
                        if line.startswith("-")
                    ]
                )
                if patch
                else 0
            )
            entry["additions"] = additions
            entry["deletions"] = deletions
            entry["changes"] = additions + deletions
            entry["sha"] = git_blob_sha(content) if content is not None else None
            entry["_content"] = content
            detail_files.append(entry)

        # Deterministic INCREASING timestamps: later commits are newer, so the
        # out-of-order content guard in persistence sees a healthy history.
        ts = timestamp or datetime(2025, 1, 1, tzinfo=UTC) + timedelta(
            seconds=60 * len(self.commits)
        )
        commit = FakeCommit(
            sha=sha,
            parents=parents,
            message=message,
            timestamp=ts.isoformat().replace("+00:00", "Z"),
            author_name=author,
            author_email=email,
            files=detail_files,
        )
        self.commits.append(commit)
        self.trees[sha] = tree
        return sha

    # ----------------------------------------------------------- transport
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _respond(
        self, request: httpx.Request, status_code: int = 200, **kwargs: Any
    ) -> httpx.Response:
        self.requests.append(f"{request.method} {request.url.path}")
        route = f"{request.method} {request.url.path}"
        for key, remaining in list(self.fail_route.items()):
            if key in route and remaining > 0:
                self.fail_route[key] = remaining - 1
                return httpx.Response(500, json={"message": "server error"})
        return httpx.Response(status_code=status_code, **kwargs)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method

        if self.auth_mode == "revoked" and not path.startswith("/app/installations"):
            return self._respond(
                request, status_code=401, json={"message": "Bad credentials"}
            )

        if (
            method == "POST"
            and path.startswith("/app/installations/")
            and (path.endswith("/access_tokens"))
        ):
            if self.auth_mode == "revoked":
                return self._respond(
                    request, status_code=401, json={"message": "Bad credentials"}
                )
            return self._respond(
                request,
                status_code=201,
                json={
                    "token": "ghs_fake_installation_token",
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                },
            )

        if self.rate_limited_remaining > 0:
            self.rate_limited_remaining -= 1
            return httpx.Response(
                403,
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": str(int(time.time()) + 1),
                    "retry-after": "1",
                },
                json={"message": "rate limited"},
            )

        if method == "GET" and path == f"/repos/{self.owner}/{self.name}":
            return self._respond(
                request,
                json={
                    "id": 1395956448,
                    "name": self.name,
                    "full_name": f"{self.owner}/{self.name}",
                    "html_url": f"https://github.com/{self.owner}/{self.name}",
                    "private": self.private,
                    "default_branch": self.default_branch,
                },
            )

        if method == "GET" and path.startswith(
            f"/repos/{self.owner}/{self.name}/branches/"
        ):
            branch = path.rsplit("/", 1)[-1]
            if branch != self.default_branch or self.head is None:
                return self._respond(
                    request, status_code=404, json={"message": "Branch not found"}
                )
            return self._respond(request, json={"commit": {"sha": self.head}})

        if method == "GET" and path == f"/repos/{self.owner}/{self.name}/commits":
            return self._commits_list(request)

        if method == "GET" and "/commits/" in path:
            sha = path.rsplit("/", 1)[-1]
            commit = next((c for c in self.commits if c.sha == sha), None)
            if commit is None:
                return self._respond(
                    request, status_code=404, json={"message": "Not Found"}
                )
            return self._respond(request, json=self._commit_detail(commit))

        if method == "GET" and "/contents/" in path:
            rel = path.split("/contents/", 1)[1]
            from urllib.parse import unquote

            rel = unquote(rel)
            ref = request.url.params.get("ref", self.head or "")
            tree = self.trees.get(ref, {})
            if rel not in tree:
                return self._respond(
                    request, status_code=404, json={"message": "Not Found"}
                )
            content = tree[rel]
            return self._respond(
                request,
                json={
                    "path": rel,
                    "sha": git_blob_sha(content),
                    "encoding": "base64",
                    "content": base64.b64encode(content.encode("utf-8")).decode(
                        "ascii"
                    ),
                },
            )

        return self._respond(request, status_code=404, json={"message": "Not Found"})

    def _commits_list(self, request: httpx.Request) -> httpx.Response:
        per_page = int(request.url.params.get("per_page", "100"))
        per_page = min(per_page, self.per_page_cap)
        page = int(request.url.params.get("page", "1"))
        sha_param = request.url.params.get("sha")
        # GitHub returns newest first, walking the requested ref.
        ordered = list(reversed(self.commits))
        if sha_param and sha_param != self.default_branch:
            # GitHub resolves branch names here too; only look up raw SHAs.
            idx = next(
                (i for i, c in enumerate(self.commits) if c.sha == sha_param), None
            )
            if idx is None:
                return self._respond(
                    request, status_code=404, json={"message": "Not Found"}
                )
            ordered = list(reversed(self.commits[: idx + 1]))
        start = (page - 1) * per_page
        chunk = ordered[start : start + per_page]
        payload = [self._commit_summary(c) for c in chunk]
        headers = {}
        if start + per_page < len(ordered):
            params = [
                (k, v) for k, v in request.url.params.multi_items() if k != "page"
            ]
            params.append(("page", str(page + 1)))
            nxt = str(request.url.copy_with(params=params))
            headers["link"] = f'<{nxt}>; rel="next"'
        return self._respond(request, json=payload, headers=headers)

    def _commit_summary(self, commit: FakeCommit) -> dict:
        return {
            "sha": commit.sha,
            "parents": [{"sha": p} for p in commit.parents],
            "commit": {
                "message": commit.message,
                "author": {
                    "name": commit.author_name,
                    "email": commit.author_email,
                    "date": commit.timestamp,
                },
                "committer": {
                    "name": commit.author_name,
                    "email": commit.author_email,
                    "date": commit.timestamp,
                },
            },
        }

    def _commit_detail(self, commit: FakeCommit) -> dict:
        data = self._commit_summary(commit)
        files = [
            {
                "filename": entry["filename"],
                "status": entry["status"],
                "additions": entry["additions"],
                "deletions": entry["deletions"],
                "changes": entry["changes"],
                "sha": entry["sha"],
                "patch": entry["patch"],
                **(
                    {"previous_filename": entry["previous_filename"]}
                    if "previous_filename" in entry
                    else {}
                ),
            }
            for entry in commit.files
        ]
        data["files"] = files
        return data


def make_github_client(fake: FakeGitHub, **kwargs) -> Any:
    """GitHubClient wired to the fake transport with a real RS256 test key."""
    from app.github.auth import GitHubAppAuth
    from app.github.client import GitHubClient

    auth = GitHubAppAuth(
        app_id="12345",
        private_key_pem=_TEST_RSA_KEY,
        transport=fake.transport(),
    )
    kwargs.setdefault("transport", fake.transport())
    kwargs.setdefault("sleep", lambda s: None)  # no real sleeps in tests
    return GitHubClient(auth=auth, **kwargs), auth


_TEST_RSA_KEY: str | None = None


def _ensure_test_key() -> str:
    global _TEST_RSA_KEY
    if _TEST_RSA_KEY is None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _TEST_RSA_KEY = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
    return _TEST_RSA_KEY


_ensure_test_key()
