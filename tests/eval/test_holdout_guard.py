"""The holdout seal must actually raise, not merely be documented.

CLAUDE.md invariant 4. This is the test that makes peeking mechanically
annoying: without it, the guard could be silently broken and nothing would fail
until the results were already contaminated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.eval.guard import (
    HoldoutSealedError,
    assert_may_read,
    is_holdout_path,
    iter_world_paths,
    split_dir,
)
from src.world.generator import generate
from src.world.persistence import load_world, write_world


def test_holdout_path_is_detected_by_component_not_substring(tmp_path: Path) -> None:
    assert is_holdout_path(tmp_path / "worlds" / "holdout" / "world_09001.world.json")
    assert not is_holdout_path(tmp_path / "worlds" / "dev" / "world_00001.world.json")
    # A dev file whose *name* contains the word is not a holdout world.
    assert not is_holdout_path(tmp_path / "worlds" / "dev" / "holdout_notes.world.json")


def test_reading_a_holdout_path_raises_without_the_flag(tmp_path: Path) -> None:
    path = tmp_path / "worlds" / "holdout" / "world_09001.world.json"
    with pytest.raises(HoldoutSealedError):
        assert_may_read(path)


def test_the_flag_opens_the_seal(tmp_path: Path) -> None:
    path = tmp_path / "worlds" / "holdout" / "world_09001.world.json"
    assert assert_may_read(path, final_eval=True) == path


def test_dev_paths_are_never_gated(tmp_path: Path) -> None:
    path = tmp_path / "worlds" / "dev" / "world_00001.world.json"
    assert assert_may_read(path) == path


def test_load_world_refuses_a_sealed_world_on_disk(tmp_path: Path) -> None:
    """End to end: a real file in a real holdout directory stays unreadable.

    The world used here is generated fresh in tmp_path, so no world from the
    project's actual sealed corpus is touched.
    """
    world, truth = generate(500_001, split="holdout")
    holdout_dir = tmp_path / "worlds" / "holdout"
    world_file, _ = write_world(world, truth, holdout_dir)

    with pytest.raises(HoldoutSealedError):
        load_world(world_file)

    reopened = load_world(world_file, final_eval=True)
    assert reopened.world_id == world.world_id


def test_iter_world_paths_gates_the_whole_split(tmp_path: Path) -> None:
    world, truth = generate(500_002, split="holdout")
    write_world(world, truth, tmp_path / "worlds" / "holdout")

    with pytest.raises(HoldoutSealedError):
        list(iter_world_paths("holdout", root=tmp_path / "worlds"))

    opened = list(iter_world_paths("holdout", root=tmp_path / "worlds", final_eval=True))
    assert len(opened) == 1


def test_unknown_split_is_rejected() -> None:
    with pytest.raises(ValueError):
        split_dir("dev_worlds_v2")
