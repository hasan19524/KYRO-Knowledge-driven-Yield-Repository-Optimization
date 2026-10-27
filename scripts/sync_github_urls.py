"""Sync the GitHub App's webhook URL to the current tunnel origin (auto-sync).

The Cloudflare quick-tunnel URL changes on every restart. This script keeps
the App's webhook URL in step automatically using the App's OWN credentials
(App ID + private key, already on disk for ingestion) so nobody edits GitHub
settings by hand. Called by startup.md after the tunnel URL is known:

    backend\\.venv\\Scripts\\python.exe scripts\\sync_github_urls.py https://xyz.trycloudflare.com

What it CAN do (and does):
  * Webhook URL -> PATCH /app/hook/config (App JWT). Only the "url" key is
    sent; omitted keys (content_type, secret, insecure_ssl) are preserved by
    GitHub, so the webhook secret that n8n validates is never touched.

What it CANNOT do (GitHub has no API for it - settings page only):
  * OAuth callback URLs (redirect_uris). Mitigated by design: sign-in from
    this laptop uses http://127.0.0.1:3001/backend/api/auth/github/callback,
    which is added to the App ONCE and never changes. A tunnel callback is
    only needed for phone demos; this script prints it for a quick paste.

Only public URLs and HTTP statuses are printed; never tokens or secrets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.github.auth import GitHubAppAuth  # noqa: E402  (repo-root script; backend on path)

WEBHOOK_PATH = "/webhook/github"
CALLBACK_PATH = "/backend/api/auth/github/callback"
LOCALHOST_CALLBACK = f"http://127.0.0.1:3001{CALLBACK_PATH}"


def normalize_origin(raw: str) -> str:
    """Accept a bare host, a URL, or a URL with a path; keep scheme+host+port."""
    value = raw.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        raise ValueError(f"cannot parse an origin from {raw!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def is_local(origin: str) -> bool:
    return (urlparse(origin).hostname or "") in ("127.0.0.1", "localhost", "::1")


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: sync_github_urls.py <public-origin>   (e.g. https://abc-xyz.trycloudflare.com)"
        )
        return 2

    try:
        origin = normalize_origin(sys.argv[1])
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 2

    auth = GitHubAppAuth()
    try:
        auth.require_configured()
    except Exception as exc:  # noqa: BLE001 - GitHubCredentialsMissing; message only
        print(f"FAIL: {exc}")
        return 1

    headers = {
        "Authorization": f"Bearer {auth.app_jwt()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(base_url=auth.base_url, timeout=30.0) as client:
        me = client.get("/app", headers=headers)
        if me.status_code != 200:
            print(
                f"FAIL: GET /app -> HTTP {me.status_code} (check GITHUB_APP_ID + private key)"
            )
            return 1
        slug = me.json().get("slug", "?")

        current = client.get("/app/hook/config", headers=headers)
        if current.status_code != 200:
            print(f"FAIL: GET /app/hook/config -> HTTP {current.status_code}")
            return 1
        before = str(current.json().get("url", ""))
        desired = origin + WEBHOOK_PATH

        if before == desired:
            print(f"GitHub App '{slug}': webhook URL already correct ({desired})")
        elif is_local(origin):
            print(
                f"GitHub App '{slug}': origin is localhost - webhook URL left unchanged ({before})"
            )
        else:
            # Send ONLY the url key: GitHub treats the other keys (secret!)
            # as "keep current" when omitted from a PATCH.
            patch = client.patch(
                "/app/hook/config", headers=headers, json={"url": desired}
            )
            if patch.status_code != 200:
                message = ""
                try:
                    message = str(patch.json().get("message", ""))[:200]
                except Exception:  # noqa: BLE001 - body may not be JSON
                    pass
                print(
                    f"FAIL: PATCH /app/hook/config -> HTTP {patch.status_code} {message}"
                )
                return 1
            after = client.get("/app/hook/config", headers=headers)
            persisted = (
                str(after.json().get("url", "")) if after.status_code == 200 else ""
            )
            if persisted != desired:
                print(f"FAIL: webhook URL did not persist (read back: {persisted!r})")
                return 1
            print(f"GitHub App '{slug}': webhook URL updated -> {persisted}")

        print("OAuth callbacks cannot be set via API (GitHub has no endpoint for it).")
        print(
            f"  Keep this one configured ONCE for laptop sign-in: {LOCALHOST_CALLBACK}"
        )
        print(
            f"  For a phone demo through the tunnel, add for the day: {origin}{CALLBACK_PATH}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
