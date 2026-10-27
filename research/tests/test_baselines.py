"""Contract, fast-path, determinism & budget tests for the GA and PSO baselines.

Synthetic micro-scenarios (clearly test data, not research data) exercising the
frozen dispatch contract in research/sim/interface.py. The new baselines must
behave exactly like dragonfly on the shared contract surface so the study
comparison is apples-to-apples.
"""

from __future__ import annotations

import random
import time

import pytest

from research.schedulers import get_scheduler
from research.sim.interface import Task, WorkerState

BASELINES = ("ga", "pso")


def mk_tasks(specs: list[tuple[int, float, float]]) -> list[Task]:
    """(task_id, arrival, service) -> arrival-sorted Task list."""
    return [
        Task(task_id=i, arrival=a, service=s)
        for i, a, s in sorted(specs, key=lambda x: x[1])
    ]


def mk_idle(ids_and_speeds: list[tuple[int, float]]) -> list[WorkerState]:
    return [WorkerState(worker_id=i, speed=s) for i, s in ids_and_speeds]


def assert_valid(ready, idle, pairs):
    expected = min(len(ready), len(idle))
    assert len(pairs) == expected, f"expected {expected} pairs, got {len(pairs)}"
    ready_ids = {t.task_id for t in ready}
    idle_ids = {w.worker_id for w in idle}
    tasks = [p[0] for p in pairs]
    workers = [p[1] for p in pairs]
    assert len(set(tasks)) == len(tasks), "task assigned twice"
    assert len(set(workers)) == len(workers), "worker assigned twice"
    assert set(tasks) <= ready_ids, "assigned a non-ready task"
    assert set(workers) <= idle_ids, "assigned a busy/non-idle worker"


# ------------------------------------------------------------------ registry


@pytest.mark.parametrize("name", BASELINES)
def test_registry_returns_baseline_instances(name):
    sched = get_scheduler(name, seed=0)
    assert sched.name == name
    sched.reset(2, seed=0)
    pairs = sched.dispatch(
        0.0, mk_tasks([(1, 0.0, 2.0)]), mk_idle([(0, 1.0), (1, 1.0)])
    )
    assert len(pairs) == 1


def test_registry_unknown_name_lists_valid_names():
    with pytest.raises(ValueError) as exc:
        get_scheduler("definitely-not-an-algo")
    msg = str(exc.value)
    for valid in ("dragonfly", "fcfs", "round_robin", "ga", "pso"):
        assert valid in msg, f"error message should list {valid!r}"


# --------------------------------------------------------------- fast paths


@pytest.mark.parametrize("name", BASELINES)
def test_single_task_goes_to_fastest_worker(name):
    sched = get_scheduler(name)
    sched.reset(3, seed=1)
    ready = mk_tasks([(7, 0.0, 10.0)])
    idle = mk_idle([(0, 0.8), (1, 1.5), (2, 1.0)])  # deliberately unsorted
    pairs = sched.dispatch(0.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert pairs[0] == (7, 1), "single ready task should go to fastest worker"


@pytest.mark.parametrize("name", BASELINES)
def test_single_worker_gets_smallest_service_task(name):
    sched = get_scheduler(name)
    sched.reset(3, seed=1)
    ready = mk_tasks([(1, 0.0, 50.0), (2, 0.0, 5.0), (3, 0.0, 20.0)])
    idle = mk_idle([(0, 1.0)])
    pairs = sched.dispatch(0.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert pairs[0][0] == 2, (
        "one idle worker should take the smallest task (SPT optimum)"
    )


# ------------------------------------------------------------ burst window


@pytest.mark.parametrize("name", BASELINES)
def test_burst_window_valid_pairing(name):
    sched = get_scheduler(name)
    sched.reset(4, seed=1)
    rng = random.Random(99)
    ready = mk_tasks([(i, i * 0.5, rng.uniform(1, 30)) for i in range(10)])
    idle = mk_idle([(0, 0.7), (1, 1.0), (2, 1.1), (3, 0.9)])
    pairs = sched.dispatch(10.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert len(pairs) == 4


# ------------------------------------------------------------ determinism


@pytest.mark.parametrize("name", BASELINES)
def test_deterministic_same_seed(name):
    rng = random.Random(5)
    specs = [(i, i * 0.3, rng.uniform(1, 15)) for i in range(8)]
    idle = mk_idle([(0, 1.0), (1, 0.9), (2, 1.2)])
    runs = []
    for _ in range(2):
        sched = get_scheduler(name)
        sched.reset(3, seed=42)
        runs.append(sched.dispatch(5.0, mk_tasks(specs), idle))
    assert runs[0] == runs[1], f"{name} must be deterministic for a fixed seed"


@pytest.mark.parametrize("name", BASELINES)
@pytest.mark.parametrize("seed", [0, 1, 7])
def test_contract_fuzz(name, seed):
    """Randomized scenarios must always satisfy the dispatch contract."""
    rng = random.Random(seed * 131 + hash(name) % 1000)
    sched = get_scheduler(name, seed)
    for trial in range(30):
        n_workers = rng.randint(1, 5)
        sched.reset(n_workers, seed)
        t0 = rng.uniform(0, 100)
        ready = mk_tasks(
            [
                (i, t0 + i * rng.uniform(0, 2), rng.uniform(0.1, 25))
                for i in range(rng.randint(0, 15))
            ]
        )
        idle_ids = rng.sample(range(n_workers), rng.randint(0, n_workers))
        idle = mk_idle([(i, rng.uniform(0.5, 1.5)) for i in idle_ids])
        if ready and idle:
            pairs = sched.dispatch(t0 + 30, ready, idle)
            assert_valid(ready, idle, pairs)
        else:
            assert sched.dispatch(t0 + 30, ready, idle) == []


# ------------------------------------------------------------ budget guard


@pytest.mark.parametrize("name", BASELINES)
def test_dispatch_within_time_budget(name):
    """One dispatch on 12 ready / 6 idle must finish well under the budget."""
    sched = get_scheduler(name)
    sched.reset(6, seed=3)
    rng = random.Random(7)
    ready = mk_tasks([(i, i * 0.1, rng.uniform(1, 20)) for i in range(12)])
    idle = mk_idle([(i, rng.uniform(0.5, 1.5)) for i in range(6)])
    t0 = time.perf_counter()
    pairs = sched.dispatch(0.0, ready, idle)
    elapsed = time.perf_counter() - t0
    assert_valid(ready, idle, pairs)
    assert elapsed < 2.0, f"{name} dispatch took {elapsed:.3f}s (> 2.0s)"
