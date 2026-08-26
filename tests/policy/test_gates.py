"""One rejection test per policy rule. CLAUDE.md: every rule needs a test
proving it refuses a violating proposal.

A gate that has never been observed to say no is not known to work.
"""

from __future__ import annotations

import pytest

from src.policy.gates import (
    PolicyLimits,
    PolicyVerdict,
    Rule,
    affordable_rollout_customers,
    gate_experiment,
    gate_rollout,
)

#: A proposal that violates nothing. Each test below breaks exactly one field.
CLEAN = dict(
    experiment_id="exp_clean",
    projected_spend_inr=40_000.0,
    remaining_budget_inr=400_000.0,
    discount_depth=0.08,
    contribution_margin=0.30,
    customers_treated=6_000,
    population=20_000,
    power=0.80,
)


def _fired(verdict: PolicyVerdict) -> set[Rule]:
    return {v.rule for v in verdict.violations}


def test_a_clean_proposal_is_approved() -> None:
    verdict = gate_experiment(**CLEAN)
    assert verdict.approved
    assert verdict.violations == ()
    assert set(verdict.checked) == set(Rule), "every rule must be checked, not just the ones that fire"


def test_rejects_spend_beyond_remaining_budget() -> None:
    verdict = gate_experiment(**{**CLEAN, "projected_spend_inr": 400_001.0})
    assert not verdict.approved
    assert _fired(verdict) == {Rule.REMAINING_BUDGET}
    violation = verdict.violations[0]
    assert violation.observed == 400_001.0
    assert violation.limit == 400_000.0
    assert "exceeds remaining budget" in violation.message


def test_rejects_a_discount_above_the_ceiling() -> None:
    verdict = gate_experiment(**{**CLEAN, "discount_depth": 0.26})
    assert not verdict.approved
    assert _fired(verdict) == {Rule.MAX_DISCOUNT}
    assert verdict.violations[0].observed == pytest.approx(0.26)
    assert verdict.violations[0].limit == pytest.approx(0.25)


def test_rejects_a_margin_below_the_floor() -> None:
    verdict = gate_experiment(**{**CLEAN, "contribution_margin": 0.14})
    assert not verdict.approved
    assert _fired(verdict) == {Rule.MIN_CONTRIBUTION_MARGIN}
    assert "below floor" in verdict.violations[0].message


def test_rejects_exposure_beyond_the_cap() -> None:
    """One campaign may not consume the customer base every later question needs."""
    verdict = gate_experiment(**{**CLEAN, "customers_treated": 14_000})
    assert not verdict.approved
    assert _fired(verdict) == {Rule.MAX_CUSTOMER_EXPOSURE}
    assert verdict.violations[0].observed == pytest.approx(0.70)


def test_rejects_an_underpowered_design() -> None:
    verdict = gate_experiment(**{**CLEAN, "power": 0.79})
    assert not verdict.approved
    assert _fired(verdict) == {Rule.MIN_EXPERIMENT_POWER}
    assert "unreadable" in verdict.violations[0].message


def test_every_violated_rule_is_reported_not_just_the_first() -> None:
    """The agent has to re-plan against the verdict; one rule at a time would
    make that a guessing game."""
    verdict = gate_experiment(
        experiment_id="exp_bad", projected_spend_inr=1e9, remaining_budget_inr=1_000.0,
        discount_depth=0.90, contribution_margin=0.01, customers_treated=99_000,
        population=100_000, power=0.10,
    )
    assert _fired(verdict) == set(Rule)


def test_verdicts_name_the_rule_and_the_value_never_a_bare_boolean() -> None:
    verdict = gate_experiment(**{**CLEAN, "discount_depth": 0.40})
    payload = verdict.to_dict()
    assert payload["violations"][0]["rule"] == "max_discount"
    assert payload["violations"][0]["observed"] == pytest.approx(0.40)
    assert payload["violations"][0]["limit"] == pytest.approx(0.25)
    assert payload["reason"]


# --------------------------------------------------------------------------- #
# The rollout gate — the hole Day 5 measured
# --------------------------------------------------------------------------- #


def test_the_rollout_gate_refuses_spend_beyond_budget() -> None:
    verdict = gate_rollout(
        experiment_id="exp_r", projected_spend_inr=500_000.0, remaining_budget_inr=100_000.0,
        discount_depth=0.08, contribution_margin=0.30, customers_treated=5_000, population=20_000,
    )
    assert not verdict.approved
    assert Rule.REMAINING_BUDGET in _fired(verdict)


def test_the_rollout_gate_does_not_recheck_power() -> None:
    """The experiment already ran; its readability is settled."""
    verdict = gate_rollout(
        experiment_id="exp_r", projected_spend_inr=1_000.0, remaining_budget_inr=100_000.0,
        discount_depth=0.08, contribution_margin=0.30, customers_treated=5_000, population=20_000,
    )
    assert Rule.MIN_EXPERIMENT_POWER not in set(verdict.checked)
    assert verdict.approved


def test_the_gate_says_how_much_is_affordable_not_just_no() -> None:
    """Refusing outright would throw away a campaign the merchant can part-fund."""
    permitted = affordable_rollout_customers(
        remaining_budget_inr=10_000.0, cost_per_treated_customer_inr=5.0, population=20_000
    )
    assert permitted == 2_000

    # Bounded by the exposure cap even when the budget would allow more.
    capped = affordable_rollout_customers(
        remaining_budget_inr=1e9, cost_per_treated_customer_inr=5.0, population=20_000
    )
    assert capped == 12_000  # 60% of 20,000


def test_limits_are_configurable_per_merchant() -> None:
    strict = PolicyLimits(max_discount_pct=0.05)
    assert not gate_experiment(**{**CLEAN, "discount_depth": 0.08}, limits=strict).approved
    assert gate_experiment(**CLEAN).approved
