"""Round Robin: rotating worker pointer over arrival-ordered tasks.

Tasks are always taken oldest-first (FIFO within the queue); the worker slot
rotates cyclically across dispatch calls, skipping workers that are busy.
Deterministic policy - the seed only sets the starting rotation offset, so
reported variance across seeds for this baseline is honestly ~0.
"""

from __future__ import annotations

from research.sim.interface import Task, WorkerState


class RoundRobinScheduler:
    """Cyclic worker rotation over the FIFO queue."""

    name = "round_robin"

    def __init__(self) -> None:
        self.n_workers = 0
        self._cursor = 0
        self.stats: dict = {"dispatch_count": 0}

    def reset(self, n_workers: int, seed: int) -> None:
        self.n_workers = n_workers
        # seed sets only the rotation start offset (deterministic policy)
        self._cursor = (seed % n_workers) if n_workers > 0 else 0
        self.stats = {"dispatch_count": 0}

    def dispatch(
        self, now: float, ready: list[Task], idle: list[WorkerState]
    ) -> list[tuple[int, int]]:
        if not ready or not idle:
            return []
        need = min(len(ready), len(idle))
        idle_ids = {w.worker_id for w in idle}
        # rotation space must cover every idle id even if ids are not 0..n-1
        space = max(self.n_workers, max(idle_ids, default=-1) + 1)
        if self._cursor >= space:
            self._cursor = 0

        # walk cyclically from the cursor, picking idle workers
        order: list[int] = []
        for i in range(space):
            wid = (self._cursor + i) % space
            if wid in idle_ids:
                order.append(wid)
                if len(order) == need:
                    break
        # pathological fallback: idle ids outside the rotation space
        if len(order) < need:
            for wid in sorted(idle_ids):
                if wid not in order:
                    order.append(wid)
                    if len(order) == need:
                        break

        self.stats["dispatch_count"] += 1
        # advance cursor past the last assigned worker -> next call rotates on
        if order:
            self._cursor = (order[-1] + 1) % space
        return [(ready[i].task_id, order[i]) for i in range(need)]

    def on_done(self, task: Task, worker_id: int, start: float, finish: float) -> None:
        return None
