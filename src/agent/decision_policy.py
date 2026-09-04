"""The deterministic decision. The model proposes; this module disposes.

Six ordered gates. The first that fires returns, and no gate can be reached
around:

    G1  valid input .......... is there a proposal we can price at all?
    G2  break-even economics . can this campaign reach positive net contribution?
    G3  evidence quality ..... is the confidence sourced from a measurement?
    G4  learning economics ... can the merchant afford to find out?
    G5  exposure / budget .... does the pilot pass the standing policy limits?
    G6  rollout approval ..... does the measured result justify spending?

Two entry points, and the asymmetry between them is the design:

* :func:`recommend` runs G1–G5 and **can never return PROMOTE**. A model that
  claims experimental confidence without an experiment is not evidence, so the
  pre-experiment path tops out at RUN_EXPERIMENT_FIRST.
* :func:`decide_after_experiment` runs G3 and G6 against a real
  :class:`~src.experiment.evaluator.FinalResult`. This is the only route to
  PROMOTE.

**G4 is scoped to affordability only.** Whether an experiment costs less than
the information it buys is unresolved in this project (SCI-3), and no threshold
for it exists in the committed constants. Rather than invent one, every
experiment recommendation carries
``G4_VALUE_OF_INFORMATION_UNRESOLVED`` through to the merchant. An explicitly
open question is worth more than a fabricated precision.
"""

from __future__ import annotations

from src.agent.brief import MerchantBrief
from src.agent.net_value import (
    NetProjection,
    cost_per_treated_customer_inr,
    project_net,
)
from src.agent.recommendation import (
    UNRESOLVED_VALUE_OF_INFORMATION,
    EvidenceBasis,
    MerchantRecommendation,
    Proposal,
    ProposalRejected,
    RecommendationDecision,
    validate_proposal,
)
from src.agent.tools import TOLERABLE_LOSS_FRACTION_OF_BUDGET
from src.experiment import power as power_module
from src.experiment.evaluator import (
    ArmComparison,
    FinalResult,
    InterimResult,
    ScaleDecision,
    assess_scale,
)
from src.policy.gates import (
    PolicyLimits,
    affordable_rollout_customers,
    gate_experiment,
    gate_rollout,
)

#: Smallest per-customer contribution effect worth resolving, as a share of
#: contribution per order.
#:
#: **Not a new constant.** This mirrors
#: ``EngineWithoutLLM.mde_fraction_of_order_contribution``, the value fixed
#: before any world was seen and used by every cycle and post-hoc diagnostic in
#: the project. ``tests/agent/test_decision_policy.py`` asserts the two stay
#: equal, so the duplication cannot silently drift.
MDE_FRACTION_OF_ORDER_CONTRIBUTION = 0.02


def _cohort(brief: MerchantBrief, cohort_id: str):
    return brief.whole_base if cohort_id == "ALL" else brief.cohort(cohort_id)


def _diagnosis(brief: MerchantBrief, projection: NetProjection) -> str:
    break_even = projection.required_break_even_lift_absolute
    if break_even is None:
        return (
            f"Each order earns Rs.{projection.contribution_per_order_inr:,.0f} of "
            f"contribution and the incentive costs Rs."
            f"{projection.incentive_cost_per_order_inr:,.0f} of it. The promotion "
            "cannot pay for itself at any response level."
        )
    return (
        f"Baseline conversion is {brief.observed_conversion:.1%}. This promotion "
        f"needs a lift of {break_even:.2%} before it breaks even, because the "
        f"incentive is charged on every treated order, not only the extra ones."
    )


