"""The two refusals: no verdict before the horizon, no scaling on a point estimate.

These are the tests that matter most today. Both protect against the same
failure — acting on a number that is not yet, or not actually, evidence.
"""

from __future__ import annotations

import math

import pytest

from src.experiment.evaluator import (
    ArmObservation,
    FinalResult,
    HorizonNotReachedError,
    InterimResult,
    Verdict,
    evaluate,
)
from src.economics.contribution import arm_from_counts
from src.experiment.registry import ExperimentRegistry, design_experiment


def arms(
    n_control: int,
    control_orders: int,
    n_treatment: int,
    treatment_orders: int,
    *,
    contribution_per_order: float = 240.0,
    incentive: float = 0.0,
) -> list[ArmObservation]:
    """Build observations with measured per-customer contribution.

    Uses the constant-order-value case, where the per-customer contribution is
    Bernoulli and its mean and variance are exact — which is also the case where
    this estimator and the old incremental-orders one agree exactly.
    """
    control = arm_from_counts(
        n_control, control_orders, contribution_per_order_inr=contribution_per_order
    )
    treatment = arm_from_counts(
        n_treatment,
        treatment_orders,
        contribution_per_order_inr=contribution_per_order,
        incentive_per_order_inr=incentive,
    )
    return [
        ArmObservation(
            0, "control", n_control, control_orders,
            contribution_mean_inr=control.mean_inr, contribution_sd_inr=control.sd_inr,
        ),
        ArmObservation(
            1, "treatment", n_treatment, treatment_orders,
            contribution_mean_inr=treatment.mean_inr, contribution_sd_inr=treatment.sd_inr,
        ),
    ]


def _launch(reg: ExperimentRegistry, effect: float = 0.06, arms=("control", "treatment")):
    design = design_experiment(
        experiment_id="exp_eval",
        world_id="world_00011",
        intervention_id="int_flat",
        hypothesis_id="hyp_eval",
        prediction="Flat discount lifts conversion by 6 points.",
        reasoning="Price-sensitive segment, deep relative depth on small baskets.",
        baseline_conversion=0.12,
        expected_effect_absolute=effect,
        success_condition="CI lower bound on incremental contribution above zero.",
        failure_condition="CI contains or lies below zero.",
        budget_inr=50_000.0,
        arms=arms,
    )
    reg.register(design)
    return reg.launch("exp_eval")


# --------------------------------------------------------------------------- #
# No peeking
# --------------------------------------------------------------------------- #


def test_before_the_horizon_no_verdict_is_returned() -> None:
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    assert experiment.horizon_per_arm == 553

    result = evaluate(
        experiment,
        arms(400, 48, 400, 96),  # a huge, obvious lift
    )

    assert isinstance(result, InterimResult)
    assert result.verdict_eligible is False
    # The verdict-shaped attributes do not exist, so code cannot branch on them.
    for attribute in (
        "verdict", "scale_eligible", "absolute_difference", "p_value",
        "contribution_ci_low", "comparisons",
    ):
        assert not hasattr(result, attribute), f"InterimResult exposes {attribute}"

    with pytest.raises(HorizonNotReachedError, match="cannot be shortened"):
        result.require_verdict()


def test_an_overwhelming_early_result_is_still_refused() -> None:
    """The strongest possible temptation to stop early: a doubling of conversion.

    There is no 'early stop if significant' path, and this is the case that would
    exercise one if it existed.
    """
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        arms(552, 66, 552, 200, contribution_per_order=240.0),
        )
    assert isinstance(result, InterimResult)
    assert result.progress == pytest.approx(552 / 553)


def test_the_horizon_binds_on_every_arm_not_the_total() -> None:
    """A comparison is only as powered as its thinner side, so a well-fed control
    arm cannot buy the treatment arm an early read."""
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        arms(5000, 600, 300, 60, contribution_per_order=240.0),
        )
    assert isinstance(result, InterimResult)
    assert result.remaining_per_arm == (0, 253)


def test_at_the_horizon_a_verdict_is_returned() -> None:
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        arms(553, 66, 553, 100, contribution_per_order=240.0),
        )
    assert isinstance(result, FinalResult)
    assert result.verdict_eligible is True
    assert result.require_verdict() is result


def test_alpha_cannot_be_changed_after_launch() -> None:
    """Re-reading a borderline experiment at a looser alpha is peeking in a hat."""
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    observations = arms(553, 66, 553, 100)
    with pytest.raises(ValueError, match="pre-commitment"):
        evaluate(
            experiment,
            observations,
            alpha=0.10,
        )
    # The registered value is accepted.
    assert evaluate(experiment, observations, alpha=0.05).verdict_eligible


# --------------------------------------------------------------------------- #
# Uncertainty-aware scaling
# --------------------------------------------------------------------------- #


