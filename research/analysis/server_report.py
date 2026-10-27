#!/usr/bin/env python
"""Aggregate KYRO live sampler output into the master server metrics report.

Usage:
    python server_report.py --live-dir research/data/live --out-dir research/results

Reads every live sampler file described in research/SCHEMA.md (read-only,
append-only CSV/JSONL written by concurrently running samplers) and produces:

  * research/results/server_metrics.csv  -- long-format master dataset with
    columns: family,server,metric,value,unit,samples,window_start,window_end
  * research/results/server_metrics.md   -- human-readable report

Robustness: files may be absent, header-only, single-row, actively appended
(partial trailing line) or contain unparseable values.  Affected metrics are
skipped and noted; nothing is ever imputed or fabricated.  No database writes,
no docker, no network access.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CSV_NAME = "server_metrics.csv"
MD_NAME = "server_metrics.md"

# numpy >= 2.0 renamed trapz -> trapezoid
_TRAPZ = getattr(np, "trapezoid", None) or np.trapz  # type: ignore[attr-defined]

FAMILY_ORDER = [
    "resources",
    "host_process",
    "latency",
    "queue",
    "pipeline",
    "arrival_burstiness",
]

FAMILY_TITLES = {
    "resources": "Container resources (docker stats, 1 Hz)",
    "host_process": "Host processes (host sampler, 1 Hz)",
    "latency": "Service latency probes (HTTP / TCP)",
    "queue": "Kafka queue backlog (per topic)",
    "pipeline": "Ingestion pipeline (overall)",
    "arrival_burstiness": "Event arrival burstiness (inter-arrival times)",
}

# (role, substrings) checked against host cmd_hint, in order
ROLE_PATTERNS = [
    ("worker", ("worker_main",)),
    ("backend", ("uvicorn", "app.main")),
    ("tunnel", ("cloudflared", "tunnel")),
    ("router", ("public_router",)),
    ("frontend", ("next dev", ".next", "next/dist", "next\\dist")),
    ("sampler", ("sampler", "burst_generator")),
]


# ---------------------------------------------------------------------------
# small helpers


def derive_role(cmd_hint) -> str:
    c = str(cmd_hint or "").lower()
    for role, keys in ROLE_PATTERNS:
        if any(k in c for k in keys):
            return role
    return "other"


def parse_iso(series: pd.Series) -> pd.Series:
    """Parse mixed ISO-8601 timestamps (Z suffix or +00:00 offset) -> UTC."""
    return pd.to_datetime(series, utc=True, errors="coerce")


def iso(ts) -> str:
    if ts is None or pd.isna(ts):
        return ""
    return pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")


def clean(values) -> np.ndarray:
    arr = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce"), dtype=float)
    return arr[~np.isnan(arr)]


def pctl(values, q: float) -> float:
    arr = clean(values)
    if arr.size == 0:
        return float("nan")
    return float(np.percentile(arr, q))  # linear interpolation


def mean(values) -> float:
    arr = clean(values)
    return float(arr.mean()) if arr.size else float("nan")


def amax(values) -> float:
    arr = clean(values)
    return float(arr.max()) if arr.size else float("nan")


def add_row(rows, family, server, metric, value, unit, samples, w0, w1):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return
    rows.append(
        {
            "family": family,
            "server": server,
            "metric": metric,
            "value": float(value),
            "unit": unit,
            "samples": int(samples),
            "window_start": w0,
            "window_end": w1,
        }
    )


def read_csv_glob(live_dir: Path, pattern: str, notes: list, label: str):
    """Read + concatenate every CSV matching pattern.  Returns (df|None, n_files)."""
    paths = sorted(live_dir.glob(pattern))
    if not paths:
        return None, 0
    frames = []
    for p in paths:
        try:
            df = pd.read_csv(p, encoding="utf-8", on_bad_lines="skip")
        except pd.errors.EmptyDataError:
            notes.append(f"{label}: {p.name} is empty (not even a header) - skipped")
            continue
        except UnicodeDecodeError:
            notes.append(f"{label}: {p.name} is not valid UTF-8 - skipped")
            continue
        df["__source"] = p.name
        frames.append(df)
    if not frames:
        return None, len(paths)
    return pd.concat(frames, ignore_index=True, sort=False), len(paths)


def read_jsonl_glob(live_dir: Path, pattern: str, notes: list, label: str):
    """Read + concatenate every JSONL matching pattern.  Returns (df|None, n_files)."""
    paths = sorted(live_dir.glob(pattern))
    if not paths:
        return None, 0
    rows: list = []
    bad = 0
    for p in paths:
        try:
            fh = p.open("r", encoding="utf-8", errors="strict")
        except UnicodeDecodeError:  # pragma: no cover - open does not decode yet
            notes.append(f"{label}: {p.name} is not valid UTF-8 - skipped")
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    # most likely a partial trailing line while the sampler is writing
                    bad += 1
    if bad:
        notes.append(
            f"{label}: skipped {bad} unparseable JSONL line(s) "
            "(likely partial writes from concurrently running samplers)"
        )
    if not rows:
        return None, len(paths)
    return pd.DataFrame(rows), len(paths)


def presence_note(live_dir: Path, pattern: str) -> str:
    n = len(list(live_dir.glob(pattern)))
    if n == 0:
        return "ABSENT - family skipped, no data"
    return f"present ({n} file(s))"


# ---------------------------------------------------------------------------
# families


def family_resources(live_dir: Path, rows: list, notes: list) -> int:
    df, _ = read_csv_glob(live_dir, "resources_*.csv", notes, "resources")
    if (
        df is None
        or df.empty
        or "ts" not in df.columns
        or "container" not in df.columns
    ):
        notes.append("resources: no usable rows - family 'resources' skipped")
        return 0
    df = df.copy()
    df["ts"] = parse_iso(df["ts"])
    n0 = len(df)
    df = df.dropna(subset=["ts", "container"]).sort_values("ts")
    if len(df) < n0:
        notes.append(f"resources: dropped {n0 - len(df)} row(s) with bad ts/container")

    for container, g in df.groupby("container", sort=True):
        w0, w1 = iso(g["ts"].min()), iso(g["ts"].max())

        cpu = clean(g["cpu_pct"])
        add_row(
            rows,
            "resources",
            container,
            "cpu_pct_mean",
            mean(cpu),
            "%",
            len(cpu),
            w0,
            w1,
        )
        add_row(
            rows,
            "resources",
            container,
            "cpu_pct_p50",
            pctl(cpu, 50),
            "%",
            len(cpu),
            w0,
            w1,
        )
        add_row(
            rows,
            "resources",
            container,
            "cpu_pct_p95",
            pctl(cpu, 95),
            "%",
            len(cpu),
            w0,
            w1,
        )
        add_row(
            rows,
            "resources",
            container,
            "cpu_pct_max",
            amax(cpu),
            "%",
            len(cpu),
            w0,
            w1,
        )

        mem = clean(g["mem_used_bytes"])
        add_row(
            rows,
            "resources",
            container,
            "mem_used_bytes_mean",
            mean(mem),
            "bytes",
            len(mem),
            w0,
            w1,
        )
        add_row(
            rows,
            "resources",
            container,
            "mem_used_bytes_max",
            amax(mem),
            "bytes",
            len(mem),
            w0,
            w1,
        )

        limit = clean(g["mem_limit_bytes"])
        if limit.size and float(limit.min()) > 0:
            mem_pct = clean(g["mem_used_bytes"] / g["mem_limit_bytes"] * 100.0)
            add_row(
                rows,
                "resources",
                container,
                "mem_pct_of_limit_mean",
                mean(mem_pct),
                "%",
                len(mem_pct),
                w0,
                w1,
            )
            add_row(
                rows,
                "resources",
                container,
                "mem_pct_of_limit_max",
                amax(mem_pct),
                "%",
                len(mem_pct),
                w0,
                w1,
            )
        else:
            notes.append(
                f"resources: {container} has no valid mem_limit_bytes - mem_pct_of_limit skipped"
            )

        net = clean(g["net_io_bytes"])
        add_row(
            rows,
            "resources",
            container,
            "net_io_bytes_total_delta",
            float(net[-1] - net[0]) if net.size else float("nan"),
            "bytes",
            len(net),
            w0,
            w1,
        )
        blk = clean(g["block_io_bytes"])
        add_row(
            rows,
            "resources",
            container,
            "block_io_bytes_total_delta",
            float(blk[-1] - blk[0]) if blk.size else float("nan"),
            "bytes",
            len(blk),
            w0,
            w1,
        )

        pids = clean(g["pids"])
        add_row(
            rows,
            "resources",
            container,
            "pids_mean",
            mean(pids),
            "count",
            len(pids),
            w0,
            w1,
        )
        add_row(
            rows,
            "resources",
            container,
            "pids_max",
            amax(pids),
            "count",
            len(pids),
            w0,
            w1,
        )
    return sum(1 for r in rows if r["family"] == "resources")


def family_host_process(live_dir: Path, rows: list, notes: list) -> int:
    df, _ = read_csv_glob(live_dir, "host_*.csv", notes, "host_process")
    if df is None or df.empty or "ts" not in df.columns or "cmd_hint" not in df.columns:
        notes.append("host_process: no usable rows - family 'host_process' skipped")
        return 0
    df = df.copy()
    df["ts"] = parse_iso(df["ts"])
    n0 = len(df)
    df = df.dropna(subset=["ts"])
    if len(df) < n0:
        notes.append(f"host_process: dropped {n0 - len(df)} row(s) with bad ts")
    df["role"] = df["cmd_hint"].map(derive_role)
    unknown = int((df["role"] == "other").sum())
    if unknown:
        notes.append(
            f"host_process: {unknown} row(s) with unrecognized cmd_hint -> role 'other'"
        )

    for role, g in df.groupby("role", sort=True):
        w0, w1 = iso(g["ts"].min()), iso(g["ts"].max())
        cpu = clean(g["cpu_pct"])
        add_row(
            rows, "host_process", role, "cpu_pct_mean", mean(cpu), "%", len(cpu), w0, w1
        )
        add_row(
            rows,
            "host_process",
            role,
            "cpu_pct_p95",
            pctl(cpu, 95),
            "%",
            len(cpu),
            w0,
            w1,
        )
        add_row(
            rows, "host_process", role, "cpu_pct_max", amax(cpu), "%", len(cpu), w0, w1
        )
        rss = clean(g["rss_bytes"])
        add_row(
            rows,
            "host_process",
            role,
            "rss_bytes_mean",
            mean(rss),
            "bytes",
            len(rss),
            w0,
            w1,
        )
        add_row(
            rows,
            "host_process",
            role,
            "rss_bytes_max",
            amax(rss),
            "bytes",
            len(rss),
            w0,
            w1,
        )
    return sum(1 for r in rows if r["family"] == "host_process")


def family_latency(live_dir: Path, rows: list, notes: list) -> int:
    df, _ = read_csv_glob(live_dir, "http_latency_*.csv", notes, "latency")
    if df is None or df.empty or "ts" not in df.columns or "server" not in df.columns:
        notes.append("latency: no usable rows - family 'latency' skipped")
        return 0
    df = df.copy()
    df["ts"] = parse_iso(df["ts"])
    n0 = len(df)
    df = df.dropna(subset=["ts", "server"])
    if len(df) < n0:
        notes.append(f"latency: dropped {n0 - len(df)} row(s) with bad ts/server")
    status_col = (
        df["status"] if "status" in df.columns else pd.Series(np.nan, index=df.index)
    )
    df["status_n"] = pd.to_numeric(status_col, errors="coerce")
    err = df.get("error")
    err_s = (
        err.fillna("").astype(str) if err is not None else pd.Series("", index=df.index)
    )
    df["is_error"] = (df["status_n"] == -1) | (err_s.str.strip() != "")

    for server, g in df.groupby("server", sort=True):
        w0, w1 = iso(g["ts"].min()), iso(g["ts"].max())
        n = len(g)
        proto = (
            str(g["protocol"].iloc[0])
            if "protocol" in g.columns and g["protocol"].notna().any()
            else "http"
        )

        total = clean(g["total_ms"])
        add_row(
            rows,
            "latency",
            server,
            "total_ms_mean",
            mean(total),
            "ms",
            len(total),
            w0,
            w1,
        )
        add_row(
            rows,
            "latency",
            server,
            "total_ms_p50",
            pctl(total, 50),
            "ms",
            len(total),
            w0,
            w1,
        )
        add_row(
            rows,
            "latency",
            server,
            "total_ms_p95",
            pctl(total, 95),
            "ms",
            len(total),
            w0,
            w1,
        )
        add_row(
            rows,
            "latency",
            server,
            "total_ms_max",
            amax(total),
            "ms",
            len(total),
            w0,
            w1,
        )

        if proto == "http":
            if "ttfb_ms" in g.columns:
                ttfb_all = pd.to_numeric(g["ttfb_ms"], errors="coerce")
                ttfb = clean(ttfb_all[ttfb_all >= 0])
            else:
                ttfb = np.array([])
            add_row(
                rows,
                "latency",
                server,
                "ttfb_ms_mean",
                mean(ttfb),
                "ms",
                len(ttfb),
                w0,
                w1,
            )
            add_row(
                rows,
                "latency",
                server,
                "ttfb_ms_p95",
                pctl(ttfb, 95),
                "ms",
                len(ttfb),
                w0,
                w1,
            )
        else:
            conn = clean(g["connect_ms"]) if "connect_ms" in g.columns else np.array([])
            add_row(
                rows,
                "latency",
                server,
                "connect_ms_mean",
                mean(conn),
                "ms",
                len(conn),
                w0,
                w1,
            )

        n_err = int(g["is_error"].sum())
        n_ok = int(g["status_n"].isin([200, 1]).sum())
        add_row(
            rows,
            "latency",
            server,
            "error_rate",
            n_err / n if n else float("nan"),
            "ratio",
            n,
            w0,
            w1,
        )
        add_row(
            rows,
            "latency",
            server,
            "availability",
            n_ok / n if n else float("nan"),
            "ratio",
            n,
            w0,
            w1,
        )
        if n_err:
            notes.append(
                f"latency: {server} had {n_err}/{n} probe(s) flagged as errors"
            )
        bad_status = max(0, n - n_ok - n_err)
        if bad_status > 0:
            codes = sorted(
                {str(int(s)) for s in clean(g["status_n"]) if s not in (1.0, 200.0)}
            )
            notes.append(
                f"latency: {server} returned non-200/1 status on {bad_status}/{n} probe(s)"
                + (f" (codes: {', '.join(codes)})" if codes else "")
            )
    return sum(1 for r in rows if r["family"] == "latency")


def family_queue(live_dir: Path, rows: list, notes: list) -> int:
    df, _ = read_csv_glob(live_dir, "queues_*.csv", notes, "queue")
    if df is None or df.empty or "ts" not in df.columns or "topic" not in df.columns:
        notes.append("queue: no usable rows - family 'queue' skipped")
        return 0
    df = df.copy()
    df["ts"] = parse_iso(df["ts"])
    n0 = len(df)
    df = df.dropna(subset=["ts", "topic"]).sort_values("ts")
    if len(df) < n0:
        notes.append(f"queue: dropped {n0 - len(df)} row(s) with bad ts/topic")

    for topic, g in df.groupby("topic", sort=True):
        w0, w1 = iso(g["ts"].min()), iso(g["ts"].max())

        lag = clean(g["lag"])
        add_row(
            rows, "queue", topic, "lag_mean", mean(lag), "messages", len(lag), w0, w1
        )
        add_row(
            rows, "queue", topic, "lag_p95", pctl(lag, 95), "messages", len(lag), w0, w1
        )
        add_row(
            rows, "queue", topic, "lag_max", amax(lag), "messages", len(lag), w0, w1
        )

        # total lag across partitions per poll (bucket ts to the second: partitions
        # of one poll are written a few ms apart, polls are >= 3 s apart)
        g2 = g.dropna(subset=["lag"]).copy()
        g2["ts_bucket"] = g2["ts"].dt.floor("s")
        tot = g2.groupby("ts_bucket")["lag"].sum()
        if len(tot) >= 2:
            x = np.asarray((tot.index - tot.index[0]).total_seconds(), dtype=float)
            y = tot.to_numpy(dtype=float)
            add_row(
                rows,
                "queue",
                topic,
                "backlog_area",
                float(_TRAPZ(y, x)),
                "messages*s",
                len(y),
                w0,
                w1,
            )
        else:
            notes.append(f"queue: {topic} has <2 poll buckets - backlog_area skipped")

        window_s = (g["ts"].max() - g["ts"].min()).total_seconds()
        if window_s > 0 and "end_offset" in g.columns and "partition" in g.columns:
            ends = (
                g.dropna(subset=["end_offset"])
                .sort_values("ts")
                .groupby("partition")["end_offset"]
            )
            total_new = float((ends.last() - ends.first()).sum())
            add_row(
                rows,
                "queue",
                topic,
                "throughput",
                total_new / window_s,
                "messages/s",
                len(g),
                w0,
                w1,
            )
        else:
            notes.append(
                f"queue: {topic} window <= 0 or missing offsets - throughput skipped"
            )
    return sum(1 for r in rows if r["family"] == "queue")


def _events_frame(live_dir: Path, notes: list):
    df, _ = read_jsonl_glob(live_dir, "db_events_*.jsonl", notes, "pipeline/events")
    if df is None or df.empty:
        return None
    if "created_at" not in df.columns:
        notes.append(
            "pipeline: db_events file(s) lack created_at - event metrics skipped"
        )
        return None
    df = df.copy()
    df["created_dt"] = parse_iso(df["created_at"])
    df["processed_dt"] = (
        parse_iso(df["processed_at"]) if "processed_at" in df.columns else pd.NaT
    )
    return df


def family_pipeline(live_dir: Path, rows: list, notes: list) -> int:
    W = "overall"

    # -- ingestion events (db_events_*.jsonl) --------------------------------
    ev = _events_frame(live_dir, notes)
    if ev is not None:
        w0, w1 = iso(ev["created_dt"].min()), iso(ev["created_dt"].max())
        n = len(ev)
        add_row(rows, "pipeline", W, "events_total", n, "count", n, w0, w1)
        n_proc = int(ev["processed_dt"].notna().sum())
        add_row(rows, "pipeline", W, "events_processed", n_proc, "count", n, w0, w1)

        # backfill skew: created_at can be far older than the collection time
        if "ts" in ev.columns:
            obs = parse_iso(ev["ts"]).dropna()
            created = ev["created_dt"].dropna()
            if len(obs) and len(created):
                skew_days = (obs.min() - created.min()).total_seconds() / 86400.0
                if skew_days > 1.0:
                    notes.append(
                        f"pipeline: earliest created_at is {skew_days:.1f} day(s) before "
                        "first observation (backfill events) - created_at-based windows, "
                        "events_per_minute_mean and inter-arrival stats include that skew"
                    )

        svc = ((ev["processed_dt"] - ev["created_dt"]).dt.total_seconds()).dropna()
        neg = int((svc < 0).sum())
        if neg:
            notes.append(
                f"pipeline: {neg} event(s) with processed_at < created_at (clock skew?) - excluded"
            )
        svc = svc[svc >= 0]
        add_row(
            rows,
            "pipeline",
            W,
            "service_seconds_mean",
            mean(svc),
            "s",
            len(svc),
            w0,
            w1,
        )
        add_row(
            rows,
            "pipeline",
            W,
            "service_seconds_p50",
            pctl(svc, 50),
            "s",
            len(svc),
            w0,
            w1,
        )
        add_row(
            rows,
            "pipeline",
            W,
            "service_seconds_p95",
            pctl(svc, 95),
            "s",
            len(svc),
            w0,
            w1,
        )
        add_row(
            rows, "pipeline", W, "service_seconds_max", amax(svc), "s", len(svc), w0, w1
        )

        created = ev["created_dt"].dropna()
        if len(created):
            counts = created.dt.floor("min").value_counts()
            peak = float(counts.max())
            span_min = (created.max() - created.min()).total_seconds() / 60.0
            per_min_mean = n / span_min if span_min > 0 else float(n)
            add_row(
                rows,
                "pipeline",
                W,
                "events_per_minute_peak",
                peak,
                "events/min",
                n,
                w0,
                w1,
            )
            add_row(
                rows,
                "pipeline",
                W,
                "events_per_minute_mean",
                per_min_mean,
                "events/min",
                n,
                w0,
                w1,
            )

    # -- table sizes (db_counts_*.csv) ---------------------------------------
    dc, _ = read_csv_glob(live_dir, "db_counts_*.csv", notes, "pipeline/counts")
    if dc is not None and not dc.empty and "ts" in dc.columns:
        dc = dc.copy()
        dc["ts"] = parse_iso(dc["ts"])
        dc = dc.dropna(subset=["ts"]).sort_values("ts")
        if dc.empty:
            notes.append(
                "pipeline: db_counts rows all bad - table-size metrics skipped"
            )
        else:
            w0, w1 = iso(dc["ts"].min()), iso(dc["ts"].max())
            n = len(dc)
            for col in ("commits", "commit_files", "files", "ingestion_events"):
                vals = clean(dc[col])
                if not vals.size:
                    notes.append(
                        f"pipeline: db_counts column {col!r} unusable - skipped"
                    )
                    continue
                add_row(
                    rows, "pipeline", W, f"{col}_total", vals[-1], "count", n, w0, w1
                )
                add_row(
                    rows,
                    "pipeline",
                    W,
                    f"{col}_delta",
                    vals[-1] - vals[0],
                    "count",
                    n,
                    w0,
                    w1,
                )
    else:
        notes.append(
            "pipeline: db_counts_*.csv absent/unusable - table-size metrics skipped"
        )

    # -- per-commit real work (commit_files_*.jsonl) -------------------------
    cf, _ = read_jsonl_glob(
        live_dir, "commit_files_*.jsonl", notes, "pipeline/commit_files"
    )
    if cf is not None and not cf.empty:
        if "ts" in cf.columns:
            cts = parse_iso(cf["ts"])
            w0, w1 = iso(cts.min()), iso(cts.max())
        else:
            w0, w1 = "", ""
        n = len(cf)
        add_row(rows, "pipeline", W, "commit_work_commits", n, "count", n, w0, w1)
        for col, metric in (
            ("n_files", "commit_work_files"),
            ("additions", "commit_work_additions"),
            ("deletions", "commit_work_deletions"),
            ("changes", "commit_work_changes"),
            ("patch_bytes", "commit_work_patch_bytes"),
        ):
            vals = clean(cf[col]) if col in cf.columns else np.array([])
            add_row(
                rows,
                "pipeline",
                W,
                metric,
                float(vals.sum()) if vals.size else float("nan"),
                "count",
                n,
                w0,
                w1,
            )
    else:
        notes.append(
            "pipeline: commit_files_*.jsonl absent/empty - commit work size metrics skipped"
        )

    # -- load-generator push log (burst_manifest.jsonl) ----------------------
    bm, _ = read_jsonl_glob(live_dir, "burst_manifest.jsonl", notes, "pipeline/burst")
    if bm is not None and not bm.empty:
        n = len(bm)
        ok = int(bm["ok"].sum()) if "ok" in bm.columns else 0
        add_row(rows, "pipeline", W, "burst_pushes_total", n, "count", n, "", "")
        add_row(rows, "pipeline", W, "burst_pushes_ok", ok, "count", n, "", "")
        if "label" in bm.columns:
            for label, cnt in bm["label"].astype(str).value_counts().items():
                safe = "".join(ch if ch.isalnum() else "_" for ch in label)
                add_row(
                    rows,
                    "pipeline",
                    W,
                    f"burst_pushes_{safe}",
                    int(cnt),
                    "count",
                    n,
                    "",
                    "",
                )
    else:
        notes.append(
            "pipeline: burst_manifest.jsonl absent/empty - burst push metrics skipped"
        )

    return sum(1 for r in rows if r["family"] == "pipeline")


def family_arrival_burstiness(live_dir: Path, rows: list, notes: list) -> int:
    ev = _events_frame(live_dir, notes)
    if ev is None:
        notes.append("arrival_burstiness: no usable events - family skipped")
        return 0
    created = ev["created_dt"].dropna().sort_values()
    if len(created) < 2:
        notes.append(
            "arrival_burstiness: fewer than 2 events with created_at - family skipped"
        )
        return 0
    w0, w1 = iso(created.min()), iso(created.max())
    # use Timedelta.diff -> total_seconds (resolution-agnostic, unlike raw int64)
    diffs = created.diff().dt.total_seconds().dropna().to_numpy(dtype=float)
    if diffs.size == 0 or float(diffs.mean()) <= 0:
        notes.append(
            "arrival_burstiness: degenerate inter-arrival series - family skipped"
        )
        return 0
    add_row(
        rows,
        "arrival_burstiness",
        "overall",
        "inter_arrival_mean",
        float(diffs.mean()),
        "s",
        diffs.size,
        w0,
        w1,
    )
    cv = float(np.std(diffs, ddof=1) / diffs.mean()) if diffs.size > 1 else float("nan")
    add_row(
        rows,
        "arrival_burstiness",
        "overall",
        "inter_arrival_cv",
        cv,
        "ratio",
        diffs.size,
        w0,
        w1,
    )
    add_row(
        rows,
        "arrival_burstiness",
        "overall",
        "inter_arrival_p95",
        pctl(diffs, 95),
        "s",
        diffs.size,
        w0,
        w1,
    )
    add_row(
        rows,
        "arrival_burstiness",
        "overall",
        "inter_arrival_max",
        float(diffs.max()),
        "s",
        diffs.size,
        w0,
        w1,
    )
    return sum(1 for r in rows if r["family"] == "arrival_burstiness")


# ---------------------------------------------------------------------------
# report rendering


def fmt_value(v, unit: str) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if unit == "bytes":
        for div, suf in ((1 << 30, "GiB"), (1 << 20, "MiB"), (1 << 10, "KiB")):
            if abs(v) >= div:
                return f"{v / div:.2f} {suf}"
        return f"{v:.0f} B"
    if unit == "count" and float(v).is_integer():
        return f"{int(v):,}"
    if float(v).is_integer() and abs(v) >= 1000:
        return f"{int(v):,}"
    if abs(v) >= 100:
        return f"{v:,.1f}"
    return f"{v:.4g}"


def family_table(fam_rows: list) -> str:
    servers = sorted({r["server"] for r in fam_rows})
    metrics = list(dict.fromkeys(r["metric"] for r in fam_rows))  # keep insertion order
    header = ["server"] + metrics
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for s in servers:
        bym = {r["metric"]: r for r in fam_rows if r["server"] == s}
        cells = [s] + [
            fmt_value(bym[m]["value"], bym[m]["unit"]) if m in bym else ""
            for m in metrics
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_md(live_dir: Path, df: pd.DataFrame, notes: list) -> str:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not df.empty:
        win_start = min(w for w in df["window_start"] if w)
        win_end = max(w for w in df["window_end"] if w)
        window = f"{win_start} .. {win_end} (UTC)"
    else:
        window = "n/a (no data)"

    out = [
        "# KYRO Real-Time Server & Pipeline Metrics",
        "",
        f"- Window covered: {window}",
        f"- Generated: {now} by `research/analysis/server_report.py`",
        f"- Source: `{live_dir.as_posix()}` (live samplers, read-only aggregation)",
        f"- Master dataset: `results/{CSV_NAME}` ({len(df)} rows)",
        "",
    ]

    for fam in FAMILY_ORDER:
        fam_rows = [r for r in df.to_dict("records")] if not df.empty else []
        fam_rows = [r for r in fam_rows if r["family"] == fam]
        out.append(f"## {FAMILY_TITLES[fam]}")
        out.append("")
        if fam_rows:
            out.append(family_table(fam_rows))
        else:
            out.append("_No data for this family (see Data notes)._")
        out.append("")

    out.append("## Data notes")
    out.append("")
    out.append("File presence at generation time:")
    out.append("")
    for pattern in (
        "resources_*.csv",
        "host_*.csv",
        "http_latency_*.csv",
        "queues_*.csv",
        "db_counts_*.csv",
        "db_events_*.jsonl",
        "commit_files_*.jsonl",
        "burst_manifest.jsonl",
    ):
        out.append(f"- `{pattern}`: {presence_note(live_dir, pattern)}")
    out.append("")
    if notes:
        out.append("Anomalies / processing notes:")
        out.append("")
        for note in notes:
            out.append(f"- {note}")
    else:
        out.append("No anomalies detected.")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# entry point


def run(live_dir: Path, out_dir: Path):
    rows: list = []
    notes: list = []
    # record which source files exist before aggregating (Data notes / console)
    for pattern in (
        "resources_*.csv",
        "host_*.csv",
        "http_latency_*.csv",
        "queues_*.csv",
        "db_counts_*.csv",
        "db_events_*.jsonl",
        "commit_files_*.jsonl",
        "burst_manifest.jsonl",
    ):
        if not list(live_dir.glob(pattern)):
            notes.append(f"{pattern}: ABSENT - no data")
    counts = {}
    for fam, fn in (
        ("resources", family_resources),
        ("host_process", family_host_process),
        ("latency", family_latency),
        ("queue", family_queue),
        ("pipeline", family_pipeline),
        ("arrival_burstiness", family_arrival_burstiness),
    ):
        counts[fam] = fn(live_dir, rows, notes)

    df = pd.DataFrame(
        rows,
        columns=[
            "family",
            "server",
            "metric",
            "value",
            "unit",
            "samples",
            "window_start",
            "window_end",
        ],
    )
    # preserve order but drop duplicate notes (some source files feed 2 families)
    notes[:] = list(dict.fromkeys(notes))
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / CSV_NAME
    md_path = out_dir / MD_NAME
    df.to_csv(csv_path, index=False, encoding="utf-8")
    md_path.write_text(render_md(live_dir, df, notes), encoding="utf-8")
    return df, counts, notes, csv_path, md_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Aggregate KYRO live sampler data into the master server metrics report."
    )
    ap.add_argument(
        "--live-dir",
        default="research/data/live",
        help="directory with live sampler files",
    )
    ap.add_argument(
        "--out-dir",
        default="research/results",
        help="output directory for CSV + Markdown",
    )
    args = ap.parse_args(argv)

    live_dir = Path(args.live_dir)
    out_dir = Path(args.out_dir)
    if not live_dir.is_dir():
        print(f"ERROR: live dir not found: {live_dir}", file=sys.stderr)
        return 2

    df, counts, notes, csv_path, md_path = run(live_dir, out_dir)

    print(f"KYRO server_report: live dir = {live_dir}")
    for fam in FAMILY_ORDER:
        n = counts.get(fam, 0)
        servers = (
            sorted({r["server"] for r in df.to_dict("records") if r["family"] == fam})
            if not df.empty
            else []
        )
        status = f"{n} rows ({', '.join(servers)})" if n else "SKIPPED (no usable data)"
        print(f"  family {fam:<16}: {status}")
    print(f"wrote {csv_path} ({len(df)} rows total)")
    print(f"wrote {md_path}")
    if notes:
        print("data notes:")
        for note in notes:
            print(f"  - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