def recommend(
    brief: MerchantBrief,
    proposal: Proposal,
    *,
    limits: PolicyLimits | None = None,
    spent_inr: float = 0.0,
) -> MerchantRecommendation:
    """Decide what to do before any experiment has run.

    Never returns PROMOTE. Spending requires a measurement, and nothing here has
    one.
    """
    limits = limits or PolicyLimits()
    remaining_budget = max(brief.budget_inr - spent_inr, 0.0)
    requested = proposal.requested_decision
    gates: list[str] = []

    # ---- G1: is the proposal something we can price at all? ----------------
    try:
        intervention = brief.intervention(proposal.intervention_id)
        cohort = _cohort(brief, proposal.cohort_id)
        economics = brief.economics_for(cohort.cohort_id, intervention.intervention_id)
    except KeyError as exc:
        return MerchantRecommendation(
            decision=RecommendationDecision.INSUFFICIENT_EVIDENCE,
            diagnosis="The proposal does not refer to anything in this merchant's data.",
            rationale=f"G1 failed: unknown reference {exc}.",
            intervention_id=None,
            cohort_id=None,
            expected_incremental_contribution_inr=0.0,
            expected_incentive_cost_inr=0.0,
            expected_net_contribution_inr=0.0,
            required_break_even_lift_absolute=None,
            evidence_basis=EvidenceBasis.NONE,
            experiment_required=False,
            binding_constraints=("G1_INVALID_INPUT",),
            citations=proposal.citations,
            model_requested=requested,
        )
    gates.append("G1")

    projection = project_net(
        customers_treated=cohort.n_customers,
        baseline_conversion=brief.observed_conversion,
        expected_lift_absolute=proposal.expected_lift_absolute,
        contribution_per_order_inr=economics.contribution_per_order_inr,
        incentive_cost_per_order_inr=economics.incentive_cost_per_order_inr,
    )
    diagnosis = _diagnosis(brief, projection)

    def _refuse(reason: str, constraint: str) -> MerchantRecommendation:
        return MerchantRecommendation(
            decision=RecommendationDecision.DO_NOT_PROMOTE,
            diagnosis=diagnosis,
            rationale=reason,
            intervention_id=intervention.intervention_id,
            cohort_id=cohort.cohort_id,
            expected_incremental_contribution_inr=projection.incremental_contribution_inr,
            expected_incentive_cost_inr=projection.incentive_cost_inr,
            expected_net_contribution_inr=projection.net_contribution_inr,
            required_break_even_lift_absolute=projection.required_break_even_lift_absolute,
            evidence_basis=proposal.evidence_basis,
            experiment_required=False,
            customers_treated=cohort.n_customers,
            binding_constraints=(constraint,),
            citations=proposal.citations,
            model_requested=requested,
            gates_passed=tuple(gates),
        )

    # ---- G2: can this reach positive net contribution at all? --------------
    if projection.required_break_even_lift_absolute is None:
        return _refuse(
            "G2 failed: contribution per order does not exceed the incentive per "
            "order, so no conversion lift makes this campaign profitable.",
            "G2_BREAK_EVEN_UNREACHABLE",
        )
    if not projection.is_positive:
        return _refuse(
            f"G2 failed: at the proposed lift of {proposal.expected_lift_absolute:.2%} "
            f"the campaign earns Rs.{projection.incremental_contribution_inr:,.0f} and "
            f"costs Rs.{projection.incentive_cost_inr:,.0f}, a net of "
            f"Rs.{projection.net_contribution_inr:,.0f}.",
            "G2_NEGATIVE_EXPECTED_NET",
        )
    gates.append("G2")

    # ---- G3: is the confidence sourced from a measurement? -----------------
    # PRIOR and HISTORY can raise a question. Neither can authorise spending,
    # and a model asserting EXPERIMENT without one is not taken at its word.
    gates.append("G3")

    # ---- G4: can the merchant afford to find out? --------------------------
    mde = economics.contribution_per_order_inr * MDE_FRACTION_OF_ORDER_CONTRIBUTION
    feasibility = power_module.assess_feasibility(
        brief.observed_conversion,
        proposal.expected_lift_absolute,
        contribution_per_incremental_order_inr=economics.contribution_per_order_inr,
        incentive_cost_per_treated_order_inr=economics.incentive_cost_per_order_inr,
        mde_contribution_per_customer_inr=mde,
        remaining_budget_inr=remaining_budget,
        population=brief.population,
    )
    unresolved = (UNRESOLVED_VALUE_OF_INFORMATION,)

    if not feasibility.feasible:
        return MerchantRecommendation(
            decision=RecommendationDecision.DO_NOT_PROMOTE,
            diagnosis=diagnosis,
            rationale=(
                f"G4 failed: the experiment needed to answer this cannot be run "
                f"within budget or population. {feasibility.reason}"
            ),
            intervention_id=intervention.intervention_id,
            cohort_id=cohort.cohort_id,
            expected_incremental_contribution_inr=projection.incremental_contribution_inr,
            expected_incentive_cost_inr=projection.incentive_cost_inr,
            expected_net_contribution_inr=projection.net_contribution_inr,
            required_break_even_lift_absolute=projection.required_break_even_lift_absolute,
            evidence_basis=proposal.evidence_basis,
            experiment_required=True,
            experiment_horizon_per_arm=feasibility.required_n_per_arm,
            customers_treated=cohort.n_customers,
            binding_constraints=("G4_EXPERIMENT_UNAFFORDABLE", feasibility.limiting_factor),
            unresolved=unresolved,
            citations=proposal.citations,
            model_requested=requested,
            gates_passed=tuple(gates),
        )
    gates.append("G4")

    horizon = feasibility.required_n_per_arm
    treated = horizon  # one treatment arm
    pilot_orders = min(
        brief.observed_conversion + proposal.expected_lift_absolute, 1.0
    ) * treated
    pilot_spend = pilot_orders * economics.incentive_cost_per_order_inr

    # ---- G5: standing policy limits on the pilot ---------------------------
    verdict = gate_experiment(
        experiment_id=f"{brief.merchant_id}:{intervention.intervention_id}",
        projected_spend_inr=pilot_spend,
        remaining_budget_inr=remaining_budget,
        discount_depth=intervention.depth_at_observed_aov,
        contribution_margin=brief.observed_margin,
        customers_treated=treated * 2,  # control and treatment are both exposed
        population=brief.population,
        power=0.80,
        limits=limits,
    )
    if not verdict.approved:
        return MerchantRecommendation(
            decision=RecommendationDecision.DO_NOT_PROMOTE,
            diagnosis=diagnosis,
            rationale=(
                "G5 failed: the pilot breaches a standing policy limit — "
                + "; ".join(v.message for v in verdict.violations)
            ),
            intervention_id=intervention.intervention_id,
            cohort_id=cohort.cohort_id,
            expected_incremental_contribution_inr=projection.incremental_contribution_inr,
            expected_incentive_cost_inr=projection.incentive_cost_inr,
            expected_net_contribution_inr=projection.net_contribution_inr,
            required_break_even_lift_absolute=projection.required_break_even_lift_absolute,
            evidence_basis=proposal.evidence_basis,
            experiment_required=True,
            experiment_cost_inr=pilot_spend,
            experiment_horizon_per_arm=horizon,
            customers_treated=cohort.n_customers,
            binding_constraints=tuple(v.rule.value for v in verdict.violations),
            unresolved=unresolved,
            citations=proposal.citations,
            model_requested=requested,
            gates_passed=tuple(gates),
        )
    gates.append("G5")

    return MerchantRecommendation(
        decision=RecommendationDecision.RUN_EXPERIMENT_FIRST,
        diagnosis=diagnosis,
        rationale=(
            f"The economics can work: at the proposed lift this earns "
            f"Rs.{projection.net_contribution_inr:,.0f} net. But the confidence rests on "
            f"{proposal.evidence_basis.value.lower()}, not on a measurement on this "
            f"merchant, so the honest next step is a controlled test of "
            f"{horizon:,} customers per arm at a cost of Rs.{pilot_spend:,.0f}. "
            "Rollout stays closed until that test clears the scaling rule."
        ),
        intervention_id=intervention.intervention_id,
        cohort_id=cohort.cohort_id,
        expected_incremental_contribution_inr=projection.incremental_contribution_inr,
        expected_incentive_cost_inr=projection.incentive_cost_inr,
        expected_net_contribution_inr=projection.net_contribution_inr,
        required_break_even_lift_absolute=projection.required_break_even_lift_absolute,
        evidence_basis=proposal.evidence_basis,
        experiment_required=True,
        experiment_cost_inr=pilot_spend,
        experiment_horizon_per_arm=horizon,
        customers_treated=cohort.n_customers,
        binding_constraints=(),
        unresolved=unresolved,
        citations=proposal.citations,
        assumptions=(
            "The expected lift is the model's hypothesis, not a measurement.",
            "Break-even assumes the incentive is redeemed on every treated order.",
        ),
        model_requested=requested,
        gates_passed=tuple(gates),
    )


