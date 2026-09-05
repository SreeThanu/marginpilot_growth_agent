"""Price a merchant's promotion through the existing pre-experiment decision path.

The division this module exists to enforce:

    the merchant states the business conditions,
    MarginPilot supplies the growth hypothesis,
    the deterministic policy makes the decision.

The merchant may state six things, all of them facts about their own shop: what
the incentive costs, how many customers are eligible, what a basket is worth,
what margin it earns, how often people already buy, and what may be spent.

They may not state the **expected lift** or the **evidence basis**. Those are
MarginPilot's hypothesis about how customers will respond; they are read from
``proposal_payload`` and are not parameters of :func:`reprice`. A merchant who
could set the expected lift would be dictating the answer rather than describing
the question, and the whole point of the gate ladder is that those are different
acts.

That boundary has a consequence worth stating plainly, because the interface
must not imply otherwise: changing a business condition changes the promotion's
**economics and constraints**, not the demand hypothesis. A cheaper offer does
not become one customers respond to differently — nothing in this project can
recompute a response from a merchant's stated conditions, and a control that
appeared to do so would be advertising a demand model that does not exist. What
the panel actually asks is: *given these conditions, what would MarginPilot's
existing hypothesis be worth, and is that worth buying?*

How the conditions reach the engine
-----------------------------------
The stated conditions are applied to a **copy** of the ``FixtureSpec`` and the
merchant view is rebuilt by the fixture's own ``build_view``, then projected by
:func:`~src.agent.brief.build_brief`. Contribution per order, incentive per
order and discount depth are re-derived by ``contribution_per_order_inr()`` and
``Intervention.effective_depth()`` / ``.incentive_cost_inr()`` — the same
functions the fixture path calls. No formula is duplicated here, and
``src/economics``, ``src/experiment``, ``src/policy`` and ``src/agent`` are all
read, never edited.

Rebuilding rather than patching matters: ``build_view`` re-centres the customer
records on the stated average order value, so a merchant who says their baskets
are worth Rs.1,200 gets a brief describing that shop rather than the previous
shop under a new headline.

The boundary this module must not cross
---------------------------------------
``demo.fixtures._intervention(spec)`` feeds two things: ``build_view``, which is
what the model and the policy are allowed to read, and ``FixtureExecutor``,
which generates experiment observations from the fixture's
``declared_true_lift_absolute``. A user-facing control that reached the second
would be a control over ground truth.

So this module calls :func:`~src.agent.decision_policy.recommend_from_raw` and
nothing else. It never imports ``FixtureExecutor`` or ``run_scenario``, never
simulates an outcome, and never reads a declared response.
``tests/api/test_reprice.py`` pins that by walking this file's AST, so the
boundary survives a future edit that forgets why it was here.

Two consequences follow, and both are load-bearing rather than incidental:

* ``recommend_from_raw`` runs G1-G5 only. That path has no branch that
  constructs ``PROMOTE`` — spending requires a measured ``FinalResult`` at a
  pre-committed horizon, which this module has no route to. The verdicts
  reachable from here are DO_NOT_PROMOTE, RUN_EXPERIMENT_FIRST and
  INSUFFICIENT_EVIDENCE.
* Nothing here writes. No audit entry, no registry launch, no spend. An
  evaluation is not an execution, so there is nothing to record.

Admissibility is checked before the gates
-----------------------------------------
``Intervention.effective_depth()`` clamps to ``[0.0, 0.5]``, so an absurd
request would otherwise read as a plausible one: Rs.100,000 off a Rs.600 basket
silently becomes a 50% discount, and a negative amount becomes a free promotion
with a break-even of zero. Worse, on a thin-margin merchant G2 refuses on
economics long before G5 ever examines depth, so the standing discount ceiling
is unreachable through the gates and could not refuse anything.

A request is therefore screened for admissibility *before* it is priced, using
``src.policy.gates.check_discount`` — the same rule function ``gate_experiment``
calls, not a second copy of it. An inadmissible request returns
``REQUEST_INADMISSIBLE``, which is deliberately **not** one of the three
decisions: the merchant asked something the policy will not price, which is a
different event from the policy pricing it and saying no.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

from demo.fixtures import FIXTURES, FixtureSpec, build_view, proposal_payload
from src.agent.brief import MerchantBrief, build_brief
from src.agent.decision_policy import recommend_from_raw
from src.policy.gates import PolicyLimits, RuleViolation, check_discount
from src.world.schema import Intervention, InterventionKind

#: Kinds whose magnitude is denominated in rupees, so ``incentive_inr`` maps
#: onto the schema field directly with no unit conversion.
#:
#: Percentage and bundle offers carry a *fraction*, and turning a rupee amount
#: into one would mean dividing by the merchant's AOV here — arithmetic over an
#: economic quantity, in the adapter, which is exactly what this layer is not
#: allowed to do. Those kinds are declined rather than approximated.
_RUPEE_MAGNITUDE_FIELD = {
    InterventionKind.FLAT_DISCOUNT: "flat_discount_inr",
    InterventionKind.FREE_SHIPPING: "shipping_fee_waived_inr",
}


#: Largest customer base this adapter will build a view for.
#:
#: **Not an economic threshold, and not a policy limit.** ``build_view``
#: materialises one ``CustomerView`` per customer at roughly 5µs each, so a
#: request for a million would spend seconds generating records this path never
#: reads. The cap bounds that cost and is disclosed as what it is when it fires.
#: The standing limits on how many customers a campaign may *treat* live in
#: ``PolicyLimits.max_customer_exposure_share`` and are unaffected by this.
MAX_POPULATION = 200_000


class RequestInadmissible(ValueError):
    """The merchant asked for something the policy will not price.

    Distinct from a refusal *by* the policy. Carries the violated rule when one
    fired, so the caller reports the engine's own finding rather than a message
    invented at the boundary.
    """

    def __init__(self, reason: str, violation: RuleViolation | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.violation = violation


@dataclass(frozen=True, slots=True)
class MerchantConditions:
    """The business conditions a merchant may state about a proposed promotion.

    Six fields, and the boundary they draw is the point of this class. Every one
    of them is something the merchant *knows about their own shop* — what the
    offer costs, how many customers are eligible, what a basket is worth, what
    it earns, how often people buy, and what may be spent finding out.

    What is deliberately absent: the expected lift and the evidence basis. Those
    are MarginPilot's hypothesis about how customers will respond, they come from
    ``proposal_payload`` unchanged, and a merchant who could set them would be
    dictating the answer rather than describing the question.

    ``None`` means "as the merchant record already states it", so a request that
    names only an incentive is exactly the request this module answered before
    the other five fields existed.
    """

    incentive_inr: float
    population: int | None = None
    aov_inr: float | None = None
    margin: float | None = None
    observed_conversion: float | None = None
    budget_inr: float | None = None

    def overrides(self) -> dict[str, Any]:
        """The ``FixtureSpec`` fields this request changes, and only those."""
        stated = {
            "population": self.population,
            "aov_inr": self.aov_inr,
            "margin": self.margin,
            "observed_conversion": self.observed_conversion,
            "budget_inr": self.budget_inr,
            "intervention_magnitude": self.incentive_inr,
        }
        return {k: v for k, v in stated.items() if v is not None}


def _finite(value: float, label: str) -> float:
    if not math.isfinite(float(value)):
        raise RequestInadmissible(f"{label} must be a finite number.")
    return float(value)


def _validate(conditions: MerchantConditions) -> None:
    """Refuse a structurally impossible request before the engine sees it.

    Only the checks the engine does not already make itself. Conversion, margin
    and AOV are range-checked inside ``src/economics`` and
    ``src/experiment/power``; those raise on their own and are caught in
    :func:`reprice`, so their rules are not restated here. What is added is the
    handful of degenerate values the engine accepts without complaint and
    answers nonsensically — a promotion to nobody, a negative budget, a basket
    worth nothing — plus this adapter's own population ceiling.

    Nothing is clamped. A clamped request is answered as though the merchant had
    asked something they did not ask.
    """
    incentive = _finite(conditions.incentive_inr, "The incentive")
    if incentive < 0.0:
        raise RequestInadmissible(
            f"An incentive cannot be negative; Rs.{incentive:,.2f} was requested."
        )

    if conditions.population is not None:
        population = conditions.population
        if int(population) != population:
            raise RequestInadmissible("Eligible customers must be a whole number.")
        if population < 1:
            raise RequestInadmissible(
                "A promotion needs at least one eligible customer; "
                f"{population:,} were stated."
            )
        if population > MAX_POPULATION:
            raise RequestInadmissible(
                f"{population:,} eligible customers is above the "
                f"{MAX_POPULATION:,} this evaluator will build a merchant view "
                "for. That is a limit of this tool, not of the policy."
            )

    if conditions.aov_inr is not None:
        aov = _finite(conditions.aov_inr, "Average order value")
        if aov <= 0.0:
            raise RequestInadmissible(
                "Average order value must be greater than zero; "
                f"Rs.{aov:,.2f} was stated."
            )

    if conditions.margin is not None:
        _finite(conditions.margin, "Contribution margin")

    if conditions.observed_conversion is not None:
        conversion = _finite(conditions.observed_conversion, "Baseline conversion")
        if not 0.0 < conversion <= 1.0:
            raise RequestInadmissible(
                "Baseline conversion must be above 0% and at most 100%; "
                f"{conversion:.2%} was stated."
            )

    if conditions.budget_inr is not None:
        budget = _finite(conditions.budget_inr, "The budget")
        if budget < 0.0:
            raise RequestInadmissible(
                f"A budget cannot be negative; Rs.{budget:,.2f} was stated."
            )


@lru_cache(maxsize=len(FIXTURES))
def _view(scenario_id: str):
    """The merchant view for one fixture, built once.

    Keyed on the scenario only — never on a user-supplied amount, which would
    make the cache grow without bound as a control is dragged. Re-pricing costs
    ~3ms once the view exists, so there is nothing further worth caching.
    """
    return build_view(FIXTURES[scenario_id])


def _stated_spec(spec: FixtureSpec, conditions: MerchantConditions) -> FixtureSpec:
    """The fixture as the merchant has described their own shop.

    A copy. ``FixtureSpec`` is frozen, ``replace`` builds a new one, and the
    committed spec — including Scenario C's locked fingerprint — is untouched by
    any request.

    Note which field the incentive lands on: ``intervention_magnitude``, the
    same field the committed fixture declares. Whether that magnitude is rupees
    or a fraction is decided by ``intervention_kind``, which the merchant cannot
    state, so a rupee amount can only ever reach a rupee-denominated offer.
    """
    target_kind = spec.intervention_kind
    if target_kind not in {k.value for k in _RUPEE_MAGNITUDE_FIELD}:
        raise RequestInadmissible(
            f"{spec.intervention_name} is priced as a fraction of the basket, "
            "not in rupees, so a rupee incentive cannot be applied to it."
        )
    return replace(spec, **conditions.overrides())


def _stated_brief(spec: FixtureSpec, conditions: MerchantConditions) -> MerchantBrief:
    """The merchant brief implied by the stated conditions.

    Built by the fixture's own constructor rather than by patching a cached
    view. ``build_view`` re-centres the customer records on the stated average
    order value and re-prices the intervention against it, so the brief is
    internally consistent: a merchant who says their baskets are worth Rs.1,200
    gets customer records that average Rs.1,200, not the previous merchant's
    records under a new headline.

    Patching the cached view in place would have been faster and would have left
    the customer distribution describing a shop nobody asked about. The whole
    construction path is reused instead, which costs about 5µs per customer and
    is why :data:`MAX_POPULATION` exists.

    The unmodified case still takes the cached view, so the panel's opening
    state costs nothing.
    """
    stated = _stated_spec(spec, conditions)
    view = _view(spec.scenario_id) if stated == spec else build_view(stated)
    return build_brief(view)


def _screen(amount: float, brief: MerchantBrief, intervention_id: str,
            limits: PolicyLimits) -> None:
    """Refuse a request the policy will not price. Never clamps it into range."""
    depth = brief.intervention(intervention_id).depth_at_observed_aov
    violation = check_discount(depth, limits)
    if violation is not None:
        raise RequestInadmissible(
            f"Rs.{amount:,.0f} is a discount of {violation.observed:.2%} of the "
            f"observed basket, above the standing ceiling of "
            f"{violation.limit:.2%}.",
            violation,
        )


def _request_payload(spec: FixtureSpec, brief: MerchantBrief, amount: float,
                     raw: dict[str, Any],
                     conditions: MerchantConditions) -> dict[str, Any]:
    """What the merchant asked for, as the decision path received it.

    Read off the brief rather than off the fixture spec, matching
    ``service._merchant_payload``: what the panel shows is then exactly what the
    policy was given.
    """
    intervention = brief.intervention(raw["intervention_id"])
    economics = brief.economics_for(raw["cohort_id"], raw["intervention_id"])
    return {
        "scenario": spec.scenario_id,
        "incentive_inr": amount,
        "declared_incentive_inr": spec.intervention_magnitude,
        "is_declared_offer": amount == spec.intervention_magnitude,
        "intervention_id": intervention.intervention_id,
        "offer_name": intervention.name,
        "offer_kind": intervention.kind,
        "offer_description": intervention.description,
        "depth_at_observed_aov": intervention.depth_at_observed_aov,
        "incentive_cost_per_order_inr": economics.incentive_cost_per_order_inr,
        "contribution_per_order_inr": economics.contribution_per_order_inr,
        "cohort_id": raw["cohort_id"],
        "cohort_customers": (
            brief.population
            if raw["cohort_id"] == "ALL"
            else brief.cohort(raw["cohort_id"]).n_customers
        ),
        # MarginPilot's hypothesis about how customers respond. Held fixed while
        # the merchant varies the business conditions, never read from the
        # request, and never the fixture's declared true response.
        "expected_lift_absolute": raw["expected_lift_absolute"],
        "evidence_basis": raw["evidence_basis"],
        "hypothesis": raw["hypothesis"],
        # The conditions as the policy received them, read off the brief.
        "observed_conversion": brief.observed_conversion,
        "observed_aov_inr": brief.observed_aov_inr,
        "observed_margin": brief.observed_margin,
        "budget_inr": brief.budget_inr,
        "population": brief.population,
        # What the merchant record says, so a view can show which conditions the
        # merchant restated and which are the shop's own figures.
        "declared": {
            "incentive_inr": spec.intervention_magnitude,
            "population": spec.population,
            "aov_inr": spec.aov_inr,
            "margin": spec.margin,
            "observed_conversion": spec.observed_conversion,
            "budget_inr": spec.budget_inr,
        },
        # Only the conditions actually moved off the record's own figure.
        # A form that submits every field submits the unchanged ones too, and a
        # view that showed all six as "restated" would be telling the merchant
        # they had changed things they had not.
        "stated": list(_restated_fields(spec, conditions)),
        "is_declared_request": not _restated_fields(spec, conditions),
        "max_population": MAX_POPULATION,
    }


def _restated_fields(spec: FixtureSpec, conditions: MerchantConditions) -> tuple[str, ...]:
    """Which conditions the merchant actually moved off the record's own value."""
    return tuple(
        field
        for field, value in sorted(conditions.overrides().items())
        if getattr(spec, field) != value
    )


