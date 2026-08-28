"""The merchant's past-campaign history must be the same in every process.

A same-process assertion cannot catch the bug this guards against. Python salts
string hashing per interpreter, so ``hash(world_id)`` is stable within one run
and different across runs — a seed derived from it looks perfectly deterministic
to any test that does not start a second interpreter. These tests start one.

The consequence is not cosmetic: the history is evidence the agent reasons from,
and evidence that changes between runs makes a result irreproducible and an
ablation meaningless.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_PROBE = """
import sys
sys.path.insert(0, %r)
from src.eval.contracts import merchant_view
from src.world.generator import generate_world
view = merchant_view(generate_world(7))
print(";".join(
    f"{h.intervention_id}:{h.net_per_treated_customer_inr:.6f}:{h.standard_error_inr:.6f}"
    for h in view.history
))
""" % str(REPO)


def _history_under(hash_seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, env=env, cwd=REPO
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_history_is_identical_across_hash_seeds() -> None:
    """Different PYTHONHASHSEED, identical history. Fails for any hash()-derived seed."""
    assert _history_under("0") == _history_under("12345")


def test_history_is_not_empty() -> None:
    """A silently empty history would pass the test above for the wrong reason."""
    assert _history_under("0").count(";") == 3


def test_history_never_uses_builtin_hash() -> None:
    """The property, checked at the source, so the reason survives a refactor."""
    source = (REPO / "src" / "eval" / "contracts.py").read_text()
    offending = [
        line
        for line in source.splitlines()
        if "hash(" in line
        and "blake2b" not in line
        and "hashlib" not in line
        and not line.lstrip().startswith("#")
    ]
    assert not offending, f"builtin hash() reached a seed: {offending}"
