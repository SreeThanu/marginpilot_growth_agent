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

**Uncertainty-aware scaling.** A positive point estimate is never authority to
spend the merchant's money. Scaling requires two things of the posterior on
incremental contribution: that the campaign is probably profitable, and that its
bad tail is survivable — see :func:`assess_scale`. This is stricter than
significance on conversion, so an experiment can show a clearly significant
conversion lift and still be refused, which is the case the whole project is
built around.

The original rule required the entire 95% interval to clear zero. On Day 5 that
was measured against an oracle selector — perfect choice of intervention, full
budget — and it scaled 0 experiments in 10 worlds while missing 9 truly
profitable rollouts. A rule that refuses even oracular selection is not
conservative, it is inoperable, so it was replaced before any agent existed and
before any holdout was opened. Both rules are computed; only the posterior one
decides. The reasoning is pre-registered in ``docs/simulator.md``.

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


#: Posterior probability of positive net contribution required to scale.
#:
#: With a flat prior and a normal likelihood the posterior equals the sampling
#: distribution, so this threshold is numerically a one-sided test at alpha 0.20.
#: That is stated plainly rather than dressed up: the Bayesian framing does not
#: manufacture evidence, it changes the bar and pairs it with an explicit floor
#: on the downside. The old rule — the whole 95% interval above zero — is a
#: one-sided bar at 0.025, which at this corpus's achievable sample sizes
#: refused to scale even under perfect selection.
DEFAULT_MIN_PROBABILITY = 0.80

#: Percentile of the posterior used as the downside floor.
DEFAULT_LOSS_PERCENTILE = 0.05


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
    """What was actually observed in one arm.

    Carries per-customer contribution as a measured mean and spread rather than
    a modelled figure. The earlier version passed only counts and reconstructed
    contribution as "incremental orders x a fixed contribution per order", which
    cannot see a treatment that changes what people buy rather than whether they
    buy — and had the wrong sign in half the dev worlds because of it.

    ``contribution_mean_inr`` is over *assigned* customers, so non-buyers are
    included as zeros. Dropping them would condition on an outcome of the
    treatment and understate the variance the decision rests on.
    """

    arm: int
    name: str
    n_assigned: int
    n_converted: int
    #: Mean per-assigned-customer contribution, net of incentive redeemed.
    contribution_mean_inr: float = 0.0
    #: Sample standard deviation of that per-customer contribution.
    contribution_sd_inr: float = 0.0

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
    #: Standard error of the net-contribution estimate. With a flat prior this
    #: is also the posterior standard deviation.
    contribution_se_inr: float = 0.0

    # -- posterior view of the same evidence --------------------------------

    @property
    def probability_net_positive(self) -> float:
        """P(net contribution > 0) under a flat prior.

        The quantity a merchant actually wants: not "is this distinguishable
        from zero" but "how likely is it that spending here makes money".
        """
        if self.contribution_se_inr <= 0:
            return 1.0 if self.net_contribution_inr > 0 else 0.0
        return float(stats.norm.cdf(self.net_contribution_inr / self.contribution_se_inr))

    def posterior_percentile_inr(self, percentile: float) -> float:
        """A percentile of the posterior on net contribution, in rupees."""
        if self.contribution_se_inr <= 0:
            return self.net_contribution_inr
        return float(
            stats.norm.ppf(percentile, loc=self.net_contribution_inr, scale=self.contribution_se_inr)
        )

    @property
    def net_per_treated_customer_inr(self) -> float:
        """Net contribution per treated customer — the scale-free form."""
        return self.net_contribution_inr / self.n_treatment if self.n_treatment else 0.0

    @property
    def se_per_treated_customer_inr(self) -> float:
        return self.contribution_se_inr / self.n_treatment if self.n_treatment else 0.0

    @property
    def scale_eligible(self) -> bool:
        """Frequentist rule: the whole interval must clear zero.

        Retained for reporting and for the record of what the earlier rule would
        have decided. The live decision is :func:`assess_scale`.
        """
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
class ScaleDecision:
    """Whether the evidence supports spending, and why.

    Two conditions, both required:

    1. ``P(net > 0) >= min_probability`` — the campaign is probably profitable.
    2. the ``loss_percentile`` of the posterior, projected to the population the
       rollout would cover, sits above ``-tolerable_loss_inr`` — the bad tail is
       survivable.

    The first is about being right on average; the second is about what happens
    when it is wrong. A rule with only the first would scale campaigns whose
    downside could exceed the entire promotion budget.

    The asymmetry of the old rule is kept: spending requires evidence, declining
    requires none. Nothing here licenses an affirmative claim of harm.
    """

    scale: bool
    probability_net_positive: float
    projected_net_inr: float
    projected_downside_inr: float
    tolerable_loss_inr: float
    min_probability: float
    reason: str

    @property
    def failed_on_probability(self) -> bool:
        return self.probability_net_positive < self.min_probability

    @property
    def failed_on_downside(self) -> bool:
        return self.projected_downside_inr <= -self.tolerable_loss_inr


