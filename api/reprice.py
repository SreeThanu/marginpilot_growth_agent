"""Re-price one merchant's offer through the existing pre-experiment decision path.

The merchant supplies exactly one business input: **what the incentive costs**.
Everything else — base size, AOV, margin, baseline conversion, budget, the
expected lift and its evidence basis — is read from the merchant record and the
existing proposal, unchanged. This module supplies an amount and reports what
came back; it computes no economics of its own.

How the amount reaches the engine
---------------------------------
The offer is re-priced by rebuilding the merchant *view* with a new magnitude on
the intervention and running :func:`~src.agent.brief.build_brief` over it. Depth,
incentive-per-order and contribution-per-order are then re-derived by
``Intervention.effective_depth()`` / ``.incentive_cost_inr()`` and
``contribution_per_order_inr()`` — the same methods the fixture path calls. No
formula is duplicated here, and ``src/economics``, ``src/experiment``,
``src/policy`` and ``src/agent`` are all read, never edited.

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
from dataclasses import replace
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


@lru_cache(maxsize=len(FIXTURES))
def _view(scenario_id: str):
    """The merchant view for one fixture, built once.

    Keyed on the scenario only — never on a user-supplied amount, which would
    make the cache grow without bound as a control is dragged. Re-pricing costs
    ~3ms once the view exists, so there is nothing further worth caching.
    """
    return build_view(FIXTURES[scenario_id])


def _repriced_brief(spec: FixtureSpec, amount: float) -> MerchantBrief:
    """The merchant brief as it would read if the offer cost ``amount``.

    Only the matching intervention is replaced; the rest of the tuple is carried
    through untouched, so the brief the policy reads is structurally the fixture
    path's brief with one number moved, not a one-element variant of it.

    The view itself is never mutated. ``dataclasses.replace`` copies, so the
    cached view, the ``FixtureSpec`` and Scenario C's committed fingerprint are
    all untouched by any request.
    """
    view = _view(spec.scenario_id)
    target = view.interventions[0]
    field = _RUPEE_MAGNITUDE_FIELD.get(target.kind)
    if field is None:
        raise RequestInadmissible(
            f"{target.name} is priced as a fraction of the basket, not in rupees, "
            "so a rupee incentive cannot be applied to it."
        )

    repriced = tuple(
        replace(iv, **{field: amount}) if iv is target else iv
        for iv in view.interventions
    )
    return build_brief(replace(view, interventions=repriced))


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
                     raw: dict[str, Any]) -> dict[str, Any]:
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
        # The model's hypothesis, held fixed while the incentive varies. Never
        # read from the request, and never the fixture's declared true response.
        "expected_lift_absolute": raw["expected_lift_absolute"],
        "evidence_basis": raw["evidence_basis"],
        "hypothesis": raw["hypothesis"],
        "observed_conversion": brief.observed_conversion,
        "observed_aov_inr": brief.observed_aov_inr,
        "observed_margin": brief.observed_margin,
        "budget_inr": brief.budget_inr,
        "population": brief.population,
    }


def depth_ceiling(limits: PolicyLimits | None = None) -> float:
    """The standing discount ceiling, so a view can bound its own control."""
    return (limits or PolicyLimits()).max_discount_pct


def reprice(scenario_id: str, incentive_inr: float,
            *, limits: PolicyLimits | None = None) -> dict[str, Any]:
    """Price one merchant's offer at ``incentive_inr`` and return the verdict.

    Raises :class:`RequestInadmissible` for a request the policy will not price.
    Everything else is decided by ``recommend_from_raw`` and reported verbatim.
    """
    limits = limits or PolicyLimits()
    spec = FIXTURES[scenario_id]

    amount = float(incentive_inr)
    if not math.isfinite(amount):
        raise RequestInadmissible(
            "The incentive must be a finite rupee amount."
        )
    if amount < 0.0:
        raise RequestInadmissible(
            f"An incentive cannot be negative; Rs.{amount:,.2f} was requested."
        )

    brief = _repriced_brief(spec, amount)
    raw = proposal_payload(spec)
    _screen(amount, brief, raw["intervention_id"], limits)

    recommendation = recommend_from_raw(brief, raw, limits=limits)
    return {
        "status": "EVALUATED",
        "scenario": spec.scenario_id,
        "label": spec.title,
        "request": _request_payload(spec, brief, amount, raw),
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
