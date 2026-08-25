"""Read and write worlds, one at a time, with ground truth kept separate.

Two files per world::

    worlds/dev/world_00001.world.json    # the merchant — readable by the harness
    worlds/dev/world_00001.truth.json    # Y(0)/Y(1) — src/eval/ only

Splitting them is the point. If potential outcomes lived inside the world file,
every loader in the project would hold them in memory and "no agent tool returns
ground truth" would rest on discipline alone. Split, an agent-facing loader
physically never opens the file (CLAUDE.md invariant 8).

Three layers guard ground truth, because one is not enough:

1. ``World`` has no reference to ``GroundTruth`` (``src/world/schema.py``).
2. :func:`load_ground_truth` refuses callers outside ``src/eval/`` at runtime.
3. ``tests/test_ground_truth_isolation.py`` statically scans ``src/`` for any
   module outside ``src/eval/`` that so much as names the loader.

Worlds are always read one at a time. 100 worlds do not fit comfortably in 8GB
and never need to.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any, Iterator

from src.eval.guard import assert_may_read
from src.world.schema import SCHEMA_VERSION, GroundTruth, World

WORLD_SUFFIX = ".world.json"
TRUTH_SUFFIX = ".truth.json"

#: Module prefixes allowed to load potential outcomes. ``src.eval`` is the
#: evaluation harness; the test prefixes exist so the guard itself can be tested
#: and so ``tests/world/`` can assert every customer has both outcomes.
#:
#: A module inside ``src/`` named ``test_*`` would slip past this check — which
#: is exactly what the static scan in tests/ exists to catch. Runtime and static
#: checks cover each other's blind spots.
_GROUND_TRUTH_CALLER_PREFIXES = ("src.eval", "tests")
_GROUND_TRUTH_CALLER_BASENAME_PREFIXES = ("test_",)


class GroundTruthAccessError(PermissionError):
    """Raised when a module outside ``src/eval/`` tries to read ground truth."""


def _calling_module_name() -> str:
    """Name of the first module outside this one on the stack.

    Frame walking rather than a caller-supplied argument: a guard the caller can
    satisfy by passing a string is a comment, not a guard.
    """
    frame = inspect.currentframe()
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name != __name__:
            return name
        frame = frame.f_back
    return ""


def _assert_caller_may_read_ground_truth() -> None:
    name = _calling_module_name()
    basename = name.rsplit(".", 1)[-1]
    allowed = name.startswith(_GROUND_TRUTH_CALLER_PREFIXES) or basename.startswith(
        _GROUND_TRUTH_CALLER_BASENAME_PREFIXES
    )
    if not allowed:
        raise GroundTruthAccessError(
            f"module {name!r} may not read potential outcomes. Y(0)/Y(1) are visible to "
            "src/eval/ only, and no agent tool may ever return them, directly or "
            "derived (CLAUDE.md invariant 8). If you need observable data, load the "
            "world instead — that is what an experiment gets to see."
        )


def _dump(payload: dict[str, Any], path: Path) -> None:
    """Write canonical JSON.

    ``sort_keys`` and a fixed separator make the bytes a function of the content
    alone, so "same seed produces a byte-identical world" is testable on the file
    rather than only on the object. UTF-8 without ASCII escaping keeps the
    semantic text readable in a diff.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")


def world_path(world_id: str, directory: str | os.PathLike[str]) -> Path:
    return Path(directory) / f"{world_id}{WORLD_SUFFIX}"


def truth_path(world_id: str, directory: str | os.PathLike[str]) -> Path:
    return Path(directory) / f"{world_id}{TRUTH_SUFFIX}"


def serialize_world(world: World) -> str:
    """Canonical JSON text for a world. Exposed for the determinism test."""
    return json.dumps(
        world.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def write_world(
    world: World, ground_truth: GroundTruth, directory: str | os.PathLike[str]
) -> tuple[Path, Path]:
    """Write both files. Returns ``(world_path, truth_path)``."""
    if ground_truth.world_id != world.world_id:
        raise ValueError(
            f"ground truth is for {ground_truth.world_id!r}, world is {world.world_id!r}"
        )
    wpath = world_path(world.world_id, directory)
    tpath = truth_path(world.world_id, directory)
    _dump(world.to_dict(), wpath)
    _dump(ground_truth.to_dict(), tpath)
    return wpath, tpath


def load_world(path: str | os.PathLike[str], *, final_eval: bool = False) -> World:
    """Load one world. Holdout paths require ``final_eval=True``."""
    target = assert_may_read(path, final_eval=final_eval)
    raw = json.loads(target.read_text(encoding="utf-8"))
    _assert_schema_compatible(raw.get("schema_version"), target)
    return World.from_dict(raw)


def load_ground_truth(
    path: str | os.PathLike[str], *, final_eval: bool = False
) -> GroundTruth:
    """Load potential outcomes. ``src/eval/`` only.

    ``path`` may be either the world file or the truth file for convenience at
    the call site; both resolve to the same truth file.
    """
    _assert_caller_may_read_ground_truth()
    target = assert_may_read(path, final_eval=final_eval)
    name = target.name
    if name.endswith(WORLD_SUFFIX):
        target = target.with_name(name[: -len(WORLD_SUFFIX)] + TRUTH_SUFFIX)
    raw = json.loads(target.read_text(encoding="utf-8"))
    _assert_schema_compatible(raw.get("schema_version"), target)
    return GroundTruth.from_dict(raw)


def iter_worlds(
    directory: str | os.PathLike[str], *, final_eval: bool = False
) -> Iterator[World]:
    """Yield worlds from a directory one at a time.

    A generator, not a list: nothing in this project needs two worlds resident
    simultaneously, and 100 of them would not fit.
    """
    for path in sorted(Path(directory).glob(f"*{WORLD_SUFFIX}")):
        yield load_world(path, final_eval=final_eval)


def _assert_schema_compatible(version: str | None, path: Path) -> None:
    """Refuse a file from a different major schema rather than mis-parsing it."""
    if version is None:
        raise ValueError(f"{path} has no schema_version")
    if version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise ValueError(
            f"{path} was written with schema {version}, this build expects "
            f"{SCHEMA_VERSION}. Regenerate the worlds with `make worlds`."
        )
