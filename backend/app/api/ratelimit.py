"""Rate-limit dependency for expensive/abuse-prone endpoints.

Applied AFTER authentication (the limiter itself depends on require_user),
so unauthenticated traffic never consumes a user's budget and dev-mode
identities are counted like any other subject.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app import config
from app.api.auth import CurrentUser, get_state, require_user
from app.state import AppState


def rate_limit(bucket: str, setting: str, window_s: int = 60):
    """Build a per-user fixed-window dependency reading `config.<setting>`.

    `setting` is evaluated per request so operators/tests can change limits
    without rebuilding the app; 0 disables enforcement.
    """

    def dependency(
        state: AppState = Depends(get_state),
        user: CurrentUser = Depends(require_user),
    ) -> None:
        limit = int(getattr(config, setting, 0))
        retry_after = state.rate_limiter.hit(
            bucket=bucket, subject_id=user.id, limit=limit, window_s=window_s
        )
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


__all__ = ["rate_limit"]
