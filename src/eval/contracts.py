"""The contract every strategy implements, and the view every strategy sees.

Both live here because the harness is what runs strategies against each other,
and a comparison is only fair if all six see exactly the same thing.

:class:`MerchantView` is the agent-facing projection of a world. What it leaves
out is the point: no ``WorldParams``, so no true elasticity, no response scale,
no per-intervention affinity, no true baseline conversion — and no potential
outcomes. A strategy that could read those would not need to experiment, and the
whole evaluation would be measuring nothing. The tool layer on Day 6 builds on
this projection rather than replacing it.

The observable aggregates here are the ones a merchant genuinely has: historical
conversion, average order value, catalogue margin, customer count, budget. They
are the merchant's own numbers, not the simulator's parameters.
"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence, Union, runtime_checkable

from src.world.schema import Intervention, Product, SemanticContext, World


class ScalingRule(str, Enum):
    """How a strategy decides whether a tested campaign deserves the budget.

    This is the axis the baselines differ on, so it has to be explicit rather
    than hardcoded in the harness. Baseline 3's defining flaw — scaling on
    conversion while ignoring contribution — is only expressible if the rule is
    a property of the strategy.
    """

    #: P(net > 0) >= 0.80 and the posterior 5th percentile, projected to the
    #: rollout population, stays above a tolerable loss. MarginPilot's rule.
    BAYESIAN_POSTERIOR = "bayesian_posterior"
    #: The whole CI on incremental contribution clears zero. The earlier rule,
    #: kept so its decisions can still be reported alongside.
    CI_LOWER_BOUND = "ci_lower_bound"
    #: The CI on *conversion* clears zero. Statistically sound, economically
    #: blind: this is what most growth tooling does.
    CONVERSION_LIFT = "conversion_lift"
    #: Positive point estimate on contribution. No uncertainty discipline.
    POINT_ESTIMATE = "point_estimate"
    #: Never scale. Isolates the cost of learning.
    NEVER = "never"


@dataclass(frozen=True, slots=True)
class CustomerView:
    """One customer as the merchant's own records show them.

    Behavioural history only. ``baseline_purchase_prob``, ``price_elasticity``
    and ``responsiveness`` are latent parameters the strategy is supposed to
    estimate, and are deliberately absent — a rule keyed on the true purchase
    probability would be reading the answer, not targeting.
    """

    customer_id: str
    segment_id: str
    tenure_days: int
    orders_last_90d: int
    days_since_last_order: int
    #: Mean value of this customer's past orders. Genuinely in the merchant's
    #: order table, unlike the parameters above.
    historical_aov_inr: float


@dataclass(frozen=True, slots=True)
class InterventionHistory:
    """What a past campaign of this type actually returned for this merchant.

    Cycle 2, Fix B. The agent previously reasoned about interventions from their
    descriptions; a merchant with any promotional history knows which offer
    types have paid before.

    Deliberately a *small* past campaign — 300 treated customers — so the figure
    is informative without being decisive. A large enough history would make
    selection arithmetic and the agent would win by reading one number, which
    would measure nothing about reasoning. ``sample_size`` is exposed so the
    agent can weigh the estimate rather than trust it.

    Realized outcomes only. The latent that produced them is not here.
    """

    intervention_id: str
    treated_customers: int
    orders: int
    #: Realized *incremental* net contribution per treated customer, measured
    #: against a control arm the merchant held back at the time.
    #:
    #: Incremental, not gross. Gross contribution on treated orders counts the
    #: buyers who would have bought anyway and makes every campaign look
    #: profitable — which is the exact error this project exists to demonstrate.
    #: A history built that way would push the agent toward more spending, not
    #: better spending.
    net_per_treated_customer_inr: float
    #: Standard error of that mean. The honest width of the estimate.
    standard_error_inr: float

    @property
    def sample_size(self) -> int:
        return self.treated_customers

    @property
    def looks_profitable(self) -> bool:
        """Point estimate only, and stated as such — not authority to act."""
        return self.net_per_treated_customer_inr > 0


@dataclass(frozen=True, slots=True)
class SegmentView:
    """A segment as the merchant knows it: name, size, and the qualitative note.

    Deliberately without the behaviour multipliers. ``elasticity_multiplier``
    would hand the agent a number it is supposed to estimate.
    """

    segment_id: str
    name: str
    share: float
    notes: str
    behaviour_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MerchantView:
    """Everything a strategy is allowed to see before it decides."""

    world_id: str
    population: int
    budget_inr: float
    #: Historical conversion rate, as observed. Not the simulator's parameter.
    observed_conversion: float
    observed_aov_inr: float
    observed_margin: float
    experiment_window_days: int
    semantic: SemanticContext
    products: tuple[Product, ...]
    segments: tuple[SegmentView, ...]
    customers: tuple[CustomerView, ...]
    interventions: tuple[Intervention, ...]
    #: Past campaign results per intervention (Cycle 2, Fix B). Empty in Cycle 1.
    history: tuple[InterventionHistory, ...] = ()

    @property
    def projected_revenue_inr(self) -> float:
        return self.population * self.observed_conversion * self.observed_aov_inr

    def history_for(self, intervention_id: str) -> "InterventionHistory | None":
        for entry in self.history:
            if entry.intervention_id == intervention_id:
                return entry
        return None

    def intervention(self, intervention_id: str) -> Intervention:
        for candidate in self.interventions:
            if candidate.intervention_id == intervention_id:
                return candidate
        raise KeyError(intervention_id)


@dataclass(frozen=True, slots=True)
class ExperimentProposal:
    """What a strategy asks for. It proposes; the engine disposes.

    Note what is absent: no arm assignments, no horizon, no sample size. The
    horizon follows from the power calculation on the stated effect, and
    assignment is the experiment engine's alone (CLAUDE.md invariants 1 and 3).
    A strategy states what it believes and how small an effect would still be
    worth knowing about; everything else is derived.
    """

    intervention_id: str
    hypothesis_id: str
    prediction: str
    reasoning: str
    #: Predicted absolute lift in conversion.
    expected_effect_absolute: float
    #: The smallest per-customer contribution effect worth resolving, in rupees.
    #: Sets the horizon via the contribution power calculation.
    mde_contribution_per_customer_inr: float
    success_condition: str
    failure_condition: str
    arms: tuple[str, ...] = ("control", "treatment")


@dataclass(frozen=True, slots=True)
class DirectAction:
    """Run a campaign without testing it first.

    Baseline 2's whole approach, and the thing MarginPilot argues against: the
    merchant applies a rule to a targeted group and books the result, learning
    nothing about whether it worked. Included because it is what most merchants
    actually do, so beating it has to be demonstrated rather than assumed.
    """

    intervention_id: str
    #: Customers to treat. Chosen by the strategy from observable history.
    target_customer_ids: tuple[str, ...]
    rationale: str


Proposal = Union[ExperimentProposal, DirectAction]


@runtime_checkable
class Strategy(Protocol):
    """Six implementations share this: five baselines and MarginPilot itself.

    One interface so the harness can run them over identical worlds with
    identical inputs. A strategy that returns no proposals is doing nothing,
    which is Baseline 1 and a perfectly legitimate answer.
    """

    name: str
    #: How this strategy decides to scale a tested campaign.
    scaling_rule: ScalingRule
    #: How many experiments this strategy is willing to run per world.
    #:
    #: Experimentation is scarce, not free. Measured on dev worlds, one
    #: experiment costs roughly 2.8x the entire profit pool of the world it runs
    #: in, so a strategy can afford about one. Making the allowance explicit
    #: turns "run four experiments" into a choice the strategy owns and pays
    #: for, rather than something the harness hands out for nothing.
    max_experiments: int

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        ...


#: Size of the past campaign the merchant remembers, per intervention.
#: Small on purpose — see InterventionHistory.
HISTORY_SAMPLE = 300


def _intervention_history(world: World) -> tuple[InterventionHistory, ...]:
    """Simulate one small past campaign per intervention, against a control arm.

    Drawn from the world's own response model, so it reflects that world's true
    affinities the way a real merchant's history would — through sampling noise,
    not as a clean readout. Seeded from the world id via blake2b, so a world's
    history is stable across runs and processes, and identical for every
    strategy that sees it.

    **Both arms are simulated.** The merchant held back a control group at the
    time, so the figure is an incremental effect rather than the gross
    contribution of treated orders. Without a control the history would report
    every campaign as profitable, which is precisely the mistake the project
    is about, and would make this fix actively harmful.

    Uses the response model, never ``Y(0)``/``Y(1)``: this is a past campaign
    the merchant ran, not a peek at the experiment about to be run.
    """
    import numpy as np

    from src.world.generator import intervention_affinity, treated_conversion_probability

    margin = float(np.mean([p.contribution_margin for p in world.products]))
    # blake2b, not Python's hash(): string hashing is salted per process, so
    # hash() would give the same world a different past campaign on every run
    # and the history would not be reproducible. Same reason
    # src/experiment/randomize.py refuses it for arm assignment.
    seed = int.from_bytes(
        hashlib.blake2b(world.world_id.encode("utf-8"), digest_size=8).digest(), "big"
    )
    rng = np.random.default_rng(seed)
    sample = world.customers[:HISTORY_SAMPLE]

    control = world.customers[HISTORY_SAMPLE : HISTORY_SAMPLE * 2]

    entries = []
    for intervention in world.interventions:
        affinity = intervention_affinity(world.params, intervention)

        treated_values, orders = [], 0
        for customer in sample:
            basket = customer.expected_order_value_inr
            if intervention.bundle_added_value_inr:
                basket += intervention.bundle_added_value_inr
            p1 = treated_conversion_probability(customer, intervention, basket, affinity)
            if rng.random() < p1:
                orders += 1
                treated_values.append(basket * margin - intervention.incentive_cost_inr(basket))
            else:
                treated_values.append(0.0)

        control_values = []
        for customer in control:
            converted = rng.random() < customer.baseline_purchase_prob
            control_values.append(customer.expected_order_value_inr * margin if converted else 0.0)

        treated_arr = np.asarray(treated_values, dtype=float)
        control_arr = np.asarray(control_values, dtype=float)
        if len(control_arr) == 0:
            control_arr = np.zeros(1)

        # Two-sample difference of means, and its standard error. The same
        # estimator src/experiment/evaluator.py uses at the horizon.
        effect = float(treated_arr.mean() - control_arr.mean())
        se = float(
            np.sqrt(
                treated_arr.var(ddof=1) / len(treated_arr)
                + control_arr.var(ddof=1) / max(len(control_arr), 2)
            )
        )
        entries.append(
            InterventionHistory(
                intervention_id=intervention.intervention_id,
                treated_customers=len(sample),
                orders=orders,
                net_per_treated_customer_inr=effect,
                standard_error_inr=se,
            )
        )
    return tuple(entries)


def merchant_view(world: World) -> MerchantView:
    """Project a world down to what a merchant can actually see.

    Built by explicit field selection rather than by copying and deleting, so
    that a new latent added to ``WorldParams`` is invisible here by default. The
    failure mode worth engineering against is a leak added by accident later,
    not one written deliberately today.
    """
    import numpy as np

    observed_conversion = float(
        np.mean([c.baseline_purchase_prob for c in world.customers])
    )
    observed_aov = float(np.mean([c.expected_order_value_inr for c in world.customers]))
    observed_margin = float(np.mean([p.contribution_margin for p in world.products]))

    return MerchantView(
        world_id=world.world_id,
        population=len(world.customers),
        budget_inr=world.params.promotion_budget_inr,
        observed_conversion=observed_conversion,
        observed_aov_inr=observed_aov,
        observed_margin=observed_margin,
        experiment_window_days=world.params.experiment_window_days,
        semantic=world.semantic,
        products=world.products,
        customers=tuple(
            CustomerView(
                customer_id=c.customer_id,
                segment_id=c.segment_id,
                tenure_days=c.tenure_days,
                orders_last_90d=c.orders_last_90d,
                days_since_last_order=c.days_since_last_order,
                historical_aov_inr=c.expected_order_value_inr,
            )
            for c in world.customers
        ),
        segments=tuple(
            SegmentView(
                segment_id=s.segment_id,
                name=s.name,
                share=s.share,
                notes=s.notes,
                behaviour_tags=s.behaviour_tags,
            )
            for s in world.segments
        ),
        interventions=world.interventions,
        history=_intervention_history(world),
    )
