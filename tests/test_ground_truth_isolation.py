"""Potential outcomes are visible to ``src/eval/`` only — enforced two ways.

CLAUDE.md invariant 8: ``Y(0)``/``Y(1)`` are visible to ``eval/`` only, and no
agent tool may ever return them, directly or derived.

A runtime guard alone could be bypassed by a module that never calls the loader
but imports the types and reconstructs outcomes itself. A static scan alone
could be defeated by a dynamic import. Each check covers the other's blind spot,
so both exist.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.world.generator import generate
from src.world.persistence import GroundTruthAccessError, load_ground_truth, write_world

SRC = Path(__file__).resolve().parent.parent / "src"

#: The only files allowed to name ground truth at all. ``schema`` defines the
#: types, ``generator`` draws them, ``persistence`` stores them behind the
#: guard, and ``eval`` is the one consumer.
_ALLOWED_FILES = {
    "src/world/schema.py",
    "src/world/generator.py",
    "src/world/persistence.py",
}
_ALLOWED_PACKAGE_PREFIX = "src/eval/"

_GROUND_TRUTH_NAMES = {
    "GroundTruth",
    "PotentialOutcome",
    "PotentialOutcomePair",
    "load_ground_truth",
    "generate_ground_truth",
    "truth_path",
    "tau_contribution_inr",
}


def _project_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(SRC.parent)).replace("\\", "/")


# --------------------------------------------------------------------------- #
# Static: nothing outside eval/ may even name ground truth
# --------------------------------------------------------------------------- #


def test_no_module_outside_eval_names_potential_outcomes() -> None:
    violations: list[str] = []

    for path in _project_files():
        relative = _relative(path)
        if relative in _ALLOWED_FILES or relative.startswith(_ALLOWED_PACKAGE_PREFIX):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _GROUND_TRUTH_NAMES:
                violations.append(f"{relative}:{node.lineno} references {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in _GROUND_TRUTH_NAMES:
                violations.append(f"{relative}:{node.lineno} references .{node.attr}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in _GROUND_TRUTH_NAMES:
                        violations.append(f"{relative}:{node.lineno} imports {alias.name}")

    assert not violations, (
        "Y(0)/Y(1) are visible to src/eval/ only (CLAUDE.md invariant 8):\n  "
        + "\n  ".join(violations)
    )


def test_the_static_scan_detects_a_planted_reference(tmp_path: Path) -> None:
    """The scan is only worth having if it fails when it should."""
    planted = tmp_path / "tools.py"
    planted.write_text("from src.world.persistence import load_ground_truth\n", encoding="utf-8")

    tree = ast.parse(planted.read_text(encoding="utf-8"))
    found = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name in _GROUND_TRUTH_NAMES
    ]
    assert found == ["load_ground_truth"]


# --------------------------------------------------------------------------- #
# Runtime: the loader refuses callers outside eval/
# --------------------------------------------------------------------------- #


def _call_loader_as(module_name: str, world_file: Path) -> None:
    """Invoke the loader from a frame that claims to be ``module_name``.

    ``exec`` with a fabricated ``__name__`` is how a caller from ``src/agent/``
    is simulated without adding a module to the package that the static scan
    would then have to whitelist.
    """
    namespace = {
        "__name__": module_name,
        "load_ground_truth": load_ground_truth,
        "path": world_file,
    }
    exec("load_ground_truth(path)", namespace)  # noqa: S102 - deliberate, see docstring


@pytest.fixture()
def dev_world(tmp_path: Path) -> Path:
    world, truth = generate(600_001, split="dev")
    world_file, _ = write_world(world, truth, tmp_path / "worlds" / "dev")
    return world_file


@pytest.mark.parametrize(
    "module_name",
    ["src.agent.tools", "src.agent.agent", "src.baselines.strategist", "src.ui.dashboard", "src.policy.gates"],
)
def test_modules_outside_eval_cannot_load_ground_truth(module_name: str, dev_world: Path) -> None:
    with pytest.raises(GroundTruthAccessError):
        _call_loader_as(module_name, dev_world)


def test_eval_can_load_ground_truth(dev_world: Path) -> None:
    namespace = {
        "__name__": "src.eval.harness",
        "load_ground_truth": load_ground_truth,
        "path": dev_world,
        "result": None,
    }
    exec("result = load_ground_truth(path)", namespace)  # noqa: S102
    assert namespace["result"] is not None
    assert namespace["result"].outcomes


def test_world_object_holds_no_route_to_ground_truth() -> None:
    """The first line of defence: a World simply has no way to reach outcomes."""
    world, _ = generate(600_002)
    exposed = {name for name in dir(world) if not name.startswith("_")}
    assert not exposed & {"ground_truth", "truth", "outcomes", "potential_outcomes", "tau"}

    serialized = world.to_dict()
    flattened = repr(serialized)
    for marker in ("y0", "y1", "potential_outcome", "tau"):
        assert marker not in flattened, f"world serialization leaks {marker!r}"
