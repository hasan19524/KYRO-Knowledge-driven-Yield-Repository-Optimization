"""GitHub App authentication (locked: installation identity only).

Never logs or returns token material. Supports either inline PEM content
(GITHUB_APP_PRIVATE_KEY) or a mounted key file (GITHUB_APP_PRIVATE_KEY_PATH).
"""

from __future__ import annotations

import threading
import time
from datetime import UTC
from pathlib import Path

import httpx
import jwt

from app import config


class GitHubCredentialsMissing(RuntimeError):
    """Raised when GitHub App credentials are not present in the environment."""


class GitHubAuthError(RuntimeError):
    """Raised when GitHub rejects App/authentication (401/403, non-rate-limit)."""


def _load_private_key() -> str:
    if config.GITHUB_APP_PRIVATE_KEY.strip():
        return config.GITHUB_APP_PRIVATE_KEY
    if config.GITHUB_APP_PRIVATE_KEY_PATH:
        path = Path(config.GITHUB_APP_PRIVATE_KEY_PATH)
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


class GitHubAppAuth:
    def __init__(
        self,
        app_id: str | None = None,
        private_key_pem: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self.app_id = (app_id if app_id is not None else config.GITHUB_APP_ID).strip()
        self.private_key = (
            private_key_pem if private_key_pem is not None else _load_private_key()
        )
        self.base_url = (base_url or config.GITHUB_API_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else config.GITHUB_TIMEOUT_S
        self._transport = transport
        self._lock = threading.Lock()
        self._token_cache: dict[int, tuple[str, float]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.private_key)

    def require_configured(self) -> None:
        if not self.configured:
            raise GitHubCredentialsMissing(
                "GitHub App credentials are not configured. Set GITHUB_APP_ID and "
                "GITHUB_APP_PRIVATE_KEY (PEM) or GITHUB_APP_PRIVATE_KEY_PATH."
            )

    def app_jwt(self) -> str:
        self.require_configured()
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self.app_id},
            self.private_key,
            algorithm="RS256",
        )

    def installation_token(self, installation_id: int) -> str:
        self.require_configured()
        with self._lock:
            cached = self._token_cache.get(installation_id)
            if cached and cached[1] > time.time():
                return cached[0]

        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                resp = client.post(
                    f"/app/installations/{installation_id}/access_tokens",
                    headers={
                        "Authorization": f"Bearer {self.app_jwt()}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
        except httpx.HTTPError as exc:
            raise GitHubAuthError(
                f"failed to reach GitHub for installation token: {exc}"
            ) from exc

        if resp.status_code in (401, 403):
            # Never include response body tokens/keys; message only.
            raise GitHubAuthError(
                f"GitHub rejected installation authentication (HTTP {resp.status_code})"
            )
        if resp.status_code != 201:
            raise GitHubAuthError(
                f"unexpected installation token response (HTTP {resp.status_code})"
            )

        token = resp.json().get("token", "")
        expires_at = _parse_github_datetime(resp.json().get("expires_at")) or (
            time.time() + 3300
        )
        # Refresh 5 minutes before expiry.
        with self._lock:
            self._token_cache[installation_id] = (token, expires_at - 300)
        return token

    def invalidate(self, installation_id: int) -> None:
        with self._lock:
            self._token_cache.pop(installation_id, None)


def _parse_github_datetime(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime

    try:
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(UTC)
            .timestamp()
        )
    except ValueError:
        return None
