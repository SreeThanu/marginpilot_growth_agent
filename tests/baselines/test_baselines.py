"""The baselines, and the properties that make them a fair comparison.

Each baseline's defining flaw has to be real and has to be the *only* thing that
differs from MarginPilot. A strawman baseline would make the headline claim
worthless, so the tests below pin what each one may and may not do.
"""

from __future__ import annotations

import inspect

import pytest

from src.baselines import (
    ALL_BASELINES,
    ConversionOptimizer,
    DoNothing,
    EngineWithoutLLM,
    LearnOnly,
    RuleBasedMarketer,
)
from src.eval.contracts import DirectAction, ExperimentProposal, ScalingRule, Strategy, merchant_view
from src.eval.harness import run_world
from src.world.generator import generate


@pytest.fixture(scope="module")
def world_and_truth():
    return generate(6)


def test_every_baseline_implements_one_interface(world_and_truth) -> None:
    """A comparison is only fair if all of them see exactly the same thing."""
    world, _ = world_and_truth
    view = merchant_view(world)
    for baseline in ALL_BASELINES:
        assert isinstance(baseline, Strategy)
        assert isinstance(baseline.scaling_rule, ScalingRule)
        for proposal in baseline.decide(view, view.budget_inr):
            assert isinstance(proposal, (ExperimentProposal, DirectAction))


def test_do_nothing_does_nothing(world_and_truth) -> None:
    """The honest floor: no experiments, no spend, no realized contribution."""
    world, truth = world_and_truth
    result = run_world(DoNothing(), world, truth)
    assert result.outcomes == []
    assert result.promotion_spend_inr == 0.0
    assert result.incremental_contribution_inr == 0.0
    assert result.cost_of_learning_inr == 0.0


def test_learn_only_runs_the_same_experiments_as_the_engine_and_scales_none(
    world_and_truth,
) -> None:
    """Its realized net is the cost of learning with the winnings removed."""
    world, truth = world_and_truth
    view = merchant_view(world)
    assert [p.intervention_id for p in LearnOnly().decide(view, view.budget_inr)] == [
        p.intervention_id for p in EngineWithoutLLM().decide(view, view.budget_inr)
    ]

    result = run_world(LearnOnly(), world, truth)
    assert result.experiments_scaled == 0
    assert result.cost_of_learning_inr == pytest.approx(result.promotion_spend_inr)
    assert result.incremental_contribution_inr <= 0


def test_rule_based_never_experiments_and_so_never_learns(world_and_truth) -> None:
    world, truth = world_and_truth
    result = run_world(RuleBasedMarketer(), world, truth)
    assert result.experiments_launched == 0
    assert result.untested_campaigns == 1
    # It spends, but none of that spend buys information.
    assert result.promotion_spend_inr > 0
    assert result.cost_of_learning_inr == 0.0


def test_rule_based_targets_on_observable_history_not_latent_propensity() -> None:
    """Keying the rule on the true purchase probability would be reading the
    answer. The proxy is recency and frequency, which a merchant actually has."""
    source = inspect.getsource(RuleBasedMarketer)
    for latent in ("baseline_purchase_prob", "price_elasticity", "responsiveness"):
        assert latent not in source


def test_conversion_optimizer_scales_on_conversion_not_contribution() -> None:
    optimizer = ConversionOptimizer()
    assert optimizer.scaling_rule is ScalingRule.CONVERSION_LIFT

    from src.eval.harness import _should_scale
    from src.experiment.evaluator import ArmComparison, FinalResult

    # A campaign with a clear conversion win and a clearly negative contribution:
    # the exact case the project is built around.
    comparison = ArmComparison(
        arm=1, name="treatment", n_control=5000, n_treatment=5000,
        conversion_control=0.12, conversion_treatment=0.18,
        absolute_difference=0.06, difference_ci_low=0.045, difference_ci_high=0.075,
        p_value=1e-9,
        net_contribution_inr=-18_000.0,
        contribution_ci_low=-31_000.0, contribution_ci_high=-5_000.0,
    )
    final = FinalResult("exp", 0.05, 5000, (comparison,))

    assert _should_scale(ScalingRule.CONVERSION_LIFT, final) is True
    assert _should_scale(ScalingRule.CI_LOWER_BOUND, final) is False


def test_the_ablation_reads_no_semantic_context() -> None:
    """Baseline 5 has the machinery and not the reasoning.

    If it could read the merchant's story, the Day 9 comparison against
    MarginPilot would no longer isolate what semantic reasoning is worth.
    """
    from src.baselines import engine_without_llm

    source = inspect.getsource(engine_without_llm)
    for banned in (".semantic", "seasonal_events", "competitor_events", "customer_service_themes"):
        assert banned not in source


def test_the_ablation_uses_the_same_machinery_as_marginpilot() -> None:
    """Same decision rule, same contribution-powered horizon. Only reasoning differs.

    If the ablation ever decides on a different rule, the Day 9 comparison stops
    measuring what semantic reasoning is worth and starts measuring a difference
    in decision policy instead.
    """
    assert EngineWithoutLLM().scaling_rule is ScalingRule.BAYESIAN_POSTERIOR


def test_the_ablation_pays_for_its_own_experiments() -> None:
    """Four experiments per world is Baseline 5's choice, not a free allowance.

    Experimentation is scarce — one experiment costs several times the profit
    pool of the world it runs in — so testing a fixed list of four is the cost
    of having no way to decide which single question is worth asking.
    """
    assert EngineWithoutLLM().max_experiments == 4
    assert DoNothing().max_experiments == 0
    assert RuleBasedMarketer().max_experiments == 0
    assert ConversionOptimizer().max_experiments == 1


def test_the_harness_enforces_the_declared_allowance() -> None:
    """A strategy cannot quietly run more experiments than it declared."""
    import dataclasses

    world, truth = generate(4)
    capped = dataclasses.replace(EngineWithoutLLM(), max_experiments=1)
    result = run_world(capped, world, truth)

    assert result.experiments_launched == 1
    refused = [o for o in result.outcomes if not o.launched]
    assert refused, "the remaining proposals should be refused, not silently dropped"
    assert any("allowance" in o.refusal_reason for o in refused)


def test_the_ablation_order_is_preset_and_not_data_driven(world_and_truth) -> None:
    """Reordering per merchant would be a form of reasoning — the thing ablated."""
    world, _ = world_and_truth
    other, _ = generate(9)
    first = [p.intervention_id for p in EngineWithoutLLM().decide(merchant_view(world), 1e9)]
    second = [p.intervention_id for p in EngineWithoutLLM().decide(merchant_view(other), 1e9)]
    assert first == second


def test_no_baseline_can_touch_arm_assignment() -> None:
    """CLAUDE.md invariant 1, at the level of the proposal type."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(ExperimentProposal)}
    assert not fields & {"arm", "assignment", "seed", "horizon", "n_per_arm"}
