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
from src.experiment.registry import ExperimentRegistry, design_experiment


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
        [
            ArmObservation(0, "control", 400, 48),
            ArmObservation(1, "treatment", 400, 96),  # a huge, obvious lift
        ],
        contribution_per_incremental_order_inr=240.0,
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
        [
            ArmObservation(0, "control", 552, 66),
            ArmObservation(1, "treatment", 552, 200),
        ],
        contribution_per_incremental_order_inr=240.0,
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
        [
            ArmObservation(0, "control", 5000, 600),
            ArmObservation(1, "treatment", 300, 60),
        ],
        contribution_per_incremental_order_inr=240.0,
    )
    assert isinstance(result, InterimResult)
    assert result.remaining_per_arm == (0, 253)


def test_at_the_horizon_a_verdict_is_returned() -> None:
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    result = evaluate(
        experiment,
        [
            ArmObservation(0, "control", 553, 66),
            ArmObservation(1, "treatment", 553, 100),
        ],
        contribution_per_incremental_order_inr=240.0,
    )
    assert isinstance(result, FinalResult)
    assert result.verdict_eligible is True
    assert result.require_verdict() is result


def test_alpha_cannot_be_changed_after_launch() -> None:
    """Re-reading a borderline experiment at a looser alpha is peeking in a hat."""
    reg = ExperimentRegistry()
    experiment = _launch(reg)
    observations = [
        ArmObservation(0, "control", 553, 66),
        ArmObservation(1, "treatment", 553, 100),
    ]
    with pytest.raises(ValueError, match="pre-commitment"):
        evaluate(
            experiment,
            observations,
            contribution_per_incremental_order_inr=240.0,
            alpha=0.10,
        )
    # The registered value is accepted.
    assert evaluate(
        experiment, observations, contribution_per_incremental_order_inr=240.0, alpha=0.05
    ).verdict_eligible


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
        [
            ArmObservation(0, "control", 553, 66),   # 11.9%
            ArmObservation(1, "treatment", 553, 76),  # 13.7%
        ],
        contribution_per_incremental_order_inr=240.0,
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
        [
            ArmObservation(0, "control", 2000, 240),
            ArmObservation(1, "treatment", 2000, 400),
        ],
        contribution_per_incremental_order_inr=240.0,
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
        [
            ArmObservation(0, "control", 1000, 120),
            ArmObservation(1, "treatment", 1000, 180),
        ],
        contribution_per_incremental_order_inr=240.0,   # Rs.800 AOV x 30% margin
        incentive_cost_per_treated_order_inr=100.0,     # Rs.100 off every treated order
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
        [
            ArmObservation(0, "control", n, int(0.12 * n)),
            ArmObservation(1, "treatment", n, int(0.18 * n)),
        ],
        contribution_per_incremental_order_inr=240.0,
        incentive_cost_per_treated_order_inr=100.0,
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
            [
                ArmObservation(0, "control", n, int(round(0.12 * n))),
                ArmObservation(1, "treatment", n, int(round(0.18 * n))),
            ],
            contribution_per_incremental_order_inr=240.0,
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
        [
            ArmObservation(0, "control", n, int(0.12 * n)),
            ArmObservation(1, "flat", n, int(0.13 * n)),
            ArmObservation(2, "shipping", n, int(0.20 * n)),
        ],
        contribution_per_incremental_order_inr=240.0,
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
            contribution_per_incremental_order_inr=240.0,
        )


def test_impossible_observations_are_refused() -> None:
    with pytest.raises(ValueError, match="impossible"):
        ArmObservation(0, "control", 100, 101)