def assess_scale(
    comparison: "ArmComparison",
    *,
    projection_population: int,
    tolerable_loss_inr: float,
    min_probability: float = DEFAULT_MIN_PROBABILITY,
    loss_percentile: float = DEFAULT_LOSS_PERCENTILE,
) -> ScaleDecision:
    """Apply the posterior scaling rule to one arm comparison.

    The posterior is computed at pilot scale and then projected linearly to the
    population a rollout would treat, because that is the money actually at
    risk — a tolerable loss has to be measured against the decision being made,
    not against the sample used to inform it.
    """
    probability = comparison.probability_net_positive
    per_customer = comparison.net_per_treated_customer_inr
    se_per_customer = comparison.se_per_treated_customer_inr

    projected_net = per_customer * projection_population
    projected_se = se_per_customer * projection_population
    projected_downside = (
        float(stats.norm.ppf(loss_percentile, loc=projected_net, scale=projected_se))
        if projected_se > 0
        else projected_net
    )

    passes_probability = probability >= min_probability
    passes_downside = projected_downside > -tolerable_loss_inr

    if passes_probability and passes_downside:
        reason = (
            f"scale: P(net>0)={probability:.2f} >= {min_probability:.2f} and 5th percentile "
            f"Rs.{projected_downside:,.0f} above the tolerable loss of "
            f"Rs.{-tolerable_loss_inr:,.0f}"
        )
    elif not passes_probability:
        reason = (
            f"hold: P(net>0)={probability:.2f} < {min_probability:.2f}. Not enough evidence "
            "that spending here makes money."
        )
    else:
        reason = (
            f"hold: P(net>0)={probability:.2f} is adequate but the 5th percentile "
            f"Rs.{projected_downside:,.0f} breaches the tolerable loss of "
            f"Rs.{-tolerable_loss_inr:,.0f}. The bad tail is too expensive."
        )

    return ScaleDecision(
        scale=passes_probability and passes_downside,
        probability_net_positive=probability,
        projected_net_inr=projected_net,
        projected_downside_inr=projected_downside,
        tolerable_loss_inr=tolerable_loss_inr,
        min_probability=min_probability,
        reason=reason,
    )


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
    alpha: float | None = None,
) -> InterimResult | FinalResult:
    """Evaluate an experiment, refusing a verdict before the horizon.

    Contribution is *measured*, not modelled: each observation carries the mean
    and spread of per-customer contribution actually seen in its arm, and the
    effect is the difference between arm means. Basket effects, mix shifts and
    incentive costs are therefore inside the measurement rather than assumed
    away by a formula — which is what the incremental-orders-only estimator got
    wrong.

    Args:
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

    # Net incremental contribution: a two-sample difference of per-customer
    # contribution means, scaled to the treated arm.
    #
    #   net = n_t * (mean_t - mean_c)
    #   se  = n_t * sqrt(sd_t^2 / n_t + sd_c^2 / n_c)
    #
    # No assumption about where contribution comes from. If the treatment raised
    # baskets, that is already inside mean_t; if it only shifted who converts,
    # this reduces to the same answer the old estimator gave. The two agree
    # exactly when order values are constant across arms, and diverge precisely
    # in the case the old one could not represent.
    contribution_difference = treatment.contribution_mean_inr - control.contribution_mean_inr
    net = n_t * contribution_difference
    se_net = n_t * math.sqrt(
        treatment.contribution_sd_inr**2 / n_t + control.contribution_sd_inr**2 / n_c
    )

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
        contribution_se_inr=se_net,
    )
