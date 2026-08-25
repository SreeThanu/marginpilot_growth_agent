"""The seal on the holdout worlds.

CLAUDE.md invariant 4: the 20 holdout worlds are never read, printed, tuned
against or inspected during development. They are opened once, by ``make eval``.

A promise in a docstring is not a seal, so this module makes peeking take a
deliberate act: every read of a world file goes through :func:`assert_may_read`,
and a path under ``worlds/holdout/`` raises :class:`HoldoutSealedError` unless
the caller passes ``final_eval=True``. The flag has to be typed, by a person, in
a place a reviewer can grep for — ``git log -S final_eval`` shows every time the
seal was opened and when.

Deliberately stdlib-only and importing nothing from the rest of the project, so
that ``src/world/persistence.py`` can enforce the seal at the single point where
worlds are read without creating a dependency cycle. Duplicating the check
instead would create two places where it could be weakened, which is worse.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

#: Directory names under the worlds root.
DEV_SPLIT = "dev"
HOLDOUT_SPLIT = "holdout"

#: Default location for generated worlds. Gitignored — worlds are regenerable
#: from their seed, and a holdout world must never reach the repo where it could
#: be read by eye.
DEFAULT_WORLDS_ROOT = Path("worlds")


class HoldoutSealedError(RuntimeError):
    """Raised on any attempt to read a holdout world without ``final_eval``."""


def is_holdout_path(path: str | os.PathLike[str]) -> bool:
    """True if ``path`` lies under a ``holdout`` directory.

    Matches on a path *component*, not a substring: a dev world named
    ``holdout_notes.world.json`` is not a holdout world, and a directory called
    ``worlds/holdout`` is one however it was reached.
    """
    resolved = Path(path).expanduser().resolve()
    return HOLDOUT_SPLIT in resolved.parts


def assert_may_read(path: str | os.PathLike[str], *, final_eval: bool = False) -> Path:
    """Authorize a read of ``path``. Returns it, so calls can be inlined.

    Raises :class:`HoldoutSealedError` for a holdout path unless ``final_eval``
    is explicitly true.
    """
    target = Path(path)
    if is_holdout_path(target) and not final_eval:
        raise HoldoutSealedError(
            f"{target} is a sealed holdout world. Holdout worlds are opened once, at "
            "final evaluation, by passing final_eval=True. If you are debugging, "
            "generate a fresh dev world instead — reading this file contaminates the "
            "only unbiased estimate this project has (CLAUDE.md invariant 4)."
        )
    return target


def split_dir(split: str, *, root: str | os.PathLike[str] = DEFAULT_WORLDS_ROOT) -> Path:
    if split not in (DEV_SPLIT, HOLDOUT_SPLIT):
        raise ValueError(f"unknown split: {split!r} (expected {DEV_SPLIT!r} or {HOLDOUT_SPLIT!r})")
    return Path(root) / split


def iter_world_paths(
    split: str,
    *,
    root: str | os.PathLike[str] = DEFAULT_WORLDS_ROOT,
    final_eval: bool = False,
) -> Iterator[Path]:
    """Yield world file paths for a split, one at a time, in a stable order.

    Lazy on purpose: 100 worlds are never all resident at once. The 8GB machine
    this runs on is a hard constraint, not a preference.
    """
    directory = split_dir(split, root=root)
    for path in sorted(directory.glob("*.world.json")):
        yield assert_may_read(path, final_eval=final_eval)
