"""Open dev worlds. The unsealed counterpart to :func:`src.eval.holdout.open_holdout`.

Separate from ``devrun`` because the ground-truth guard in
``src/world/persistence.py`` walks the stack and admits only callers under
``src.eval``. A module executed with ``python -m`` is named ``__main__``, so a
script cannot load its own ground truth however it is placed — and that is the
guard working, not a nuisance to route around. Loading lives here, where the
caller's module name is honestly ``src.eval.devcorpus``.

``final_eval`` is never passed. Nothing in this module can reach a sealed world.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from src.eval.guard import iter_world_paths
from src.world.persistence import load_ground_truth, load_world
from src.world.schema import GroundTruth, World


def open_dev(
    root: str | Path = "worlds", limit: int | None = None
) -> Iterator[tuple[World, GroundTruth]]:
    """Yield dev worlds with their ground truth, one at a time.

    One resident at a time, for the same reason ``open_holdout`` is lazy: 80 of
    these do not fit in 8GB together.
    """
    for count, path in enumerate(iter_world_paths("dev", root=root)):
        if limit is not None and count >= limit:
            return
        yield load_world(path), load_ground_truth(path)
