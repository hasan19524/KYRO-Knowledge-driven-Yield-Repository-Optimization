"""DB change-tail sampler -> research/data/live/{db_events,db_counts,commit_files}_*.

Polls KYRO's Postgres READ-ONLY every --interval seconds:
  * NEW ingestion_events rows (id > last seen)  -> db_events_*.jsonl (full row + payload)
  * NEW commits rows                            -> commit_files_*.jsonl (per-commit aggregates)
  * table counts every 10 s                     -> db_counts_*.csv

Long-running, append-only, never writes to KYRO tables, never raises fatally.
Stop: Ctrl-C or a file named STOP_DB_SAMPLER in this directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "live"
STOP_FILE = Path(__file__).resolve().parent / "STOP_DB_SAMPLER"
DSN = "postgresql+psycopg://kyro:kyro@127.0.0.1:5433/kyro"


def utcnow() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def jdefault(o):
    if isinstance(o, dt.datetime):
        return o.isoformat()
    return str(o)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    ev_path = OUT_DIR / f"db_events_{day}.jsonl"
    cf_path = OUT_DIR / f"commit_files_{day}.jsonl"
    cnt_path = OUT_DIR / f"db_counts_{day}.csv"
    if not cnt_path.exists():
        cnt_path.write_text(
            "ts,commits,commit_files,files,ingestion_events\n", encoding="utf-8"
        )

    engine = create_engine(DSN, pool_pre_ping=True)
    last_event_id = 0
    last_commit_id = 0
    last_counts_ts = 0.0
    errors = 0
    print(f"[db_sampler] tailing ingestion_events + commits -> {OUT_DIR}", flush=True)

    while not STOP_FILE.exists():
        t0 = time.monotonic()
        try:
            with engine.connect() as conn:
                # --- new ingestion events (full fidelity) ---
                rows = (
                    conn.execute(
                        text(
                            'SELECT id, event_id, topic, "partition", "offset", '
                            "repository_github_id, kind, status, pg_status, index_status, "
                            "attempts, error, created_at, updated_at, processed_at, payload "
                            "FROM ingestion_events WHERE id > :last ORDER BY id"
                        ),
                        {"last": last_event_id},
                    )
                    .mappings()
                    .all()
                )
                if rows:
                    with ev_path.open("a", encoding="utf-8") as f:
                        for r in rows:
                            rec = {"ts": utcnow(), **dict(r)}
                            f.write(json.dumps(rec, default=jdefault) + "\n")
                    last_event_id = int(rows[-1]["id"])

                # --- new commits -> per-commit real work aggregates ---
                crows = (
                    conn.execute(
                        text(
                            "SELECT c.id AS commit_row_id, c.repository_id AS repo_github_id, "
                            "c.github_commit_sha AS sha, c.committed_at, "
                            "count(cf.id) AS n_files, "
                            "coalesce(sum(cf.additions),0) AS additions, "
                            "coalesce(sum(cf.deletions),0) AS deletions, "
                            "coalesce(sum(cf.changes),0) AS changes, "
                            "coalesce(sum(coalesce(length(cf.patch),0)),0) AS patch_bytes "
                            "FROM commits c LEFT JOIN commit_files cf ON cf.commit_id = c.id "
                            "WHERE c.id > :last GROUP BY c.id, c.repository_id, "
                            "c.github_commit_sha, c.committed_at ORDER BY c.id"
                        ),
                        {"last": last_commit_id},
                    )
                    .mappings()
                    .all()
                )
                if crows:
                    with cf_path.open("a", encoding="utf-8") as f:
                        for r in crows:
                            rec = {"ts": utcnow(), **dict(r)}
                            f.write(json.dumps(rec, default=jdefault) + "\n")
                    last_commit_id = int(crows[-1]["commit_row_id"])

                # --- periodic counts ---
                if time.monotonic() - last_counts_ts >= 10.0:
                    counts = conn.execute(
                        text(
                            "SELECT (SELECT count(*) FROM commits), "
                            "(SELECT count(*) FROM commit_files), "
                            "(SELECT count(*) FROM files), "
                            "(SELECT count(*) FROM ingestion_events)"
                        )
                    ).one()
                    with cnt_path.open("a", newline="", encoding="utf-8") as f:
                        f.write(
                            f"{utcnow()},{counts[0]},{counts[1]},{counts[2]},{counts[3]}\n"
                        )
                    last_counts_ts = time.monotonic()
            errors = 0
        except Exception as exc:  # noqa: BLE001 - sampler must survive anything
            errors += 1
            print(f"[db_sampler] error#{errors}: {exc}", file=sys.stderr, flush=True)
            if errors > 30:
                time.sleep(10)
        wait = args.interval - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
    print("[db_sampler] stopped by STOP file", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
