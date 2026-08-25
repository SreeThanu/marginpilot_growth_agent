"""Worlds round-trip exactly, and are read one at a time.

The 8GB constraint is not a preference: 100 worlds resident at once would swap.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from src.world.generator import generate
from src.world.persistence import (
    TRUTH_SUFFIX,
    WORLD_SUFFIX,
    iter_worlds,
    load_world,
    serialize_world,
    write_world,
)


def test_world_round_trips_through_disk(tmp_path: Path) -> None:
    world, truth = generate(101)
    world_file, truth_file = write_world(world, truth, tmp_path)

    assert world_file.name.endswith(WORLD_SUFFIX)
    assert truth_file.name.endswith(TRUTH_SUFFIX)

    restored = load_world(world_file)
    assert restored == world
    assert serialize_world(restored) == serialize_world(world)


def test_the_world_file_never_contains_potential_outcomes(tmp_path: Path) -> None:
    """Ground truth lives in a separate file so an agent-facing loader
    physically cannot read it (CLAUDE.md invariant 8)."""
    world, truth = generate(102)
    world_file, _ = write_world(world, truth, tmp_path)

    text = world_file.read_text(encoding="utf-8")
    for marker in ("y0_", "y1_", "contribution_inr", "converted"):
        assert marker not in text


def test_same_seed_writes_byte_identical_files(tmp_path: Path) -> None:
    world_a, truth_a = generate(103)
    world_b, truth_b = generate(103)

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    wa, ta = write_world(world_a, truth_a, first_dir)
    wb, tb = write_world(world_b, truth_b, second_dir)

    assert wa.read_bytes() == wb.read_bytes()
    assert ta.read_bytes() == tb.read_bytes()


def test_iter_worlds_is_lazy(tmp_path: Path) -> None:
    for seed in (201, 202, 203):
        world, truth = generate(seed)
        write_world(world, truth, tmp_path)

    stream = iter_worlds(tmp_path)
    assert isinstance(stream, types.GeneratorType), "worlds must not be materialised as a list"

    seen = [w.world_id for w in stream]
    assert seen == sorted(seen)
    assert len(seen) == 3


def test_mismatched_ground_truth_is_refused(tmp_path: Path) -> None:
    world, _ = generate(301)
    _, other_truth = generate(302)
    with pytest.raises(ValueError):
        write_world(world, other_truth, tmp_path)


def test_a_world_from_another_schema_is_refused_not_misparsed(tmp_path: Path) -> None:
    world, truth = generate(303)
    world_file, _ = write_world(world, truth, tmp_path)

    payload = json.loads(world_file.read_text(encoding="utf-8"))
    payload["schema_version"] = "99.0.0"
    world_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        load_world(world_file)
