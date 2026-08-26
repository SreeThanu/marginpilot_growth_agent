"""The money gate. Deterministic, no LLM, and the only thing that says yes.

CLAUDE.md invariant 2: the agent proposes, this module disposes. Every
money-adjacent action — launching an experiment, rolling one out — passes
through here first, and nothing downstream is permitted to spend without a
verdict from this file.

Every rule returns a structured :class:`RuleViolation` naming the rule that
fired, the value that violated it, and the limit it violated — never a bare
boolean. A gate that answers "no" without saying which rule and which number is
useless twice over: the agent cannot re-plan against it, and the audit trail
cannot show a reviewer why the refusal was correct.

Five rules, matching CLAUDE.md:

1. **Remaining budget** — projected spend must fit what is left.
2. **Maximum discount** — depth is capped, whatever the agent believes.
3. **Minimum contribution margin** — never promote below a margin floor.
4. **Maximum customer exposure** — a single campaign may not touch the whole base.
5. **Minimum experiment power** — an unreadable experiment is refused before it
   spends, not after.

This module imports no LLM client and never will;
``tests/test_module_boundaries.py`` enforces that by AST scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Rule(str, Enum):
    """Named so a rejection is greppable in the audit log."""

    REMAINING_BUDGET = "remaining_budget"
    MAX_DISCOUNT = "max_discount"
    MIN_CONTRIBUTION_MARGIN = "min_contribution_margin"
    MAX_CUSTOMER_EXPOSURE = "max_customer_exposure"
    MIN_EXPERIMENT_POWER = "min_experiment_power"


@dataclass(frozen=True, slots=True)
class PolicyLimits:
    """The merchant's standing constraints.

    Defaults are deliberately conservative. Every one of them is a number the
    merchant would recognise and could argue with, which is the point — a policy
    nobody can read is a policy nobody agreed to.
    """

    #: Deepest discount permitted, as a fraction of order value.
    max_discount_pct: float = 0.25
    #: Never promote a basket whose contribution margin is below this.
    min_contribution_margin: float = 0.15
    #: A single campaign may treat at most this share of the customer base.
    #: Stops one experiment consuming the population every later question needs.
    max_customer_exposure_share: float = 0.60
    #: Statistical power a design must reach to be worth funding.
    min_experiment_power: float = 0.80
    #: Fraction of budget that must survive a single action, so one campaign
    #: cannot leave the merchant unable to act at all.
    min_budget_headroom_share: float = 0.0


@dataclass(frozen=True, slots=True)
class RuleViolation:
    """One rule, one violating value, one limit. Never a bare boolean."""

    rule: Rule
    observed: float
    limit: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.value,
            "observed": self.observed,
            "limit": self.limit,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    """What the gate decided, and on what grounds.

    Carries the rules that were *checked* as well as the ones that fired, so the
    audit trail records what the gate actually examined rather than only what it
    objected to.
    """

    approved: bool
    action: str
    violations: tuple[RuleViolation, ...] = ()
    checked: tuple[Rule, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        if self.approved:
            return f"approved: {len(self.checked)} rules checked, none violated"
        return "; ".join(v.message for v in self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "action": self.action,
            "violations": [v.to_dict() for v in self.violations],
            "checked": [r.value for r in self.checked],
            "detail": self.detail,
            "reason": self.reason,
        }


class PolicyRejection(PermissionError):
    """Raised when code attempts an action the gate refused.

    Exists so that an ungated spend is impossible rather than merely discouraged:
    callers that ignore a verdict hit this instead of moving money.
    """

    def __init__(self, verdict: PolicyVerdict) -> None:
        super().__init__(verdict.reason)
        self.verdict = verdict


# --------------------------------------------------------------------------- #
# Individual rules
# --------------------------------------------------------------------------- #


def check_budget(projected_spend_inr: float, remaining_budget_inr: float,
                 limits: PolicyLimits) -> RuleViolation | None:
    """Projected spend must fit inside what is left, with headroom."""
    usable = remaining_budget_inr * (1.0 - limits.min_budget_headroom_share)
    if projected_spend_inr > usable:
        return RuleViolation(
            rule=Rule.REMAINING_BUDGET,
            observed=projected_spend_inr,
            limit=usable,
            message=(
                f"REJECTED — projected spend Rs.{projected_spend_inr:,.0f} exceeds "
                f"remaining budget Rs.{usable:,.0f}"
            ),
        )
    return None


def check_discount(depth: float, limits: PolicyLimits) -> RuleViolation | None:
    """Discount depth is capped regardless of what the agent expects to earn."""
    if depth > limits.max_discount_pct:
        return RuleViolation(
            rule=Rule.MAX_DISCOUNT,
            observed=depth,
            limit=limits.max_discount_pct,
            message=(
                f"REJECTED — discount {depth:.0%} exceeds max_discount "
                f"{limits.max_discount_pct:.0%}"
            ),
        )
    return None


def check_margin(contribution_margin: float, limits: PolicyLimits) -> RuleViolation | None:
    """Never promote below the margin floor.

    A campaign on a basket that barely contributes cannot pay for itself no
    matter how well it converts.
    """
    if contribution_margin < limits.min_contribution_margin:
        return RuleViolation(
            rule=Rule.MIN_CONTRIBUTION_MARGIN,
            observed=contribution_margin,
            limit=limits.min_contribution_margin,
            message=(
                f"REJECTED — contribution margin {contribution_margin:.1%} below floor "
                f"{limits.min_contribution_margin:.1%}"
            ),
        )
    return None


def check_exposure(customers_treated: int, population: int,
                   limits: PolicyLimits) -> RuleViolation | None:
    """One campaign may not consume the whole customer base."""
    if population <= 0:
        return None
    share = customers_treated / population
    if share > limits.max_customer_exposure_share:
        return RuleViolation(
            rule=Rule.MAX_CUSTOMER_EXPOSURE,
            observed=share,
            limit=limits.max_customer_exposure_share,
            message=(
                f"REJECTED — would treat {share:.0%} of customers "
                f"({customers_treated:,} of {population:,}), above the "
                f"{limits.max_customer_exposure_share:.0%} exposure cap"
            ),
        )
    return None


def check_power(power: float, limits: PolicyLimits) -> RuleViolation | None:
    """An experiment that cannot read its own result is refused before it spends."""
    if power < limits.min_experiment_power:
        return RuleViolation(
            rule=Rule.MIN_EXPERIMENT_POWER,
            observed=power,
            limit=limits.min_experiment_power,
            message=(
                f"REJECTED — design power {power:.2f} below minimum "
                f"{limits.min_experiment_power:.2f}; the experiment would spend budget "
                "to buy an unreadable answer"
            ),
        )
    return None


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #


def gate_experiment(
    *,
    experiment_id: str,
    projected_spend_inr: float,
    remaining_budget_inr: float,
    discount_depth: float,
    contribution_margin: float,
    customers_treated: int,
    population: int,
    power: float,
    limits: PolicyLimits | None = None,
) -> PolicyVerdict:
    """All five rules, applied before an experiment may launch."""
    limits = limits or PolicyLimits()
    checks = (
        check_budget(projected_spend_inr, remaining_budget_inr, limits),
        check_discount(discount_depth, limits),
        check_margin(contribution_margin, limits),
        check_exposure(customers_treated, population, limits),
        check_power(power, limits),
    )
    violations = tuple(v for v in checks if v is not None)
    return PolicyVerdict(
        approved=not violations,
        action=f"launch:{experiment_id}",
        violations=violations,
        checked=tuple(Rule),
        detail={
            "projected_spend_inr": projected_spend_inr,
            "remaining_budget_inr": remaining_budget_inr,
            "discount_depth": discount_depth,
            "contribution_margin": contribution_margin,
            "customers_treated": customers_treated,
            "population": population,
            "power": power,
        },
    )


def gate_rollout(
    *,
    experiment_id: str,
    projected_spend_inr: float,
    remaining_budget_inr: float,
    discount_depth: float,
    contribution_margin: float,
    customers_treated: int,
    population: int,
    limits: PolicyLimits | None = None,
) -> PolicyVerdict:
    """Rules applied before a *rollout* may spend.

    Day 5 recorded four to seven budget overruns per run because rollouts had no
    gate at all: an experiment was funded, cleared the scaling rule, and then
    spent whatever the remaining population cost. Scaling is the larger of the
    two spends, so gating the pilot and not the rollout gated the cheaper half.

    Power is not re-checked — the experiment already ran, and its readability is
    settled — but budget, depth, margin and exposure all still bind.
    """
    limits = limits or PolicyLimits()
    checks = (
        check_budget(projected_spend_inr, remaining_budget_inr, limits),
        check_discount(discount_depth, limits),
        check_margin(contribution_margin, limits),
        check_exposure(customers_treated, population, limits),
    )
    violations = tuple(v for v in checks if v is not None)
    return PolicyVerdict(
        approved=not violations,
        action=f"rollout:{experiment_id}",
        violations=violations,
        checked=(
            Rule.REMAINING_BUDGET,
            Rule.MAX_DISCOUNT,
            Rule.MIN_CONTRIBUTION_MARGIN,
            Rule.MAX_CUSTOMER_EXPOSURE,
        ),
        detail={
            "projected_spend_inr": projected_spend_inr,
            "remaining_budget_inr": remaining_budget_inr,
            "customers_treated": customers_treated,
            "population": population,
        },
    )


def affordable_rollout_customers(
    *,
    remaining_budget_inr: float,
    cost_per_treated_customer_inr: float,
    population: int,
    limits: PolicyLimits | None = None,
) -> int:
    """How many customers a rollout may actually treat.

    The gate's constructive half. Refusing an over-budget rollout outright would
    throw away a campaign the merchant can partly afford, so the gate also says
    how much of it is fundable — bounded by both budget and the exposure cap.
    """
    limits = limits or PolicyLimits()
    if cost_per_treated_customer_inr <= 0:
        return int(population * limits.max_customer_exposure_share)
    usable = remaining_budget_inr * (1.0 - limits.min_budget_headroom_share)
    by_budget = int(usable // cost_per_treated_customer_inr)
    by_exposure = int(population * limits.max_customer_exposure_share)
    return max(min(by_budget, by_exposure), 0)
