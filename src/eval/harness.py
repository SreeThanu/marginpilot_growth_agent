"""The measurement spine: run a strategy across worlds and count what happened.

This module is deliberately built before anything intelligent exists, and it
runs with no LLM anywhere in it. If the measurement does not work, nothing built
on top of it can be believed.

How an experiment is actually observed
--------------------------------------
Customers are assigned by ``src.experiment.randomize``. A customer in the
control arm contributes their ``Y(0)``; a customer in a treatment arm
contributes their ``Y(1)`` for that intervention. Exactly one outcome per
customer, as in reality — the harness knows both but shows the strategy only
one, which is the entire reason the world generator produces both.

Ground truth is read **here and in ``replay.py`` only** (CLAUDE.md invariant 8).
The strategy receives a :class:`~src.eval.contracts.MerchantView`, which carries
no potential outcomes and no world parameters.

What counts as spend
--------------------
The incentive is paid on every treated order — pilot and rollout alike. A
strategy that scales a campaign pays for the whole population it rolls out to,
and the realized contribution of that rollout is computed from the same ground
truth, so "did this make money" is answered against the world's real outcomes
rather than against the experiment's estimate of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from src.economics.contribution import assess
from src.experiment import power as power_module
from src.experiment.evaluator import FinalResult, InterimResult, Verdict, evaluate
from src.experiment.evaluator import ArmObservation
from src.experiment.randomize import assign
from src.experiment.registry import ExperimentRegistry, design_experiment_on_contribution
from src.eval.contracts import (
    DirectAction,
    ExperimentProposal,
    MerchantView,
    ScalingRule,
    Strategy,
    merchant_view,
)
from src.world.generator import generate, generate_ground_truth, generate_world
from src.world.schema import GroundTruth, Intervention, World


@dataclass(frozen=True, slots=True)
class ExperimentOutcome:
    """One experiment, from proposal to realized rupees."""

    world_id: str
    intervention_id: str
    launched: bool
    refusal_reason: str

    horizon_per_arm: int = 0
    n_control: int = 0
    n_treatment: int = 0
    control_orders: int = 0
    treatment_orders: int = 0

    estimated_net_inr: float = 0.0
    ci_low_inr: float = 0.0
    ci_high_inr: float = 0.0
    verdict: str = "not_run"
    scaled: bool = False
    #: True for a campaign run without an experiment (Baseline 2's approach).
    untested: bool = False

    pilot_spend_inr: float = 0.0
    rollout_spend_inr: float = 0.0
    pilot_net_inr: float = 0.0
    rollout_net_inr: float = 0.0
    realized_aov_inr: float = 0.0
    #: True net and spend over the customers NOT in the pilot — what a rollout
    #: would earn and cost. Ground truth; used by replay to price the
    #: counterfactual where a different rule would have scaled.
    true_rollout_net_inr: float = 0.0
    true_rollout_spend_inr: float = 0.0
    realized_net_inr: float = 0.0
    #: What the intervention would truly have earned over the whole population,
    #: from ground truth. Used to score decisions, never shown to a strategy.
    true_full_population_net_inr: float = 0.0

    @property
    def total_spend_inr(self) -> float:
        return self.pilot_spend_inr + self.rollout_spend_inr

    @property
    def cost_of_learning_inr(self) -> float:
        """Spend that bought information rather than a scaled winner.

        The binding constraint on the whole approach: experimentation is only
        worth it if the winners it finds repay the losers it rules out. An
        untested campaign learns nothing, so none of its spend is learning —
        it is simply spend.
        """
        if self.untested or not self.launched:
            return 0.0
        return 0.0 if self.scaled else self.pilot_spend_inr


@dataclass
class WorldResult:
    """Everything one strategy did in one world."""

    world_id: str
    strategy: str
    budget_inr: float
    population: int
    outcomes: list[ExperimentOutcome] = field(default_factory=list)

    @property
    def promotion_spend_inr(self) -> float:
        return sum(o.total_spend_inr for o in self.outcomes)

    @property
    def incremental_contribution_inr(self) -> float:
        """Realized, from ground truth. The primary business metric."""
        return sum(o.realized_net_inr for o in self.outcomes)

    @property
    def incremental_revenue_inr(self) -> float:
        """Rupees of revenue attributable to treatment — orders times basket."""
        return sum(
            (o.treatment_orders / o.n_treatment - o.control_orders / o.n_control)
            * o.n_treatment
            * o.realized_aov_inr
            for o in self.outcomes
            if o.launched and o.n_treatment and o.n_control
        )

    @property
    def incremental_conversion(self) -> float:
        launched = [o for o in self.outcomes if o.launched and o.n_treatment and o.n_control]
        if not launched:
            return 0.0
        return float(
            np.mean(
                [
                    o.treatment_orders / o.n_treatment - o.control_orders / o.n_control
                    for o in launched
                ]
            )
        )

    @property
    def romi(self) -> float:
        spend = self.promotion_spend_inr
        if spend <= 0:
            return 0.0
        # Gross contribution earned, so ROMI > 1 <=> net > 0, as in economics/.
        return (self.incremental_contribution_inr + spend) / spend

    @property
    def budget_overrun(self) -> bool:
        return self.promotion_spend_inr > self.budget_inr

    @property
    def cost_of_learning_inr(self) -> float:
        return sum(o.cost_of_learning_inr for o in self.outcomes)

    @property
    def untested_campaigns(self) -> int:
        return sum(1 for o in self.outcomes if o.untested)

    @property
    def experiments_launched(self) -> int:
        return sum(1 for o in self.outcomes if o.launched and not o.untested)

    @property
    def experiments_refused(self) -> int:
        return sum(1 for o in self.outcomes if not o.launched)

    @property
    def experiments_scaled(self) -> int:
        return sum(1 for o in self.outcomes if o.scaled)

    @property
    def experiments_killed(self) -> int:
        return sum(1 for o in self.outcomes if o.launched and not o.scaled)

    @property
    def false_positives_scaled(self) -> int:
        """Scaled something that truly loses money. The expensive error."""
        return sum(1 for o in self.outcomes if o.scaled and o.true_full_population_net_inr < 0)

    @property
    def true_positives_killed(self) -> int:
        """Declined something that truly makes money. The invisible error."""
        return sum(
            1
            for o in self.outcomes
            if o.launched and not o.scaled and o.true_full_population_net_inr > 0
        )

    @property
    def estimation_error_inr(self) -> float:
        """Mean absolute gap between the estimate and the truth, per experiment.

        Decision quality and estimation quality are different things: a strategy
        can decide well on bad estimates by luck. Reported separately so Day 9
        can tell them apart.
        """
        launched = [o for o in self.outcomes if o.launched and o.n_treatment]
        if not launched:
            return 0.0
        errors = []
        for o in launched:
            true_per_customer = o.true_full_population_net_inr / max(self.population, 1)
            est_per_customer = o.estimated_net_inr / max(o.n_treatment, 1)
            errors.append(abs(est_per_customer - true_per_customer))
        return float(np.mean(errors))


def _observed_arm(
    customer_ids: Sequence[str],
    truth: GroundTruth,
    intervention_id: str,
    treated: bool,
) -> tuple[int, list[float], list[float]]:
    """Count orders and collect basket values for one arm.

    Control customers reveal ``Y(0)``, treated customers ``Y(1)`` — one outcome
    each, which is what an experiment can actually see.
    """
    orders = 0
    values: list[float] = []
    contributions: list[float] = []
    for customer_id in customer_ids:
        pair = truth.outcomes[customer_id][intervention_id]
        outcome = pair.y1 if treated else pair.y0
        if outcome.converted:
            orders += 1
            values.append(outcome.order_value_inr)
            contributions.append(outcome.contribution_inr)
    return orders, values, contributions


def _true_population_net(
    world: World, truth: GroundTruth, intervention: Intervention
) -> float:
    """What this intervention would truly earn across the entire population.

    Ground truth, used only to score decisions after the fact. No strategy sees
    it, and it never enters an estimate.
    """
    total = 0.0
    for customer in world.customers:
        pair = truth.outcomes[customer.customer_id][intervention.intervention_id]
        total += pair.y1.contribution_inr - pair.y0.contribution_inr
        if pair.y1.converted:
            total -= intervention.incentive_cost_inr(pair.y1.order_value_inr)
    return total


def _should_scale(rule: ScalingRule, evaluation: FinalResult | InterimResult) -> bool:
    """Apply the strategy's own scaling rule to a finished experiment.

    The rule is the strategy's to choose and the difference between the
    baselines. What no strategy chooses is *when* it may read the result — an
    interim evaluation carries no verdict at all, so every rule below is
    unreachable before the horizon.
    """
    if not isinstance(evaluation, FinalResult):
        return False
    comparison = evaluation.comparisons[0]
    if rule is ScalingRule.NEVER:
        return False
    if rule is ScalingRule.CI_LOWER_BOUND:
        return comparison.contribution_ci_low > 0
    if rule is ScalingRule.POINT_ESTIMATE:
        return comparison.net_contribution_inr > 0
    if rule is ScalingRule.CONVERSION_LIFT:
        # Statistically rigorous, economically blind: a significant lift in
        # conversion, with contribution never consulted.
        return comparison.difference_ci_low > 0
    raise ValueError(f"unknown scaling rule: {rule}")


def _run_direct_action(
    action: DirectAction,
    view: MerchantView,
    world: World,
    truth: GroundTruth,
) -> ExperimentOutcome:
    """Apply a campaign with no experiment, and book what really happened.

    There is no control arm, so there is no estimate — the strategy has no idea
    what it earned. The harness still computes the truth, because the evaluation
    has to score the outcome even when the strategy cannot see it.
    """
    intervention = view.intervention(action.intervention_id)
    targets = set(action.target_customer_ids)

    spend = 0.0
    realized = 0.0
    treated_orders = 0
    for customer_id in targets:
        pair = truth.outcomes[customer_id][action.intervention_id]
        realized += pair.y1.contribution_inr - pair.y0.contribution_inr
        if pair.y1.converted:
            treated_orders += 1
            cost = intervention.incentive_cost_inr(pair.y1.order_value_inr)
            spend += cost
            realized -= cost

    return ExperimentOutcome(
        world_id=world.world_id,
        intervention_id=action.intervention_id,
        launched=True,
        untested=True,
        refusal_reason="",
        n_treatment=len(targets),
        treatment_orders=treated_orders,
        verdict="untested",
        scaled=True,
        pilot_spend_inr=spend,
        realized_net_inr=realized,
        true_full_population_net_inr=_true_population_net(world, truth, intervention),
    )


def run_world(
    strategy: Strategy,
    world: World,
    truth: GroundTruth,
    *,
    alpha: float = 0.05,
    power_level: float = 0.80,
) -> WorldResult:
    """Run one strategy against one world, end to end."""
    view = merchant_view(world)
    budget_remaining = view.budget_inr
    result = WorldResult(
        world_id=world.world_id,
        strategy=strategy.name,
        budget_inr=view.budget_inr,
        population=view.population,
    )
    registry = ExperimentRegistry()

    rule = getattr(strategy, "scaling_rule", ScalingRule.CI_LOWER_BOUND)

    for index, proposal in enumerate(strategy.decide(view, budget_remaining)):
        if isinstance(proposal, DirectAction):
            outcome = _run_direct_action(proposal, view, world, truth)
            budget_remaining -= outcome.pilot_spend_inr
            result.outcomes.append(outcome)
            continue

        intervention = view.intervention(proposal.intervention_id)
        contribution_per_order = view.observed_aov_inr * view.observed_margin
        incentive_per_order = intervention.incentive_cost_inr(view.observed_aov_inr)

        # Can this question be answered at all, within budget and population?
        feasibility = power_module.assess_feasibility(
            view.observed_conversion,
            proposal.expected_effect_absolute,
            contribution_per_incremental_order_inr=contribution_per_order,
            incentive_cost_per_treated_order_inr=incentive_per_order,
            mde_contribution_per_customer_inr=proposal.mde_contribution_per_customer_inr,
            # Clamped at zero: a strategy that has already overspent should be
            # told the next experiment is unaffordable, which is a refusal, not
            # a crash. Whether it overspent at all is recorded separately as a
            # budget overrun, and Day 7's policy gate is what will prevent it.
            remaining_budget_inr=max(budget_remaining, 0.0),
            population=view.population,
            n_arms=len(proposal.arms),
            alpha=alpha,
            power=power_level,
        )
        if not feasibility.feasible:
            result.outcomes.append(
                ExperimentOutcome(
                    world_id=world.world_id,
                    intervention_id=proposal.intervention_id,
                    launched=False,
                    refusal_reason=feasibility.reason,
                    true_full_population_net_inr=_true_population_net(world, truth, intervention),
                )
            )
            continue

        experiment_id = f"{world.world_id}_{strategy.name}_{index}"
        design = design_experiment_on_contribution(
            experiment_id=experiment_id,
            world_id=world.world_id,
            intervention_id=proposal.intervention_id,
            hypothesis_id=proposal.hypothesis_id,
            prediction=proposal.prediction,
            reasoning=proposal.reasoning,
            baseline_conversion=view.observed_conversion,
            expected_effect_absolute=proposal.expected_effect_absolute,
            contribution_per_incremental_order_inr=contribution_per_order,
            incentive_cost_per_treated_order_inr=incentive_per_order,
            mde_contribution_per_customer_inr=proposal.mde_contribution_per_customer_inr,
            success_condition=proposal.success_condition,
            failure_condition=proposal.failure_condition,
            budget_inr=budget_remaining,
            arms=proposal.arms,
            alpha=alpha,
            power_level=power_level,
        )
        registry.register(design)
        experiment = registry.launch(experiment_id)
        horizon = experiment.horizon_per_arm

        # Assign, then take the first `horizon` customers of each arm.
        arms: list[list[str]] = [[] for _ in proposal.arms]
        for customer in world.customers:
            arm = assign(customer.customer_id, experiment_id, experiment.n_arms)
            if len(arms[arm]) < horizon:
                arms[arm].append(customer.customer_id)

        control_ids, treatment_ids = arms[0], arms[1]
        control_orders, _, _ = _observed_arm(control_ids, truth, proposal.intervention_id, False)
        treatment_orders, treated_values, _ = _observed_arm(
            treatment_ids, truth, proposal.intervention_id, True
        )

        realized_incentive_per_order = (
            float(np.mean([intervention.incentive_cost_inr(v) for v in treated_values]))
            if treated_values
            else incentive_per_order
        )
        realized_aov = float(np.mean(treated_values)) if treated_values else view.observed_aov_inr

        economics = assess(
            n_control=len(control_ids),
            n_treatment=len(treatment_ids),
            control_orders=control_orders,
            treatment_orders=treatment_orders,
            aov_inr=realized_aov,
            contribution_margin=view.observed_margin,
            incentive_per_order_inr=realized_incentive_per_order,
        )

        evaluation = evaluate(
            experiment,
            [
                ArmObservation(0, proposal.arms[0], len(control_ids), control_orders),
                ArmObservation(1, proposal.arms[1], len(treatment_ids), treatment_orders),
            ],
            contribution_per_incremental_order_inr=economics.contribution_per_incremental_order_inr,
            incentive_cost_per_treated_order_inr=realized_incentive_per_order,
        )

        pilot_spend = economics.incentive_cost_inr
        budget_remaining -= pilot_spend

        # Realized pilot contribution, from ground truth rather than the estimate.
        pilot_net = 0.0
        for customer_id in treatment_ids:
            pair = truth.outcomes[customer_id][proposal.intervention_id]
            pilot_net += pair.y1.contribution_inr - pair.y0.contribution_inr
            if pair.y1.converted:
                pilot_net -= intervention.incentive_cost_inr(pair.y1.order_value_inr)

        # What a rollout to the untested remainder would truly earn and cost.
        # Computed whether or not this run scales, because replay needs to price
        # the counterfactual where a different rule would have scaled.
        experimented = set(control_ids) | set(treatment_ids)
        true_rollout_net = 0.0
        true_rollout_spend = 0.0
        for customer in world.customers:
            if customer.customer_id in experimented:
                continue
            pair = truth.outcomes[customer.customer_id][proposal.intervention_id]
            true_rollout_net += pair.y1.contribution_inr - pair.y0.contribution_inr
            if pair.y1.converted:
                cost = intervention.incentive_cost_inr(pair.y1.order_value_inr)
                true_rollout_spend += cost
                true_rollout_net -= cost

        scaled = _should_scale(rule, evaluation)
        rollout_spend = true_rollout_spend if scaled else 0.0
        rollout_net = true_rollout_net if scaled else 0.0
        if scaled:
            budget_remaining -= rollout_spend

        comparison = evaluation.comparisons[0] if isinstance(evaluation, FinalResult) else None
        result.outcomes.append(
            ExperimentOutcome(
                world_id=world.world_id,
                intervention_id=proposal.intervention_id,
                launched=True,
                refusal_reason="",
                horizon_per_arm=horizon,
                n_control=len(control_ids),
                n_treatment=len(treatment_ids),
                control_orders=control_orders,
                treatment_orders=treatment_orders,
                estimated_net_inr=comparison.net_contribution_inr if comparison else 0.0,
                ci_low_inr=comparison.contribution_ci_low if comparison else 0.0,
                ci_high_inr=comparison.contribution_ci_high if comparison else 0.0,
                verdict=(evaluation.verdict.value if isinstance(evaluation, FinalResult) else "no_verdict"),
                scaled=scaled,
                pilot_spend_inr=pilot_spend,
                rollout_spend_inr=rollout_spend,
                pilot_net_inr=pilot_net,
                rollout_net_inr=rollout_net,
                realized_aov_inr=realized_aov,
                true_rollout_net_inr=true_rollout_net,
                true_rollout_spend_inr=true_rollout_spend,
                realized_net_inr=pilot_net + rollout_net,
                true_full_population_net_inr=_true_population_net(world, truth, intervention),
            )
        )

    return result


def run_worlds(
    strategy: Strategy, seeds: Iterable[int], *, split: str = "dev"
) -> list[WorldResult]:
    """Run a strategy across several worlds, one world resident at a time.

    Worlds are generated from their seed rather than loaded from disk so the
    harness works on a clean checkout, and so a dev seed can never accidentally
    address a holdout file.
    """
    results = []
    for seed in seeds:
        world, truth = generate(seed, split=split)
        results.append(run_world(strategy, world, truth))
        del world, truth
    return results


def metrics_table(results: Sequence[WorldResult]) -> str:
    """The five primary metrics plus secondaries. Ugly is fine; real is the point."""
    lines = []
    header = (
        f"{'world':<14}{'incr conv':>10}{'incr rev':>13}{'incr contrib':>15}"
        f"{'spend':>13}{'ROMI':>7}{'exp':>5}{'scaled':>7}{'verdict':>14}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in results:
        verdicts = ",".join(sorted({o.verdict for o in r.outcomes})) or "none"
        lines.append(
            f"{r.world_id:<14}{r.incremental_conversion * 100:>9.2f}%"
            f"{r.incremental_revenue_inr:>13,.0f}{r.incremental_contribution_inr:>15,.0f}"
            f"{r.promotion_spend_inr:>13,.0f}{r.romi:>7.2f}"
            f"{r.experiments_launched:>5}{r.experiments_scaled:>7}{verdicts:>14}"
        )
    lines.append("-" * len(header))
    total_contribution = sum(r.incremental_contribution_inr for r in results)
    total_spend = sum(r.promotion_spend_inr for r in results)
    lines.append(
        f"{'TOTAL':<14}{'':>10}{'':>13}{total_contribution:>15,.0f}{total_spend:>13,.0f}"
        f"{((total_contribution + total_spend) / total_spend if total_spend else 0):>7.2f}"
    )
    lines.append("")
    lines.append("Secondary metrics")
    lines.append(
        f"  experiments launched      : {sum(r.experiments_launched for r in results)}"
    )
    lines.append(
        f"  refused as unanswerable   : {sum(r.experiments_refused for r in results)}"
    )
    lines.append(f"  scaled                    : {sum(r.experiments_scaled for r in results)}")
    lines.append(f"  killed / not scaled       : {sum(r.experiments_killed for r in results)}")
    lines.append(
        f"  false positives scaled    : {sum(r.false_positives_scaled for r in results)}"
    )
    lines.append(
        f"  true positives not scaled : {sum(r.true_positives_killed for r in results)}"
    )
    lines.append(f"  budget overruns           : {sum(1 for r in results if r.budget_overrun)}")
    lines.append(
        f"  mean |estimate - truth|   : Rs.{np.mean([r.estimation_error_inr for r in results]):.4f} per customer"
    )
    return "\n".join(lines)
