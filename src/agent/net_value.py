"""Net contribution arithmetic for a proposed campaign. Deterministic, no model.

Every quantity here is built from :mod:`src.economics.contribution` rather than
re-derived, so the product and the research evaluation cannot drift apart on
what a rupee means.

The one thing this module adds is the **break-even lift**: the conversion lift
at which net contribution crosses zero. It is arithmetic, not a threshold —

    net(L) = L·N·C − (p0 + L)·N·I

    net(L) = 0  ⟺  L·C = (p0 + L)·I  ⟺  L = p0·I / (C − I)

where ``C`` is contribution per order and ``I`` is incentive cost per treated
order. When ``C ≤ I`` no lift reaches break-even at all: every incremental order
costs more to buy than it earns, and the campaign loses money at any response
level. That case returns ``None``, which is a finding rather than an error.

Note the asymmetry the second term carries. Cost is charged on ``(p0 + L)·N``
treated *orders* — every buyer, not just the ones the promotion created. That is
the line conversion-optimising systems leave out, and it is why a campaign with
a real positive lift can still destroy contribution.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.economics.contribution import (
    incentive_cost_inr,
    incremental_contribution_inr,
    net_incremental_contribution_inr,
)


@dataclass(frozen=True, slots=True)
class NetProjection:
    """What a campaign is expected to earn, and what it costs to earn it."""

    customers_treated: int
    baseline_conversion: float
    expected_lift_absolute: float
    incremental_orders: float
    treated_orders: float
    contribution_per_order_inr: float
    incentive_cost_per_order_inr: float
    incremental_contribution_inr: float
    incentive_cost_inr: float
    net_contribution_inr: float
    #: ``None`` when contribution per order does not exceed incentive per order,
    #: i.e. when no response level can make the campaign pay.
    required_break_even_lift_absolute: float | None

    @property
    def is_positive(self) -> bool:
        return self.net_contribution_inr > 0.0

    @property
    def net_per_treated_customer_inr(self) -> float:
        if self.customers_treated <= 0:
            return 0.0
        return self.net_contribution_inr / self.customers_treated


def required_break_even_lift(
    *,
    baseline_conversion: float,
    contribution_per_order_inr: float,
    incentive_cost_per_order_inr: float,
) -> float | None:
    """The lift at which net contribution reaches zero, or ``None`` if unreachable.

    ``None`` is the economically meaningful answer when each order earns no more
    than the incentive that bought it: there is then no conversion lift, however
    large, that turns the campaign profitable.
    """
    if baseline_conversion < 0.0:
        raise ValueError("baseline_conversion cannot be negative")
    margin_per_order = contribution_per_order_inr - incentive_cost_per_order_inr
    if margin_per_order <= 0.0:
        return None
    return baseline_conversion * incentive_cost_per_order_inr / margin_per_order


def project_net(
    *,
    customers_treated: int,
    baseline_conversion: float,
    expected_lift_absolute: float,
    contribution_per_order_inr: float,
    incentive_cost_per_order_inr: float,
) -> NetProjection:
    """Expected net contribution for treating ``customers_treated`` customers.

    Uses the project's own economics functions throughout, so the incentive is
    charged across all treated orders exactly as
    ``src/eval/harness.py`` charges it against ground truth.
    """
    if customers_treated < 0:
        raise ValueError("customers_treated cannot be negative")
    if not 0.0 <= baseline_conversion <= 1.0:
        raise ValueError(f"baseline_conversion out of range: {baseline_conversion}")
    if expected_lift_absolute < 0.0:
        raise ValueError("expected_lift_absolute cannot be negative")

    treated_conversion = min(baseline_conversion + expected_lift_absolute, 1.0)
    realised_lift = treated_conversion - baseline_conversion

    incremental = realised_lift * customers_treated
    treated_orders = treated_conversion * customers_treated

    # aov and margin are folded into contribution_per_order_inr already, so the
    # economics helper is called with margin 1.0 and the per-order figure as aov.
    gross = incremental_contribution_inr(incremental, contribution_per_order_inr, 1.0)
    cost = incentive_cost_inr(treated_orders, incentive_cost_per_order_inr)
    net = net_incremental_contribution_inr(gross, cost)

    return NetProjection(
        customers_treated=customers_treated,
        baseline_conversion=baseline_conversion,
        expected_lift_absolute=realised_lift,
        incremental_orders=incremental,
        treated_orders=treated_orders,
        contribution_per_order_inr=contribution_per_order_inr,
        incentive_cost_per_order_inr=incentive_cost_per_order_inr,
        incremental_contribution_inr=gross,
        incentive_cost_inr=cost,
        net_contribution_inr=net,
        required_break_even_lift_absolute=required_break_even_lift(
            baseline_conversion=baseline_conversion,
            contribution_per_order_inr=contribution_per_order_inr,
            incentive_cost_per_order_inr=incentive_cost_per_order_inr,
        ),
    )


def cost_per_treated_customer_inr(
    *,
    baseline_conversion: float,
    expected_lift_absolute: float,
    incentive_cost_per_order_inr: float,
) -> float:
    """Expected incentive spend per *customer* treated, not per order.

    The rollout gate sizes spend by customers, so the per-order incentive has to
    be discounted by the share of treated customers who actually order.
    """
    treated_conversion = min(baseline_conversion + expected_lift_absolute, 1.0)
    return treated_conversion * incentive_cost_per_order_inr
