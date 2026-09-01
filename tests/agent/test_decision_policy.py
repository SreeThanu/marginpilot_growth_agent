"""The deterministic layer must be the authority, and must fail closed.

Every test here is an attempt to make the system approve spending it should not.
"""

from __future__ import annotations

import pytest

from src.agent.brief import build_brief
from src.agent.decision_policy import (
    MDE_FRACTION_OF_ORDER_CONTRIBUTION,
    decide_after_experiment,
    recommend,
    recommend_from_raw,
)
from src.agent.net_value import project_net, required_break_even_lift
from src.agent.recommendation import (
    UNRESOLVED_VALUE_OF_INFORMATION,
    EvidenceBasis,
    ProposalRejected,
    RecommendationDecision,
    validate_proposal,
)
from src.baselines.engine_without_llm import EngineWithoutLLM
from src.experiment.evaluator import ArmObservation, evaluate
from src.experiment.registry import (
    ExperimentRegistry,
    design_experiment_on_contribution,
)

from demo.fixtures import (
    SCENARIO_A,
    SCENARIO_B,
    SCENARIO_C,
    FixtureExecutor,
    build_view,
    locked_fingerprint,
    proposal_payload,
)


@pytest.fixture(scope="module")
def brief_c():
    return build_brief(build_view(SCENARIO_C))


@pytest.fixture(scope="module")
def brief_a():
    return build_brief(build_view(SCENARIO_A))


# --------------------------------------------------------------------------- #
# Economics
# --------------------------------------------------------------------------- #


def test_break_even_lift_is_the_hand_computed_value() -> None:
    """L = p0*I/(C-I). At p0=0.08, C=540, I=60 that is 0.08*60/480 = 0.01."""
    assert required_break_even_lift(
        baseline_conversion=0.08,
        contribution_per_order_inr=540.0,
        incentive_cost_per_order_inr=60.0,
    ) == pytest.approx(0.01)


def test_break_even_is_unreachable_when_the_incentive_eats_the_order() -> None:
    assert required_break_even_lift(
        baseline_conversion=0.10,
        contribution_per_order_inr=132.0,
        incentive_cost_per_order_inr=132.0,
    ) is None


def test_the_readme_worked_example_reproduces() -> None:
    """1,000 treated, 60 incremental orders, Rs.14,400 earned, Rs.18,000 spent."""
    projection = project_net(
        customers_treated=1_000,
        baseline_conversion=0.12,
        expected_lift_absolute=0.06,
        contribution_per_order_inr=240.0,
        incentive_cost_per_order_inr=100.0,
    )
    assert projection.incremental_orders == pytest.approx(60.0)
    assert projection.incremental_contribution_inr == pytest.approx(14_400.0)
    assert projection.incentive_cost_inr == pytest.approx(18_000.0)
    assert projection.net_contribution_inr == pytest.approx(-3_600.0)


def test_cost_is_charged_on_every_treated_order_not_only_incremental_ones() -> None:
    """The always-buyer penalty. 180 treated orders, only 60 of them incremental."""
    projection = project_net(
        customers_treated=1_000,
        baseline_conversion=0.12,
        expected_lift_absolute=0.06,
        contribution_per_order_inr=240.0,
        incentive_cost_per_order_inr=100.0,
    )
    assert projection.treated_orders == pytest.approx(180.0)
    assert projection.incentive_cost_inr > projection.incremental_orders * 100.0


def test_a_positive_conversion_lift_can_still_be_a_negative_net(brief_a) -> None:
    """ADV-4 in economic form: conversion is not the objective."""
    proposal = validate_proposal(proposal_payload(SCENARIO_A))
    result = recommend(brief_a, proposal)
    assert proposal.expected_lift_absolute > 0
    assert result.expected_net_contribution_inr < 0
    assert result.decision is RecommendationDecision.DO_NOT_PROMOTE


