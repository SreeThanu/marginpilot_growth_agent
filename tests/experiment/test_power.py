"""Sample size and MDE, checked against hand-computed values.

CLAUDE.md: experiment/ needs real unit tests with hand-computed expected values.
These carry the project's credibility — the horizon they produce is what makes
"no peeking" a fixed commitment rather than a preference.
"""

from __future__ import annotations

import math

import pytest
from scipy import stats

from src.experiment.power import (
    analyse,
    detectable_effect,
    is_adequately_powered,
    required_sample_size_per_arm,
)


def test_matches_the_hand_computed_readme_case() -> None:
    """Baseline 12%, MDE 6 points (12% -> 18%), alpha 0.05, power 0.80.

    Worked by hand:
        z_0.975 = 1.959964, z_0.80 = 0.841621, sum = 2.801585, squared = 7.848880
        p0(1-p0) = 0.12 * 0.88 = 0.1056
        p1(1-p1) = 0.18 * 0.82 = 0.1476        sum = 0.2532
        delta^2 = 0.06^2 = 0.0036
        n = 7.848880 * 0.2532 / 0.0036 = 552.04  ->  553 per arm
    """
    z_alpha = stats.norm.ppf(0.975)
    z_beta = stats.norm.ppf(0.80)
    expected_raw = (z_alpha + z_beta) ** 2 * (0.12 * 0.88 + 0.18 * 0.82) / 0.06**2

    assert math.isclose(expected_raw, 552.04, abs_tol=0.05)
    assert required_sample_size_per_arm(0.12, 0.06) == 553


def test_the_readme_pilot_is_powered_for_its_effect_and_not_for_a_smaller_one() -> None:
    """1,000 per arm detects the 6-point effect comfortably, and a 3-point one not at all."""
    assert is_adequately_powered(0.12, 0.06, 1000)
    assert not is_adequately_powered(0.12, 0.03, 1000)


def test_smaller_effects_need_quadratically_more_sample() -> None:
    """Halving the effect roughly quadruples the sample. If this ever stops
    holding, the formula has been replaced by something that is not a power
    calculation."""
    big = required_sample_size_per_arm(0.12, 0.06)
    small = required_sample_size_per_arm(0.12, 0.03)
    assert 3.5 < small / big < 4.5


def test_more_power_and_tighter_alpha_both_cost_sample() -> None:
    base = required_sample_size_per_arm(0.12, 0.06, alpha=0.05, power=0.80)
    assert required_sample_size_per_arm(0.12, 0.06, alpha=0.05, power=0.95) > base
    assert required_sample_size_per_arm(0.12, 0.06, alpha=0.01, power=0.80) > base


def test_multiple_comparisons_cost_sample() -> None:
    """A three-arm design makes two comparisons; testing both at the nominal
    alpha would inflate the family-wise error rate."""
    two_arm = required_sample_size_per_arm(0.12, 0.06, comparisons=1)
    three_arm = required_sample_size_per_arm(0.12, 0.06, comparisons=2)
    assert three_arm > two_arm


def test_detectable_effect_inverts_the_sample_size() -> None:
    """The inverse is what lets a design be refused as unreadable before it runs."""
    for baseline, mde in ((0.12, 0.06), (0.05, 0.02), (0.20, 0.04)):
        n = required_sample_size_per_arm(baseline, mde)
        recovered = detectable_effect(baseline, n)
        assert recovered == pytest.approx(mde, rel=0.02)


def test_detectable_effect_shrinks_as_sample_grows() -> None:
    effects = [detectable_effect(0.12, n) for n in (250, 500, 1000, 4000)]
    assert effects == sorted(effects, reverse=True)


def test_underpowered_designs_are_identifiable_at_design_time() -> None:
    """A 1-point effect on a 1,000-per-arm pilot is not a risky experiment, it is
    an unreadable one — it returns 'no significant difference' whatever the truth."""
    assert detectable_effect(0.12, 1000) > 0.01
    assert not is_adequately_powered(0.12, 0.01, 1000)


def test_analyse_carries_its_inputs_for_the_audit_record() -> None:
    analysis = analyse(0.12, 0.06)
    assert analysis.n_per_arm == 553
    assert analysis.treatment_conversion == pytest.approx(0.18)
    assert analysis.mde_relative == pytest.approx(0.5)


@pytest.mark.parametrize(
    "baseline,mde",
    [(0.0, 0.05), (1.0, 0.05), (0.12, 0.0), (0.12, -0.03), (0.98, 0.05)],
)
def test_impossible_designs_are_refused(baseline: float, mde: float) -> None:
    with pytest.raises(ValueError):
        required_sample_size_per_arm(baseline, mde)
