"""Contract & behaviour tests for the three studied schedulers.

Fixtures are SYNTHETIC micro-scenarios (clearly test data, not research data)
built to exercise the frozen dispatch contract in research/sim/interface.py.
"""

from __future__ import annotations

import random

import pytest

from research.schedulers import ALGORITHMS, get_scheduler
from research.sim.interface import Task, WorkerState


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


# --------------------------------------------------------------------- fcfs


def test_fcfs_oldest_first_to_lowest_ids():
    sched = get_scheduler("fcfs")
    sched.reset(2, seed=0)
    ready = mk_tasks(
        [(10, 0.0, 5.0), (11, 0.1, 5.0), (12, 0.2, 5.0), (13, 0.3, 5.0), (14, 0.4, 5.0)]
    )
    idle = mk_idle([(3, 1.0), (1, 1.0)])  # deliberately unsorted
    pairs = sched.dispatch(0.5, ready, idle)
    assert_valid(ready, idle, pairs)
    # oldest two tasks -> the two lowest worker ids
    assert pairs == [(10, 1), (11, 3)]


# --------------------------------------------------------------- round robin


def test_round_robin_rotates_across_calls():
    sched = get_scheduler("round_robin")
    sched.reset(2, seed=0)
    idle = mk_idle([(0, 1.0), (1, 1.0)])
    r1 = mk_tasks([(1, 0.0, 3.0)])
    p1 = sched.dispatch(0.0, r1, idle)
    r2 = mk_tasks([(2, 0.1, 3.0)])
    p2 = sched.dispatch(0.1, r2, idle)
    assert p1 != p2, "rotation did not advance the worker pointer"
    # third call wraps around back to the first worker
    p3 = sched.dispatch(0.2, mk_tasks([(3, 0.2, 3.0)]), idle)
    assert p3[0][1] == p1[0][1]


def test_round_robin_skips_busy_workers():
    sched = get_scheduler("round_robin")
    sched.reset(4, seed=0)
    ready = mk_tasks([(1, 0.0, 3.0), (2, 0.0, 3.0)])
    idle = mk_idle([(1, 1.0), (3, 1.0)])  # 0 and 2 are busy
    pairs = sched.dispatch(0.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert {p[1] for p in pairs} == {1, 3}


# --------------------------------------------------------------- dragonfly


def test_dragonfly_single_task_to_fastest_worker():
    sched = get_scheduler("dragonfly")
    sched.reset(3, seed=1)
    ready = mk_tasks([(7, 0.0, 10.0)])
    idle = mk_idle([(0, 0.8), (1, 1.5), (2, 1.0)])
    pairs = sched.dispatch(0.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert pairs[0] == (7, 1), "single ready task should go to fastest worker"


def test_dragonfly_single_worker_gets_shortest_task():
    sched = get_scheduler("dragonfly")
    sched.reset(3, seed=1)
    ready = mk_tasks([(1, 0.0, 50.0), (2, 0.0, 5.0), (3, 0.0, 20.0)])
    idle = mk_idle([(0, 1.0)])
    pairs = sched.dispatch(0.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert pairs[0][0] == 2, (
        "one idle worker should take the smallest task (SPT optimum)"
    )


def test_dragonfly_burst_window_valid_pairing():
    sched = get_scheduler("dragonfly")
    sched.reset(4, seed=1)
    rng = random.Random(99)
    ready = mk_tasks([(i, i * 0.5, rng.uniform(1, 30)) for i in range(10)])
    idle = mk_idle([(0, 0.7), (1, 1.0), (2, 1.1), (3, 0.9)])
    pairs = sched.dispatch(10.0, ready, idle)
    assert_valid(ready, idle, pairs)
    assert len(pairs) == 4


def test_dragonfly_deterministic_same_seed():
    rng = random.Random(5)
    specs = [(i, i * 0.3, rng.uniform(1, 15)) for i in range(8)]
    runs = []
    for _ in range(2):
        sched = get_scheduler("dragonfly")
        sched.reset(3, seed=42)
        runs.append(
            sched.dispatch(
                5.0, mk_tasks(specs), mk_idle([(0, 1.0), (1, 0.9), (2, 1.2)])
            )
        )
    assert runs[0] == runs[1], "dragonfly must be deterministic for a fixed seed"


# ------------------------------------------------------------------ registry


def test_registry_builds_all_algorithms():
    for name in ALGORITHMS:
        s = get_scheduler(name, seed=0)
        s.reset(2, seed=0)
        pairs = s.dispatch(
            0.0, mk_tasks([(1, 0.0, 2.0)]), mk_idle([(0, 1.0), (1, 1.0)])
        )
        assert len(pairs) == 1


def test_registry_unknown_name_raises():
    with pytest.raises(ValueError, match="dragonfly"):
        get_scheduler("definitely-not-an-algo")


# ----------------------------------------------------------- contract fuzz


@pytest.mark.parametrize("name", ALGORITHMS)
@pytest.mark.parametrize("seed", [0, 1, 7])
def test_contract_fuzz(name, seed):
    """Randomized scenarios must always satisfy the dispatch contract."""
    rng = random.Random(seed * 131 + hash(name) % 1000)
    sched = get_scheduler(name, seed)
    for trial in range(40):
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
