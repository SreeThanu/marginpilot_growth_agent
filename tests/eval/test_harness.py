"""The measurement spine, and the leak it must not have.

The spine runs with no LLM anywhere in it. The strategy sees a MerchantView and
nothing else — if it could see world parameters or potential outcomes it would
not need to experiment, and the evaluation would measure nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.agent.stub import StubAgent
from src.eval.contracts import ExperimentProposal, MerchantView, Strategy, merchant_view
from src.eval.harness import metrics_table, run_world, run_worlds
from src.eval.replay import DECISION_RULES, replay, replay_table
from src.world.generator import generate


def test_merchant_view_leaks_no_latent_parameters() -> None:
    """The view is built by explicit field selection, so a latent added to
    WorldParams later is invisible here by default."""
    world, _ = generate(7)
    view = merchant_view(world)

    exposed = {f.name for f in dataclasses.fields(view)}
    forbidden = {
        "params", "promo_response_scale", "competitive_pressure", "shipping_affinity",
        "clearance_affinity", "pct_affinity", "bundle_affinity", "elasticity_mean",
        "cannibalization_rate", "truth", "ground_truth", "outcomes",
    }
    assert not exposed & forbidden

    # Customers are exposed, but only as behavioural history. The latent
    # parameters a strategy is supposed to estimate must not ride along.
    customer_fields = {f.name for f in dataclasses.fields(view.customers[0])}
    assert not customer_fields & {
        "baseline_purchase_prob", "price_elasticity", "responsiveness",
        "expected_order_value_inr",
    }

    flattened = repr(view)
    for marker in ("promo_response_scale", "affinity", "elasticity_mean", "cannibalization"):
        assert marker not in flattened, f"MerchantView leaks {marker}"


def test_segment_view_carries_notes_but_not_multipliers() -> None:
    """The qualitative note is the reasoning surface; the multipliers are the
    answer the agent is supposed to estimate."""
    world, _ = generate(8)
    segment = merchant_view(world).segments[0]
    exposed = {f.name for f in dataclasses.fields(segment)}
    assert "notes" in exposed
    assert not exposed & {
        "elasticity_multiplier", "responsiveness_mean", "conversion_multiplier", "aov_multiplier"
    }


def test_the_stub_satisfies_the_strategy_protocol_and_uses_no_llm() -> None:
    import inspect

    from src.agent import stub

    assert isinstance(StubAgent(), Strategy)
    source = inspect.getsource(stub)
    for marker in ("anthropic", "openai", "import llm", "api_key"):
        assert marker not in source.lower()


def test_a_proposal_cannot_carry_an_arm_assignment_or_a_horizon() -> None:
    """Strategies propose; the engine disposes (CLAUDE.md invariants 1 and 3)."""
    fields = {f.name for f in dataclasses.fields(ExperimentProposal)}
    assert not fields & {
        "horizon", "horizon_per_arm", "n_per_arm", "sample_size", "arm", "assignment", "seed"
    }


def test_spine_runs_end_to_end_on_a_dev_world() -> None:
    world, truth = generate(5)
    result = run_world(StubAgent(), world, truth)

    assert result.experiments_launched == 1
    outcome = result.outcomes[0]
    assert outcome.horizon_per_arm > 0
    assert outcome.n_control == outcome.n_treatment == outcome.horizon_per_arm
    # Every arm reached its horizon, so a verdict exists.
    assert outcome.verdict in {"scale", "kill", "inconclusive"}
    # Spend is real and within budget.
    assert outcome.pilot_spend_inr > 0
    assert result.promotion_spend_inr <= result.budget_inr
    assert not result.budget_overrun


def test_scaling_requires_both_the_decision_rule_and_the_policy_gate() -> None:
    """Two independent conditions, and the gate can veto the rule.

    The decision rule says the evidence supports spending; the policy gate says
    the merchant can afford it and it stays inside the discount, margin and
    exposure limits. Either can refuse alone, and a scale needs both — which is
    why this asserts an implication rather than an equality.
    """
    for seed in (1, 2, 3, 4, 5):
        world, truth = generate(seed)
        for outcome in run_world(StubAgent(), world, truth).outcomes:
            if not outcome.launched:
                continue
            if outcome.scaled:
                # Scaling implies the posterior rule was satisfied...
                assert outcome.probability_net_positive >= 0.80
                assert outcome.projected_downside_inr > -outcome.tolerable_loss_inr
                # ...and that the gate did not refuse.
                assert "REJECTED" not in outcome.policy_reason
        del world, truth


def test_metrics_table_reports_real_numbers() -> None:
    results = run_worlds(StubAgent(), [1, 2])
    table = metrics_table(results)
    assert "TOTAL" in table
    assert "experiments launched      : 2" in table
    assert all(r.promotion_spend_inr > 0 for r in results)


def test_replay_prices_every_rule_against_the_same_worlds() -> None:
    results = run_worlds(StubAgent(), [1, 2, 3])
    rows = replay(results)
    assert set(rows) == set(DECISION_RULES)

    never = sum(r.realized_net_inr for r in rows["never_scale"])
    always = sum(r.realized_net_inr for r in rows["always_scale"])
    oracle = sum(r.realized_net_inr for r in rows["oracle"])
    ci_rule = sum(r.realized_net_inr for r in rows["ci_lower_bound"])

    # The oracle bounds every achievable rule, by construction.
    assert oracle >= always
    assert oracle >= never
    assert oracle >= ci_rule
    assert "ci_lower_bound" in replay_table(results)


def test_never_scale_never_spends_on_rollout() -> None:
    results = run_worlds(StubAgent(), [1, 2])
    for row in replay(results)["never_scale"]:
        assert row.scaled is False


def test_an_overspent_strategy_is_refused_rather_than_crashing() -> None:
    """A strategy that has exhausted its budget must be told 'no', not error.

    Baseline 5 proposes four experiments; if the first is scaled the rollout can
    consume the budget, and the remaining proposals then have negative funds
    available. That is a refusal — a first-class outcome — not an exception.
    """
    from src.baselines import EngineWithoutLLM

    world, truth = generate(3)
    result = run_world(EngineWithoutLLM(), world, truth)
    assert result.outcomes, "the engine should have attempted something"
    # Whatever happened, every proposal resolved to a launch or a refusal.
    for outcome in result.outcomes:
        assert outcome.launched or outcome.refusal_reason
