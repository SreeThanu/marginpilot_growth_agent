"""Contribution arithmetic, checked against values computed by hand.

CLAUDE.md: economics/ needs real unit tests with hand-computed expected values.
Every number below is worked out in the docstring or comment beside it, so the
tests verify the arithmetic rather than echo the implementation.
"""

from __future__ import annotations

import pytest

from src.economics.contribution import (
    ContributionResult,
    assess,
    contribution_per_order_inr,
    conversion_rate,
    incentive_cost_inr,
    incremental_contribution_inr,
    incremental_orders,
    net_incremental_contribution_inr,
    project_to_population,
    romi,
)


def test_the_canonical_case() -> None:
    """The README's worked example, line by line.

        control:   1,000 customers, 120 orders -> 12.0%
        treatment: 1,000 customers, 180 orders -> 18.0%
        incremental orders          = (0.18 - 0.12) * 1000     =      60
        contribution per order      = 800 * 0.30               =     240
        incremental contribution    = 60 * 240                 =  14,400
        incentive cost              = 180 * 100                =  18,000
        net                         = 14,400 - 18,000          =  -3,600
        ROMI                        = 14,400 / 18,000          =     0.8
    """
    result = assess(
        n_control=1000,
        n_treatment=1000,
        control_orders=120,
        treatment_orders=180,
        aov_inr=800.0,
        contribution_margin=0.30,
        incentive_per_order_inr=100.0,
    )

    assert result.control_conversion == pytest.approx(0.12)
    assert result.treatment_conversion == pytest.approx(0.18)
    assert result.conversion_lift_relative == pytest.approx(0.50)
    assert result.incremental_order_count == pytest.approx(60.0)
    assert result.incremental_contribution_inr == pytest.approx(14_400.0)
    assert result.incentive_cost_inr == pytest.approx(18_000.0)
    assert result.net_incremental_contribution_inr == pytest.approx(-3_600.0)
    assert result.romi == pytest.approx(0.8)
    assert result.is_profitable is False


def test_the_canonical_case_projects_to_minus_36000() -> None:
    """CLAUDE.md pins the projection: -Rs.3,600 at 1,000 becomes -Rs.36,000 at 10,000."""
    result = assess(
        n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=100.0,
    )
    assert result.projected_to(10_000) == pytest.approx(-36_000.0)


def test_the_incentive_is_paid_on_every_treated_order_not_the_incremental_ones() -> None:
    """The asymmetry the whole project is about.

    Charging the incentive only on incremental orders would turn the canonical
    loss (60 * 240 - 180 * 100 = -3,600) into a profit (60 * 240 - 60 * 100 =
    +8,400) and delete the finding.
    """
    correct = incentive_cost_inr(treated_orders=180, incentive_per_order_inr=100.0)
    wrong = incentive_cost_inr(treated_orders=60, incentive_per_order_inr=100.0)
    assert correct == 18_000.0
    assert wrong == 6_000.0
    assert net_incremental_contribution_inr(14_400.0, correct) == pytest.approx(-3_600.0)
    assert net_incremental_contribution_inr(14_400.0, wrong) == pytest.approx(8_400.0)


def test_a_profitable_campaign() -> None:
    """Same lift, a cheaper incentive: Rs.30 off.

        incremental contribution = 14,400
        incentive cost           = 180 * 30 = 5,400
        net                      = +9,000
        ROMI                     = 14,400 / 5,400 = 2.666...
    """
    result = assess(
        n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=30.0,
    )
    assert result.net_incremental_contribution_inr == pytest.approx(9_000.0)
    assert result.romi == pytest.approx(14_400.0 / 5_400.0)
    assert result.is_profitable is True


def test_romi_above_one_is_equivalent_to_positive_net() -> None:
    """The two headline metrics must never disagree."""
    for incentive in (10.0, 30.0, 79.0, 80.0, 81.0, 100.0, 200.0):
        result = assess(
            n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
            aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=incentive,
        )
        assert (result.romi > 1.0) == (result.net_incremental_contribution_inr > 0.0)


