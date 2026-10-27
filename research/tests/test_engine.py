"""Synthetic micro-trace tests for research.sim.engine.

ALL TASKS AND SCHEDULERS IN THIS FILE ARE SYNTHETIC TEST FIXTURES -- NOT
real trace data. Fast and hermetic: no DB, no network, no disk.
"""

from __future__ import annotations

import random
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

# research/ as importable package root (namespace pkg, no __init__)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from research.sim.engine import run_simulation  # noqa: E402
from research.sim.interface import Task, WorkerState  # noqa: E402


# ---------------------------------------------------------------------------
# Inline stub schedulers (TEST FIXTURES, not the real research/schedulers/)
# ---------------------------------------------------------------------------


class FCFSScheduler:
    """Minimal first-come-first-served: zip ready (arrival-sorted) x idle."""

    name = "fcfs_test"

    def reset(self, n_workers: int, seed: int) -> None:
        pass

    def dispatch(self, now, ready, idle):
        return [(t.task_id, w.worker_id) for t, w in zip(ready, idle)]

    def on_done(self, task, worker_id, start, finish):
        pass


class RoundRobinStub:
    """Cycles worker assignment order across dispatch rounds."""

    name = "rr_test"

    def reset(self, n_workers: int, seed: int) -> None:
        self._offset = 0

    def dispatch(self, now, ready, idle):
        n = min(len(ready), len(idle))
        pairs = []
        for i in range(n):
            worker = idle[(self._offset + i) % len(idle)]
            pairs.append((ready[i].task_id, worker.worker_id))
        self._offset = (self._offset + n) % len(idle)
        return pairs

    def on_done(self, task, worker_id, start, finish):
        pass


class RandomStub:
    """Seed-driven shuffle, for determinism testing."""

    name = "random_test"

    def reset(self, n_workers: int, seed: int) -> None:
        self._rng = random.Random(seed)

    def dispatch(self, now, ready, idle):
        order = list(range(len(ready)))
        self._rng.shuffle(order)
        return [(ready[i].task_id, w.worker_id) for i, w in zip(order, idle)]

    def on_done(self, task, worker_id, start, finish):
        pass


def T(task_id, arrival, service):
    return Task(task_id=task_id, arrival=float(arrival), service=float(service))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_queue_zero_makespan():
    """Synthetic: no tasks -> all metrics zero, no crash."""
    res = run_simulation(
        [], FCFSScheduler(), n_workers=2, speeds=[1.0, 1.0], sla_s=30.0, seed=1
    )
    assert res.n_tasks == 0
    assert res.makespan == 0.0
    assert res.mean_flow == 0.0
    assert res.p95_flow == 0.0
    assert res.sla_violations == 0
    assert res.utilization == [0.0, 0.0]
    assert res.imbalance_cv == 0.0
    assert res.per_task == []


def test_single_task():
    """Synthetic: one task, one worker -> makespan == service."""
    res = run_simulation(
        [T(1, 0.0, 10.0)],
        FCFSScheduler(),
        n_workers=1,
        speeds=[1.0],
        sla_s=30.0,
        seed=1,
    )
    assert res.n_tasks == 1
    assert res.makespan == 10.0
    assert res.mean_flow == 10.0
    assert res.p95_flow == 10.0
    assert res.sla_violations == 0
    assert res.utilization == [1.0]
    row = res.per_task[0]
    assert (
        row["task_id"],
        row["arrival"],
        row["start"],
        row["finish"],
        row["flow"],
        row["worker"],
    ) == (1, 0.0, 0.0, 10.0, 10.0, 0)


def test_fcfs_fifo_sanity_one_worker():
    """Synthetic: FCFS on 1 worker -> tasks start in arrival order, FIFO."""
    tasks = [T(1, 0.0, 5.0), T(2, 1.0, 5.0), T(3, 2.0, 5.0)]
    res = run_simulation(
        tasks, FCFSScheduler(), n_workers=1, speeds=[1.0], sla_s=30.0, seed=1
    )
    rows = {r["task_id"]: r for r in res.per_task}
    # t1: 0-5; t2 waits (arrived 1) runs 5-10; t3 runs 10-15
    assert (rows[1]["start"], rows[1]["finish"]) == (0.0, 5.0)
    assert (rows[2]["start"], rows[2]["finish"]) == (5.0, 10.0)
    assert (rows[3]["start"], rows[3]["finish"]) == (10.0, 15.0)
    assert rows[2]["flow"] == 9.0 and rows[3]["flow"] == 13.0
    assert res.makespan == 15.0
    assert res.sla_violations == 0  # flows 5, 9, 13 all <= 30


def test_all_arrivals_at_once_burst():
    """Synthetic: 6 tasks at t=0, 3 workers -> two waves, known utilizations."""
    tasks = [T(i, 0.0, float(i)) for i in range(1, 7)]  # services 1..6
    res = run_simulation(
        tasks, FCFSScheduler(), n_workers=3, speeds=[1.0, 1.0, 1.0], sla_s=30.0, seed=1
    )
    assert res.n_tasks == 6
    # t=0: tasks 1,2,3 -> workers 0,1,2 (finish 1,2,3); then t4 on w0 (1+4=5),
    # t5 on w1 (2+5=7), t6 on w2 (3+6=9)
    assert res.makespan == 9.0
    # worker busy-seconds: w0=1+4=5, w1=2+5=7, w2=3+6=9 over makespan 9
    assert res.utilization == pytest.approx([5 / 9, 7 / 9, 1.0])
    # flows: 1, 2, 3, 5, 7, 9
    assert res.mean_flow == pytest.approx(27 / 6)
    assert res.p95_flow == pytest.approx(8.5)  # linear interp on [1,2,3,5,7,9]
    assert res.sla_violations == 0


