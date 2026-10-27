"""Discrete-event simulator for the KYRO workload trace.

Implements EXACTLY the dispatch model documented in research/sim/interface.py
(FROZEN contract -- this module only consumes it):

  * Single global queue, non-preemptive.
  * Sim clock advances from event to event: at each step either the next
    task arrives or the next worker frees (whichever is earlier).
  * Whenever >= 1 worker is idle AND >= 1 task is ready, the scheduler's
    dispatch(now, ready, idle) is called and the assigned pairs start
    immediately (start = now). `ready` is arrival-sorted (oldest first).
  * Worker j finishes its task at start + task.service / worker.speed.
  * scheduler.on_done is fed on every completion.

run_simulation(tasks, scheduler, n_workers, speeds, sla_s, seed) -> SimResult
is deterministic for a fixed seed (the engine itself holds no randomness;
the seed is handed to scheduler.reset).

CLI (single scheduler on a trace CSV):
  python -m research.sim.engine --tasks research/data/trace/tasks.csv \
      --scheduler round_robin --workers 4 --speeds 1.0,0.9,0.8,1.1 \
      --sla 30 --seed 1 --out research/data/trace/run_round_robin_seed1.json
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .interface import SimResult, Task, WorkerState

_INF = float("inf")


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile (numpy default 'linear' method)."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[int(pos)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _validate_dispatch(
    ready: list[Task], idle: list[WorkerState], pairs, task_by_id: dict[int, Task]
) -> None:
    """Enforce the interface contract on what the scheduler returned."""
    expected = min(len(ready), len(idle))
    if not isinstance(pairs, (list, tuple)):
        raise ValueError(
            f"scheduler.dispatch must return a list of (task_id, worker_id) "
            f"pairs, got {type(pairs).__name__}"
        )
    if len(pairs) != expected:
        raise ValueError(
            f"scheduler.dispatch returned {len(pairs)} pairs, expected "
            f"exactly {expected} = min(len(ready)={len(ready)}, "
            f"len(idle)={len(idle)})"
        )
    ready_ids = {t.task_id for t in ready}
    idle_ids = {w.worker_id for w in idle}
    seen_tasks: set[int] = set()
    seen_workers: set[int] = set()
    for pair in pairs:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            raise ValueError(
                f"scheduler.dispatch returned a malformed pair {pair!r}; "
                f"expected (task_id, worker_id)"
            )
        task_id, worker_id = pair
        if task_id not in ready_ids:
            raise ValueError(
                f"scheduler.dispatch assigned task_id={task_id} which is not "
                f"in the ready queue (ready ids: {sorted(ready_ids)})"
            )
        if task_id in seen_tasks:
            raise ValueError(
                f"scheduler.dispatch assigned task_id={task_id} more than once"
            )
        if worker_id not in idle_ids:
            raise ValueError(
                f"scheduler.dispatch assigned worker_id={worker_id} which is "
                f"not idle (idle ids: {sorted(idle_ids)})"
            )
        if worker_id in seen_workers:
            raise ValueError(
                f"scheduler.dispatch assigned worker_id={worker_id} more than once"
            )
        seen_tasks.add(task_id)
        seen_workers.add(worker_id)


def run_simulation(
    tasks: list[Task],
    scheduler,
    n_workers: int,
    speeds: list[float],
    sla_s: float,
    seed: int,
) -> SimResult:
    """Run one deterministic discrete-event simulation. See module docstring."""
    if n_workers <= 0:
        raise ValueError(f"n_workers must be >= 1, got {n_workers}")
    if len(speeds) != n_workers:
        raise ValueError(
            f"len(speeds)={len(speeds)} does not match n_workers={n_workers}"
        )
    if any(s <= 0 for s in speeds):
        raise ValueError(f"all worker speeds must be > 0, got {speeds}")

    workers = [
        WorkerState(worker_id=i, speed=float(speeds[i])) for i in range(n_workers)
    ]
    for w in workers:
        w.busy_until = -_INF  # all idle at time -inf (default 0.0 would
        #                        exclude workers from negative-arrival traces)

    scheduler.reset(n_workers, seed)

    ordered = sorted(tasks, key=lambda t: (t.arrival, t.task_id))
    task_by_id = {t.task_id: t for t in ordered}
    if len(task_by_id) != len(ordered):
        raise ValueError("duplicate task_id values in the task list")

    n = len(ordered)
    idx = 0  # next arrival index into `ordered`
    now = ordered[0].arrival if ordered else 0.0
    ready: list[Task] = []  # arrival order == admission order
    # heap entries: (finish, seq, task, worker); seq breaks ties deterministically
    running: list[tuple[float, int, Task, WorkerState]] = []
    seq = 0
    start_of: dict[int, float] = {}
    finish_of: dict[int, float] = {}
    worker_of: dict[int, int] = {}
    busy_time = [0.0] * n_workers
    # scheduler overhead: wall time spent inside dispatch() only (paper metric)
    dispatch_cpu_s = 0.0
    dispatch_calls = 0

    while True:
        # 1) complete everything due at `now` (frees workers, feeds on_done)
        while running and running[0][0] <= now:
            finish, _, task, w = heapq.heappop(running)
            w.busy_until = finish
            finish_of[task.task_id] = finish
            busy_time[w.worker_id] += finish - start_of[task.task_id]
            scheduler.on_done(task, w.worker_id, start_of[task.task_id], finish)

        # 2) admit every arrival due at `now`
        while idx < n and ordered[idx].arrival <= now:
            ready.append(ordered[idx])
            idx += 1

        # 3) dispatch while the contract allows it
        idle = [w for w in workers if w.busy_until <= now]
        if ready and idle:
            ready_view = list(ready)  # arrival-sorted, oldest first
            _t0 = time.perf_counter()
            pairs = scheduler.dispatch(now, ready_view, idle)
            dispatch_cpu_s += time.perf_counter() - _t0
            dispatch_calls += 1
            _validate_dispatch(ready_view, idle, pairs, task_by_id)
            idle_by_id = {w.worker_id: w for w in idle}
            ready_by_id = {t.task_id: t for t in ready}
            for task_id, worker_id in pairs:
                task = ready_by_id.pop(task_id)
                ready.remove(task)
                w = idle_by_id[worker_id]
                finish = now + task.service / w.speed
                start_of[task.task_id] = now
                worker_of[task.task_id] = worker_id
                w.busy_until = finish
                w.assigned += 1
                seq += 1
                heapq.heappush(running, (finish, seq, task, w))
            continue  # zero-service tasks free at `now`: re-loop immediately

        # 4) advance the clock to the earlier of next arrival / next completion
        next_arrival = ordered[idx].arrival if idx < n else _INF
        next_finish = running[0][0] if running else _INF
        if next_arrival == _INF and next_finish == _INF:
            break
        now = min(next_arrival, next_finish)

    # ---- honest aggregation -------------------------------------------------
    if not ordered:
        return SimResult(
            scheduler=getattr(scheduler, "name", type(scheduler).__name__),
            seed=seed,
            n_tasks=0,
            n_workers=n_workers,
            makespan=0.0,
            mean_flow=0.0,
            p95_flow=0.0,
            sla_violations=0,
            sla_s=sla_s,
            utilization=[0.0] * n_workers,
            imbalance_cv=0.0,
            per_task=[],
        )

    first_arrival = ordered[0].arrival
    last_finish = max(finish_of.values())
    makespan = last_finish - first_arrival
    flows = sorted(finish_of[t.task_id] - t.arrival for t in ordered)
    mean_flow = sum(flows) / len(flows)
    p95_flow = _percentile(flows, 0.95)
    sla_violations = sum(1 for f in flows if f > sla_s)

    utilization = [
        (busy_time[j] / makespan) if makespan > 0 else 0.0 for j in range(n_workers)
    ]
    util_mean = sum(utilization) / n_workers
    if util_mean > 0:
        var = sum((u - util_mean) ** 2 for u in utilization) / n_workers
        imbalance_cv = math.sqrt(var) / util_mean
    else:
        imbalance_cv = 0.0

    per_task = [
        {
            "task_id": t.task_id,
            "arrival": t.arrival,
            "start": start_of[t.task_id],
            "finish": finish_of[t.task_id],
            "flow": finish_of[t.task_id] - t.arrival,
            "worker": worker_of[t.task_id],
        }
        for t in ordered
    ]

    return SimResult(
        scheduler=getattr(scheduler, "name", type(scheduler).__name__),
        seed=seed,
        n_tasks=len(ordered),
        n_workers=n_workers,
        makespan=makespan,
        mean_flow=mean_flow,
        p95_flow=p95_flow,
        sla_violations=sla_violations,
        sla_s=sla_s,
        utilization=utilization,
        imbalance_cv=imbalance_cv,
        per_task=per_task,
        extra={
            "dispatch_cpu_s": round(dispatch_cpu_s, 6),
            "dispatch_calls": dispatch_calls,
        },
    )


def _ensure_project_root_on_path() -> Path:
    """research/ as importable package root (namespace pkg, no __init__)."""
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def main() -> int:
    _ensure_project_root_on_path()
    from research.extract.load_tasks import load_tasks
    from research.schedulers import get_scheduler  # written by the schedulers agent

    ap = argparse.ArgumentParser(description=__doc__)
    # optional subcommand token so BOTH forms work:
    #   python -m research.sim.engine --tasks ... (documented form)
    #   python -m research.sim.engine run --tasks ...
    ap.add_argument("command", nargs="?", default="run", choices=["run"])
    ap.add_argument("--tasks", required=True, help="trace tasks.csv path")
    ap.add_argument(
        "--scheduler",
        required=True,
        help="scheduler name, e.g. dragonfly | fcfs | round_robin",
    )
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--speeds",
        default="1.0,1.0,1.0,1.0",
        help="comma-separated per-worker speed factors",
    )
    ap.add_argument("--sla", type=float, default=30.0, help="SLA seconds on flow time")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True, help="output SimResult JSON path")
    args = ap.parse_args()

    speeds = [float(s) for s in args.speeds.split(",")]
    if len(speeds) != args.workers:
        print(f"ERROR: {len(speeds)} speeds for {args.workers} workers")
        return 2

    tasks = load_tasks(args.tasks)
    if not tasks:
        print(f"ERROR: no tasks loaded from {args.tasks} (run build_trace.py first)")
        return 2

    scheduler = get_scheduler(args.scheduler, args.seed)
    result = run_simulation(tasks, scheduler, args.workers, speeds, args.sla, args.seed)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2)

    print(
        f"{result.scheduler} seed={result.seed} tasks={result.n_tasks} "
        f"makespan={result.makespan:.1f}s mean_flow={result.mean_flow:.1f}s "
        f"p95={result.p95_flow:.1f}s sla_viol={result.sla_violations} "
        f"cv={result.imbalance_cv:.3f}"
    )
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