def test_incremental_orders_uses_rates_so_unequal_arms_are_safe() -> None:
    """A control arm twice the size must not invent incremental orders.

    Rates: control 120/2000 = 6%, treatment 180/1000 = 18%.
    Incremental = (0.18 - 0.06) * 1000 = 120, not the raw 180 - 120 = 60.
    """
    assert incremental_orders(120, 180, 2000, 1000) == pytest.approx(120.0)
    # Equal arms reduce to the plain difference.
    assert incremental_orders(120, 180, 1000, 1000) == pytest.approx(60.0)


def test_a_treatment_that_hurts_yields_negative_incremental_orders() -> None:
    """Interventions can backfire, and the arithmetic must not hide it."""
    result = assess(
        n_control=1000, n_treatment=1000, control_orders=180, treatment_orders=120,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=100.0,
    )
    assert result.incremental_order_count == pytest.approx(-60.0)
    assert result.incremental_contribution_inr == pytest.approx(-14_400.0)
    assert result.net_incremental_contribution_inr == pytest.approx(-14_400.0 - 12_000.0)


def test_contribution_per_order_is_margin_times_aov() -> None:
    assert contribution_per_order_inr(800.0, 0.30) == pytest.approx(240.0)
    assert contribution_per_order_inr(1740.0, 0.287) == pytest.approx(499.38)


def test_incremental_revenue_is_before_margin() -> None:
    result = assess(
        n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=100.0,
    )
    assert result.incremental_revenue_inr == pytest.approx(60 * 800.0)


def test_the_two_scalars_the_evaluator_needs() -> None:
    """This module is where evaluator.evaluate's arguments come from."""
    result = assess(
        n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=100.0,
    )
    assert result.contribution_per_incremental_order_inr == pytest.approx(240.0)
    assert result.incentive_per_order_inr == pytest.approx(100.0)


def test_economics_agrees_with_the_evaluator_on_the_canonical_case() -> None:
    """Two modules, one number. If these ever diverge, one of them is wrong."""
    from src.experiment.evaluator import ArmObservation, evaluate
    from src.experiment.registry import ExperimentRegistry, design_experiment

    result = assess(
        n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=100.0,
    )

    registry = ExperimentRegistry()
    design = design_experiment(
        experiment_id="exp_x", world_id="w", intervention_id="int_flat",
        hypothesis_id="h", prediction="p", reasoning="r",
        baseline_conversion=0.12, expected_effect_absolute=0.06,
        success_condition="s", failure_condition="f", budget_inr=1.0,
    )
    registry.register(design)
    experiment = registry.launch("exp_x")

    evaluated = evaluate(
        experiment,
        [ArmObservation(0, "control", 1000, 120), ArmObservation(1, "treatment", 1000, 180)],
        contribution_per_incremental_order_inr=result.contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr=result.incentive_per_order_inr,
    )
    assert evaluated.comparisons[0].net_contribution_inr == pytest.approx(
        result.net_incremental_contribution_inr, abs=1e-6
    )


def test_zero_spend_has_no_romi_rather_than_infinite_romi() -> None:
    assert romi(14_400.0, 0.0) == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"orders": -1, "customers": 10},
        {"orders": 11, "customers": 10},
    ],
)
def test_impossible_counts_are_refused(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        conversion_rate(**kwargs)


def test_impossible_margins_are_refused() -> None:
    with pytest.raises(ValueError):
        contribution_per_order_inr(800.0, 1.5)


def test_pure_functions_have_no_hidden_state() -> None:
    """Called twice with the same inputs, the same answer. No caching, no drift."""
    args = dict(
        n_control=1000, n_treatment=1000, control_orders=120, treatment_orders=180,
        aov_inr=800.0, contribution_margin=0.30, incentive_per_order_inr=100.0,
    )
    assert assess(**args) == assess(**args)
    assert isinstance(assess(**args), ContributionResult)
