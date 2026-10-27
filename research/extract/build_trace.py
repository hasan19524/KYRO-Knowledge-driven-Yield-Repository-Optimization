"""Build research/data/trace/tasks.csv from the live collector files.

Reads (read-only, never writes to KYRO's DB):
  live/db_events_YYYYMMDD.jsonl     -- one row per ingestion_events row (payload included)
  live/commit_files_YYYYMMDD.jsonl  -- per-new-commit work aggregates (sha keyed)
  live/burst_manifest.jsonl         -- generated-commit burst pushes (shas + label)

Writes the schedulable workload trace (SCHEMA.md section 6):
  task_id,arrival_ts,kind,repo_github_id,commits_in_event,files_touched,
  additions,deletions,changes,patch_bytes,service_seconds,attempts,status,
  experiment_label

Rules:
  * task_id      = ingestion_events.id
  * arrival_ts   = created_at (kept as the original ISO-8601 string)
  * service_seconds = processed_at - created_at in seconds; EMPTY when
    processed_at is NULL (row is kept, status flags it)
  * work aggregates: sum commit_files rows over the event's
    payload.commits[*].sha; when NO sha matches commit_files, fall back to
    the payload itself (payload.changes per-file counters if present,
    else the payload commit added/removed/modified file lists, else 0)
  * experiment_label: any event sha in burst_manifest -> "burst";
    kind == "backfill" -> "backfill"; else "organic"
  * sorted by arrival_ts (ties by task_id); idempotent full rebuild

The live collector may append while we read, so a truncated final JSONL
line is skipped with a warning, and duplicate event ids keep the LAST
record seen (full-fidelity re-logs with updated status win).

Usage:
  python research/extract/build_trace.py \
      --live-dir research/data/live --out research/data/trace/tasks.csv
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

OUT_COLUMNS = [
    "task_id",
    "arrival_ts",
    "kind",
    "repo_github_id",
    "commits_in_event",
    "files_touched",
    "additions",
    "deletions",
    "changes",
    "patch_bytes",
    "service_seconds",
    "attempts",
    "status",
    "experiment_label",
]


def _parse_ts(value: str) -> datetime:
    """ISO-8601 with 'Z' or '+00:00' (both occur in the live files)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_jsonl(path: str) -> list[dict]:
    """One JSON object per line; tolerate a torn final line (live append)."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                # Collector may be mid-append; only the tail can be torn.
                print(
                    f"WARN: {path}:{lineno}: unparseable line skipped ({exc})",
                    file=sys.stderr,
                )
    return rows


def load_commit_files(live_dir: str) -> dict[str, dict]:
    """sha -> work aggregates. Files sorted by name = chronological append,
    so a duplicate sha keeps the LAST record."""
    table: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(live_dir, "commit_files_*.jsonl"))):
        for r in _read_jsonl(path):
            sha = r.get("sha")
            if not sha:
                continue
            table[sha] = {
                "n_files": int(r.get("n_files") or 0),
                "additions": int(r.get("additions") or 0),
                "deletions": int(r.get("deletions") or 0),
                "changes": int(r.get("changes") or 0),
                "patch_bytes": int(r.get("patch_bytes") or 0),
            }
    return table


def load_burst_shas(live_dir: str) -> set[str]:
    """Every sha pushed during a generated-commit burst window."""
    shas: set[str] = set()
    path = os.path.join(live_dir, "burst_manifest.jsonl")
    if not os.path.exists(path):
        return shas
    for r in _read_jsonl(path):
        for sha in r.get("shas") or []:
            shas.add(sha)
    return shas


def load_db_events(live_dir: str) -> list[dict]:
    """All db_events_*.jsonl rows, deduped by ingestion_events.id (last wins)."""
    by_id: dict[int, dict] = {}
    no_id: list[dict] = []
    for path in sorted(glob.glob(os.path.join(live_dir, "db_events_*.jsonl"))):
        for r in _read_jsonl(path):
            event_pk = r.get("id")
            if event_pk is None:
                no_id.append(r)
            else:
                by_id[event_pk] = r
    return sorted(by_id.values(), key=lambda r: r["id"]) + no_id


def _event_work(payload: dict, shas: list[str], commit_files: dict[str, dict]) -> dict:
    """Work aggregates for one ingestion event.

    Primary: sum the real commit_files aggregates over the event's shas.
    Fallback (no sha matched at all): the payload itself --
    payload.changes carries per-file {additions, deletions, changes, patch},
    else the commit added/removed/modified file-path lists, else zeros.
    """
    matched = [commit_files[s] for s in shas if s in commit_files]
    if matched:
        return {
            "files_touched": sum(m["n_files"] for m in matched),
            "additions": sum(m["additions"] for m in matched),
            "deletions": sum(m["deletions"] for m in matched),
            "changes": sum(m["changes"] for m in matched),
            "patch_bytes": sum(m["patch_bytes"] for m in matched),
        }

    changes = payload.get("changes") or []
    if changes:
        # payload.changes: one entry per changed file with real line counters.
        return {
            "files_touched": len(changes),
            "additions": sum(int(e.get("additions") or 0) for e in changes),
            "deletions": sum(int(e.get("deletions") or 0) for e in changes),
            "changes": sum(int(e.get("changes") or 0) for e in changes),
            "patch_bytes": sum(len(e.get("patch") or "") for e in changes),
        }

    commits = payload.get("commits") or []
    if commits:
        # Payload commit added/removed/modified are FILE-PATH lists (no line
        # counts here), so additions/deletions count changed files.
        n_added = sum(len(c.get("added") or []) for c in commits)
        n_removed = sum(len(c.get("removed") or []) for c in commits)
        n_modified = sum(len(c.get("modified") or []) for c in commits)
        return {
            "files_touched": n_added + n_removed + n_modified,
            "additions": n_added,
            "deletions": n_removed,
            "changes": n_added + n_removed,
            "patch_bytes": 0,
        }

    return {
        "files_touched": 0,
        "additions": 0,
        "deletions": 0,
        "changes": 0,
        "patch_bytes": 0,
    }


def build_rows(live_dir: str) -> list[dict]:
    commit_files = load_commit_files(live_dir)
    burst_shas = load_burst_shas(live_dir)
    events = load_db_events(live_dir)

    rows: list[dict] = []
    for r in events:
        payload = r.get("payload") or {}
        commits = payload.get("commits") or []
        shas = [c.get("sha") for c in commits if c.get("sha")]

        work = _event_work(payload, shas, commit_files)

        created_at = r.get("created_at") or ""
        processed_at = r.get("processed_at")
        if processed_at:
            service = (_parse_ts(processed_at) - _parse_ts(created_at)).total_seconds()
            service_str = f"{service:.6f}"
        else:
            service_str = ""  # never processed: keep row, flag via status

        kind = r.get("kind") or ""
        if any(s in burst_shas for s in shas):
            label = "burst"
        elif kind == "backfill":
            label = "backfill"
        else:
            label = "organic"

        rows.append(
            {
                "task_id": r.get("id"),
                "arrival_ts": created_at,
                "kind": kind,
                "repo_github_id": ""
                if r.get("repository_github_id") is None
                else r.get("repository_github_id"),
                "commits_in_event": len(commits),
                "files_touched": work["files_touched"],
                "additions": work["additions"],
                "deletions": work["deletions"],
                "changes": work["changes"],
                "patch_bytes": work["patch_bytes"],
                "service_seconds": service_str,
                "attempts": r.get("attempts"),
                "status": r.get("status") or "",
                "experiment_label": label,
            }
        )

    def sort_key(row: dict):
        ts = (
            _parse_ts(row["arrival_ts"])
            if row["arrival_ts"]
            else datetime.fromtimestamp(0, tz=timezone.utc)
        )
        return (ts, row["task_id"] if row["task_id"] is not None else -1)

    rows.sort(key=sort_key)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live-dir", default="research/data/live")
    ap.add_argument("--out", default="research/data/trace/tasks.csv")
    args = ap.parse_args()

    rows = build_rows(args.live_dir)

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        import csv

        writer = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    services = [float(r["service_seconds"]) for r in rows if r["service_seconds"]]
    print(
        f"wrote {out_path}: {len(rows)} rows "
        f"({len(services)} with service_seconds, {len(rows) - len(services)} unprocessed)"
    )
    if services:
        services_sorted = sorted(services)
        mid = len(services_sorted) // 2
        if len(services_sorted) % 2:
            median = services_sorted[mid]
        else:
            median = (services_sorted[mid - 1] + services_sorted[mid]) / 2
        print(
            f"service_seconds min/median/max = "
            f"{services_sorted[0]:.6f} / {median:.6f} / {services_sorted[-1]:.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
