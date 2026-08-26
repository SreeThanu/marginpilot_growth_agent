"""The agent's complete tool surface. Ten tools, exactly as CLAUDE.md lists them.

Every tool reads from a :class:`~src.eval.contracts.MerchantView` and nothing
else. A ``World`` is never passed in, so world parameters — true elasticity,
response scale, per-intervention affinity, true baseline conversion — are not
reachable from here, and neither are ``Y(0)``/``Y(1)``. That is enforced three
ways, because a comment is not enforcement:

1. :class:`ToolContext` has no field that can hold a ``World``, ``WorldParams``
   or ``GroundTruth``, and it is frozen.
2. Every tool's annotated parameter types are checked in
   ``tests/agent/test_tools.py`` against a denylist of those types, so adding a
   tool that accepts one fails the build.
3. Experiment observations arrive through an injected
   :class:`ExperimentExecutor` supplied by ``src/eval/``. The agent asks for
   results; it never computes them, and never holds the data they came from.

The boundary that matters most is what the tools *cannot* do. There is no tool
to assign a customer to an arm, no tool to set a horizon, no tool to change a
budget, and no tool to edit a launched hypothesis. Those are invariants 1, 3 and
7, and they are enforced by absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

from src.economics.contribution import contribution_per_order_inr
from src.eval.contracts import MerchantView
from src.experiment import power as power_module
from src.experiment.evaluator import (
    ArmObservation,
    FinalResult,
    InterimResult,
    ScaleDecision,
    assess_scale,
    evaluate,
)
from src.experiment.power import DesignFeasibility
from src.experiment.registry import (
    ExperimentRegistry,
    LaunchedExperiment,
    design_experiment_on_contribution,
)
from src.agent.hypothesis import AgentHypothesis

#: Share of the promotion budget the agent may lose in the bad tail of a single
#: scaled campaign. Mirrors the harness so the agent's own validation and the
#: evaluation agree on what "tolerable" means.
TOLERABLE_LOSS_FRACTION_OF_BUDGET = 0.02


@runtime_checkable
class ExperimentExecutor(Protocol):
    """Supplies observed arm data once an experiment has run.

    Implemented in ``src/eval/`` against ground truth. The agent holds only this
    interface, so the data it can see is exactly what a merchant's own reporting
    would show: counts and per-customer contribution, one outcome per customer.
    """

    def observe(
        self, experiment: LaunchedExperiment, intervention_id: str
    ) -> Sequence[ArmObservation]:
        ...

    def population_not_in_experiment(self, experiment: LaunchedExperiment) -> int:
        ...


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Everything the tools are allowed to touch.

    Note what is absent: no ``World``, no ``GroundTruth``, no ``WorldParams``.
    Frozen, so a tool cannot smuggle one in at runtime either.
    """

    view: MerchantView
    registry: ExperimentRegistry
    executor: ExperimentExecutor
    budget_remaining_inr: float
    max_experiments: int
    launched: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProposedDesign:
    """A validated-but-not-launched design. Proposing is not authority to spend."""

    experiment_id: str
    intervention_id: str
    hypothesis: AgentHypothesis
    horizon_per_arm: int
    projected_spend_inr: float
    feasibility: DesignFeasibility


# --------------------------------------------------------------------------- #
# 1-3: observation
# --------------------------------------------------------------------------- #


def get_merchant_metrics(ctx: ToolContext) -> dict[str, Any]:
    """Headline numbers the merchant already has in their own dashboards."""
    view = ctx.view
    return {
        "world_id": view.world_id,
        "customers": view.population,
        "observed_conversion": round(view.observed_conversion, 4),
        "observed_aov_inr": round(view.observed_aov_inr, 2),
        "observed_margin": round(view.observed_margin, 4),
        "contribution_per_order_inr": round(
            contribution_per_order_inr(view.observed_aov_inr, view.observed_margin), 2
        ),
        "projected_revenue_inr": round(view.projected_revenue_inr, 2),
        "promotion_budget_inr": round(view.budget_inr, 2),
        "budget_remaining_inr": round(ctx.budget_remaining_inr, 2),
        "experiment_window_days": view.experiment_window_days,
        "experiments_allowed": ctx.max_experiments,
        "experiments_used": len(ctx.launched),
        "merchant": view.semantic.merchant_name,
        "vertical": view.semantic.vertical,
        "description": view.semantic.merchant_description,
    }


