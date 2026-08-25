"""Reading an experiment — but only once it is readable.

Three rules are enforced here, and all three are refusals rather than features.

**No peeking (CLAUDE.md invariant 3).** Before every arm reaches the horizon,
:func:`evaluate` returns an :class:`InterimResult`, which carries counts for
monitoring and *nothing that can be read as a verdict*. It has no difference, no
confidence interval, no p-value and no ``scale_eligible`` attribute — asking for
one raises ``AttributeError``, because the safest way to prevent an early read
is for the number not to exist. There is deliberately no ``force`` parameter and
no "early stop if significant" path.

**No alpha shopping.** The significance level is taken from the design that was
registered before launch. Passing a different one raises. Re-reading a
borderline experiment at alpha 0.10 is the same act as peeking, wearing a
different hat.

**Uncertainty-aware scaling.** An experiment is scale-eligible only when the
*lower bound* of the confidence interval on incremental contribution clears
zero. A positive point estimate is not authority to spend the merchant's money:
half of those intervals contain zero, and scaling on them is how a system
converts noise into spend. This is stricter than significance on conversion —
an experiment can show a clearly significant conversion lift and still be
refused, which is exactly the case the whole project is built around.

Contribution arithmetic proper belongs to ``src/economics/`` on Day 4. This
module takes per-order figures as arguments and does not know what a margin is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from scipy import stats

from src.experiment.registry import LaunchedExperiment


class Verdict(str, Enum):
    """What the statistics support. Not a decision — Day 7's policy gate decides."""

    #: CI on incremental contribution lies entirely above zero.
    SCALE = "scale"
    #: CI lies entirely below zero. The campaign destroys contribution.
    KILL = "kill"
    #: CI contains zero. No authority to spend, and no proof of harm.
    INCONCLUSIVE = "inconclusive"


class HorizonNotReachedError(RuntimeError):
    """Raised when a verdict is requested before the pre-committed horizon."""


@dataclass(frozen=True, slots=True)
class ArmObservation:
    """What was actually observed in one arm."""

    arm: int
    name: str
    n_assigned: int
    n_converted: int

    def __post_init__(self) -> None:
        if self.n_assigned < 0 or self.n_converted < 0:
            raise ValueError("counts cannot be negative")
        if self.n_converted > self.n_assigned:
            raise ValueError(
                f"arm {self.arm}: {self.n_converted} conversions from "
                f"{self.n_assigned} customers is impossible"
            )

    @property
    def conversion_rate(self) -> float:
        return self.n_converted / self.n_assigned if self.n_assigned else 0.0


@dataclass(frozen=True, slots=True)
class InterimResult:
    """Monitoring only. Carries no verdict, and cannot be made to produce one.

    The absent attributes are the design. There is no ``absolute_difference``,
    no ``ci_low``, no ``p_value`` and no ``scale_eligible`` on this type, so code
    that tries to branch on one fails loudly instead of reading an experiment
    early.
    """

    experiment_id: str
    horizon_per_arm: int
    assigned_per_arm: tuple[int, ...]
    converted_per_arm: tuple[int, ...]

    #: Present on both result types so callers can branch on one flag.
    verdict_eligible: bool = False

    @property
    def remaining_per_arm(self) -> tuple[int, ...]:
        return tuple(max(self.horizon_per_arm - n, 0) for n in self.assigned_per_arm)

    @property
    def progress(self) -> float:
        """Fraction of the horizon reached by the thinnest arm."""
        if not self.assigned_per_arm or self.horizon_per_arm <= 0:
            return 0.0
        return min(self.assigned_per_arm) / self.horizon_per_arm

    def require_verdict(self) -> "FinalResult":
        """Always raises. Present so the refusal has a clear, greppable name."""
        raise HorizonNotReachedError(
            f"{self.experiment_id} has not reached its horizon of "
            f"{self.horizon_per_arm} per arm (assigned: {self.assigned_per_arm}). "
            "The horizon was fixed at design time and cannot be shortened, and "
            "there is no early-stopping path (CLAUDE.md invariant 3)."
        )


@dataclass(frozen=True, slots=True)
class ArmComparison:
    """One treatment arm against control, at the horizon."""

    arm: int
    name: str
    n_control: int
    n_treatment: int
    conversion_control: float
    conversion_treatment: float
    absolute_difference: float
    difference_ci_low: float
    difference_ci_high: float
    p_value: float
    net_contribution_inr: float
    contribution_ci_low: float
    contribution_ci_high: float

    @property
    def scale_eligible(self) -> bool:
        """The whole interval must clear zero. A positive estimate is not enough."""
        return self.contribution_ci_low > 0.0

    @property
    def relative_lift(self) -> float:
        if self.conversion_control == 0.0:
            return math.inf if self.absolute_difference > 0 else 0.0
        return self.absolute_difference / self.conversion_control

    @property
    def verdict(self) -> Verdict:
        if self.contribution_ci_low > 0.0:
            return Verdict.SCALE
        if self.contribution_ci_high < 0.0:
            return Verdict.KILL
        return Verdict.INCONCLUSIVE


@dataclass(frozen=True, slots=True)
class FinalResult:
    """The experiment at its horizon. The only type that carries a verdict."""

    experiment_id: str
    alpha: float
    horizon_per_arm: int
    comparisons: tuple[ArmComparison, ...]
    verdict_eligible: bool = True

    @property
    def best(self) -> ArmComparison:
        """The treatment arm with the highest incremental contribution estimate."""
        return max(self.comparisons, key=lambda c: c.net_contribution_inr)

    @property
    def scale_eligible(self) -> bool:
        return any(c.scale_eligible for c in self.comparisons)

    @property
    def verdict(self) -> Verdict:
        """SCALE if any arm qualifies; KILL only if every arm is clearly negative."""
        if any(c.verdict is Verdict.SCALE for c in self.comparisons):
            return Verdict.SCALE
        if all(c.verdict is Verdict.KILL for c in self.comparisons):
            return Verdict.KILL
        return Verdict.INCONCLUSIVE

    def require_verdict(self) -> "FinalResult":
        return self


