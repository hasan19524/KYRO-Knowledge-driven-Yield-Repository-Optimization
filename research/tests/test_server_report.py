"""Tests for research/analysis/server_report.py using small synthetic fixtures.

All fixtures are clearly synthetic test data written to pytest's tmp_path,
matching the formats in research/SCHEMA.md.  Nothing here touches the real
live/ directory, the database, or docker.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis import server_report  # noqa: E402


# ---------------------------------------------------------------------------
# helpers


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def metric_map(df: pd.DataFrame, family: str) -> dict:
    """{(server, metric): value} for one family."""
    sub = df[df["family"] == family]
    return {(r.server, r.metric): float(r.value) for r in sub.itertuples()}


def run_report(tmp_path: Path):
    out_dir = tmp_path / "out"
    df, counts, notes, csv_path, md_path = server_report.run(tmp_path, out_dir)
    return df, counts, notes, csv_path, md_path


T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# resources aggregation math


def test_resources_aggregation_math(tmp_path):
    """21 samples, cpu 1..21: mean=11, p50=11, p95=20, max=21; deltas exact."""
    lines = [
        "ts,container,cpu_pct,mem_used_bytes,mem_limit_bytes,net_io_bytes,block_io_bytes,pids"
    ]
    for i in range(21):
        lines.append(
            f"{iso_z(T0 + timedelta(seconds=i))},kyro-test,{i + 1},1000000,2000000,"
            f"{100 + 50 * i},7,5"
        )
    # deliberately NO trailing newline (robustness requirement)
    (tmp_path / "resources_20261020.csv").write_text("\n".join(lines), encoding="utf-8")

    df, counts, notes, csv_path, md_path = run_report(tmp_path)
    m = metric_map(df, "resources")

    assert m[("kyro-test", "cpu_pct_mean")] == pytest.approx(11.0)
    assert m[("kyro-test", "cpu_pct_p50")] == pytest.approx(11.0)
    assert m[("kyro-test", "cpu_pct_p95")] == pytest.approx(20.0)
    assert m[("kyro-test", "cpu_pct_max")] == pytest.approx(21.0)
    assert m[("kyro-test", "mem_used_bytes_mean")] == pytest.approx(1_000_000)
    assert m[("kyro-test", "mem_used_bytes_max")] == pytest.approx(1_000_000)
    assert m[("kyro-test", "mem_pct_of_limit_mean")] == pytest.approx(50.0)
    assert m[("kyro-test", "mem_pct_of_limit_max")] == pytest.approx(50.0)
    # net_io = 100 + 50*i, i in 0..20 -> first=100, last=1100, delta=1000
    assert m[("kyro-test", "net_io_bytes_total_delta")] == pytest.approx(1000.0)
    assert m[("kyro-test", "block_io_bytes_total_delta")] == pytest.approx(0.0)
    assert m[("kyro-test", "pids_mean")] == pytest.approx(5.0)
    assert m[("kyro-test", "pids_max")] == pytest.approx(5.0)

    # samples + window on a cpu metric
    row = df[(df.family == "resources") & (df.metric == "cpu_pct_mean")].iloc[0]
    assert row["samples"] == 21
    assert row["window_start"].startswith("2026-10-20T12:00:00")
    assert row["window_end"].startswith("2026-10-20T12:00:20")
    assert counts["resources"] == 12


# ---------------------------------------------------------------------------
# latency error_rate / availability


def test_latency_error_rate_and_availability(tmp_path):
    # backend: 6 clean 200s, 1 status=-1, 1 status=200 with error text,
    #          1 status=500 -> errors = 2/9, availability = 6/9 (200s minus the
    #          error-flagged one is still 200; error flag is independent)
    rows = []
    for i in range(6):
        rows.append(
            f"{iso_z(T0 + timedelta(seconds=5 * i))},backend,http,200,10.0,20.0,{100.0 + i},"
        )
    rows.append(
        f"{iso_z(T0 + timedelta(seconds=35))},backend,http,-1,,,,connection refused"
    )
    rows.append(
        f"{iso_z(T0 + timedelta(seconds=40))},backend,http,200,10.0,20.0,150.0,timeout"
    )
    rows.append(
        f"{iso_z(T0 + timedelta(seconds=45))},backend,http,500,10.0,20.0,300.0,"
    )
    # postgres tcp: 2 clean probes, ttfb sentinels -1
    rows.append(f"{iso_z(T0 + timedelta(seconds=50))},postgres,tcp,1,0.5,-1.0,0.8,")
    rows.append(f"{iso_z(T0 + timedelta(seconds=55))},postgres,tcp,1,1.5,-1.0,1.8,")
    header = "ts,server,protocol,status,connect_ms,ttfb_ms,total_ms,error"
    (tmp_path / "http_latency_20261020.csv").write_text(
        header + "\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )

    df, *_ = run_report(tmp_path)
    m = metric_map(df, "latency")

    assert m[("backend", "error_rate")] == pytest.approx(2 / 9)
    # availability = status in (200, 1): 6 clean + the error-text row (status
    # still 200) = 7; the -1 and 500 rows are unavailable
    assert m[("backend", "availability")] == pytest.approx(7 / 9)
    assert m[("backend", "total_ms_mean")] == pytest.approx(
        (100 + 101 + 102 + 103 + 104 + 105 + 150 + 300) / 8
    )
    assert m[("backend", "total_ms_max")] == pytest.approx(300.0)
    # ttfb exists only for http servers
    assert ("backend", "ttfb_ms_mean") in m
    assert ("postgres", "ttfb_ms_mean") not in m
    # connect_ms mean only for tcp servers
    assert ("postgres", "connect_ms_mean") in m
    assert m[("postgres", "connect_ms_mean")] == pytest.approx(1.0)
    assert ("backend", "connect_ms_mean") not in m


# ---------------------------------------------------------------------------
# queue backlog_area integral


def test_queue_backlog_area_known_series(tmp_path):
    # two partitions of one topic sampled at t=0,3,6s:
    #   lag totals per bucket: 0+1=1, 2+1=3, 6+1=7
    #   trapezoid: (1+3)/2*3 + (3+7)/2*3 = 6 + 15 = 21 messages*s
    rows = []
    lag_by_part = {0: [0, 2, 6], 1: [1, 1, 1]}
    end_by_part = {0: [10, 12, 16], 1: [100, 101, 104]}
    for s in range(3):
        ts = iso_z(T0 + timedelta(seconds=3 * s))
        for part in (0, 1):
            lag = lag_by_part[part][s]
            end = end_by_part[part][s]
            rows.append(f"{ts},kyro.github.push,{part},{end},{end - lag},{lag}")
    header = "ts,topic,partition,end_offset,committed_offset,lag"
    (tmp_path / "queues_20261020.csv").write_text(
        header + "\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )

    df, *_ = run_report(tmp_path)
    m = metric_map(df, "queue")

    assert m[("kyro.github.push", "backlog_area")] == pytest.approx(21.0)
    assert m[("kyro.github.push", "lag_max")] == pytest.approx(6.0)
    # throughput = sum((last-first) per partition) / window_s
    #            = ((16-10) + (104-100)) / 6 = 10/6
    assert m[("kyro.github.push", "throughput")] == pytest.approx(10 / 6)


# ---------------------------------------------------------------------------
# pipeline service_seconds stats (db_events jsonl)


def test_pipeline_service_seconds_stats(tmp_path):
    base = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

    def ev(i, created_off, processed_off):
        created = base + timedelta(seconds=created_off)
        processed = (
            None if processed_off is None else base + timedelta(seconds=processed_off)
        )
        return {
            "ts": iso_z(base + timedelta(seconds=processed_off or created_off)),
            "id": i,
            "event_id": f"evt-{i}",
            "topic": "kyro.github.push",
            "partition": 0,
            "offset": i,
            "status": "processed" if processed else "pending",
            "created_at": created.isoformat(),
            "processed_at": processed.isoformat() if processed else None,
            "payload": {},
        }

    events = [ev(1, 0, 2), ev(2, 10, 16), ev(3, 20, 95), ev(4, 30, None)]
    (tmp_path / "db_events_20261020.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )

    df, *_ = run_report(tmp_path)
    m = metric_map(df, "pipeline")

    assert m[("overall", "events_total")] == pytest.approx(4.0)
    assert m[("overall", "events_processed")] == pytest.approx(3.0)
    # service seconds = [2, 6, 75]
    assert m[("overall", "service_seconds_mean")] == pytest.approx((2 + 6 + 75) / 3)
    assert m[("overall", "service_seconds_p50")] == pytest.approx(6.0)
    assert m[("overall", "service_seconds_max")] == pytest.approx(75.0)
    # events_per_minute: 4 events over 30s span -> mean 8/min; peak bucket=1/min
    assert m[("overall", "events_per_minute_mean")] == pytest.approx(4 / 0.5)

    # arrival burstiness: created_at 0,10,20,30 -> inter-arrivals [10,10,10]
    a = metric_map(df, "arrival_burstiness")
    assert a[("overall", "inter_arrival_mean")] == pytest.approx(10.0)
    assert a[("overall", "inter_arrival_cv")] == pytest.approx(0.0, abs=1e-12)
    assert a[("overall", "inter_arrival_max")] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# db_counts totals/deltas


def test_pipeline_db_counts_totals_and_deltas(tmp_path):
    rows = [
        "ts,commits,commit_files,files,ingestion_events",
        f"{iso_z(T0)},10,20,5,100",
        f"{iso_z(T0 + timedelta(seconds=10))},12,24,7,105",
        f"{iso_z(T0 + timedelta(seconds=20))},15,30,9,110",
    ]
    (tmp_path / "db_counts_20261020.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )

    df, *_ = run_report(tmp_path)
    m = metric_map(df, "pipeline")

    assert m[("overall", "commits_total")] == pytest.approx(15.0)
    assert m[("overall", "commits_delta")] == pytest.approx(5.0)
    assert m[("overall", "ingestion_events_total")] == pytest.approx(110.0)
    assert m[("overall", "ingestion_events_delta")] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# missing / partial / empty files


def test_missing_files_tolerance(tmp_path):
    """Empty live dir: no crash, empty CSV with header, notes list every gap."""
    df, counts, notes, csv_path, md_path = run_report(tmp_path)

    assert len(df) == 0
    assert csv_path.exists()
    assert md_path.exists()
    assert all(v == 0 for v in counts.values())
    assert any("ABSENT" in n for n in notes)
    # CSV has the exact schema header even with no rows
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "family,server,metric,value,unit,samples,window_start,window_end"
    assert "ABSENT" in md_path.read_text(encoding="utf-8")


def test_partial_and_header_only_files(tmp_path):
    """Header-only CSVs + 1-row JSONL + corrupt trailing line: no crash, notes emitted."""
    (tmp_path / "resources_20261020.csv").write_text(
        "ts,container,cpu_pct,mem_used_bytes,mem_limit_bytes,net_io_bytes,block_io_bytes,pids\n",
        encoding="utf-8",
    )
    (tmp_path / "host_20261020.csv").write_text(
        "ts,pid,name,cpu_pct,rss_bytes,cmd_hint\n"
        f'{iso_z(T0)},1234,"python.exe",1.5,1048576,"C:\\x\\.venv\\Scripts\\python.exe -m uvicorn app.main:app"\n'
        "not_a_timestamp,not_a_pid,not_a_name,not_a_cpu,not_a_rss,not_a_cmd_hint\n",
        encoding="utf-8",
    )
    # jsonl with one good line and one corrupt line (simulated partial write)
    good = {
        "ts": iso_z(T0),
        "id": 1,
        "event_id": "e1",
        "created_at": (T0).isoformat(),
        "processed_at": (T0 + timedelta(seconds=1)).isoformat(),
        "payload": {},
    }
    (tmp_path / "db_events_20261020.jsonl").write_text(
        json.dumps(good) + "\n" + '{"ts": "2026-10-20T12:00:01.0', encoding="utf-8"
    )

    df, counts, notes, csv_path, md_path = run_report(tmp_path)

    # header-only resources -> 0 rows but family skipped gracefully
    assert counts["resources"] == 0
    # host: the good uvicorn row survives, the garbage line is skipped
    hm = metric_map(df, "host_process")
    assert ("backend", "cpu_pct_mean") in hm
    assert any("dropped" in n for n in notes)
    # jsonl: corrupt line noted, good line aggregated
    pm = metric_map(df, "pipeline")
    assert pm[("overall", "events_total")] == pytest.approx(1.0)
    assert pm[("overall", "service_seconds_mean")] == pytest.approx(1.0)
    assert any("unparseable JSONL" in n for n in notes)


def test_role_derivation():
    assert (
        server_report.derive_role(
            r"backend\.venv\Scripts\python.exe -m uvicorn app.main:app"
        )
        == "backend"
    )
    assert (
        server_report.derive_role(r".venv\Scripts\python.exe -m app.worker_main")
        == "worker"
    )
    assert (
        server_report.derive_role(
            r"C:\nodejs\node.exe ...\next\dist\bin\next dev -p 3001"
        )
        == "frontend"
    )
    assert server_report.derive_role(r"...\scripts\public_router.mjs") == "router"
    assert (
        server_report.derive_role(
            r"D:\KYRO\cloudflared\cloudflared.exe tunnel --url http://127.0.0.1:8090"
        )
        == "tunnel"
    )
    assert (
        server_report.derive_role(
            r"research\.venv\Scripts\python.exe .\host_sampler.py"
        )
        == "sampler"
    )
    assert (
        server_report.derive_role(r"research\scripts\burst_generator.py --camp")
        == "sampler"
    )
    assert server_report.derive_role("something else entirely") == "other"
