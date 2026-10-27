"""First-Come-First-Serve: the classic strict-arrival-order baseline.

Pairs the oldest ready tasks with idle workers in ascending worker-id order.
Deterministic, zero variance across seeds - the reference every reviewer
expects in a scheduling comparison.
"""

from __future__ import annotations

from research.sim.interface import Task, WorkerState


class FcfsScheduler:
    """Strict arrival-order pairing (FCFS/FIFO dispatch)."""

    name = "fcfs"

    def __init__(self) -> None:
        self.n_workers = 0
        self.stats: dict = {"dispatch_count": 0}

    def reset(self, n_workers: int, seed: int) -> None:
        # FCFS has no randomness; seed intentionally unused (variance = 0).
        self.n_workers = n_workers
        self.stats = {"dispatch_count": 0}

    def dispatch(
        self, now: float, ready: list[Task], idle: list[WorkerState]
    ) -> list[tuple[int, int]]:
        if not ready or not idle:
            return []
        workers = sorted(idle, key=lambda w: w.worker_id)
        k = min(len(ready), len(idle))
        self.stats["dispatch_count"] += 1
        return [(ready[i].task_id, workers[i].worker_id) for i in range(k)]

    def on_done(self, task: Task, worker_id: int, start: float, finish: float) -> None:
        return None
