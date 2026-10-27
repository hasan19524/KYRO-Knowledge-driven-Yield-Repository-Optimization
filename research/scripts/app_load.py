"""Drive REAL application traffic against the running KYRO stack.

Every request below is a genuine end-to-end call into the live application
(no mocks, no stubs): register/login perform real bcrypt hashing and real
Postgres reads/writes, github/start performs real OAuth state HMAC signing,
/api/repositories performs a real authorized query, page loads traverse the
real router/frontend. Round-trip latency per request is recorded to:

    research/data/live/app_requests.csv   (one row per real request)

Entrypoints measured: direct backend :8000, router :8090, frontend :3001.

Rate-limit safety (server side, config.py):
  RATE_LIMIT_REGISTER_PER_MIN = 10  (bucketed per email - new emails each run)
  RATE_LIMIT_LOGIN_PER_MIN    = 10  (bucketed per email; qa email capped at 6)
  github/start shares the login limit under the "github-oauth" bucket -> paced
  at 7 s so 8 starts fit inside any 60 s window.

Stop: STOP_APP_LOAD file in this directory.
"""

from __future__ import annotations

import csv
import datetime as dt
import http.client
import json
import random
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
STOP_FILE = Path(__file__).resolve().parent / "STOP_APP_LOAD"
HEADER = [
    "ts",
    "phase",
    "entrypoint",
    "method",
    "path",
    "status",
    "total_ms",
    "error",
]

BACKEND = ("127.0.0.1", 8000, "backend")
ROUTER = ("127.0.0.1", 8090, "router")
FRONTEND = ("127.0.0.1", 3001, "frontend")

QA_EMAIL = "qa.signup.20261020@example.com"
QA_PASSWORD = "QaSignup2026!"
LOAD_PASSWORD = "LoadProbe2026!"  # throwaway local load-test credential

# pacing: bucket -> minimum gap seconds (10/min server limit where noted)
GAPS = {
    "register": 2.0,
    "login": 7.0,
    "github": 7.0,
    "read": 2.0,
    "page": 2.0,
    "health": 1.0,
}
_last: dict[str, float] = {}


def now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def pace(bucket: str) -> None:
    gap = GAPS.get(bucket, 1.0)
    prev = _last.get(bucket, 0.0)
    wait = prev + gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[bucket] = time.monotonic()


class NoRedirect(http.client.HTTPConnection):
    """http.client never follows redirects by default - 302s stay 302s."""


def req(
    entry: tuple[str, int, str],
    method: str,
    path: str,
    phase: str,
    bucket: str,
    body: dict | None = None,
    token: str | None = None,
    timeout: float = 10.0,
) -> tuple[list, str | None]:
    """One real request; returns (csv_row, bearer_token_or_None)."""
    pace(bucket)
    host, port, name = entry
    headers = {"Accept": "application/json"}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, err = -1, ""
    t0 = time.perf_counter()
    try:
        conn = NoRedirect(host, port, timeout=timeout)
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        status = resp.status
        conn.close()
        if method == "POST" and status in (200, 201) and phase in ("register", "login"):
            try:
                tok = json.loads(raw).get("token")
            except Exception:  # noqa: BLE001
                tok = None
            return (
                [
                    now_iso(),
                    phase,
                    name,
                    method,
                    path,
                    status,
                    round((time.perf_counter() - t0) * 1000, 2),
                    "",
                ],
                tok,
            )
    except Exception as exc:  # noqa: BLE001 - load generator must never die
        err = type(exc).__name__
    return (
        [
            now_iso(),
            phase,
            name,
            method,
            path,
            status,
            round((time.perf_counter() - t0) * 1000, 2),
            err,
        ],
        None,
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    path = OUT_DIR / f"app_requests_{day}.csv"
    first = not path.exists()
    rows: list[list] = []
    print(f"[app_load] writing {path}", flush=True)

    run_id = int(time.time()) % 100000
    tokens: list[str] = []

    # 1) health (direct backend)
    for i in range(4):
        if STOP_FILE.exists():
            break
        r, _ = req(BACKEND, "GET", "/health", "health", "health")
        rows.append(r)

    # 2) register - 4 fresh load accounts (real bcrypt + real user rows)
    load_emails = [f"qa-load-{run_id}-{i}@example.com" for i in range(4)]
    for i, email in enumerate(load_emails):
        if STOP_FILE.exists():
            break
        entry = BACKEND if i < 2 else ROUTER  # 2 direct, 2 through router
        prefix = "/api" if entry is BACKEND else "/backend/api"
        r, tok = req(
            entry,
            "POST",
            f"{prefix}/auth/register",
            "register",
            "register",
            {"email": email, "password": LOAD_PASSWORD, "name": f"Load Probe {i}"},
        )
        rows.append(r)
        if tok:
            tokens.append(tok)

    # 3) login - qa x6 (4 direct / 2 router, bucket 6 <= 10/min), load accounts x1 each
    login_plan = (
        [(QA_EMAIL, QA_PASSWORD, BACKEND)] * 4
        + [(QA_EMAIL, QA_PASSWORD, ROUTER)] * 2
        + [(load_emails[0], LOAD_PASSWORD, BACKEND)]
    )
    for email, pw, entry in login_plan:
        if STOP_FILE.exists():
            break
        prefix = "/api" if entry is BACKEND else "/backend/api"
        r, tok = req(
            entry,
            "POST",
            f"{prefix}/auth/login",
            "login",
            "login",
            {"email": email, "password": pw},
        )
        rows.append(r)
        if tok and tok not in tokens:
            tokens.append(tok)

    # 4) OAuth start - real HMAC state signing + 302 to GitHub (never followed)
    for i in range(8):
        if STOP_FILE.exists():
            break
        entry = BACKEND if i < 4 else ROUTER
        prefix = "/api" if entry is BACKEND else "/backend/api"
        r, _ = req(
            entry, "GET", f"{prefix}/auth/github/start", "github_start", "github"
        )
        rows.append(r)

    # 5) authorized reads - real DB-backed repository listing + detail
    if tokens:
        t0 = tokens[0]
        for i in range(4):
            if STOP_FILE.exists():
                break
            entry = BACKEND if i < 2 else ROUTER
            prefix = "/api" if entry is BACKEND else "/backend/api"
            r, _ = req(
                entry, "GET", f"{prefix}/repositories", "repo_list", "read", token=t0
            )
            rows.append(r)
        r, _ = req(
            BACKEND,
            "GET",
            "/api/repositories/1395956448",
            "repo_detail",
            "read",
            token=t0,
        )
        rows.append(r)

    # 6) page loads through frontend + router
    for entry in (FRONTEND, ROUTER):
        for _ in range(3):
            if STOP_FILE.exists():
                break
            r, _ = req(entry, "GET", "/", "page_load", "page")
            rows.append(r)

    # 7) closing health
    r, _ = req(BACKEND, "GET", "/health", "health", "health")
    rows.append(r)

    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if first:
            w.writerow(HEADER)
        w.writerows(rows)

    ok = sum(1 for r in rows if r[5] not in (-1, 0))
    print(f"[app_load] done rows={len(rows)} http_ok={ok} -> {path}", flush=True)
    if STOP_FILE.exists():
        print("[app_load] stopped early via STOP_APP_LOAD", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
