"""Budget overruns must now be structurally impossible.

Day 5 recorded four to seven overruns per run: the pilot was gated and the
rollout was not, so a scaled campaign spent whatever the remaining population
happened to cost. Scaling is the larger of the two spends.
"""

from __future__ import annotations

import pytest

from src.baselines import ALL_BASELINES
from src.eval.harness import run_world
from src.world.generator import generate

SEEDS = (1, 2, 3, 4, 5)


@pytest.mark.parametrize("strategy", ALL_BASELINES, ids=lambda s: s.name)
def test_no_strategy_can_exceed_its_budget(strategy) -> None:
    for seed in SEEDS:
        world, truth = generate(seed)
        result = run_world(strategy, world, truth)
        assert not result.budget_overrun, (
            f"{strategy.name} overspent on {world.world_id}: "
            f"Rs.{result.promotion_spend_inr:,.0f} against a budget of "
            f"Rs.{result.budget_inr:,.0f}"
        )
        del world, truth


def test_a_scaled_rollout_is_gated_not_just_the_pilot() -> None:
    """The specific hole Day 5 measured."""
    from src.policy.gates import PolicyLimits

    world, truth = generate(5)
    # A budget too small to fund any rollout: scaling must be refused, and the
    # refusal must be recorded rather than silently overspending.
    tight = PolicyLimits(min_budget_headroom_share=0.999)
    result = run_world(ALL_BASELINES[4], world, truth, limits=tight)

    assert not result.budget_overrun
    for outcome in result.outcomes:
        if outcome.launched and not outcome.untested:
            assert not outcome.scaled or outcome.rollout_spend_inr == 0.0


def test_an_untested_campaign_is_trimmed_to_what_the_budget_allows() -> None:
    """Baseline 2 and 4 spend without testing; the gate still binds on them."""
    from src.baselines import RuleBasedMarketer

    world, truth = generate(2)
    result = run_world(RuleBasedMarketer(), world, truth)
    assert not result.budget_overrun
    assert result.promotion_spend_inr <= result.budget_inr