def _normalise(
    observations: Sequence[ArmObservation] | Mapping[int, ArmObservation],
) -> tuple[ArmObservation, ...]:
    values = list(observations.values()) if isinstance(observations, Mapping) else list(observations)
    return tuple(sorted(values, key=lambda o: o.arm))


def evaluate(
    experiment: LaunchedExperiment,
    observations: Sequence[ArmObservation] | Mapping[int, ArmObservation],
    *,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float = 0.0,
    alpha: float | None = None,
) -> InterimResult | FinalResult:
    """Evaluate an experiment, refusing a verdict before the horizon.

    Args:
        contribution_per_incremental_order_inr: contribution earned per genuinely
            incremental order. Passed in; ``src/economics/`` computes it on Day 4.
        incentive_cost_per_treated_order_inr: incentive paid per *treated* order,
            incremental or not. This asymmetry — earned on the incremental
            orders, paid on all of them — is what makes a conversion win capable
            of losing money, so the evaluator has to model it even before the
            economics module exists.
        alpha: must match the registered design if given. Defaults to it.

    Returns:
        :class:`InterimResult` before the horizon, :class:`FinalResult` at it.
    """
    observed = _normalise(observations)
    if len(observed) != experiment.n_arms:
        raise ValueError(
            f"{experiment.experiment_id} has {experiment.n_arms} arms but "
            f"{len(observed)} observations were supplied"
        )
    if tuple(o.arm for o in observed) != tuple(range(experiment.n_arms)):
        raise ValueError(f"arm indices must be 0..{experiment.n_arms - 1}")

    design_alpha = experiment.design.power.alpha
    if alpha is not None and not math.isclose(alpha, design_alpha):
        raise ValueError(
            f"alpha {alpha} differs from the {design_alpha} registered before launch. "
            "The significance level is part of the pre-commitment; changing it after "
            "seeing data is peeking by another name (CLAUDE.md invariant 3)."
        )
    alpha = design_alpha

    assigned = tuple(o.n_assigned for o in observed)
    converted = tuple(o.n_converted for o in observed)

    if not experiment.horizon_reached(assigned):
        return InterimResult(
            experiment_id=experiment.experiment_id,
            horizon_per_arm=experiment.horizon_per_arm,
            assigned_per_arm=assigned,
            converted_per_arm=converted,
        )

    control = observed[0]
    comparisons = tuple(
        _compare(
            control,
            treatment,
            alpha=alpha,
            comparisons=max(experiment.n_arms - 1, 1),
            contribution_per_incremental_order_inr=contribution_per_incremental_order_inr,
            incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        )
        for treatment in observed[1:]
    )
    return FinalResult(
        experiment_id=experiment.experiment_id,
        alpha=alpha,
        horizon_per_arm=experiment.horizon_per_arm,
        comparisons=comparisons,
    )


def _compare(
    control: ArmObservation,
    treatment: ArmObservation,
    *,
    alpha: float,
    comparisons: int,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
) -> ArmComparison:
    """Two-proportion comparison plus the contribution interval.

    The same Bonferroni split used to size the experiment is applied when
    reading it: sizing for a corrected alpha and then testing at the nominal one
    would quietly give back the protection the larger sample was bought for.
    """
    p_c, p_t = control.conversion_rate, treatment.conversion_rate
    n_c, n_t = control.n_assigned, treatment.n_assigned
    difference = p_t - p_c

    var_c = p_c * (1 - p_c) / n_c
    var_t = p_t * (1 - p_t) / n_t
    se_difference = math.sqrt(var_c + var_t)

    z_crit = float(stats.norm.ppf(1.0 - (alpha / comparisons) / 2.0))

    # Pooled-variance z-test for the p-value; unpooled for the interval. This is
    # the conventional pairing: the null assumes a common rate, the interval does
    # not assume the null is true.
    pooled = (control.n_converted + treatment.n_converted) / (n_c + n_t)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_c + 1 / n_t))
    if se_pooled > 0:
        z_stat = difference / se_pooled
        p_value = float(2.0 * (1.0 - stats.norm.cdf(abs(z_stat))))
    else:
        p_value = 1.0

    # Net incremental contribution over the treated arm:
    #   net = n_t * (difference * c - p_t * k)
    # Contribution is earned only on incremental orders; the incentive is paid on
    # every treated order. Variance by the delta method, using
    # Cov(difference, p_t) = Var(p_t):
    #   Var(net) = n_t^2 * [ Var(p_t)*(c - k)^2 + c^2 * Var(p_c) ]
    c = contribution_per_incremental_order_inr
    k = incentive_cost_per_treated_order_inr
    net = n_t * (difference * c - p_t * k)
    se_net = n_t * math.sqrt(var_t * (c - k) ** 2 + (c**2) * var_c)

    return ArmComparison(
        arm=treatment.arm,
        name=treatment.name,
        n_control=n_c,
        n_treatment=n_t,
        conversion_control=p_c,
        conversion_treatment=p_t,
        absolute_difference=difference,
        difference_ci_low=difference - z_crit * se_difference,
        difference_ci_high=difference + z_crit * se_difference,
        p_value=p_value,
        net_contribution_inr=net,
        contribution_ci_low=net - z_crit * se_net,
        contribution_ci_high=net + z_crit * se_net,
    )
