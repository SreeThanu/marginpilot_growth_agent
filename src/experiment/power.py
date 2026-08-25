"""Sample size and minimum detectable effect for a two-proportion comparison.

This module computes the number that makes CLAUDE.md invariant 3 enforceable.
The horizon is derived here at *design* time from a minimum detectable effect,
written immutably into the registry at launch, and never revisited — so an
experiment's stopping point is fixed before a single observation exists and
cannot be renegotiated once the data starts to look interesting.

The inverse direction matters just as much. Given the sample an experiment can
actually reach, :func:`detectable_effect` returns the smallest effect that
sample could distinguish from noise. A design whose hypothesised effect is below
that number is not a risky experiment, it is an unreadable one: it will return
"no significant difference" whatever the truth is, and burn budget doing it.
Refusing those is a Day 7 policy decision, but the number it refuses on is here.

Deliberately plain formulas over a statistics package: these are the values that
carry the project's credibility, and every one of them is checked in the tests
against a hand-computed figure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy import optimize, stats

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80


@dataclass(frozen=True, slots=True)
class PowerAnalysis:
    """The design-time power calculation, kept whole so it can be logged.

    Recorded in the experiment registry as evidence of what was decided before
    the data existed. Storing the inputs alongside the answer is what makes the
    horizon auditable rather than merely asserted.
    """

    baseline_conversion: float
    mde_absolute: float
    alpha: float
    power: float
    comparisons: int
    n_per_arm: int

    @property
    def treatment_conversion(self) -> float:
        return self.baseline_conversion + self.mde_absolute

    @property
    def mde_relative(self) -> float:
        """The effect as a fraction of baseline — the form merchants think in."""
        return self.mde_absolute / self.baseline_conversion


def _z(alpha: float, power: float, comparisons: int) -> tuple[float, float]:
    """Critical values, with a Bonferroni correction across comparisons.

    A three-arm experiment makes two comparisons against control; testing both
    at the nominal alpha inflates the family-wise error rate. Splitting alpha is
    the conservative choice, and being conservative about false positives is the
    correct bias for a system whose false positives cost the merchant money.
    """
    if comparisons < 1:
        raise ValueError(f"comparisons must be >= 1 (got {comparisons})")
    adjusted_alpha = alpha / comparisons
    z_alpha = stats.norm.ppf(1.0 - adjusted_alpha / 2.0)  # two-sided
    z_beta = stats.norm.ppf(power)
    return float(z_alpha), float(z_beta)


def _validate(baseline_conversion: float, alpha: float, power: float) -> None:
    if not 0.0 < baseline_conversion < 1.0:
        raise ValueError(f"baseline_conversion must be in (0, 1), got {baseline_conversion}")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if not 0.0 < power < 1.0:
        raise ValueError(f"power must be in (0, 1), got {power}")


def required_sample_size_per_arm(
    baseline_conversion: float,
    mde_absolute: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> int:
    """Customers per arm needed to detect ``mde_absolute`` on conversion.

    Standard two-proportion normal approximation::

        n = (z_{a/2} + z_b)^2 * (p0(1-p0) + p1(1-p1)) / (p1 - p0)^2

    Rounded up: a fractional customer cannot be recruited, and rounding down
    would leave the experiment fractionally underpowered against the effect it
    was designed to detect.

    Worked example, checked in the tests: baseline 12%, MDE 6 points (the
    README's 12% -> 18% case), alpha 0.05, power 0.80 gives 553 per arm — which
    is why the README's 1,000-per-arm pilot is adequately powered for that
    effect and would not be for a 3-point one.
    """
    _validate(baseline_conversion, alpha, power)
    if mde_absolute <= 0.0:
        raise ValueError(f"mde_absolute must be positive, got {mde_absolute}")

    treatment = baseline_conversion + mde_absolute
    if not 0.0 < treatment < 1.0:
        raise ValueError(
            f"baseline {baseline_conversion} + MDE {mde_absolute} = {treatment}, "
            "which is not a probability"
        )

    z_alpha, z_beta = _z(alpha, power, comparisons)
    variance = baseline_conversion * (1 - baseline_conversion) + treatment * (1 - treatment)
    n = (z_alpha + z_beta) ** 2 * variance / mde_absolute**2
    return int(math.ceil(n))


def analyse(
    baseline_conversion: float,
    mde_absolute: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> PowerAnalysis:
    """The full design-time calculation, ready to be written into the registry."""
    n = required_sample_size_per_arm(
        baseline_conversion, mde_absolute, alpha=alpha, power=power, comparisons=comparisons
    )
    return PowerAnalysis(
        baseline_conversion=baseline_conversion,
        mde_absolute=mde_absolute,
        alpha=alpha,
        power=power,
        comparisons=comparisons,
        n_per_arm=n,
    )


def detectable_effect(
    baseline_conversion: float,
    n_per_arm: int,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> float:
    """Smallest absolute effect this sample can detect. The inverse of the above.

    Solved numerically rather than in closed form: the pooled variance term
    depends on the treatment rate, which depends on the effect being solved for.
    Bisection on a monotone function is exact enough and cannot silently return
    a wrong branch the way an algebraic rearrangement can.

    A design proposing an effect smaller than this is underpowered — it cannot
    return a readable answer at that sample, so running it spends budget to learn
    nothing. Day 7's policy gate refuses on this number.
    """
    _validate(baseline_conversion, alpha, power)
    if n_per_arm < 1:
        raise ValueError(f"n_per_arm must be positive, got {n_per_arm}")

    def shortfall(mde: float) -> float:
        return (
            required_sample_size_per_arm(
                baseline_conversion, mde, alpha=alpha, power=power, comparisons=comparisons
            )
            - n_per_arm
        )

    # Required n falls as the effect grows, so shortfall is decreasing in mde.
    upper = min(1.0 - baseline_conversion, 1.0) - 1e-9
    if shortfall(upper) > 0:
        # Even the largest expressible effect needs more sample than we have.
        return upper
    lower = 1e-6
    if shortfall(lower) < 0:
        return lower
    return float(optimize.brentq(shortfall, lower, upper, xtol=1e-9))


def is_adequately_powered(
    baseline_conversion: float,
    mde_absolute: float,
    n_per_arm: int,
    *,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> bool:
    """Can ``n_per_arm`` detect ``mde_absolute``? Reported, not enforced here.

    Enforcement belongs to ``src/policy/`` on Day 7. This module answers the
    question; it does not decide what to do about the answer.
    """
    required = required_sample_size_per_arm(
        baseline_conversion, mde_absolute, alpha=alpha, power=power, comparisons=comparisons
    )
    return n_per_arm >= required


# --------------------------------------------------------------------------- #
# Powering on contribution — the quantity the decision actually turns on
# --------------------------------------------------------------------------- #
#
# Sizing an experiment for a conversion MDE and then deciding on a confidence
# interval over rupees is a category error: the two quantities have different
# variances, and the conversion-powered sample is badly undersized for the
# rupee question. Contribution carries the incentive cost, which is paid on
# every treated order and is therefore a second source of variance that the
# conversion calculation does not see at all.
#
# Per treated customer the effect is
#
#     theta = (p_t - p_c) * c  -  p_t * k
#
# where c is contribution per incremental order and k is the incentive paid per
# treated order. By the delta method, with Cov(p_t - p_c, p_t) = Var(p_t),
#
#     n * Var(theta_hat) = p_t(1-p_t)(c-k)^2 + p_c(1-p_c)c^2  =:  S
#
# so the sample needed to detect theta_min is (z_a/2 + z_b)^2 * S / theta_min^2,
# exactly analogous to the proportion formula but in rupees.


@dataclass(frozen=True, slots=True)
class ContributionPowerAnalysis:
    """Design-time power on net contribution per treated customer."""

    baseline_conversion: float
    expected_lift_absolute: float
    contribution_per_incremental_order_inr: float
    incentive_cost_per_treated_order_inr: float
    mde_contribution_per_customer_inr: float
    alpha: float
    power: float
    comparisons: int
    n_per_arm: int

    @property
    def treatment_conversion(self) -> float:
        return self.baseline_conversion + self.expected_lift_absolute

    @property
    def mde_total_inr(self) -> float:
        """The MDE expressed as rupees over the whole treated arm at horizon."""
        return self.mde_contribution_per_customer_inr * self.n_per_arm

    @property
    def expected_net_per_customer_inr(self) -> float:
        """What the design expects to find, in rupees per treated customer."""
        return (
            self.expected_lift_absolute * self.contribution_per_incremental_order_inr
            - self.treatment_conversion * self.incentive_cost_per_treated_order_inr
        )


def contribution_variance_term(
    baseline_conversion: float,
    expected_lift_absolute: float,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
) -> float:
    """``S`` above: ``n * Var(theta_hat)``. Exposed because it is worth testing."""
    p_c = baseline_conversion
    p_t = baseline_conversion + expected_lift_absolute
    if not 0.0 < p_t < 1.0:
        raise ValueError(f"treatment conversion {p_t} is not a probability")
    c = contribution_per_incremental_order_inr
    k = incentive_cost_per_treated_order_inr
    return p_t * (1 - p_t) * (c - k) ** 2 + p_c * (1 - p_c) * c**2


def required_sample_size_for_contribution(
    baseline_conversion: float,
    expected_lift_absolute: float,
    *,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
    mde_contribution_per_customer_inr: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> int:
    """Customers per arm needed to detect a contribution effect, in rupees."""
    _validate(baseline_conversion, alpha, power)
    if mde_contribution_per_customer_inr <= 0:
        raise ValueError(
            f"mde_contribution_per_customer_inr must be positive, got "
            f"{mde_contribution_per_customer_inr}"
        )

    s = contribution_variance_term(
        baseline_conversion,
        expected_lift_absolute,
        contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr,
    )
    z_alpha, z_beta = _z(alpha, power, comparisons)
    return int(math.ceil((z_alpha + z_beta) ** 2 * s / mde_contribution_per_customer_inr**2))


def analyse_contribution(
    baseline_conversion: float,
    expected_lift_absolute: float,
    *,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
    mde_contribution_per_customer_inr: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> ContributionPowerAnalysis:
    """The contribution power calculation, ready for the registry."""
    n = required_sample_size_for_contribution(
        baseline_conversion,
        expected_lift_absolute,
        contribution_per_incremental_order_inr=contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        mde_contribution_per_customer_inr=mde_contribution_per_customer_inr,
        alpha=alpha,
        power=power,
        comparisons=comparisons,
    )
    return ContributionPowerAnalysis(
        baseline_conversion=baseline_conversion,
        expected_lift_absolute=expected_lift_absolute,
        contribution_per_incremental_order_inr=contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        mde_contribution_per_customer_inr=mde_contribution_per_customer_inr,
        alpha=alpha,
        power=power,
        comparisons=comparisons,
        n_per_arm=n,
    )


def detectable_contribution_effect(
    baseline_conversion: float,
    expected_lift_absolute: float,
    n_per_arm: int,
    *,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    comparisons: int = 1,
) -> float:
    """Smallest per-customer contribution effect this sample can resolve.

    Closed form, unlike the conversion inverse: the variance term does not
    depend on the effect being solved for.
    """
    _validate(baseline_conversion, alpha, power)
    if n_per_arm < 1:
        raise ValueError(f"n_per_arm must be positive, got {n_per_arm}")
    s = contribution_variance_term(
        baseline_conversion,
        expected_lift_absolute,
        contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr,
    )
    z_alpha, z_beta = _z(alpha, power, comparisons)
    return (z_alpha + z_beta) * math.sqrt(s / n_per_arm)


def affordable_sample_per_arm(
    remaining_budget_inr: float,
    *,
    treatment_conversion: float,
    incentive_cost_per_treated_order_inr: float,
    n_treatment_arms: int = 1,
) -> int:
    """How many customers per arm the remaining budget can actually pay for.

    Only treated arms cost money, and only their *converting* customers redeem
    the incentive, so the spend per treated customer is ``p_t * k``.
    """
    if remaining_budget_inr < 0:
        raise ValueError("remaining budget cannot be negative")
    per_customer = treatment_conversion * incentive_cost_per_treated_order_inr
    if per_customer <= 0:
        return 2**31 - 1  # a free intervention is limited by population, not budget
    return int(remaining_budget_inr // (per_customer * max(n_treatment_arms, 1)))


@dataclass(frozen=True, slots=True)
class DesignFeasibility:
    """Whether a question is answerable at all, given budget and population.

    A **first-class outcome, not an error**. "This question cannot be answered
    within budget" is a legitimate and useful conclusion for the agent to reach,
    and it should be able to reach it at design time — before spending anything —
    rather than by running an experiment that was always going to be unreadable.
    """

    feasible: bool
    reason: str
    required_n_per_arm: int
    affordable_n_per_arm: int
    available_n_per_arm: int
    limiting_factor: str
    detectable_at_affordable_n_inr: float
    mde_contribution_per_customer_inr: float
    projected_spend_inr: float

    @property
    def shortfall_per_arm(self) -> int:
        return max(self.required_n_per_arm - min(self.affordable_n_per_arm, self.available_n_per_arm), 0)


def assess_feasibility(
    baseline_conversion: float,
    expected_lift_absolute: float,
    *,
    contribution_per_incremental_order_inr: float,
    incentive_cost_per_treated_order_inr: float,
    mde_contribution_per_customer_inr: float,
    remaining_budget_inr: float,
    population: int,
    n_arms: int = 2,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> DesignFeasibility:
    """Can this experiment answer its question within budget and population?

    Refusing here is cheap; refusing after the money is spent is not.
    """
    comparisons = max(n_arms - 1, 1)
    required = required_sample_size_for_contribution(
        baseline_conversion,
        expected_lift_absolute,
        contribution_per_incremental_order_inr=contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        mde_contribution_per_customer_inr=mde_contribution_per_customer_inr,
        alpha=alpha,
        power=power,
        comparisons=comparisons,
    )
    treatment_conversion = baseline_conversion + expected_lift_absolute
    affordable = affordable_sample_per_arm(
        remaining_budget_inr,
        treatment_conversion=treatment_conversion,
        incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        n_treatment_arms=comparisons,
    )
    available = population // n_arms
    attainable = min(affordable, available)

    detectable = detectable_contribution_effect(
        baseline_conversion,
        expected_lift_absolute,
        max(attainable, 1),
        contribution_per_incremental_order_inr=contribution_per_incremental_order_inr,
        incentive_cost_per_treated_order_inr=incentive_cost_per_treated_order_inr,
        alpha=alpha,
        power=power,
        comparisons=comparisons,
    )
    spend = required * treatment_conversion * incentive_cost_per_treated_order_inr * comparisons

    if attainable >= required:
        limiting = "none"
        reason = (
            f"answerable: {required} per arm needed, {attainable} attainable "
            f"({affordable} affordable, {available} available)"
        )
        return DesignFeasibility(
            True, reason, required, affordable, available, limiting, detectable,
            mde_contribution_per_customer_inr, spend,
        )

    limiting = "budget" if affordable < available else "population"
    reason = (
        f"not answerable within {limiting}: detecting Rs."
        f"{mde_contribution_per_customer_inr:,.2f} per customer needs {required} per arm, "
        f"but only {attainable} are attainable. At that sample the smallest "
        f"resolvable effect is Rs.{detectable:,.2f} per customer. Spending the budget "
        "on this design would buy an unreadable answer."
    )
    return DesignFeasibility(
        False, reason, required, affordable, available, limiting, detectable,
        mde_contribution_per_customer_inr, spend,
    )
