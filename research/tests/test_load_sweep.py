"""Synthetic micro-trace tests for research.experiments.load_sweep.

ALL TASKS AND TRACES IN THIS FILE ARE SYNTHETIC TEST FIXTURES -- NOT real
trace data. Fast and hermetic: no DB, no network, deterministic.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

# research/ as importable package root (namespace pkg, no __init__)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.experiments.load_sweep import (  # noqa: E402
    CSV_COLUMNS,
    assert_same_task_list,
    compress_tasks,
    run_sweep,
    write_csv,
)
from research.extract.load_tasks import load_tasks  # noqa: E402
from research.sim.interface import Task  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic micro-CSV fixture (TEST DATA, mirrors SCHEMA.md section 6)
# ---------------------------------------------------------------------------

_HEADER = (
    "task_id,arrival_ts,kind,repo_github_id,commits_in_event,files_touched,"
    "additions,deletions,changes,patch_bytes,service_seconds,attempts,status,"
    "experiment_label"
)
# arrivals: t=0, t=+10s, t=+30s (span 30s); the 4th row has EMPTY
# service_seconds (never processed) so load_tasks skips it -> 3 tasks
_ROWS = [
    "1,2026-10-20T12:00:00Z,live,1,1,2,3,4,7,100,10.0,1,processed,synthetic_test",
    "2,2026-10-20T12:00:10Z,live,1,1,2,3,4,7,100,5.0,1,processed,synthetic_test",
    "3,2026-10-20T12:00:30Z,backfill,2,1,2,3,4,7,100,2.5,1,processed,synthetic_test",
    "4,2026-10-20T12:01:00Z,live,2,1,2,3,4,7,100,,1,deferred,synthetic_test",
]


def _write_tasks_csv(path: Path) -> Path:
    path.write_text("\n".join([_HEADER, *_ROWS]) + "\n", encoding="utf-8")
    return path


def _load_synthetic(tmp_path: Path) -> list[Task]:
    return load_tasks(_write_tasks_csv(tmp_path / "tasks.csv"))


def T(task_id: int, arrival: float, service: float) -> Task:
    return Task(task_id=task_id, arrival=float(arrival), service=float(service))


# ---------------------------------------------------------------------------
# compress_tasks
# ---------------------------------------------------------------------------


def test_factor_1_keeps_arrivals_identical(tmp_path):
    """factor 1 == the original real trace: arrivals and services untouched."""
    tasks = _load_synthetic(tmp_path)
    assert [t.arrival for t in tasks] == [0.0, 10.0, 30.0]

    out = compress_tasks(tasks, 1)
    assert len(out) == len(tasks)
    assert [t.arrival for t in out] == [t.arrival for t in tasks]
    assert [t.service for t in out] == [t.service for t in tasks]
    assert [t.task_id for t in out] == [t.task_id for t in tasks]
    # input list must not be mutated
    assert [t.arrival for t in tasks] == [0.0, 10.0, 30.0]


def test_factor_4_divides_arrival_span_by_4_service_unchanged(tmp_path):
    """factor 4: arrival span /4 exactly, service demands unchanged."""
    tasks = _load_synthetic(tmp_path)
    span_in = max(t.arrival for t in tasks) - min(t.arrival for t in tasks)
    assert span_in == 30.0

    out = compress_tasks(tasks, 4)
    span_out = max(t.arrival for t in out) - min(t.arrival for t in out)
    assert span_out == pytest.approx(span_in / 4)  # 7.5s
    assert [t.arrival for t in out] == [0.0, 2.5, 7.5]
    assert [t.service for t in out] == [10.0, 5.0, 2.5]  # unchanged
    assert [t.task_id for t in out] == [1, 2, 3]


def test_compress_rejects_non_positive_factor():
    with pytest.raises(ValueError, match="> 0"):
        compress_tasks([T(1, 0.0, 1.0)], 0)
    with pytest.raises(ValueError, match="> 0"):
        compress_tasks([T(1, 0.0, 1.0)], -2)


# ---------------------------------------------------------------------------
# fairness guard
# ---------------------------------------------------------------------------


def test_fairness_assert_passes_on_identical_list(tmp_path):
    tasks = _load_synthetic(tmp_path)
    derived = compress_tasks(tasks, 2)
    assert_same_task_list(derived, compress_tasks(tasks, 2))  # no raise


def test_fairness_assert_triggers_on_short_manipulated_list(tmp_path):
    """Dropping one task must trip the guard immediately."""
    tasks = _load_synthetic(tmp_path)
    derived = compress_tasks(tasks, 2)
    manipulated = derived[:-1]  # one task silently removed
    with pytest.raises(AssertionError, match="FAIRNESS VIOLATION"):
        assert_same_task_list(derived, manipulated)


def test_fairness_assert_triggers_on_same_length_manipulated_list(tmp_path):
    """Same length but altered arrival/service must also trip the guard."""
    tasks = _load_synthetic(tmp_path)
    derived = compress_tasks(tasks, 2)

    rearrived = list(derived)
    rearrived[1] = T(
        rearrived[1].task_id, rearrived[1].arrival + 0.001, rearrived[1].service
    )
    with pytest.raises(AssertionError, match="FAIRNESS VIOLATION"):
        assert_same_task_list(derived, rearrived)

    reserviced = list(derived)
    reserviced[2] = T(
        reserviced[2].task_id, reserviced[2].arrival, reserviced[2].service + 1.0
    )
    with pytest.raises(AssertionError, match="FAIRNESS VIOLATION"):
        assert_same_task_list(derived, reserviced)


# ---------------------------------------------------------------------------
# end-to-end sweep: exact CSV schema and row count
# ---------------------------------------------------------------------------


def test_output_csv_exact_columns_and_row_count(tmp_path):
    """CSV has EXACTLY the 10 downstream-parsed columns; rows = f x a x s."""
    tasks = _load_synthetic(tmp_path)
    factors = [1, 4]
    algorithms = ["fcfs", "round_robin"]
    seeds = 2

    rows = run_sweep(
        tasks,
        factors,
        algorithms,
        seeds,
        n_workers=2,
        speeds=[1.0, 1.0],
        sla_s=30.0,
    )
    assert len(rows) == len(factors) * len(algorithms) * seeds

    out = tmp_path / "load_sweep.csv"
    write_csv(rows, out)
    with out.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        data = list(reader)
    assert header == CSV_COLUMNS
    assert len(header) == 10
    assert len(data) == len(factors) * len(algorithms) * seeds

    # every algorithm saw the identical n_requests per factor (fairness)
    for factor in factors:
        counts = {int(r[3]) for r in data if float(r[0]) == factor}
        assert counts == {len(tasks)}


def test_sweep_is_deterministic(tmp_path):
    """Same synthetic input -> identical rows (paper reproducibility)."""
    tasks = _load_synthetic(tmp_path)
    kwargs = dict(
        factors=[1, 2],
        algorithms=["fcfs"],
        seeds=2,
        n_workers=2,
        speeds=[1.0, 0.9],
        sla_s=30.0,
    )
    assert run_sweep(tasks, **kwargs) == run_sweep(tasks, **kwargs)
