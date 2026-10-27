"""Scheduler registry for the KYRO load-balancing study.

The study compares five dispatch policies on identical real traces:
  * dragonfly    - Dragonfly-Algorithm swarm optimization (the contribution)
  * fcfs         - first-come-first-serve (classic strict baseline)
  * round_robin  - cyclic worker rotation (classic load-balancing baseline)
  * ga           - genetic-algorithm baseline (same encoding/objective as DA)
  * pso          - particle-swarm baseline (same encoding/objective as DA)

get_scheduler(name, seed) -> Scheduler implementing research.sim.interface.
"""

from __future__ import annotations

from .dragonfly import DragonflyScheduler
from .fcfs import FcfsScheduler
from .ga import GaScheduler
from .pso import PsoScheduler
from .round_robin import RoundRobinScheduler

ALGORITHMS = ("dragonfly", "fcfs", "round_robin", "ga", "pso")

_REGISTRY = {
    "dragonfly": DragonflyScheduler,
    "fcfs": FcfsScheduler,
    "round_robin": RoundRobinScheduler,
    "ga": GaScheduler,
    "pso": PsoScheduler,
}


def get_scheduler(name: str, seed: int = 0):
    """Instantiate a scheduler by name (see ALGORITHMS)."""
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown scheduler {name!r}; valid: {sorted(_REGISTRY)}")
    return cls()
