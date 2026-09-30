"""GitHub REST client with pagination, rate-limit awareness and bounded retries.

All calls go through the GitHub App installation identity (no PATs, no
passwords). Errors are classified so the sync manager can distinguish
ACCESS_REVOKED (401/403) from transient conditions (rate limit / 5xx).
"""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import httpx

from app import config
from app.github.auth import GitHubAppAuth, GitHubAuthError, GitHubCredentialsMissing

log = logging.getLogger("kyro.github")

API_VERSION = "2022-11-28"


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubNotFound(GitHubError):
    pass


class GitHubRateLimited(GitHubError):
    pass


class GitHubUnavailable(GitHubError):
    pass


class GitHubClient:
    def __init__(
        self,
        auth: GitHubAppAuth | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        rate_limit_max_wait_s: float | None = None,
        sleep=time.sleep,
    ) -> None:
        self.auth = auth or GitHubAppAuth()
        self.base_url = (base_url or config.GITHUB_API_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else config.GITHUB_TIMEOUT_S
        self.max_retries = (
            max_retries if max_retries is not None else config.GITHUB_MAX_RETRIES
        )
        self.rate_limit_max_wait = (
            rate_limit_max_wait_s
            if rate_limit_max_wait_s is not None
            else config.GITHUB_RATE_LIMIT_MAX_WAIT_S
        )
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=transport,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------ core
    def _headers(self, installation_id: int | None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "kyro-ingestion",
        }
        if installation_id is not None:
            headers["Authorization"] = (
                f"Bearer {self.auth.installation_token(installation_id)}"
            )
        else:
            headers["Authorization"] = f"Bearer {self.auth.app_jwt()}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        installation_id: int | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._client.request(
                    method, path, params=params, headers=self._headers(installation_id)
                )
            except httpx.HTTPError as exc:
                if attempt > self.max_retries:
                    raise GitHubUnavailable(
                        f"GitHub unreachable after retries: {exc}"
                    ) from exc
                self._sleep(min(2**attempt, 8))
                continue

            if resp.status_code < 300:
                return resp

            if resp.status_code == 404:
                raise GitHubNotFound(f"GitHub 404 for {method} {path}", status=404)

            if resp.status_code == 401:
                raise GitHubAuthError(
                    f"GitHub 401 for {method} {path} (authentication failed)"
                )

            if resp.status_code in (403, 429):
                retry_after = resp.headers.get("retry-after")
                remaining = resp.headers.get("x-ratelimit-remaining")
                if (
                    retry_after is not None
                    or remaining == "0"
                    or resp.status_code == 429
                ):
                    wait = self._rate_limit_wait(resp)
                    if wait > self.rate_limit_max_wait:
                        raise GitHubRateLimited(
                            f"GitHub rate limited; reset wait {wait:.0f}s exceeds cap "
                            f"{self.rate_limit_max_wait:.0f}s",
                            status=resp.status_code,
                        )
                    log.warning(
                        "github_rate_limited path=%s wait=%.1fs attempt=%d",
                        path,
                        wait,
                        attempt,
                    )
                    self._sleep(wait)
                    continue
                raise GitHubAuthError(
                    f"GitHub 403 for {method} {path} (permission denied, not rate limit)"
                )

            if resp.status_code >= 500:
                if attempt > self.max_retries:
                    raise GitHubUnavailable(
                        f"GitHub {resp.status_code} after {self.max_retries} retries for {path}",
                        status=resp.status_code,
                    )
                self._sleep(min(2**attempt, 8))
                continue

            raise GitHubError(
                f"GitHub unexpected HTTP {resp.status_code} for {path}",
                status=resp.status_code,
            )

    @staticmethod
    def _rate_limit_wait(resp: httpx.Response) -> float:
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after) + 0.5
            except ValueError:
                pass
        reset = resp.headers.get("x-ratelimit-reset")
        if reset:
            try:
                return max(0.0, float(reset) - time.time()) + 0.5
            except ValueError:
                pass
        return 5.0

    @staticmethod
    def _next_page(resp: httpx.Response) -> int | None:
        link = resp.headers.get("link", "")
        if 'rel="next"' not in link:
            return None
        from urllib.parse import parse_qs, urlparse

        for part in link.split(","):
            if 'rel="next"' not in part:
                continue
            start = part.find("<")
            end = part.find(">", start)
            if start < 0 or end <= start:
                continue
            url = part[start + 1 : end]
            # Parse the query properly: a naive split on "page=" would match
            # the tail of "per_page=..." and return the wrong page number.
            pages = parse_qs(urlparse(url).query).get("page")
            if pages:
                try:
                    return int(pages[0])
                except ValueError:
                    return None
        return None

    # -------------------------------------------------------------- endpoints
    def get_repository(
        self, owner: str, name: str, installation_id: int | None
    ) -> dict:
        return self._request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}",
            installation_id=installation_id,
        ).json()

    def get_branch_sha(
        self, owner: str, name: str, branch: str, installation_id: int | None
    ) -> str:
        data = self._request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/branches/{quote(branch)}",
            installation_id=installation_id,
        ).json()
        return data["commit"]["sha"]

    def iter_commits(
        self,
        owner: str,
        name: str,
        *,
        sha: str,
        installation_id: int | None,
        per_page: int = 100,
        stop_sha: str | None = None,
    ):
        """Yield commit summaries (newest first, GitHub order) with pagination.

        Stops early once `stop_sha` (already-published boundary) is observed.
        """
        page: int | None = 1
        while page is not None:
            resp = self._request(
                "GET",
                f"/repos/{quote(owner)}/{quote(name)}/commits",
                params={"sha": sha, "per_page": per_page, "page": page},
                installation_id=installation_id,
            )
            items = resp.json()
            if not isinstance(items, list):
                raise GitHubError(f"unexpected commits payload type: {type(items)}")
            for item in items:
                yield item
                if stop_sha is not None and item.get("sha") == stop_sha:
                    # Boundary observed: yield it (caller decides) and stop.
                    return
            page = self._next_page(resp)

    def get_commit(
        self, owner: str, name: str, commit_sha: str, installation_id: int | None
    ) -> dict:
        return self._request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/commits/{quote(commit_sha)}",
            installation_id=installation_id,
        ).json()

    def get_file_content(
        self,
        owner: str,
        name: str,
        path: str,
        ref: str,
        installation_id: int | None,
    ) -> tuple[str | None, str]:
        """Return (decoded_text_or_None, blob_sha). None text = non-UTF8/binary."""
        quoted_path = "/".join(quote(seg) for seg in path.split("/"))
        data = self._request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/contents/{quoted_path}",
            params={"ref": ref},
            installation_id=installation_id,
        ).json()
        if isinstance(data, list):
            raise GitHubError(f"path is a directory, not a file: {path}")
        blob_sha = data.get("sha", "")
        if data.get("encoding") != "base64" or not data.get("content"):
            return None, blob_sha
        import base64

        raw = base64.b64decode(data["content"])
        try:
            return raw.decode("utf-8"), blob_sha
        except UnicodeDecodeError:
            return None, blob_sha

    def close(self) -> None:
        self._client.close()


__all__ = [
    "GitHubAuthError",
    "GitHubClient",
    "GitHubCredentialsMissing",
    "GitHubError",
    "GitHubNotFound",
    "GitHubRateLimited",
    "GitHubUnavailable",
]
