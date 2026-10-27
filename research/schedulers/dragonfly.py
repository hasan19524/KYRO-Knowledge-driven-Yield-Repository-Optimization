"""Dragonfly-Algorithm scheduler (Mirjalili 2016) for dispatch-time assignment.

Adapts the Dragonfly Algorithm's static+dynamic swarming behaviour to the
task-to-worker assignment sub-problem solved at every dispatch point:

  * A candidate solution (dragonfly "position") is a continuous matrix of
    shape (n_window, n_idle) in [0, 1]; DECODE: task i is assigned to the
    idle worker with the largest value in row i (ties: lowest worker id).
  * The swarm optimizes a window of the W oldest ready tasks against the
    currently idle workers for a FIXED compute budget (population 12,
    iterations 8) so dispatch stays O(1) per call in simulation scale.
  * FITNESS of a decoded sub-assignment, evaluated by local simulation:
        f = 0.5 * max(completion) + 0.3 * mean(completion)
          + 0.2 * std(per-worker assigned load)
    where completion_i = now + service_i / speed(worker_i). Lower is better:
    the first term targets makespan, the second flow time, the third load
    balance - the three objectives of the paper in one scalar.
  * VELOCITY update follows the standard DA equations over the swarm with
    k-nearest neighbourhood (by fitness) plus FOOD (global best) and
    PREDATOR (global worst) terms; inertia weight decays linearly:
        v <- w*v + S*separation + A*alignment + C*cohesion
              + F*food + E*enemy
        x <- clip(x + v, 0, 1)
  * FOOD = best position seen so far THIS dispatch; PREDATOR = worst.
  * TRIVIAL CASES use the exact optimum of the same fitness (not heuristics):
    one ready task -> fastest idle worker; one idle worker -> smallest
    service task (SPT minimizes the completion terms for a single machine).

Deterministic: a single random.Random(seed) drives population init and all
swarm dynamics; the same seed replays identical dispatches.

Per-dispatch stats accumulate in self.stats for the research report.
"""

from __future__ import annotations

import math
import random

from research.sim.interface import Task, WorkerState

# ---- DA behaviour weights (documented module constants) --------------------
W_INERTIA_START = 0.9  # inertia: early exploration
W_INERTIA_END = 0.1  # inertia: late exploitation (linear decay per iteration)
S_WEIGHT = 0.5  # separation: repel from neighbours (avoid collisions)
A_WEIGHT = 0.4  # alignment: follow neighbour velocities (flock)
C_WEIGHT = 0.3  # cohesion: pull toward neighbour centroid (converge)
F_WEIGHT = 1.2  # food: attraction to global best (strong exploit)
E_WEIGHT = 0.6  # enemy: distraction from global worst (escape)

# fitness terms: makespan, mean flow, load balance
FIT_W_MAX = 0.5
FIT_W_MEAN = 0.3
FIT_W_IMBALANCE = 0.2

POPULATION = 12  # dragonflies per dispatch
ITERATIONS = 8  # swarming iterations per dispatch
NEIGHBOURS = 3  # k-nearest neighbourhood by fitness
WINDOW_MAX = 12  # oldest-ready task window size cap


