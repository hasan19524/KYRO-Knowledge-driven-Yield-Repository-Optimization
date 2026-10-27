"""Parse research/data/trace/tasks.csv (SCHEMA.md section 6) into Task objects.

  * rows with an EMPTY service_seconds (never processed) are skipped -- the
    simulator needs a reference service time for every schedulable task
  * arrival = created_at as seconds since the FIRST arrival in the file
  * size_files = files_touched, size_bytes = changes (real work size features)
  * Task.kind maps trace kind -> interface kind: live -> push, backfill ->
    backfill, anything else -> other
  * extra trace columns (experiment_label, status, attempts, ...) ride along
    in Task.meta so schedulers using them must flag it (see interface.py)

Stdlib only; also runs on backend/.venv python.
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

# research/ as importable package root (namespace pkg, no __init__)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.sim.interface import Task  # noqa: E402  (frozen contract)

_KIND_MAP = {"live": "push", "push": "push", "backfill": "backfill", "other": "other"}


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_tasks(csv_path: str | Path) -> list[Task]:
    """Load tasks.csv into a list of Task sorted by arrival (oldest first)."""
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return []

    rows.sort(
        key=lambda r: (
            _parse_ts(r["arrival_ts"]),
            int(r["task_id"]) if r["task_id"] else 0,
        )
    )
    base = _parse_ts(rows[0]["arrival_ts"])

    tasks: list[Task] = []
    for row in rows:
        service_raw = (row.get("service_seconds") or "").strip()
        if not service_raw:
            continue  # never processed -> not schedulable
        tasks.append(
            Task(
                task_id=int(row["task_id"]),
                arrival=(_parse_ts(row["arrival_ts"]) - base).total_seconds(),
                service=float(service_raw),
                size_files=int(row.get("files_touched") or 0),
                size_bytes=int(row.get("changes") or 0),
                kind=_KIND_MAP.get((row.get("kind") or "").strip(), "other"),
                meta={
                    "kind_raw": row.get("kind") or "",
                    "experiment_label": row.get("experiment_label") or "",
                    "status": row.get("status") or "",
                    "attempts": int(row.get("attempts") or 0),
                    "repo_github_id": row.get("repo_github_id") or "",
                    "commits_in_event": int(row.get("commits_in_event") or 0),
                    "additions": int(row.get("additions") or 0),
                    "deletions": int(row.get("deletions") or 0),
                    "patch_bytes": int(row.get("patch_bytes") or 0),
                },
            )
        )
    return tasks