def depth_ceiling(limits: PolicyLimits | None = None) -> float:
    """The standing discount ceiling, so a view can bound its own control."""
    return (limits or PolicyLimits()).max_discount_pct


def reprice(scenario_id: str, incentive_inr: float,
            *,
            population: int | None = None,
            aov_inr: float | None = None,
            margin: float | None = None,
            observed_conversion: float | None = None,
            budget_inr: float | None = None,
            limits: PolicyLimits | None = None) -> dict[str, Any]:
    """Price one merchant's promotion under the business conditions they state.

    Only ``incentive_inr`` is required; every other condition defaults to the
    merchant record's own figure, so a call naming just an incentive is the call
    this function answered when the incentive was the only editable input.

    What the merchant may state is what they know about their own shop. What
    they may not state is how customers will respond to it: the expected lift
    and its evidence basis come from ``proposal_payload`` and are not
    parameters here. Changing a business condition changes the *economics* of
    the promotion and the constraints it must clear — it does not change
    MarginPilot's hypothesis about demand, because nothing in this project can
    recompute that hypothesis from a merchant's stated conditions, and
    pretending otherwise would be inventing a demand model.

    Raises :class:`RequestInadmissible` for a request the policy will not price.
    Everything else is decided by ``recommend_from_raw`` and reported verbatim.
    """
    limits = limits or PolicyLimits()
    spec = FIXTURES[scenario_id]

    conditions = MerchantConditions(
        incentive_inr=incentive_inr,
        population=population,
        aov_inr=aov_inr,
        margin=margin,
        observed_conversion=observed_conversion,
        budget_inr=budget_inr,
    )
    _validate(conditions)

    try:
        brief = _stated_brief(spec, conditions)
    except RequestInadmissible:
        raise
    except ValueError as exc:
        # The engine's own range checks — ``contribution_per_order_inr`` on AOV
        # and margin, ``assess_feasibility`` on conversion. Reported as a
        # refusal rather than a 500, and in the engine's words rather than in a
        # second set of bounds restated here.
        raise RequestInadmissible(str(exc)) from exc

    amount = float(incentive_inr)
    raw = proposal_payload(spec)
    _screen(amount, brief, raw["intervention_id"], limits)

    try:
        recommendation = recommend_from_raw(brief, raw, limits=limits)
    except ValueError as exc:
        raise RequestInadmissible(str(exc)) from exc

    return {
        "status": "EVALUATED",
        "scenario": spec.scenario_id,
        "label": spec.title,
        "request": _request_payload(spec, brief, amount, raw, conditions),
        "recommendation": recommendation.to_dict(),
        "refusal": None,
        "policy_limits": {
            "max_discount_pct": limits.max_discount_pct,
            "min_contribution_margin": limits.min_contribution_margin,
        },
    }


def inadmissible_payload(scenario_id: str, incentive_inr: Any,
                         exc: RequestInadmissible) -> dict[str, Any]:
    """The refusal, shaped so a view never has to guess it is not a verdict."""
    violation = exc.violation
    return {
        "status": "REQUEST_INADMISSIBLE",
        "scenario": scenario_id,
        "recommendation": None,
        "refusal": {
            "reason": exc.reason,
            # The gate's own wording, kept verbatim beside the precise one. It
            # rounds depth to whole percent, which reads as "25% exceeds 25%" at
            # the boundary, so it is reported rather than rendered as the
            # headline.
            "engine_message": violation.message if violation else None,
            "rule": violation.rule.value if violation else None,
            "observed": violation.observed if violation else None,
            "limit": violation.limit if violation else None,
            "refused_by": "src/policy/gates.py::check_discount" if violation else "api/reprice.py",
        },
        "requested_incentive_inr": (
            float(incentive_inr) if isinstance(incentive_inr, (int, float))
            and math.isfinite(float(incentive_inr)) else None
        ),
    }
