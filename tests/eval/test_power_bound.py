"""The structural variance bound, and that it is actually a bound.

§4n Step A rests the primary contrast's power on it, so it is worth more than an
assertion in prose: a count of "how many of the n skip-optimal worlds did this
arm run" cannot have a standard deviation above sqrt(n/4), whatever the arm's
per-world behaviour.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.eval.power import required_replicates, structural_sd_bound


@pytest.mark.parametrize("n", [1, 4, 8, 12, 20])
def test_no_bernoulli_sum_exceeds_the_bound(n: int) -> None:
    """Simulated arms with arbitrary per-world probabilities stay under it."""
    bound = structural_sd_bound(n)
    rng = np.random.default_rng(20260831)
    for _ in range(200):
        probs = rng.random(n)
        draws = (rng.random((4000, n)) < probs).sum(axis=1)
        assert draws.std(ddof=1) <= bound + 0.05


def test_the_bound_is_attained_at_one_half() -> None:
    """Tight, not merely valid: p = 0.5 everywhere reaches it."""
    n = 8
    rng = np.random.default_rng(7)
    draws = (rng.random((200_000, n)) < 0.5).sum(axis=1)
    assert draws.std(ddof=1) == pytest.approx(structural_sd_bound(n), abs=0.02)


def test_the_bound_is_tighter_than_the_control_chi_square_upper() -> None:
    """Why Step A uses it: the sampling interval allows the unreachable.

    The control's SD over 8 replicates has a chi-square 95% upper limit of 1.884,
    above the 1.414 that eight Bernoulli indicators can produce at all.
    """
    assert structural_sd_bound(8) < 1.884


def test_worst_case_replicates_for_the_registered_mde() -> None:
    """K = 4 per arm, from the bound rather than from any observed contrast."""
    mde = (18_450.0 / 131_012.0) * 20
    assert math.ceil(required_replicates(structural_sd_bound(8), mde)) == 4