def get_customer_segments(ctx: ToolContext) -> list[dict[str, Any]]:
    """Segments with their qualitative notes — the reasoning surface.

    Shares and notes only. The behaviour multipliers that generate those notes
    are latent and are what the experiment exists to estimate.
    """
    return [
        {
            "segment_id": s.segment_id,
            "name": s.name,
            "share": round(s.share, 4),
            "notes": s.notes,
            "behaviour_tags": list(s.behaviour_tags),
        }
        for s in ctx.view.segments
    ]


def get_product_context(ctx: ToolContext) -> dict[str, Any]:
    """Catalogue, inventory pressure, and the merchant's trading situation."""
    view = ctx.view
    return {
        "products": [
            {
                "product_id": p.product_id,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "unit_price_inr": p.unit_price_inr,
                "contribution_margin": round(p.contribution_margin, 4),
                "inventory_units": p.inventory_units,
                "inventory_age_days": p.inventory_age_days,
                "stock_status": p.stock_status,
            }
            for p in view.products
        ],
        "interventions": [
            {
                "intervention_id": i.intervention_id,
                "kind": i.kind.value,
                "name": i.name,
                "description": i.description,
                "depth_at_average_basket": round(
                    i.effective_depth(view.observed_aov_inr), 4
                ),
                "cost_per_treated_order_inr": round(
                    i.incentive_cost_inr(view.observed_aov_inr), 2
                ),
            }
            for i in view.interventions
        ],
        "seasonal_events": list(view.semantic.seasonal_events),
        "competitor_events": list(view.semantic.competitor_events),
        "customer_service_themes": list(view.semantic.customer_service_themes),
        "inventory_notes": list(view.semantic.inventory_notes),
        "trading_notes": list(view.semantic.trading_notes),
    }


# --------------------------------------------------------------------------- #
# 4-6: proposing, validating, launching
# --------------------------------------------------------------------------- #


def propose_experiment(
    ctx: ToolContext, hypothesis: AgentHypothesis, *, cycle: int = 0
) -> ProposedDesign:
    """Turn a hypothesis into a design. Does not launch and does not spend.

    The horizon is derived from the contribution power calculation on the stated
    effect — the agent cannot name a sample size, and there is no argument here
    through which it could.
    """
    view = ctx.view
    intervention = view.intervention(hypothesis.intervention_id)
    contribution_per_order = contribution_per_order_inr(
        view.observed_aov_inr, view.observed_margin
    )
    incentive_per_order = intervention.incentive_cost_inr(view.observed_aov_inr)

    feasibility = power_module.assess_feasibility(
        view.observed_conversion,
        hypothesis.expected_effect_absolute,
        contribution_per_incremental_order_inr=contribution_per_order,
        incentive_cost_per_treated_order_inr=incentive_per_order,
        mde_contribution_per_customer_inr=hypothesis.mde_contribution_per_customer_inr,
        remaining_budget_inr=max(ctx.budget_remaining_inr, 0.0),
        population=view.population,
    )

    experiment_id = f"{view.world_id}_marginpilot_{cycle}"
    design = design_experiment_on_contribution(
        experiment_id=experiment_id,
        world_id=view.world_id,
        intervention_id=hypothesis.intervention_id,
        hypothesis_id=hypothesis.hypothesis_id,
        prediction=hypothesis.prediction,
        reasoning=hypothesis.to_registry_hypothesis(1).reasoning,
        baseline_conversion=view.observed_conversion,
        expected_effect_absolute=hypothesis.expected_effect_absolute,
        contribution_per_incremental_order_inr=contribution_per_order,
        incentive_cost_per_treated_order_inr=incentive_per_order,
        mde_contribution_per_customer_inr=hypothesis.mde_contribution_per_customer_inr,
        success_condition=hypothesis.success_condition,
        failure_condition=hypothesis.failure_condition,
        budget_inr=max(ctx.budget_remaining_inr, 0.0),
    )
    ctx.registry.register(design)

    return ProposedDesign(
        experiment_id=experiment_id,
        intervention_id=hypothesis.intervention_id,
        hypothesis=hypothesis,
        horizon_per_arm=design.horizon_per_arm,
        projected_spend_inr=feasibility.projected_spend_inr,
        feasibility=feasibility,
    )


