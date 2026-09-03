"""Collectors that turn engine objects into JSON-ready dicts.

Read-only by construction. Each function calls into a module that already owns
the behaviour and then flattens what came back. Nothing here branches on a
decision value, recomputes a rupee figure, or supplies a default for a missing
one — a value the engine did not produce is returned as ``None`` so the view can
say "not available" rather than show a number nobody calculated.

Results are cached because the fixtures are deterministic in their committed
seeds: the second call must return the first call's answer, and a cache makes
that structural rather than incidental.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from demo.audit_demo import MALFORMED_PROPOSALS, audit_recommendation
from demo.evidence import reproducibility_badges
from demo.fixtures import FIXTURE_LABEL, FIXTURES, build_view, proposal_payload
from demo.run_scenarios import run_scenario
from src.agent.brief import build_brief
from src.agent.decision_policy import recommend_from_raw
from src.agent.recommendation import ProposalRejected, validate_proposal
from src.eval.adversarial import run_all
from src.policy.gates import PolicyLimits

#: Order the scenarios appear in the product. Matches the story the demo tells:
#: refuse, then test, then earn the rollout.
SCENARIO_ORDER = ("A", "B", "C")


# --------------------------------------------------------------------------- #
# Merchant context — read off the brief the model is given, not off the fixture
# --------------------------------------------------------------------------- #


def _merchant_payload(brief) -> dict[str, Any]:
    """The merchant as the decision path sees it.

    Deliberately sourced from :class:`~src.agent.brief.MerchantBrief` rather
    than from the fixture spec. What the screen shows is then exactly what the
    model was allowed to read, and a field the brief withholds cannot leak into
    the UI by way of a convenience import.
    """
    return {
        "merchant_id": brief.merchant_id,
        "population": brief.population,
        "budget_inr": brief.budget_inr,
        "observed_conversion": brief.observed_conversion,
        "observed_aov_inr": brief.observed_aov_inr,
        "observed_margin": brief.observed_margin,
        "contribution_per_order_inr": brief.contribution_per_order_inr,
        "experiment_window_days": brief.experiment_window_days,
        "context": list(brief.context),
    }


def _intervention_payload(brief, intervention_id: str | None) -> dict[str, Any] | None:
    if not intervention_id:
        return None
    try:
        i = brief.intervention(intervention_id)
    except KeyError:
        return None
    return {
        "intervention_id": i.intervention_id,
        "kind": i.kind,
        "name": i.name,
        "description": i.description,
        "incentive_cost_per_order_inr": i.incentive_cost_per_order_inr,
        "depth_at_observed_aov": i.depth_at_observed_aov,
    }


def _history_payload(brief, intervention_id: str | None) -> dict[str, Any] | None:
    if not intervention_id:
        return None
    h = brief.history_for(intervention_id)
    if h is None:
        return None
    return {
        "intervention_id": h.intervention_id,
        "treated_customers": h.treated_customers,
        "orders": h.orders,
        "net_per_treated_customer_inr": h.net_per_treated_customer_inr,
        "standard_error_inr": h.standard_error_inr,
    }


def _proposal_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """The model's reply after the engine's own validator has seen it.

    Validation is not repeated here. ``validate_proposal`` is the only thing
    that decides whether a reply is usable, and its refusal is surfaced as a
    refusal rather than smoothed into a partial object.
    """
    try:
        proposal = validate_proposal(raw)
    except ProposalRejected as exc:
        return {"accepted": False, "rejected_because": str(exc), "proposal": None}
    return {"accepted": True, "rejected_because": None, "proposal": proposal.to_dict()}


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=None)
def scenario_detail(scenario_id: str) -> dict[str, Any]:
    """One scenario, decided end to end by the engine."""
    spec = FIXTURES[scenario_id]
    record = run_scenario(spec)
    brief = build_brief(build_view(spec))
    raw = proposal_payload(spec)
    final = record["final"]

    return {
        "scenario": spec.scenario_id,
        "title": spec.title,
        "story": spec.story,
        "label": FIXTURE_LABEL,
        "merchant": _merchant_payload(brief),
        "intervention": _intervention_payload(brief, final.get("intervention_id")),
        "history": _history_payload(brief, final.get("intervention_id")),
        "proposal": _proposal_payload(raw),
        "initial": record["initial"],
        "experiment": record["experiment"],
        "final": final,
    }


def scenario_index() -> list[dict[str, Any]]:
    """Enough of each scenario to render the selector, no more."""
    index = []
    for scenario_id in SCENARIO_ORDER:
        detail = scenario_detail(scenario_id)
        index.append(
            {
                "scenario": detail["scenario"],
                "title": detail["title"],
                "story": detail["story"],
                "decision": detail["final"]["decision"],
                "expected_net_contribution_inr": detail["final"][
                    "expected_net_contribution_inr"
                ],
                "merchant_name": detail["merchant"]["merchant_id"],
                "has_experiment": detail["experiment"] is not None,
            }
        )
    return index


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=None)
def audit_trail(scenario_id: str) -> dict[str, Any]:
    """The decision chain for one scenario, written by ``src/audit/log.py``.

    ``audit_recommendation`` is handed the same record the decision endpoint
    returns, so the chain on the audit screen covers the decision on the
    overview screen rather than a re-run of it.
    """
    spec = FIXTURES[scenario_id]
    trail = audit_recommendation(run_scenario(spec))
    return {
        "scenario": scenario_id,
        "experiment_id": trail.experiment_id,
        "verified": trail.verified,
        "head_hash": trail.head_hash,
        "payload_is_the_rendered_object": trail.payload_is_the_rendered_object,
        "rendered": trail.rendered,
        "entries": [
            {
                "id": e.id,
                "recorded_at": e.recorded_at,
                "world_id": e.world_id,
                "experiment_id": e.experiment_id,
                "stage": e.stage.value,
                "actor": e.actor,
                "payload_keys": sorted(e.payload.keys()),
                "payload": e.payload,
                "prev_hash": e.prev_hash,
                "entry_hash": e.entry_hash,
            }
            for e in trail.entries
        ],
    }


# --------------------------------------------------------------------------- #
# Trust and safety
# --------------------------------------------------------------------------- #


def _malformed_outcomes() -> list[dict[str, Any]]:
    """Feed each deliberately broken reply to the real decision entry point.

    ``recommend_from_raw`` owns every rule about what a valid proposal is. This
    function supplies inputs and reports what came back; it validates nothing.
    """
    brief = build_brief(build_view(FIXTURES["C"]))
    outcomes = []
    for label, raw in MALFORMED_PROPOSALS.items():
        recommendation = recommend_from_raw(brief, raw)
        outcomes.append(
            {
                "label": label,
                "decision": recommendation.decision.value,
                "rationale": recommendation.rationale,
                "binding_constraints": list(recommendation.binding_constraints),
                "spends_money": recommendation.decision.value == "PROMOTE",
            }
        )
    return outcomes


def _model_overrides() -> list[dict[str, Any]]:
    """Where the model asked for one thing and the policy returned another."""
    rows = []
    for scenario_id in SCENARIO_ORDER:
        detail = scenario_detail(scenario_id)
        final = detail["final"]
        rows.append(
            {
                "scenario": scenario_id,
                "title": detail["title"],
                "model_requested": final["model_requested"],
                "policy_decided": final["decision"],
                "overruled": final["overruled_the_model"],
                "rationale": final["rationale"],
            }
        )
    return rows


@lru_cache(maxsize=None)
def safety_report() -> dict[str, Any]:
    """The adversarial scenarios, run live, plus the fail-closed controls."""
    results = run_all()
    scenarios = [
        {
            "name": r.name,
            "attempted": r.attempted,
            "refused": r.refused,
            "refused_by": r.refused_by,
            "reason": r.reason,
        }
        for r in results
    ]
    limits = PolicyLimits()
    return {
        "scenarios": scenarios,
        "refused": sum(1 for r in results if r.refused),
        "total": len(results),
        "malformed": _malformed_outcomes(),
        "model_overrides": _model_overrides(),
        "policy_limits": {
            "max_discount_pct": limits.max_discount_pct,
            "min_contribution_margin": limits.min_contribution_margin,
            "max_customer_exposure_share": limits.max_customer_exposure_share,
            "min_experiment_power": limits.min_experiment_power,
            "min_budget_headroom_share": limits.min_budget_headroom_share,
        },
    }


# --------------------------------------------------------------------------- #
# Reproducibility
# --------------------------------------------------------------------------- #


def reproducibility() -> dict[str, Any]:
    """The pins this repository holds itself to, read from source."""
    return {
        "badges": [
            {"label": b.label, "value": b.value, "detail": b.detail}
            for b in reproducibility_badges()
        ]
    }