def test_a_positive_point_estimate_with_a_straddling_ci_is_not_scale_eligible() -> None:
    """The test that matters most.

    A real but noisy lift: the point estimate on incremental contribution is
    positive, and the interval contains zero. A positive estimate is not
    authority to spend the merchant's money.
    """
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        arms(553, 66, 553, 76),  # 11.9% vs 13.7%
    )
    assert isinstance(result, FinalResult)
    comparison = result.comparisons[0]

    assert comparison.absolute_difference > 0
    assert comparison.net_contribution_inr > 0, "point estimate should be positive"
    assert comparison.contribution_ci_low < 0 < comparison.contribution_ci_high
    assert comparison.scale_eligible is False
    assert comparison.verdict is Verdict.INCONCLUSIVE
    assert result.scale_eligible is False


def test_a_clear_win_is_scale_eligible() -> None:
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        arms(2000, 240, 2000, 400, contribution_per_order=240.0),
        )
    comparison = result.comparisons[0]
    assert comparison.contribution_ci_low > 0
    assert comparison.scale_eligible is True
    assert comparison.verdict is Verdict.SCALE


def test_a_significant_conversion_lift_can_still_be_killed_on_contribution() -> None:
    """The project's central case, at the level of the evaluator.

    Conversion rises 12% -> 18% and the lift is unambiguous. The incentive is
    paid on every treated order, not only the incremental ones, so contribution
    falls. Significance on conversion is not authority to scale.
    """
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        # Rs.800 AOV x 30% margin, Rs.100 off every treated order
        arms(1000, 120, 1000, 180, contribution_per_order=240.0, incentive=100.0),
    )
    comparison = result.comparisons[0]

    assert comparison.p_value < 0.001, "the conversion lift is unambiguous"
    assert comparison.relative_lift == pytest.approx(0.5, rel=1e-6)
    # 60 incremental orders x Rs.240 = Rs.14,400 earned;
    # 180 treated orders x Rs.100 = Rs.18,000 paid; net -Rs.3,600.
    assert comparison.net_contribution_inr == pytest.approx(-3600.0, abs=1.0)
    assert comparison.scale_eligible is False

    # But note what the sample does NOT support: at 1,000 per arm the interval on
    # contribution is roughly [-9,500, +2,300], which contains zero. The campaign
    # is refused authority to scale, and is simultaneously not a *demonstrated*
    # loss. Those are different claims and the evaluator keeps them apart.
    assert comparison.contribution_ci_low < -3600 < comparison.contribution_ci_high
    assert comparison.contribution_ci_high > 0
    assert comparison.verdict is Verdict.INCONCLUSIVE


def test_the_same_loss_becomes_a_demonstrated_kill_at_a_larger_sample() -> None:
    """Refusing to scale and proving harm need different amounts of evidence.

    The rule is deliberately asymmetric: spending requires proof of gain, while
    declining to spend requires only the absence of it. Calling the same result a
    KILL — an affirmative claim that the campaign destroys contribution — needs
    the interval to clear zero on the other side, which the pilot sample does not
    provide and a ~3x larger one does.
    """
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    n = 3000
    result = evaluate(
        experiment,
        arms(n, int(0.12 * n), n, int(0.18 * n), contribution_per_order=240.0, incentive=100.0),
    )
    comparison = result.comparisons[0]
    assert comparison.net_contribution_inr == pytest.approx(-3600.0 * 3, abs=5.0)
    assert comparison.contribution_ci_high < 0, "the loss is now demonstrated"
    assert comparison.verdict is Verdict.KILL
    assert comparison.scale_eligible is False


def test_contribution_interval_widens_with_noise_not_with_the_estimate() -> None:
    """Sanity on the delta-method variance: four times the sample should roughly
    halve the interval half-width."""
    reg = ExperimentRegistry()
    experiment = _launch(reg)

    def half_width(n: int) -> float:
        result = evaluate(
            experiment,
            arms(n, int(round(0.12 * n)), n, int(round(0.18 * n))),
        )
        c = result.comparisons[0]
        return (c.contribution_ci_high - c.contribution_ci_low) / 2 / n

    assert half_width(4000) / half_width(1000) == pytest.approx(0.5, rel=0.05)


def test_multi_arm_experiments_compare_each_treatment_to_control() -> None:
    reg = ExperimentRegistry()
    experiment = _launch(reg, arms=("control", "flat", "shipping"))
    n = experiment.horizon_per_arm
    result = evaluate(
        experiment,
        _three_arms(n),
    )
    assert len(result.comparisons) == 2
    assert result.best.name == "shipping"
    assert result.best.scale_eligible


def test_mismatched_observations_are_refused() -> None:
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    with pytest.raises(ValueError, match="2 arms"):
        evaluate(
            experiment,
            [ArmObservation(0, "control", 553, 66)],
        )


def test_impossible_observations_are_refused() -> None:
    with pytest.raises(ValueError, match="impossible"):
        ArmObservation(0, "control", 100, 101)


def _three_arms(n: int) -> list[ArmObservation]:
    """Three-arm observations for the multi-comparison test."""
    out = []
    for arm, (name, rate) in enumerate(
        (("control", 0.12), ("flat", 0.13), ("shipping", 0.20))
    ):
        converted = int(rate * n)
        summary = arm_from_counts(n, converted, contribution_per_order_inr=240.0)
        out.append(
            ArmObservation(
                arm, name, n, converted,
                contribution_mean_inr=summary.mean_inr,
                contribution_sd_inr=summary.sd_inr,
            )
        )
    return out