def test_mde_matches_the_committed_baseline_constant() -> None:
    """The one duplicated value in the product, bound to its origin by test."""
    assert MDE_FRACTION_OF_ORDER_CONTRIBUTION == (
        EngineWithoutLLM().mde_fraction_of_order_contribution
    )


# --------------------------------------------------------------------------- #
# Adversarial
# --------------------------------------------------------------------------- #


def test_adv1_model_asking_to_promote_cannot_override_negative_economics(brief_a) -> None:
    raw = proposal_payload(SCENARIO_A)
    assert raw["requested_decision"] == "PROMOTE"
    result = recommend_from_raw(brief_a, raw)
    assert result.decision is RecommendationDecision.DO_NOT_PROMOTE
    assert result.overruled_the_model


def test_adv2_a_pilot_that_exceeds_budget_is_refused(brief_c) -> None:
    proposal = validate_proposal(proposal_payload(SCENARIO_C))
    result = recommend(brief_c, proposal, spent_inr=brief_c.budget_inr)
    assert result.decision is RecommendationDecision.DO_NOT_PROMOTE
    assert any("G4" in c or "BUDGET" in c.upper() for c in result.binding_constraints)


def test_adv3_prior_and_history_evidence_never_reach_promote(brief_c) -> None:
    for basis in ("PRIOR", "HISTORY", "EXPERIMENT"):
        raw = proposal_payload(SCENARIO_C) | {"evidence_basis": basis}
        result = recommend_from_raw(brief_c, raw)
        assert result.decision is not RecommendationDecision.PROMOTE, basis


def test_adv6_malformed_model_output_fails_closed(brief_c) -> None:
    for raw in ({}, {"intervention_id": "x"}, {"citations": []}, "not a mapping"):
        result = recommend_from_raw(brief_c, raw)
        assert result.decision is RecommendationDecision.INSUFFICIENT_EVIDENCE
        assert "PROPOSAL_REJECTED" in result.binding_constraints


def test_adv7_a_deliberately_losing_fixture_is_refused(brief_a) -> None:
    """Must never be weakened to accommodate a demo."""
    result = recommend_from_raw(brief_a, proposal_payload(SCENARIO_A))
    assert result.decision is RecommendationDecision.DO_NOT_PROMOTE


def test_adv9_ground_truth_in_a_proposal_is_rejected() -> None:
    for poison in (
        {"mechanism": "y1 minus y0 is positive"},
        {"hypothesis": "the ground_truth shows a lift"},
        {"cohort_id": "high responsiveness"},
        {"mechanism": "the shipping affinity is high"},
    ):
        raw = proposal_payload(SCENARIO_C) | poison
        with pytest.raises(ProposalRejected):
            validate_proposal(raw)


def test_adv8_segment_identity_in_a_proposal_is_rejected() -> None:
    raw = proposal_payload(SCENARIO_C) | {"cohort_id": "segment_name:Deal seekers"}
    with pytest.raises(ProposalRejected):
        validate_proposal(raw)


def test_a_proposal_without_citations_is_rejected() -> None:
    raw = proposal_payload(SCENARIO_C) | {"citations": []}
    with pytest.raises(ProposalRejected):
        validate_proposal(raw)


def test_adv12_scenario_c_parameters_and_seed_are_unchanged() -> None:
    """The fixture lock was committed before the first execution."""
    assert SCENARIO_C.fingerprint() == locked_fingerprint(), (
        "Scenario C's declared parameters or seed changed after the lock was "
        "committed. That is demo tuning, and it invalidates the scenario."
    )


# --------------------------------------------------------------------------- #
# The experiment path
# --------------------------------------------------------------------------- #