def recommend_from_raw(
    brief: MerchantBrief,
    raw,
    *,
    limits: PolicyLimits | None = None,
    spent_inr: float = 0.0,
) -> MerchantRecommendation:
    """Validate a model reply and decide, failing closed on anything malformed."""
    try:
        proposal = validate_proposal(raw)
    except ProposalRejected as exc:
        return MerchantRecommendation(
            decision=RecommendationDecision.INSUFFICIENT_EVIDENCE,
            diagnosis="The assistant's proposal could not be used.",
            rationale=f"Proposal rejected: {exc}",
            intervention_id=None,
            cohort_id=None,
            expected_incremental_contribution_inr=0.0,
            expected_incentive_cost_inr=0.0,
            expected_net_contribution_inr=0.0,
            required_break_even_lift_absolute=None,
            evidence_basis=EvidenceBasis.NONE,
            experiment_required=False,
            binding_constraints=("PROPOSAL_REJECTED",),
        )
    return recommend(brief, proposal, limits=limits, spent_inr=spent_inr)


def decide_after_experiment(
    brief: MerchantBrief,
    proposal: Proposal,
    result: InterimResult | FinalResult,
    *,
    rollout_population: int,
    spent_inr: float,
    limits: PolicyLimits | None = None,
) -> MerchantRecommendation:
    """The only route to PROMOTE. Reads a measured result through G3 and G6."""
    limits = limits or PolicyLimits()
    remaining_budget = max(brief.budget_inr - spent_inr, 0.0)
    intervention = brief.intervention(proposal.intervention_id)
    cohort = _cohort(brief, proposal.cohort_id)
    economics = brief.economics_for(cohort.cohort_id, intervention.intervention_id)
    gates = ["G1", "G2", "G3"]

    if not isinstance(result, FinalResult):
        return MerchantRecommendation(
            decision=RecommendationDecision.RUN_EXPERIMENT_FIRST,
            diagnosis="The experiment has not reached its pre-committed horizon.",
            rationale="No verdict exists before the horizon, by design.",
            intervention_id=intervention.intervention_id,
            cohort_id=cohort.cohort_id,
            expected_incremental_contribution_inr=0.0,
            expected_incentive_cost_inr=0.0,
            expected_net_contribution_inr=0.0,
            required_break_even_lift_absolute=None,
            evidence_basis=EvidenceBasis.PRIOR,
            experiment_required=True,
            unresolved=(UNRESOLVED_VALUE_OF_INFORMATION,),
        )

    comparison: ArmComparison = result.comparisons[0]
    decision: ScaleDecision = assess_scale(
        comparison,
        projection_population=rollout_population,
        tolerable_loss_inr=brief.budget_inr * TOLERABLE_LOSS_FRACTION_OF_BUDGET,
    )

    measured_lift = comparison.absolute_difference
    net_per_customer = comparison.net_per_treated_customer_inr
    cost_per_customer = cost_per_treated_customer_inr(
        baseline_conversion=comparison.conversion_control,
        expected_lift_absolute=max(measured_lift, 0.0),
        incentive_cost_per_order_inr=economics.incentive_cost_per_order_inr,
    )
    affordable = affordable_rollout_customers(
        remaining_budget_inr=remaining_budget,
        cost_per_treated_customer_inr=cost_per_customer,
        population=rollout_population,
        limits=limits,
    )
    projected_net = net_per_customer * affordable
    projected_cost = cost_per_customer * affordable
    diagnosis = (
        f"The test measured a lift of {measured_lift:.2%} and a net of "
        f"Rs.{net_per_customer:,.2f} per treated customer."
    )

    def _hold(reason: str, constraint: str) -> MerchantRecommendation:
        return MerchantRecommendation(
            decision=RecommendationDecision.DO_NOT_PROMOTE,
            diagnosis=diagnosis,
            rationale=reason,
            intervention_id=intervention.intervention_id,
            cohort_id=cohort.cohort_id,
            expected_incremental_contribution_inr=projected_net + projected_cost,
            expected_incentive_cost_inr=projected_cost,
            expected_net_contribution_inr=projected_net,
            required_break_even_lift_absolute=None,
            evidence_basis=EvidenceBasis.EXPERIMENT,
            experiment_required=False,
            customers_treated=affordable,
            binding_constraints=(constraint,),
            citations=proposal.citations,
            gates_passed=tuple(gates),
        )

    # ---- G3: does the measurement clear the pre-registered scaling rule? ----
    if not decision.scale:
        return _hold(f"G3 failed: {decision.reason}", "G3_EVIDENCE_INSUFFICIENT")

    # ---- ADV-10: the result may claim success; the arithmetic decides -------
    if projected_net <= 0.0:
        return _hold(
            "G6 failed: the measured effect does not survive the rollout the "
            f"merchant can actually fund ({affordable:,} customers), which nets "
            f"Rs.{projected_net:,.0f}.",
            "G6_ROLLOUT_NET_NOT_POSITIVE",
        )

    # ---- G6: standing policy limits on the rollout -------------------------
    verdict = gate_rollout(
        experiment_id=result.experiment_id,
        projected_spend_inr=projected_cost,
        remaining_budget_inr=remaining_budget,
        discount_depth=intervention.depth_at_observed_aov,
        contribution_margin=brief.observed_margin,
        customers_treated=affordable,
        population=rollout_population,
        limits=limits,
    )
    if not verdict.approved:
        return _hold(
            "G6 failed: the rollout breaches a standing policy limit — "
            + "; ".join(v.message for v in verdict.violations),
            tuple(v.rule.value for v in verdict.violations)[0],
        )
    gates.append("G6")

    return MerchantRecommendation(
        decision=RecommendationDecision.PROMOTE,
        diagnosis=diagnosis,
        rationale=(
            f"{decision.reason}. Funded at {affordable:,} customers, the rollout is "
            f"projected to earn Rs.{projected_net:,.0f} net of "
            f"Rs.{projected_cost:,.0f} in incentives."
        ),
        intervention_id=intervention.intervention_id,
        cohort_id=cohort.cohort_id,
        expected_incremental_contribution_inr=projected_net + projected_cost,
        expected_incentive_cost_inr=projected_cost,
        expected_net_contribution_inr=projected_net,
        required_break_even_lift_absolute=None,
        evidence_basis=EvidenceBasis.EXPERIMENT,
        experiment_required=False,
        customers_treated=affordable,
        binding_constraints=(),
        citations=proposal.citations,
        assumptions=(
            "The rollout population responds as the tested sample did.",
        ),
        model_requested=proposal.requested_decision,
        gates_passed=tuple(gates),
    )
