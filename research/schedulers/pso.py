"""Particle Swarm Optimization scheduler (Kennedy & Eberhart 1995) baseline.

Second evolutionary baseline for the DA scheduler: identical window
sub-problem, encoding, decode and fitness - only the search dynamics differ,
so any quality difference is attributable to the metaheuristic.

  * A candidate solution (particle position) is a continuous matrix of shape
    (n_window, n_idle) in [0, 1] - the SAME encoding as dragonfly; DECODE and
    the per-window row repair are imported from DragonflyScheduler so the
    mapping to (task_id, worker_id) pairs is identical by construction.
  * FITNESS is also reused from DragonflyScheduler by reference:
        f = 0.5 * max(completion) + 0.3 * mean(completion)
          + 0.2 * std(per-worker assigned load)
    with completion_i = now + service_i / speed(worker_i); lower is better.
  * SWARM update per dispatch (fixed compute budget matching DA's P=12, I=8):
        v <- 0.72 * v + 1.49 * r1 * (pbest - x) + 1.49 * r2 * (gbest - x)
        x <- clip(x + v, 0, 1)
    with per-cell r1, r2 drawn from the seeded rng and velocities clamped to
    [-1, 1]; pbest is each particle's personal best, gbest the swarm-wide best
    across all iterations (ties broken by lowest particle index).
  * TRIVIAL CASES use the exact optimum of the same fitness: one ready task
    -> fastest idle worker; one idle worker -> smallest-service task (SPT).

Deterministic: a single stdlib random.Random(seed) drives initialization and
every velocity/position draw; the same seed replays identical dispatches.
Per-dispatch stats accumulate in self.stats (same pattern as dragonfly).
"""

from __future__ import annotations

import random

from research.sim.interface import Task, WorkerState

from .dragonfly import (
    FIT_W_IMBALANCE,
    FIT_W_MAX,
    FIT_W_MEAN,
    WINDOW_MAX,
    DragonflyScheduler,
)

# PSO behaviour parameters (documented module constants; Clerc's constriction-
# like values c1 = c2 = 1.49, w = 0.72 are the canonical stable configuration)
POPULATION = 12  # particles per dispatch (matches DA population budget)
ITERATIONS = 8  # swarm iterations per dispatch (matches DA iteration budget)
INERTIA = 0.72  # w: velocity inertia
C1 = 1.49  # cognitive: pull toward personal best
C2 = 1.49  # social: pull toward global best
V_MAX = 1.0  # per-cell velocity clamp bound (+-1)

# fitness weights imported for parity with DA; evaluation itself is delegated
# to DragonflyScheduler._fitness so the objective is identical by construction
OBJECTIVE_WEIGHTS = (FIT_W_MAX, FIT_W_MEAN, FIT_W_IMBALANCE)