def _run_pilot(spec, *, observations=None):
    """Design, launch and read one pilot for a fixture."""
    brief = build_brief(build_view(spec))
    proposal = validate_proposal(proposal_payload(spec))
    economics = brief.economics_for(proposal.cohort_id, proposal.intervention_id)
    design = design_experiment_on_contribution(
        experiment_id=f"{brief.merchant_id}_test",
        world_id=brief.merchant_id,
        intervention_id=proposal.intervention_id,
        hypothesis_id="hyp",
        prediction=proposal.hypothesis,
        reasoning=proposal.mechanism,
        baseline_conversion=brief.observed_conversion,
        expected_effect_absolute=proposal.expected_lift_absolute,
        contribution_per_incremental_order_inr=economics.contribution_per_order_inr,
        incentive_cost_per_treated_order_inr=economics.incentive_cost_per_order_inr,
        mde_contribution_per_customer_inr=economics.contribution_per_order_inr * 0.02,
        success_condition="s",
        failure_condition="f",
        budget_inr=brief.budget_inr,
    )
    registry = ExperimentRegistry()
    registry.register(design)
    launched = registry.launch(design.experiment_id)
    executor = FixtureExecutor(spec)
    obs = observations(launched) if observations else executor.observe(
        launched, proposal.intervention_id
    )
    return brief, proposal, launched, executor, evaluate(launched, obs)


def test_adv4_a_negative_experiment_does_not_promote() -> None:
    def losing(launched):
        n = launched.horizon_per_arm
        return (
            ArmObservation(0, "control", n, int(n * 0.08), 43.2, 146.0),
            ArmObservation(1, "treatment", n, int(n * 0.08), 30.0, 146.0),
        )

    brief, proposal, launched, executor, result = _run_pilot(SCENARIO_C, observations=losing)
    final = decide_after_experiment(
        brief, proposal, result,
        rollout_population=executor.population_not_in_experiment(launched),
        spent_inr=0.0,
    )
    assert final.decision is RecommendationDecision.DO_NOT_PROMOTE


def test_adv5_a_positive_experiment_with_no_affordable_rollout_does_not_promote() -> None:
    """Budget exhausted, so the rollout the merchant can fund is nobody."""
    brief, proposal, launched, executor, result = _run_pilot(SCENARIO_C)
    final = decide_after_experiment(
        brief, proposal, result,
        rollout_population=executor.population_not_in_experiment(launched),
        spent_inr=brief.budget_inr,
    )
    assert final.decision is not RecommendationDecision.PROMOTE


def test_adv10_a_zero_size_rollout_cannot_promote_however_good_the_result() -> None:
    brief, proposal, launched, executor, result = _run_pilot(SCENARIO_C)
    final = decide_after_experiment(
        brief, proposal, result, rollout_population=0, spent_inr=0.0,
    )
    assert final.decision is RecommendationDecision.DO_NOT_PROMOTE
    assert final.expected_net_contribution_inr <= 0


def test_an_interim_result_can_never_promote() -> None:
    """No verdict before the horizon, so no rollout before the horizon."""
    def thin(launched):
        n = max(launched.horizon_per_arm // 4, 1)
        return (
            ArmObservation(0, "control", n, int(n * 0.08), 43.2, 146.0),
            ArmObservation(1, "treatment", n, int(n * 0.12), 60.0, 160.0),
        )

    brief, proposal, launched, executor, result = _run_pilot(SCENARIO_C, observations=thin)
    final = decide_after_experiment(
        brief, proposal, result,
        rollout_population=executor.population_not_in_experiment(launched),
        spent_inr=0.0,
    )
    assert final.decision is RecommendationDecision.RUN_EXPERIMENT_FIRST


def test_scenario_b_recommends_an_experiment_and_surfaces_the_open_question() -> None:
    brief = build_brief(build_view(SCENARIO_B))
    result = recommend_from_raw(brief, proposal_payload(SCENARIO_B))
    assert result.decision is RecommendationDecision.RUN_EXPERIMENT_FIRST
    assert UNRESOLVED_VALUE_OF_INFORMATION in result.unresolved
    assert result.evidence_basis is EvidenceBasis.HISTORY
