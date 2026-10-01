"""Shared X-API-Key authentication for mutation/query endpoints.

Unset KYRO_API_KEY => authentication disabled (local development only).
When set, the key must be presented as the X-API-Key header; the Next.js
proxy injects it server-side so the browser never receives the secret.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from app import config


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = config.KYRO_API_KEY
    if not expected:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


__all__ = ["require_api_key"]
