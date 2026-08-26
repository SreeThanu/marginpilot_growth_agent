"""Contribution arithmetic. Pure functions, no state, no I/O, no LLM.

The whole project turns on one asymmetry, and it lives in this file:

    contribution is earned on the *incremental* orders,
    the incentive is paid on *every treated* order.

A campaign that lifts conversion from 12% to 18% on 1,000 customers creates 60
incremental orders worth Rs.14,400 of contribution, and pays Rs.100 to each of
180 treated buyers — Rs.18,000. Net **-Rs.3,600**. Every dashboard on the market
reports the +50% and calls it a win.

These functions are deliberately small and separately testable, because the
tests carry the project's credibility: each one is checked against a value
computed by hand rather than against the implementation's own output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #


def conversion_rate(orders: int, customers: int) -> float:
    """Orders per customer. Zero customers convert at zero, not at NaN."""
    if customers <= 0:
        return 0.0
    if orders < 0 or customers < 0:
        raise ValueError("counts cannot be negative")
    if orders > customers:
        raise ValueError(f"{orders} orders from {customers} customers is impossible")
    return orders / customers


def contribution_per_order_inr(aov_inr: float, contribution_margin: float) -> float:
    """Gross contribution a single order produces, before any incentive.

    ``margin`` is the fraction of order value surviving cost of goods, so
    Rs.800 at 30% yields Rs.240.
    """
    if aov_inr < 0:
        raise ValueError(f"aov cannot be negative, got {aov_inr}")
    if not 0.0 <= contribution_margin <= 1.0:
        raise ValueError(f"contribution_margin must be in [0, 1], got {contribution_margin}")
    return aov_inr * contribution_margin


def incremental_orders(
    control_orders: int,
    treatment_orders: int,
    n_control: int,
    n_treatment: int,
) -> float:
    """Orders that would not have happened without the treatment.

    Computed from *rates*, not from the raw difference in counts, so that
    unequal arms do not silently manufacture or destroy incremental orders.
    With equal arms this reduces to ``treatment_orders - control_orders``.
    """
    p_control = conversion_rate(control_orders, n_control)
    p_treatment = conversion_rate(treatment_orders, n_treatment)
    return (p_treatment - p_control) * n_treatment


def incremental_contribution_inr(
    incremental_order_count: float,
    aov_inr: float,
    contribution_margin: float,
) -> float:
    """Contribution earned by the incremental orders alone."""
    return incremental_order_count * contribution_per_order_inr(aov_inr, contribution_margin)


def incentive_cost_inr(treated_orders: float, incentive_per_order_inr: float) -> float:
    """What the promotion costs.

    Charged across **all** treated buyers, including those who would have
    bought at full price. This is the line every conversion-optimising system
    leaves out, and getting it wrong is the failure the project exists to
    demonstrate — so it takes treated orders, never incremental ones.
    """
    if treated_orders < 0:
        raise ValueError("treated_orders cannot be negative")
    if incentive_per_order_inr < 0:
        raise ValueError("incentive cannot be negative")
    return treated_orders * incentive_per_order_inr


def net_incremental_contribution_inr(
    incremental_contribution: float, incentive_cost: float
) -> float:
    """The number the agent is accountable for."""
    return incremental_contribution - incentive_cost


def romi(incremental_contribution: float, promotion_spend_inr: float) -> float:
    """Return on marketing investment: contribution earned per rupee spent.

    Gross contribution over spend, so ``romi > 1`` is exactly equivalent to
    positive net contribution. A campaign with no spend has no ROMI — returns
    0.0 rather than dividing by zero, and callers should read that alongside
    the spend figure.
    """
    if promotion_spend_inr <= 0:
        return 0.0
    return incremental_contribution / promotion_spend_inr


def project_to_population(
    net_contribution_inr: float, pilot_customers: int, population_customers: int
) -> float:
    """Scale a pilot result to the full customer base, linearly.

    Linear because it is the honest naive projection and the one a merchant
    would make. It ignores saturation and competitive response, which is why
    scaling decisions are gated on a confidence interval rather than on this
    number.
    """
    if pilot_customers <= 0:
        return 0.0
    return net_contribution_inr * (population_customers / pilot_customers)


# --------------------------------------------------------------------------- #
# The whole calculation in one place
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ContributionResult:
    """A complete contribution assessment of one experiment arm."""

    n_control: int
    n_treatment: int
    control_orders: int
    treatment_orders: int
    aov_inr: float
    contribution_margin: float
    incentive_per_order_inr: float

    incremental_order_count: float
    incremental_contribution_inr: float
    incentive_cost_inr: float
    net_incremental_contribution_inr: float
    romi: float

    @property
    def control_conversion(self) -> float:
        return conversion_rate(self.control_orders, self.n_control)

    @property
    def treatment_conversion(self) -> float:
        return conversion_rate(self.treatment_orders, self.n_treatment)

    @property
    def conversion_lift_absolute(self) -> float:
        return self.treatment_conversion - self.control_conversion

    @property
    def conversion_lift_relative(self) -> float:
        base = self.control_conversion
        return (self.conversion_lift_absolute / base) if base > 0 else 0.0

    @property
    def incremental_revenue_inr(self) -> float:
        """Revenue attributable to the treatment, before margin and incentive."""
        return self.incremental_order_count * self.aov_inr

    @property
    def is_profitable(self) -> bool:
        """Point estimate only. Authority to scale needs the CI lower bound —
        see ``src/experiment/evaluator.py``."""
        return self.net_incremental_contribution_inr > 0

    @property
    def contribution_per_incremental_order_inr(self) -> float:
        """One of the two scalars ``evaluator.evaluate`` takes."""
        return contribution_per_order_inr(self.aov_inr, self.contribution_margin)

    def projected_to(self, population_customers: int) -> float:
        return project_to_population(
            self.net_incremental_contribution_inr, self.n_treatment, population_customers
        )


def assess(
    *,
    n_control: int,
    n_treatment: int,
    control_orders: int,
    treatment_orders: int,
    aov_inr: float,
    contribution_margin: float,
    incentive_per_order_inr: float,
) -> ContributionResult:
    """Run the full contribution calculation for one treatment arm.

    The canonical case, checked by hand in the tests: 1,000 per arm, 120 vs 180
    orders, Rs.800 AOV, 30% margin, Rs.100 off gives 60 incremental orders,
    Rs.14,400 contribution, Rs.18,000 incentive cost, **-Rs.3,600** net, ROMI 0.8.
    """
    incremental = incremental_orders(control_orders, treatment_orders, n_control, n_treatment)
    contribution = incremental_contribution_inr(incremental, aov_inr, contribution_margin)
    cost = incentive_cost_inr(treatment_orders, incentive_per_order_inr)
    return ContributionResult(
        n_control=n_control,
        n_treatment=n_treatment,
        control_orders=control_orders,
        treatment_orders=treatment_orders,
        aov_inr=aov_inr,
        contribution_margin=contribution_margin,
        incentive_per_order_inr=incentive_per_order_inr,
        incremental_order_count=incremental,
        incremental_contribution_inr=contribution,
        incentive_cost_inr=cost,
        net_incremental_contribution_inr=net_incremental_contribution_inr(contribution, cost),
        romi=romi(contribution, cost),
    )


# --------------------------------------------------------------------------- #
# Per-arm contribution — the correct estimator
# --------------------------------------------------------------------------- #
#
# Everything above treats contribution as "incremental orders x a fixed
# contribution per order". That is only right when the treatment changes *who*
# buys and not *what they buy*. A bundle changes both: it raises the basket of
# every treated buyer, including those who would have bought anyway.
#
# Measured on dev worlds, the incremental-orders-only estimator had the wrong
# SIGN in 5 of 10 worlds on bundle experiments, reporting -Rs.0.53 per customer
# where the truth was +Rs.1.16. It could not see the basket.
#
# The fix is to stop modelling contribution and start measuring it: take each
# customer's realized contribution, net of any incentive they redeemed, and
# compare arm means. Basket effects, mix effects and incentive costs are then
# all inside the measurement rather than assumed away by the formula.


@dataclass(frozen=True, slots=True)
class ArmContribution:
    """Per-customer contribution in one experiment arm.

    ``mean`` is over *assigned* customers, not converters — a customer who did
    not buy contributed zero, and dropping them would silently condition on an
    outcome of the treatment.
    """

    n_assigned: int
    n_converted: int
    mean_inr: float
    sd_inr: float

    @property
    def total_inr(self) -> float:
        return self.mean_inr * self.n_assigned


def customer_contribution_inr(
    *,
    converted: bool,
    order_value_inr: float,
    contribution_margin: float,
    incentive_inr: float = 0.0,
) -> float:
    """One customer's contribution to the merchant over the experiment window.

    Zero if they did not buy. If they did, the margin on what they actually
    spent, less whatever incentive they redeemed.
    """
    if not converted:
        return 0.0
    return contribution_per_order_inr(order_value_inr, contribution_margin) - incentive_inr


def summarise_arm(contributions: Sequence[float], n_converted: int) -> ArmContribution:
    """Mean and sample standard deviation of per-customer contribution.

    Takes the full per-customer vector including the zeros, because those zeros
    are most of the variance and dropping them would understate the uncertainty
    the scaling decision depends on.
    """
    n = len(contributions)
    if n == 0:
        return ArmContribution(0, 0, 0.0, 0.0)
    values = np.asarray(contributions, dtype=float)
    # ddof=1: this is a sample, and at these n the correction is negligible but
    # the honesty is free.
    sd = float(values.std(ddof=1)) if n > 1 else 0.0
    return ArmContribution(
        n_assigned=n, n_converted=n_converted, mean_inr=float(values.mean()), sd_inr=sd
    )


def arm_from_counts(
    n_assigned: int,
    n_converted: int,
    *,
    contribution_per_order_inr: float,
    incentive_per_order_inr: float = 0.0,
) -> ArmContribution:
    """Build an arm summary when every order is worth the same.

    Exact rather than simulated: with a constant order value the per-customer
    contribution is Bernoulli, so the mean is ``p * (c - k)`` and the variance
    ``p(1-p)(c-k)^2``. Useful for hand-checked tests and for strategies that
    only have aggregate counts — and it is the case in which this estimator and
    the old incremental-orders one agree exactly.
    """
    if n_assigned <= 0:
        return ArmContribution(0, 0, 0.0, 0.0)
    p = n_converted / n_assigned
    per_converter = contribution_per_order_inr - incentive_per_order_inr
    mean = p * per_converter
    variance = p * (1 - p) * per_converter**2
    return ArmContribution(
        n_assigned=n_assigned,
        n_converted=n_converted,
        mean_inr=mean,
        sd_inr=math.sqrt(variance),
    )


def net_contribution_from_arms(
    control: ArmContribution, treatment: ArmContribution
) -> tuple[float, float]:
    """Net incremental contribution over the treated arm, and its standard error.

    A two-sample difference of means, scaled to the treated population::

        net = n_t * (mean_t - mean_c)
        se  = n_t * sqrt(sd_t^2 / n_t + sd_c^2 / n_c)

    No assumption about where contribution comes from: if the treatment raised
    baskets, that is already inside ``mean_t``.
    """
    if control.n_assigned == 0 or treatment.n_assigned == 0:
        return 0.0, 0.0
    per_customer = treatment.mean_inr - control.mean_inr
    variance = (
        treatment.sd_inr**2 / treatment.n_assigned + control.sd_inr**2 / control.n_assigned
    )
    return per_customer * treatment.n_assigned, math.sqrt(variance) * treatment.n_assigned
