#!/usr/bin/env python3
"""Cross-check KYRO's three env files for drift — names and pass/fail only.

KYRO has three env files with different owners (the two-file split fixed for
tunnel readiness; see docs/audit/KYRO_SYSTEM_AUDIT.md "Configuration split"):

  root .env          CONTAINER mode (Stack A infra + Stack B app via compose)
  backend/.env       NATIVE (host) mode — loaded by app/config.py
  frontend/.env.local NATIVE (host) frontend — loaded by Next.js

Keys that exist in more than one file MUST carry identical values, or you get
the classic ghost bug ("I updated the key but the backend still fails").
This script fails loudly on drift. It NEVER prints values — only key names
and MATCH / MISMATCH / MISSING.

Usage (any Python, stdlib only):
    python scripts/check_env_sync.py
Exit code 0 = consistent, 1 = drift/missing keys.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT_ENV = REPO / ".env"
BACKEND_ENV = REPO / "backend" / ".env"
FRONTEND_ENV = REPO / "frontend" / ".env.local"

# Keys mirrored between root .env (container) and backend/.env (native).
SHARED_ROOT_BACKEND = [
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "KYRO_API_KEY",
]
# Root-only keys a working container stack needs.
ROOT_REQUIRED = [
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "CHROMA_URL",
    "CHROMA_COLLECTION",
    "KAFKA_BOOTSTRAP_SERVERS",
    "KYRO_WEBHOOK_SECRET",
]
BACKEND_REQUIRED = ["KYRO_API_KEY"]
FRONTEND_REQUIRED = ["KYRO_BACKEND_URL", "KYRO_API_KEY"]


def parse_env(path: Path) -> dict[str, str] | None:
    """KEY -> raw value. Handles double-quoted multi-line values (inline PEM).

    Deliberately dependency-free; every env file KYRO ships parses under these
    rules (KEY=value, '#' comments, optional double-quoted values that may span
    physical lines until the closing quote).
    """
    if not path.is_file():
        return None
    values: dict[str, str] = {}
    pending_key: str | None = None
    pending_lines: list[str] = []
    in_quote = False
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if in_quote:
            pending_lines.append(line)
            if line.rstrip().endswith('"'):
                values[pending_key] = "\n".join(pending_lines)  # type: ignore[index]
                in_quote = False
                pending_key = None
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if value.startswith('"') and not (len(value) > 1 and value.endswith('"')):
            pending_key, pending_lines, in_quote = key, [line], True
            continue
        values[key] = value[1:-1] if value[:1] == '"' else value
    if in_quote:
        values[pending_key] = "\n".join(pending_lines)  # type: ignore[index]
    return values


def main() -> int:
    failures: list[str] = []
    files = {
        "root .env": parse_env(ROOT_ENV),
        "backend/.env": parse_env(BACKEND_ENV),
        "frontend/.env.local": parse_env(FRONTEND_ENV),
    }
    for name, data in files.items():
        if data is None:
            print(f"MISSING-FILE {name}")
            failures.append(name)

    root, back, front = (
        files["root .env"] or {},
        files["backend/.env"] or {},
        files["frontend/.env.local"] or {},
    )

    # 1) mirrored keys must be identical across the two backend-facing files
    for key in SHARED_ROOT_BACKEND:
        a, b = root.get(key), back.get(key)
        if a is None or b is None:
            which = "root .env" if a is None else "backend/.env"
            print(f"MISSING  {key}  (absent from {which})")
            failures.append(key)
        elif a != b:
            print(f"MISMATCH {key}  (root .env vs backend/.env)")
            failures.append(key)
        else:
            print(f"OK       {key}  (root == backend)")

    # 2) the proxy must inject the same key the backend expects
    if files["frontend/.env.local"] is not None:
        for key in FRONTEND_REQUIRED:
            if key not in front:
                print(f"MISSING  {key}  (absent from frontend/.env.local)")
                failures.append(key)
        fk, bk = front.get("KYRO_API_KEY"), back.get("KYRO_API_KEY")
        if fk is not None and bk is not None:
            if fk != bk:
                print("MISMATCH KYRO_API_KEY  (frontend/.env.local vs backend/.env)")
                failures.append("KYRO_API_KEY")
            else:
                print("OK       KYRO_API_KEY  (frontend == backend)")

    # 3) required per-owner keys
    for key in ROOT_REQUIRED:
        if files["root .env"] is not None and key not in root:
            print(f"MISSING  {key}  (absent from root .env)")
            failures.append(key)
    for key in BACKEND_REQUIRED:
        if files["backend/.env"] is not None and key not in back:
            print(f"MISSING  {key}  (absent from backend/.env)")
            failures.append(key)

    # 4) mode sanity: container hosts must never leak into the native file and
    #    vice versa (this is exactly how the old split-brain bug hid).
    for key, data, label in (
        ("backend/.env", back, "NATIVE"),
        ("frontend/.env.local", front, "NATIVE"),
    ):
        for name, value in data.items():
            if (
                "kyro-postgres" in value
                or "kyro-chroma" in value
                or "kyro-kafka" in value
            ):
                print(f"WRONG-MODE {name}  (container DNS in {label} file {key})")
                failures.append(name)

    if failures:
        print(f"\nFAIL - {len(failures)} problem(s); fix the files above.")
        return 1
    print("\nPASS - env files are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
