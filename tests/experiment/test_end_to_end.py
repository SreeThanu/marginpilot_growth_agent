"""Day 3 done-criterion: create an experiment, assign 10,000 customers, and
confirm both refusals hold on the way through.

Dev worlds only. The world is used for customer identifiers and a baseline
conversion rate; no holdout file is opened and no potential outcomes are read.
"""

from __future__ import annotations

import pytest

from src.economics.contribution import arm_from_counts
from src.experiment.evaluator import (
    ArmObservation,
    FinalResult,
    InterimResult,
    Verdict,
    evaluate,
)
from src.experiment.randomize import arm_counts, assign, balance_summary
from src.experiment.registry import ExperimentRegistry, ExperimentStatus, design_experiment
from src.world.generator import generate_world

POPULATION = [f"cust_{i:05d}" for i in range(10_000)]


def test_ten_thousand_customers_through_the_whole_engine() -> None:
    world = generate_world(11)  # dev seed
    baseline = world.params.baseline_conversion

    registry = ExperimentRegistry()
    design = design_experiment(
        experiment_id="exp_e2e",
        world_id=world.world_id,
        intervention_id="int_flat",
        hypothesis_id="hyp_e2e",
        prediction=f"A flat discount lifts conversion from {baseline:.1%} by 4 points.",
        reasoning="Ageing stock plus a price-sensitive segment mix.",
        baseline_conversion=baseline,
        expected_effect_absolute=0.04,
        success_condition="CI lower bound on incremental contribution above zero.",
        failure_condition="CI contains or lies below zero.",
        budget_inr=world.params.promotion_budget_inr,
    )
    registry.register(design)
    experiment = registry.launch("exp_e2e")

    horizon = experiment.horizon_per_arm
    assert horizon > 0
    assert registry.status("exp_e2e") is ExperimentStatus.RUNNING

    # Assign the population. Balanced, and reproducible from the rule alone.
    counts = arm_counts(POPULATION, "exp_e2e", experiment.n_arms)
    assert sum(counts) == 10_000
    assert balance_summary(counts)["max_relative_deviation"] < 0.05
    assert all(assign(c, "exp_e2e", 2) == assign(c, "exp_e2e", 2) for c in POPULATION[:200])

    # Halfway to the horizon: counts only, no verdict.
    half = horizon // 2
    interim = evaluate(
        experiment, _arms(half, baseline, baseline + 0.09, incentive=0.0)
    )
    assert isinstance(interim, InterimResult)
    assert interim.verdict_eligible is False

    # At the horizon: a verdict, and the interval decides whether to spend.
    final = evaluate(
        experiment, _arms(horizon, baseline, baseline + 0.09, incentive=40.0)
    )
    assert isinstance(final, FinalResult)
    assert final.verdict in (Verdict.SCALE, Verdict.KILL, Verdict.INCONCLUSIVE)
    assert final.scale_eligible == (final.comparisons[0].contribution_ci_low > 0)

    registry.complete("exp_e2e", detail=f"horizon {horizon} reached")
    assert registry.status("exp_e2e") is ExperimentStatus.COMPLETED
    assert [e.kind for e in registry.events] == ["registered", "launched", "completed"]


def test_a_real_dev_world_population_assigns_cleanly() -> None:
    world = generate_world(23)
    ids = [c.customer_id for c in world.customers]
    counts = arm_counts(ids, "exp_world_23", 2)
    assert sum(counts) == len(ids)
    assert balance_summary(counts)["max_relative_deviation"] < 0.10


def test_horizon_scales_with_the_worlds_own_baseline() -> None:
    """Different worlds need different horizons — the number is derived, not fixed."""
    horizons = set()
    for seed in (3, 17, 41):
        world = generate_world(seed)
        design = design_experiment(
            experiment_id=f"exp_{seed}",
            world_id=world.world_id,
            intervention_id="int_pct",
            hypothesis_id=f"hyp_{seed}",
            prediction="A percentage discount lifts conversion by 3 points.",
            reasoning="Baseline drift and an elastic segment mix.",
            baseline_conversion=world.params.baseline_conversion,
            expected_effect_absolute=0.03,
            success_condition="CI lower bound above zero.",
            failure_condition="CI contains or lies below zero.",
            budget_inr=world.params.promotion_budget_inr,
        )
        horizons.add(design.horizon_per_arm)
    assert len(horizons) > 1


def _arms(n: int, control_rate: float, treatment_rate: float, *, incentive: float):
    """Observations with measured per-customer contribution at a constant basket."""
    pairs = []
    for arm, (name, rate, fee) in enumerate(
        (("control", control_rate, 0.0), ("treatment", treatment_rate, incentive))
    ):
        converted = int(rate * n)
        summary = arm_from_counts(
            n, converted, contribution_per_order_inr=240.0, incentive_per_order_inr=fee
        )
        pairs.append(
            ArmObservation(
                arm, name, n, converted,
                contribution_mean_inr=summary.mean_inr,
                contribution_sd_inr=summary.sd_inr,
            )
        )
    return pairs
