"""Baseline 2 — the rule-based marketer.

A fixed rule, applied directly to a targeted group, with no experiment: send a
percentage discount to customers who look unlikely to buy. This is what most
merchants actually do, and it learns nothing — there is no control group, so the
merchant never finds out whether the campaign worked or what it cost them.

**On targeting by "P(purchase) < 0.4".** The true purchase probability is a
latent parameter of the simulator and is not in the merchant's data, so keying a
rule on it would be reading the answer rather than targeting. This baseline uses
what a real marketer has — recency and frequency — as the proxy for low
propensity. That is both the honest implementation and the realistic one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.eval.contracts import DirectAction, MerchantView, Proposal, ScalingRule
from src.world.schema import InterventionKind


@dataclass(frozen=True, slots=True)
class RuleBasedMarketer:
    name: str = "2_rule_based"
    scaling_rule: ScalingRule = ScalingRule.NEVER  # never tests, so never scales
    max_experiments: int = 0
    #: Treat customers with at most this many orders in the last 90 days.
    max_recent_orders: int = 1
    #: ...and who have not ordered for at least this long.
    min_days_since_order: int = 60

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        discount = next(
            (i for i in view.interventions if i.kind is InterventionKind.PERCENTAGE_DISCOUNT),
            view.interventions[0],
        )
        targets = tuple(
            c.customer_id
            for c in view.customers
            if c.orders_last_90d <= self.max_recent_orders
            and c.days_since_last_order >= self.min_days_since_order
        )
        if not targets:
            return []

        # Stay inside the budget by treating only as many as it can pay for.
        expected_cost_each = view.observed_conversion * discount.incentive_cost_inr(
            view.observed_aov_inr
        )
        if expected_cost_each > 0:
            affordable = int(budget_inr // expected_cost_each)
            targets = targets[:affordable]

        return [
            DirectAction(
                intervention_id=discount.intervention_id,
                target_customer_ids=targets,
                rationale=(
                    f"Fixed rule: {discount.name} to customers with "
                    f"<= {self.max_recent_orders} orders in 90 days and "
                    f">= {self.min_days_since_order} days since their last order. "
                    "No control group, so no measurement."
                ),
            )
        ]