class PsoScheduler:
    """PSO-based dispatch: swarm-optimized task-to-worker assignment."""

    name = "pso"

    def __init__(self) -> None:
        self.n_workers = 0
        self._rng = random.Random(0)
        self._da = DragonflyScheduler()  # fitness oracle (reused by reference)
        self.stats: dict = {
            "dispatch_count": 0,
            "fast_paths": 0,
            "windows": [],
            "iterations_run": 0,
        }

    def reset(self, n_workers: int, seed: int) -> None:
        """Re-seed the RNG and clear per-run stats (once per run)."""
        self.n_workers = n_workers
        self._rng = random.Random(seed)
        self.stats = {
            "dispatch_count": 0,
            "fast_paths": 0,
            "windows": [],
            "iterations_run": 0,
        }

    # ------------------------------------------------------------------ decode
    @staticmethod
    def _decode(pos: list[list[float]], n_tasks: int, n_idle: int) -> list[int]:
        """Row argmax per task slot; delegated to DA so decode never diverges."""
        return DragonflyScheduler._decode(pos, n_tasks, n_idle)

    def _fitness(
        self,
        assign: list[int],
        window: list[Task],
        idle_sorted: list[WorkerState],
        now: float,
    ) -> float:
        """Local-simulation fitness delegated to DA (identical objective)."""
        return self._da._fitness(assign, window, idle_sorted, now)

    # ---------------------------------------------------------------- dispatch
    def dispatch(
        self, now: float, ready: list[Task], idle: list[WorkerState]
    ) -> list[tuple[int, int]]:
        """Run the swarm for one dispatch point (see module docstring)."""
        if not ready or not idle:
            return []
        self.stats["dispatch_count"] += 1

        # exact optima of the SAME fitness for trivial cases (as dragonfly)
        if len(ready) == 1:
            self.stats["fast_paths"] += 1
            w = max(idle, key=lambda x: (x.speed, -x.worker_id))
            return [(ready[0].task_id, w.worker_id)]
        if len(idle) == 1:
            self.stats["fast_paths"] += 1
            t = min(ready, key=lambda x: (x.service, x.arrival, x.task_id))
            return [(t.task_id, idle[0].worker_id)]

        idle_sorted = sorted(idle, key=lambda w: w.worker_id)
        slots = len(idle_sorted)
        window = ready[: min(len(ready), WINDOW_MAX)]
        n_tasks = len(window)
        self.stats["windows"].append(n_tasks)

        rng = self._rng

        def clip(v: float) -> float:
            return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

        def clampv(v: float) -> float:
            return -V_MAX if v < -V_MAX else (V_MAX if v > V_MAX else v)

        def evaluate(pos: list[list[float]]) -> float:
            """Fitness of one particle position on this window (lower better)."""
            return self._fitness(
                self._decode(pos, n_tasks, slots), window, idle_sorted, now
            )

        def copy_pos(pos: list[list[float]]) -> list[list[float]]:
            return [row[:] for row in pos]

        # initialize swarm: random positions, small random velocities (as DA)
        pop: list[list[list[float]]] = [
            [[rng.random() for _ in range(slots)] for _ in range(n_tasks)]
            for _ in range(POPULATION)
        ]
        vel: list[list[list[float]]] = [
            [[(rng.random() - 0.5) * 0.1 for _ in range(slots)] for _ in range(n_tasks)]
            for _ in range(POPULATION)
        ]
        fits: list[float] = [evaluate(p) for p in pop]

        # personal bests start at the initial positions
        pbest = [copy_pos(p) for p in pop]
        pbest_fit = fits[:]
        # swarm-wide best: min scan gives the deterministic lowest-index tie-break
        gbest_idx = min(range(POPULATION), key=lambda i: pbest_fit[i])

        for _it in range(ITERATIONS):
            self.stats["iterations_run"] += 1
            gbest = pbest[gbest_idx]  # snapshot for this iteration
            new_pop, new_vel = [], []
            for i in range(POPULATION):
                xi, vi, pb = pop[i], vel[i], pbest[i]
                nvi = [[0.0] * slots for _ in range(n_tasks)]
                nxi = [[0.0] * slots for _ in range(n_tasks)]
                for r in range(n_tasks):
                    for c in range(slots):
                        r1 = rng.random()
                        r2 = rng.random()
                        v = (
                            INERTIA * vi[r][c]
                            + C1 * r1 * (pb[r][c] - xi[r][c])
                            + C2 * r2 * (gbest[r][c] - xi[r][c])
                        )
                        nvi[r][c] = clampv(v)
                        nxi[r][c] = clip(xi[r][c] + nvi[r][c])
                new_pop.append(nxi)
                new_vel.append(nvi)
            pop, vel = new_pop, new_vel
            fits = [evaluate(p) for p in pop]
            # fold current positions into personal/global bests (strict <:
            # a tie keeps the earlier best, hence the index tie-break)
            for i in range(POPULATION):
                if fits[i] < pbest_fit[i]:
                    pbest[i] = copy_pos(pop[i])
                    pbest_fit[i] = fits[i]
            gbest_idx = min(range(POPULATION), key=lambda i: pbest_fit[i])

        assign = self._decode(pbest[gbest_idx], n_tasks, slots)

        # map window slots -> real dispatch pairs; each idle worker at most once
        pairs: list[tuple[int, int]] = []
        used_slots: set[int] = set()
        used_workers: set[int] = set()
        n_pairs = min(len(ready), len(idle))
        for i in range(n_tasks):
            if len(pairs) >= n_pairs:
                break
            slot = assign[i]
            if slot in used_slots:
                # next-best unassigned slot in this row (deterministic order)
                row_order = sorted(
                    range(slots), key=lambda s: (-pbest[gbest_idx][i][s], s)
                )
                slot = next((s for s in row_order if s not in used_slots), None)
                if slot is None:
                    continue
            wid = idle_sorted[slot].worker_id
            if wid in used_workers:
                continue
            used_slots.add(slot)
            used_workers.add(wid)
            pairs.append((window[i].task_id, wid))

        # safety: never violate the dispatch contract (should not trigger)
        if len(pairs) != n_pairs:
            remaining = [
                (t.task_id, w.worker_id)
                for t in ready[len(window) :]
                for w in idle_sorted
                if w.worker_id not in used_workers
                and t.task_id not in {p[0] for p in pairs}
            ]
            for pair in remaining:
                if len(pairs) >= n_pairs:
                    break
                used_workers.add(pair[1])
                pairs.append(pair)
        return pairs[:n_pairs]

    def on_done(self, task: Task, worker_id: int, start: float, finish: float) -> None:
        """Feedback hook unused by the PSO (stateless per dispatch)."""
        return None
