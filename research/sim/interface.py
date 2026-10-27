"""Shared contract between the simulator (research/sim) and schedulers (research/schedulers).

This module is FROZEN. Both sides import it; neither redefines these types.

Model (single global queue, non-preemptive, batch dispatch):
  * Tasks arrive at `arrival` (seconds since trace start), each with a
    reference `service` time (real measured seconds on a speed-1.0 worker).
  * On every dispatch point the simulator hands the scheduler the current
    `ready` tasks and the `idle` workers and expects a one-to-one pairing of
    exactly min(len(ready), len(idle)) distinct tasks to distinct idle workers.
  * Worker j executes its task in service / worker.speed (speed > 0).
  * A scheduler MUST NOT assign a task twice, must only use idle workers,
    and must be deterministic given its seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Task:
    task_id: int
    arrival: float  # seconds since trace start
    service: float  # reference service time, seconds (speed 1.0)
    size_files: int = 0
    size_bytes: int = 0
    kind: str = "push"  # push | backfill | other
    meta: dict = field(default_factory=dict)  # extra features (use = must be flagged)


@dataclass
class WorkerState:
    worker_id: int
    speed: float  # > 0; service time divides by speed
    busy_until: float = 0.0  # sim clock time when this worker frees
    assigned: int = 0  # tasks completed/assigned so far (informational)


@runtime_checkable
class Scheduler(Protocol):
    """A dispatch policy. Implementations live in research/schedulers/."""

    name: str

    def reset(self, n_workers: int, seed: int) -> None:
        """Re-initialize RNG and internal state for a run. Called once per run."""

    def dispatch(
        self,
        now: float,
        ready: list[Task],
        idle: list[WorkerState],
    ) -> list[tuple[int, int]]:
        """Return [(task_id, worker_id), ...] pairing exactly
        min(len(ready), len(idle)) distinct ready tasks to distinct idle
        workers. `ready` is sorted by arrival (oldest first). Implementations
        may look ahead into `ready` but only assign tasks from it.
        """

    def on_done(self, task: Task, worker_id: int, start: float, finish: float) -> None:
        """Optional feedback hook (online learners). Default: ignore."""


@dataclass
class SimResult:
    """Everything the analysis layer needs from one run."""

    scheduler: str
    seed: int
    n_tasks: int
    n_workers: int
    makespan: float  # last finish - first arrival
    mean_flow: float  # mean(finish - arrival)
    p95_flow: float
    sla_violations: int  # flow > sla_s
    sla_s: float
    utilization: list[float]  # per-worker busy fraction
    imbalance_cv: float  # coefficient of variation of utilization
    per_task: list[dict]  # rows: task_id, arrival, start, finish, flow, worker
    extra: dict = field(default_factory=dict)  # algo metadata (convergence etc.)
