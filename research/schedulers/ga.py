"""Genetic-Algorithm scheduler (Goldberg 1989) for dispatch-time assignment.

Baseline for the DA scheduler: identical window sub-problem, encoding, decode
and fitness - only the search operators change, so any quality difference is
attributable to the metaheuristic, not the formulation.

  * A candidate solution (chromosome) is a continuous matrix of shape
    (n_window, n_idle) in [0, 1] - the SAME encoding as dragonfly; DECODE and
    the per-window row repair are imported from DragonflyScheduler so the
    mapping to (task_id, worker_id) pairs is identical by construction.
  * FITNESS is also reused from DragonflyScheduler by reference:
        f = 0.5 * max(completion) + 0.3 * mean(completion)
          + 0.2 * std(per-worker assigned load)
    with completion_i = now + service_i / speed(worker_i); lower is better.
  * EVOLUTION per dispatch (fixed compute budget matching DA's P=12, I=8):
    elitism keeps the top-2 chromosomes unchanged, parents are picked by
    k=3 tournament on fitness (ties broken by ascending index), uniform
    crossover exchanges cells with p=0.7, and gaussian mutation perturbs
    each cell with p=0.2, sigma=0.1, followed by clipping to [0, 1].
  * TRIVIAL CASES use the exact optimum of the same fitness: one ready task
    -> fastest idle worker; one idle worker -> smallest-service task (SPT).

Deterministic: a single stdlib random.Random(seed) drives population init
and every genetic operator; the same seed replays identical dispatches.
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

# GA behaviour parameters (documented module constants)
POPULATION = 12  # chromosomes per dispatch (matches DA population budget)
GENERATIONS = 8  # generations per dispatch (matches DA iteration budget)
ELITISM = 2  # top-2 chromosomes survive unchanged each generation
TOURNAMENT_K = 3  # tournament size on fitness (ties: lowest index)
CROSSOVER_P = 0.7  # per-cell uniform-crossover exchange probability
MUTATION_P = 0.2  # per-cell gaussian mutation probability
MUTATION_SIGMA = 0.1  # gaussian mutation standard deviation (positions in [0,1])

# fitness weights imported for parity with DA; evaluation itself is delegated
# to DragonflyScheduler._fitness so the objective is identical by construction
OBJECTIVE_WEIGHTS = (FIT_W_MAX, FIT_W_MEAN, FIT_W_IMBALANCE)


class GaScheduler:
    """GA-based dispatch: evolution-optimized task-to-worker assignment."""

    name = "ga"

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
        """Evolve a window assignment for one dispatch point (see module doc)."""
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

        def rand_pos() -> list[list[float]]:
            return [[rng.random() for _ in range(slots)] for _ in range(n_tasks)]

        def clip(v: float) -> float:
            return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)

        def evaluate(pos: list[list[float]]) -> float:
            """Fitness of one chromosome on this window (lower is better)."""
            return self._fitness(
                self._decode(pos, n_tasks, slots), window, idle_sorted, now
            )

        # initial population: uniformly random chromosomes
        pop: list[list[list[float]]] = [rand_pos() for _ in range(POPULATION)]
        fits: list[float] = [evaluate(p) for p in pop]

        for _gen in range(GENERATIONS):
            self.stats["iterations_run"] += 1
            order = sorted(range(POPULATION), key=lambda i: fits[i])
            new_pop: list[list[list[float]]] = [
                [row[:] for row in pop[order[0]]],
                [row[:] for row in pop[order[1]]],
            ]  # elitism: top-2 chromosomes survive unchanged

            def tournament(pop=pop, fits=fits) -> list[list[float]]:
                """Pick the fittest of TOURNAMENT_K random chromosomes."""
                cand = rng.sample(range(POPULATION), TOURNAMENT_K)
                best = min(cand, key=lambda i: (fits[i], i))
                return pop[best]

            while len(new_pop) < POPULATION:
                p1 = tournament()
                p2 = tournament()
                # uniform crossover: per cell, take parent2's value with p=0.7
                child = [
                    [
                        p2[r][c] if rng.random() < CROSSOVER_P else p1[r][c]
                        for c in range(slots)
                    ]
                    for r in range(n_tasks)
                ]
                # gaussian mutation: per cell, N(0, sigma) perturbation, then clip
                child = [
                    [
                        clip(
                            child[r][c] + rng.gauss(0.0, MUTATION_SIGMA)
                            if rng.random() < MUTATION_P
                            else child[r][c]
                        )
                        for c in range(slots)
                    ]
                    for r in range(n_tasks)
                ]
                new_pop.append(child)
            pop, fits = new_pop, [evaluate(p) for p in new_pop]

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
                # next-best unused slot in this row (deterministic order)
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
        """Feedback hook unused by the GA (stateless per dispatch)."""
        return None
