"""Arm assignment: deterministic, balanced, independent, and unreachable.

CLAUDE.md invariant 1. The last property is the one that matters most — no
agent-reachable input may influence where a customer lands.
"""

from __future__ import annotations

import inspect
import subprocess
import sys

import numpy as np
import pytest
from scipy import stats

from src.experiment import randomize
from src.experiment.randomize import arm_counts, assign, balance_summary
from src.world.generator import generate_world

POPULATION = [f"cust_{i:05d}" for i in range(10_000)]


def test_assignment_is_deterministic() -> None:
    for customer in POPULATION[:500]:
        first = assign(customer, "exp_a", 2)
        assert all(assign(customer, "exp_a", 2) == first for _ in range(5))


def test_assignment_is_stable_across_processes() -> None:
    """Python's hash() is salted per process; blake2b is not.

    Without this the same experiment would reassign every customer on restart,
    making it unreproducible and its audit trail unverifiable.
    """
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from src.experiment.randomize import assign;"
        "print(','.join(str(assign(f'cust_{i:05d}', 'exp_a', 3)) for i in range(50)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd="."
    ).stdout.strip()
    here = ",".join(str(assign(f"cust_{i:05d}", "exp_a", 3)) for i in range(50))
    assert out == here


@pytest.mark.parametrize("n_arms", [2, 3, 4])
def test_assignment_is_balanced(n_arms: int) -> None:
    counts = arm_counts(POPULATION, "exp_balance", n_arms)
    assert sum(counts) == len(POPULATION)

    expected = len(POPULATION) / n_arms
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    p_value = 1.0 - stats.chi2.cdf(chi2, df=n_arms - 1)
    assert p_value > 0.01, f"arm counts {counts} are implausibly unbalanced (p={p_value:.4f})"
    assert balance_summary(counts)["max_relative_deviation"] < 0.05


def test_assignments_are_independent_across_experiments() -> None:
    """A customer in control for experiment A must be no likelier to land in
    control for experiment B.

    Without this, a second experiment run on the same population would inherit
    the first one's split and silently confound the two.
    """
    arm_a = {c: assign(c, "exp_a", 2) for c in POPULATION}
    arm_b = {c: assign(c, "exp_b", 2) for c in POPULATION}

    table = np.zeros((2, 2), dtype=int)
    for customer in POPULATION:
        table[arm_a[customer], arm_b[customer]] += 1

    _, p_value, _, _ = stats.chi2_contingency(table)
    assert p_value > 0.01, f"assignments are dependent across experiments (p={p_value:.4f})\n{table}"

    # And the conditional split must be near 50/50, not merely non-significant.
    in_a_control = [c for c in POPULATION if arm_a[c] == 0]
    share = np.mean([arm_b[c] for c in in_a_control])
    assert 0.47 < share < 0.53


def test_assignment_signature_admits_no_override() -> None:
    """The invariant, enforced against the API surface.

    No seed, no salt, no force, no arm argument. A caller holding the entire
    agent toolbox has no way to express a preference about the outcome, and
    adding such a parameter fails this test rather than silently shipping.
    """
    parameters = list(inspect.signature(assign).parameters)
    assert parameters == ["customer_id", "experiment_id", "n_arms"]

    forbidden = {"arm", "seed", "salt", "force", "override", "assignment", "bias", "weights"}
    for name, function in inspect.getmembers(randomize, inspect.isfunction):
        if name.startswith("_"):
            continue
        found = forbidden & set(inspect.signature(function).parameters)
        # Two functions take an arm to *read* rather than to set: one filters a
        # population by arm, the other re-derives an assignment and checks it for
        # audit replay. Neither returns an assignment, so neither can steer one —
        # asserted below rather than assumed.
        if name in {"customers_in_arm", "verify_assignment"}:
            found -= {"arm"}
        assert not found, f"randomize.{name} exposes {found}, which could steer assignment"

    # The audit-replay helper answers yes/no; it cannot produce an assignment.
    assert randomize.verify_assignment("cust_00001", "exp_a", 2, 0) in (True, False)
    assert (
        randomize.verify_assignment("cust_00001", "exp_a", 2, 0)
        != randomize.verify_assignment("cust_00001", "exp_a", 2, 1)
    ), "verify_assignment must agree with exactly one arm"


def test_single_arm_experiment_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        assign("cust_00001", "exp_a", 1)


def test_assigns_a_real_dev_world_population() -> None:
    """End to end against generated customers. Dev world only — built in memory,
    so no holdout file is touched."""
    world = generate_world(11)  # dev seed range
    ids = [c.customer_id for c in world.customers]
    counts = arm_counts(ids, "exp_world_11", 2)

    assert sum(counts) == len(ids)
    assert balance_summary(counts)["max_relative_deviation"] < 0.10
    assert randomize.verify_assignment(ids[0], "exp_world_11", 2, assign(ids[0], "exp_world_11", 2))