def test_worker_speed_scales_service():
    """Synthetic: service 10 on a 2.0-speed worker -> 5 seconds."""
    res = run_simulation(
        [T(1, 0.0, 10.0)],
        FCFSScheduler(),
        n_workers=1,
        speeds=[2.0],
        sla_s=30.0,
        seed=1,
    )
    assert res.makespan == 5.0
    assert res.per_task[0]["flow"] == 5.0


def test_contract_violation_wrong_count_raises():
    """Bad scheduler returning too few pairs -> ValueError."""

    class TooFew:
        name = "too_few"

        def reset(self, n_workers, seed):
            pass

        def dispatch(self, now, ready, idle):
            return [(ready[0].task_id, idle[0].worker_id)]

        def on_done(self, task, worker_id, start, finish):
            pass

    tasks = [T(1, 0.0, 1.0), T(2, 0.0, 1.0)]
    with pytest.raises(ValueError, match="expected"):
        run_simulation(
            tasks, TooFew(), n_workers=3, speeds=[1.0] * 3, sla_s=30.0, seed=1
        )


def test_contract_violation_busy_worker_raises():
    """Bad scheduler targeting a busy worker -> ValueError."""

    class HitsBusy:
        name = "hits_busy"

        def reset(self, n_workers, seed):
            pass

        def dispatch(self, now, ready, idle):
            # correct pair COUNT, but always forces worker 0 (may be busy)
            return [
                (ready[i].task_id, 0 if i == 0 else idle[i].worker_id)
                for i in range(min(len(ready), len(idle)))
            ]

        def on_done(self, task, worker_id, start, finish):
            pass

    # w0 takes task 1 for 10s at t=0; at t=1 w0 is busy, w1 idle -> the stub
    # still targets worker 0 -> contract violation
    tasks = [T(1, 0.0, 10.0), T(2, 1.0, 1.0)]
    with pytest.raises(ValueError, match="not idle"):
        run_simulation(
            tasks, HitsBusy(), n_workers=2, speeds=[1.0, 1.0], sla_s=30.0, seed=1
        )


def test_contract_violation_duplicate_task_raises():
    """Bad scheduler assigning the same task twice -> ValueError."""

    class Dup:
        name = "dup"

        def reset(self, n_workers, seed):
            pass

        def dispatch(self, now, ready, idle):
            return [
                (ready[0].task_id, idle[0].worker_id),
                (ready[0].task_id, idle[1].worker_id),
            ]

        def on_done(self, task, worker_id, start, finish):
            pass

    tasks = [T(1, 0.0, 1.0), T(2, 0.0, 1.0)]
    with pytest.raises(ValueError, match="more than once"):
        run_simulation(tasks, Dup(), n_workers=2, speeds=[1.0, 1.0], sla_s=30.0, seed=1)


def test_contract_violation_unknown_task_raises():
    """Bad scheduler inventing a task id -> ValueError."""

    class Inventor:
        name = "inventor"

        def reset(self, n_workers, seed):
            pass

        def dispatch(self, now, ready, idle):
            return [(9999, idle[0].worker_id)]

        def on_done(self, task, worker_id, start, finish):
            pass

    with pytest.raises(ValueError, match="not in the ready queue"):
        run_simulation(
            [T(1, 0.0, 1.0)], Inventor(), n_workers=1, speeds=[1.0], sla_s=30.0, seed=1
        )


def test_determinism_same_seed_same_result():
    """Synthetic: seed-driven stub, same seed -> identical SimResult."""
    tasks = [T(i, float(i % 5), 1.0 + (i % 3)) for i in range(1, 21)]
    r1 = run_simulation(
        tasks,
        RandomStub(),
        n_workers=4,
        speeds=[1.0, 0.9, 0.8, 1.1],
        sla_s=30.0,
        seed=7,
    )
    r2 = run_simulation(
        tasks,
        RandomStub(),
        n_workers=4,
        speeds=[1.0, 0.9, 0.8, 1.1],
        sla_s=30.0,
        seed=7,
    )
    d1, d2 = asdict(r1), asdict(r2)
    # extra["dispatch_cpu_s"] is wall-clock instrumentation (paper overhead
    # metric) and intentionally non-deterministic; everything else -- including
    # extra["dispatch_calls"] -- must match exactly.
    for d in (d1, d2):
        d.get("extra", {}).pop("dispatch_cpu_s", None)
    assert d1 == d2


def test_invalid_worker_config_raises():
    """Speed/workers misconfiguration -> ValueError."""
    with pytest.raises(ValueError):
        run_simulation(
            [T(1, 0.0, 1.0)],
            FCFSScheduler(),
            n_workers=0,
            speeds=[],
            sla_s=30.0,
            seed=1,
        )
    with pytest.raises(ValueError):
        run_simulation(
            [T(1, 0.0, 1.0)],
            FCFSScheduler(),
            n_workers=2,
            speeds=[1.0],
            sla_s=30.0,
            seed=1,
        )
    with pytest.raises(ValueError):
        run_simulation(
            [T(1, 0.0, 1.0)],
            FCFSScheduler(),
            n_workers=1,
            speeds=[0.0],
            sla_s=30.0,
            seed=1,
        )


def test_utilization_and_imbalance_sane():
    """Synthetic: perfectly balanced run -> cv == 0."""
    tasks = [T(1, 0.0, 10.0), T(2, 0.0, 10.0)]
    res = run_simulation(
        tasks, FCFSScheduler(), n_workers=2, speeds=[1.0, 1.0], sla_s=30.0, seed=1
    )
    assert res.utilization == pytest.approx([1.0, 1.0])
    assert res.imbalance_cv == pytest.approx(0.0)