def validate_experiment(ctx: ToolContext, design: ProposedDesign) -> dict[str, Any]:
    """Return a verdict. **Does not execute** — CLAUDE.md invariant 2.

    Day 7 replaces the body of this with the real policy gate. The interface is
    already the one the gate will fill, so the agent's contract does not change
    when it arrives.
    """
    reasons: list[str] = []
    if not design.feasibility.feasible:
        reasons.append(design.feasibility.reason)
    if len(ctx.launched) >= ctx.max_experiments:
        reasons.append(
            f"experiment allowance exhausted ({ctx.max_experiments} per merchant)"
        )
    if design.projected_spend_inr > ctx.budget_remaining_inr:
        reasons.append(
            f"projected spend Rs.{design.projected_spend_inr:,.0f} exceeds remaining "
            f"budget Rs.{ctx.budget_remaining_inr:,.0f}"
        )
    return {
        "approved": not reasons,
        "rejections": reasons,
        "experiment_id": design.experiment_id,
        "horizon_per_arm": design.horizon_per_arm,
        "projected_spend_inr": round(design.projected_spend_inr, 2),
        "detectable_effect_inr_per_customer": round(
            design.feasibility.detectable_at_affordable_n_inr, 4
        ),
    }


def launch_experiment(ctx: ToolContext, design: ProposedDesign) -> LaunchedExperiment:
    """Execute an already-validated design. Refuses anything else."""
    verdict = validate_experiment(ctx, design)
    if not verdict["approved"]:
        raise PermissionError(
            f"cannot launch {design.experiment_id}: {'; '.join(verdict['rejections'])}"
        )
    experiment = ctx.registry.launch(design.experiment_id)
    ctx.launched.append(design.experiment_id)
    return experiment


# --------------------------------------------------------------------------- #
# 7-8: reading results
# --------------------------------------------------------------------------- #


def get_experiment_results(
    ctx: ToolContext, experiment: LaunchedExperiment
) -> InterimResult | FinalResult:
    """Observed data. Refuses a verdict before the horizon (invariant 3).

    Before the horizon this returns an :class:`InterimResult`, which has no
    difference, no interval and no verdict on it — the agent cannot read the
    experiment early because there is nothing early to read.
    """
    observations = ctx.executor.observe(experiment, experiment.design.intervention_id)
    return evaluate(experiment, observations)


def evaluate_experiment(
    ctx: ToolContext, result: InterimResult | FinalResult
) -> ScaleDecision | None:
    """Apply the pre-registered scaling rule. ``None`` before the horizon."""
    if not isinstance(result, FinalResult):
        return None
    return assess_scale(
        result.comparisons[0],
        projection_population=ctx.executor.population_not_in_experiment(
            ctx.registry.get(result.experiment_id)
        ),
        tolerable_loss_inr=ctx.view.budget_inr * TOLERABLE_LOSS_FRACTION_OF_BUDGET,
    )


# --------------------------------------------------------------------------- #
# 9-10: acting on the result
# --------------------------------------------------------------------------- #


def scale_experiment(
    ctx: ToolContext, experiment: LaunchedExperiment, decision: ScaleDecision
) -> dict[str, Any]:
    """Roll a campaign out. Gated on the decision rule, not on the agent's view."""
    if not decision.scale:
        raise PermissionError(
            f"cannot scale {experiment.experiment_id}: {decision.reason}"
        )
    ctx.registry.complete(experiment.experiment_id, detail="scaled")
    return {
        "experiment_id": experiment.experiment_id,
        "scaled": True,
        "projected_net_inr": round(decision.projected_net_inr, 2),
        "probability_net_positive": round(decision.probability_net_positive, 4),
        "reason": decision.reason,
    }


def stop_experiment(
    ctx: ToolContext, experiment: LaunchedExperiment, *, reason: str
) -> dict[str, Any]:
    """Stop a campaign. Stopping never produces a verdict of its own."""
    ctx.registry.stop(experiment.experiment_id, reason=reason)
    return {"experiment_id": experiment.experiment_id, "stopped": True, "reason": reason}


#: The complete tool surface. CLAUDE.md caps this at ten; tool sprawl is how the
#: reasoning/authority boundary erodes, so additions need an explicit reason.
TOOLS = (
    get_merchant_metrics,
    get_customer_segments,
    get_product_context,
    propose_experiment,
    validate_experiment,
    launch_experiment,
    get_experiment_results,
    evaluate_experiment,
    scale_experiment,
    stop_experiment,
)
