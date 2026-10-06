"""In-memory fixed-window rate limiting.

Scopes counters per (bucket, subject, window) with a monotonic clock, so
limits are enforced per user and per endpoint class without external
dependencies. Counters live in process memory: with multiple worker
processes each process enforces the configured limit independently (fail-
closed per process, documented in README security section).

`limit <= 0` disables enforcement (development escape hatch).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Final

_PRUNE_THRESHOLD: Final = 4096


class RateLimiter:
    """Fixed-window counter; returns None when allowed, seconds-to-reset when not."""

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._hits: dict[tuple[str, int, int], int] = {}

    def hit(
        self, *, bucket: str, subject_id: int, limit: int, window_s: int = 60
    ) -> int | None:
        """Record one request.

        Returns None when the request is allowed, otherwise the number of
        whole seconds (>= 1) until the current window resets - callers map
        that to a Retry-After header.
        """
        if limit <= 0:
            return None
        now = self._now()
        window = int(now // window_s)
        key = (bucket, subject_id, window)
        with self._lock:
            if len(self._hits) > _PRUNE_THRESHOLD:
                for stale in [k for k in self._hits if k[2] < window - 1]:
                    del self._hits[stale]
            count = self._hits.get(key, 0) + 1
            if count > limit:
                return max(1, math.ceil(window_s - (now - window * window_s)))
            self._hits[key] = count
            return None


__all__ = ["RateLimiter"]