class DragonflyScheduler:
    """DA-based dispatch: swarm-optimized task-to-worker assignment."""

    name = "dragonfly"

    def __init__(self) -> None:
        self.n_workers = 0
        self._rng = random.Random(0)
        self.stats: dict = {
            "dispatch_count": 0,
            "fast_paths": 0,
            "windows": [],
            "iterations_run": 0,
        }

    def reset(self, n_workers: int, seed: int) -> None:
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
        """Row argmax -> worker-slot index per task slot (ties: lowest slot)."""
        assign = []
        for i in range(n_tasks):
            row = pos[i]
            best_slot = 0
            best_val = row[0]
            for j in range(1, n_idle):
                if row[j] > best_val:
                    best_val = row[j]
                    best_slot = j
            assign.append(best_slot)
        return assign

    def _fitness(
        self,
        assign: list[int],
        window: list[Task],
        idle_sorted: list[WorkerState],
        now: float,
    ) -> float:
        """Local-simulation fitness; lower is better (see module docstring)."""
        completions = []
        load_per_worker: dict[int, float] = {}
        for task, slot in zip(window, assign):
            w = idle_sorted[slot]
            dur = task.service / w.speed
            completions.append(now + dur)
            load_per_worker[w.worker_id] = load_per_worker.get(w.worker_id, 0.0) + dur
        if not completions:
            return 0.0
        f_max = max(completions)
        f_mean = sum(completions) / len(completions)
        loads = list(load_per_worker.values())
        if len(loads) > 1:
            mu = sum(loads) / len(loads)
            var = sum((x - mu) ** 2 for x in loads) / len(loads)
            f_imb = math.sqrt(var)
        else:
            f_imb = 0.0
        return FIT_W_MAX * f_max + FIT_W_MEAN * f_mean + FIT_W_IMBALANCE * f_imb

    # ------------------------------------------------------------------ dispatch
    def dispatch(
        self, now: float, ready: list[Task], idle: list[WorkerState]
    ) -> list[tuple[int, int]]:
        if not ready or not idle:
            return []
        self.stats["dispatch_count"] += 1

        # exact optima of the SAME fitness for trivial cases
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

        def rand_pos() -> list[list[float]]:
            return [[rng.random() for _ in range(slots)] for _ in range(n_tasks)]

        def clip(v: float) -> float:
            return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

        pop = [rand_pos() for _ in range(POPULATION)]
        vel = [
            [[(rng.random() - 0.5) * 0.1 for _ in range(slots)] for _ in range(n_tasks)]
            for _ in range(POPULATION)
        ]

        fits = [
            self._fitness(self._decode(p, n_tasks, slots), window, idle_sorted, now)
            for p in pop
        ]

        for it in range(ITERATIONS):
            self.stats["iterations_run"] += 1
            order = sorted(range(POPULATION), key=lambda i: fits[i])
            food_idx, predator_idx = order[0], order[-1]
            w_inertia = W_INERTIA_START + (W_INERTIA_END - W_INERTIA_START) * (
                it / max(ITERATIONS - 1, 1)
            )
            # k-nearest by fitness rank (circular neighbourhood in rank space)
            neighbours = [
                [order[(rank + d) % POPULATION] for d in range(1, NEIGHBOURS + 1)]
                for rank in range(POPULATION)
            ]
            new_pop, new_fits = [], []
            for i in range(POPULATION):
                nb = neighbours[i]
                xi, vi, xf = pop[i], vel[i], pop[food_idx]
                xe = pop[predator_idx]
                nvi = [[0.0] * slots for _ in range(n_tasks)]
                for r in range(n_tasks):
                    for c in range(slots):
                        # separation: mean repulsion from neighbours
                        sep = sum(xi[r][c] - pop[j][r][c] for j in nb) / len(nb)
                        # alignment: mean neighbour velocity
                        ali = sum(vel[j][r][c] for j in nb) / len(nb)
                        # cohesion: pull toward neighbour centroid
                        coh = sum(pop[j][r][c] for j in nb) / len(nb) - xi[r][c]
                        food = xf[r][c] - xi[r][c]
                        enemy = xi[r][c] - xe[r][c]
                        nvi[r][c] = (
                            w_inertia * vi[r][c]
                            + S_WEIGHT * sep
                            + A_WEIGHT * ali
                            + C_WEIGHT * coh
                            + F_WEIGHT * food
                            + E_WEIGHT * enemy
                        )
                nxi = [
                    [clip(xi[r][c] + nvi[r][c]) for c in range(slots)]
                    for r in range(n_tasks)
                ]
                nfi = self._fitness(
                    self._decode(nxi, n_tasks, slots), window, idle_sorted, now
                )
                new_pop.append(nxi)
                new_fits.append(nfi)
            pop, fits = new_pop, new_fits

        best = min(range(POPULATION), key=lambda i: fits[i])
        assign = self._decode(pop[best], n_tasks, slots)

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
                row_order = sorted(range(slots), key=lambda s: (-pop[best][i][s], s))
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
        return None
