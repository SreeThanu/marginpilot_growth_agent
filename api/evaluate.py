"""Evaluate one merchant-stated promotion without touching a recorded case.

This adapter deliberately has no fixture or scenario dependency.  It constructs
the offer the merchant named with the existing ``Intervention`` representation,
projects the resulting merchant view into the standard brief, and asks the
existing deterministic policy to validate the assessment.

Where the growth hypothesis comes from
-------------------------------------
From :class:`src.agent.proposer.LLMProposer`, wrapping the same reasoner the
research ran on.  That class already exists for exactly this: it formats the
brief into ``PROPOSAL_PROMPT`` and returns whatever the model replies, unrepaired.
The reply then goes through ``recommend_from_raw``, which validates it and
recomputes every rupee from the brief — so the model states a hypothesis and the
deterministic policy decides what it is worth.

What is deliberately **not** used as a hypothesis source:

* **The recorded A/B/C ``proposal_payload``.**  Those are assessments of those
  merchants and those offers.  Borrowing one would attach Scenario A's 4% lift
  and its ``prior`` to a promotion nobody has ever studied.
* **:class:`~src.agent.reasoner.HeuristicReasoner`.**  It returns a hardcoded
  ``expected_effect_absolute=0.03`` that its own docstring says is not reasoning
  and "must never be reported as MarginPilot's".  A constant dressed as a
  hypothesis is the failure this module exists to avoid.

When no proposer can be constructed — no credential, or the client library is
absent — the endpoint says so and returns ``ASSESSMENT_UNAVAILABLE``.  The offer
economics are still real, because those come from the brief; the lift and the
evidence basis stay null, because nothing legitimate produced them.
"""

from __future__ import annotations

import logging
import math
import os
from enum import Enum
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from src.agent.brief import MerchantBrief, build_brief
from src.agent.decision_policy import recommend_from_raw
from src.agent.proposer import LLMProposer, Proposer
from src.agent.recommendation import (
    EvidenceBasis,
    ProposalRejected,
    validate_proposal,
)
from src.eval.contracts import CustomerView, MerchantView
from src.policy.gates import PolicyLimits, RuleViolation, check_discount
from src.world.schema import Intervention, InterventionKind, Product, SemanticContext

logger = logging.getLogger("marginpilot.api.evaluate")

MAX_POPULATION = 200_000
GENERIC_INTERVENTION_ID = "merchant_requested_offer"

#: Which reasoner to wrap, if any. ``auto`` tries each in turn and accepts the
#: first that constructs; ``none`` disables the proposer outright, which is how
#: a test or a demo pins the unavailable path without unsetting a credential.
#:
#: ``HeuristicReasoner`` is not an option and is not reachable from here. It
#: returns a fixed 0.03 by construction, and routing that through the proposal
#: validator would launder a constant into an assessment.
PROPOSER_ENV = "MARGINPILOT_PROPOSER"


#: Google's REST surface for the same model the vendor client would call.
_GEMINI_REST = "https://generativelanguage.googleapis.com/v1beta"

#: Deployment override for the REST fallback's model. Empty or unset keeps
#: ``reasoner.DEFAULT_GEMINI_MODEL``, so the research client and this transport
#: name the same model unless an operator deliberately says otherwise.
#:
#: This exists because model availability is a property of a deployment's key,
#: not of the system: a quota exhausted on one model says nothing about the
#: reasoning and should not require editing the research layer to route around.
#: It selects a model. It cannot change a prompt, a validation rule, an evidence
#: rule, or any economics.
GEMINI_MODEL_ENV = "MARGINPILOT_GEMINI_MODEL"


def _gemini_rest_ask() -> tuple[Any, str] | None:
    """The same model over plain HTTP, for a deployment without its client.

    ``google-genai`` is pinned in ``requirements.txt`` but is not installed
    everywhere this runs, and installing it is not always available as an option.
    This is the transport of last resort, and *only* the transport: the model,
    the system prompt, the proposal prompt and the reply parser are the ones
    ``GeminiReasoner`` uses, imported from it rather than restated here. What is
    deliberately not reproduced is its free-tier pacing and its 429/5xx retry —
    that logic belongs to the research client, and a copy of it here would be a
    second implementation of something that already exists. A rate limit
    therefore surfaces as no assessment, which is the honest outcome.

    The model defaults to ``reasoner.DEFAULT_GEMINI_MODEL`` and is overridable
    per deployment through :data:`GEMINI_MODEL_ENV`, because which models a given
    key can actually reach is a fact about that key rather than about the system.

    Reports itself as ``marginpilot_gemini_rest`` so a reader can tell which
    client answered. Returns ``None`` when there is no credential; it never
    substitutes anything for one.
    """
    from src.agent.reasoner import (
        DEFAULT_GEMINI_MODEL,
        SYSTEM_PROMPT,
        _ENV_PATH,
        _extract_json,
    )

    load_dotenv(_ENV_PATH)
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None

    model = os.environ.get(GEMINI_MODEL_ENV, "").strip() or DEFAULT_GEMINI_MODEL

    def ask(prompt: str) -> dict[str, Any]:
        response = httpx.post(
            f"{_GEMINI_REST}/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 8192,
                    # The prompt already specifies a JSON object; asking the API
                    # to enforce the MIME type removes the common parse failure.
                    "responseMimeType": "application/json",
                },
            },
            timeout=60.0,
        )
        # Raises on any 4xx/5xx, including 429. The caller reports that as no
        # assessment rather than retrying or degrading to something else.
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ValueError(f"no candidate in model reply: {str(payload)[:400]}")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts)
        return _extract_json(text)

    return ask, "marginpilot_gemini_rest"


#: OpenRouter's OpenAI-compatible surface, used for the Nemotron family.
#:
#: Deliberately **not** in the ``auto`` chain. Which model produced an
#: assessment is a fact the audit line records, so adding a new one to the
#: automatic order would silently change what every subsequent assessment means
#: and would break comparability with the recorded runs. Reachable only by
#: naming it: ``MARGINPILOT_PROPOSER=openrouter``.
_OPENROUTER_REST = "https://openrouter.ai/api/v1"

#: The Nemotron build this transport names unless a deployment says otherwise.
#: Same reasoning as :data:`GEMINI_MODEL_ENV`: which models a key can actually
#: reach is a property of that deployment, not of the system. It selects a
#: model. It cannot change a prompt, a validation rule, an evidence rule, or any
#: economics.
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
OPENROUTER_MODEL_ENV = "MARGINPILOT_OPENROUTER_MODEL"


def _openrouter_ask() -> tuple[Any, str] | None:
    """Nemotron over OpenRouter, reachable only by asking for it by name.

    A transport and nothing more, on the same terms as :func:`_gemini_rest_ask`:
    the system prompt and the reply parser are imported from
    :mod:`src.agent.reasoner` rather than restated, and the proposal prompt still
    comes from ``LLMProposer``. What the model is asked, and what is done with
    what it says, are unchanged — only which endpoint answers.

    Deliberately not reproduced: pacing and 429/5xx retry. That logic belongs to
    the research client and a copy here would be a second implementation of it.
    A rate limit therefore surfaces as no assessment, which is the honest
    outcome. Every other failure — an HTTP error, a reply with no choices, an
    unparseable body — raises, and the caller reports no assessment rather than
    substituting anything for one.

    Reports itself as ``marginpilot_openrouter_nemotron`` so a reader can tell
    which client answered. Returns ``None`` when there is no credential.
    """
    from src.agent.reasoner import SYSTEM_PROMPT, _ENV_PATH, _extract_json

    load_dotenv(_ENV_PATH)
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None

    model = os.environ.get(OPENROUTER_MODEL_ENV, "").strip() or DEFAULT_OPENROUTER_MODEL

    def ask(prompt: str) -> dict[str, Any]:
        response = httpx.post(
            f"{_OPENROUTER_REST}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                # Attribution only; OpenRouter reads these for usage reporting.
                "X-Title": "MarginPilot",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 8192,
                # The prompt already specifies a JSON object; asking the API to
                # enforce the type removes the common parse failure.
                "response_format": {"type": "json_object"},
            },
            timeout=60.0,
        )
        # Raises on any 4xx/5xx, including 429. The caller reports that as no
        # assessment rather than retrying or degrading to something else.
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError(f"no choice in model reply: {str(payload)[:400]}")
        text = (choices[0].get("message") or {}).get("content") or ""
        return _extract_json(text)

    return ask, "marginpilot_openrouter_nemotron"


def _reasoner_ask(choice: str) -> tuple[Any, str] | None:
    """The ``ask`` callable of an existing reasoner, or ``None``.

    Both reasoners refuse to construct without their own credential, and both
    import their client lazily, so an absent key or an uninstalled library
    arrives here as an exception rather than as a silent downgrade. That is the
    behaviour we want: there is no third path where something else answers in
    the model's name.

    The REST fallback is tried **last**, so installing ``google-genai`` is all it
    takes for the research client to win back the route with no code change.

    ``openrouter`` is an explicit choice and is deliberately absent from
    ``auto``. See :func:`_openrouter_ask` for why.
    """
    from src.agent import reasoner as reasoners

    candidates = {
        "gemini": (reasoners.GeminiReasoner, "marginpilot_gemini"),
        "claude": (reasoners.ClaudeReasoner, "marginpilot"),
    }
    order = ("gemini", "claude") if choice == "auto" else (choice,)
    for key in order:
        if key not in candidates:
            continue
        factory, name = candidates[key]
        try:
            return factory()._ask, name
        except Exception as exc:  # missing credential, missing client library
            logger.info("proposer %s unavailable: %s: %s", key, type(exc).__name__, exc)

    # Explicit opt-in only, and placed after the loop above so the ``auto``
    # order below is reached on exactly the paths it was reached on before.
    if choice == "openrouter":
        try:
            return _openrouter_ask()
        except Exception as exc:  # missing credential, malformed configuration
            logger.info("openrouter unavailable: %s: %s", type(exc).__name__, exc)
            return None

    if choice in ("auto", "gemini"):
        try:
            fallback = _gemini_rest_ask()
        except Exception as exc:
            logger.info("gemini REST unavailable: %s: %s", type(exc).__name__, exc)
            return None
        if fallback is not None:
            logger.info("using the Gemini REST transport; google-genai is absent")
            return fallback
    return None


def _proposer() -> tuple[Proposer | None, str | None]:
    """The configured proposal producer, and why there is none when there isn't."""
    choice = os.environ.get(PROPOSER_ENV, "auto").strip().lower()
    if choice == "none":
        return None, (
            f"No proposal producer is configured ({PROPOSER_ENV}=none), so "
            "MarginPilot has stated no growth hypothesis for this promotion."
        )
    found = _reasoner_ask(choice)
    if found is None:
        return None, (
            "MarginPilot could not reach a reasoner to form a growth hypothesis "
            "for this promotion: no reasoner could be constructed from this "
            "deployment's credentials and installed clients. Rather than borrow "
            "a recorded merchant's hypothesis or substitute a fixed number, no "
            "expected lift is claimed."
        )
    ask, name = found
    return LLMProposer(ask, name=name), None


class OfferKind(str, Enum):
    """Offer types the generic evaluator can receive explicitly."""

    FLAT_DISCOUNT = "flat_discount"
    PERCENTAGE_DISCOUNT = "percentage_discount"
    FREE_SHIPPING = "free_shipping"
    BUNDLE = "bundle"


class EvaluationInput(BaseModel):
    """Merchant-controlled facts only; outcome claims are forbidden."""

    model_config = ConfigDict(extra="forbid")

    offer_kind: OfferKind
    flat_discount_inr: float | None = None
    discount_pct: float | None = None
    shipping_fee_waived_inr: float | None = None
    bundle_added_value_inr: float | None = None
    cohort_id: str = "ALL"
    population: int
    aov_inr: float
    margin: float
    observed_conversion: float
    budget_inr: float


class EvaluationInadmissible(ValueError):
    """The evaluator cannot truthfully price the request as stated."""

    def __init__(self, reason: str, violation: RuleViolation | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.violation = violation


def _finite(value: float, label: str) -> float:
    if not math.isfinite(float(value)):
        raise EvaluationInadmissible(f"{label} must be a finite number.")
    return float(value)


def _non_negative(value: float | None, label: str) -> float:
    if value is None:
        raise EvaluationInadmissible(f"{label} is required for this offer type.")
    checked = _finite(value, label)
    if checked < 0.0:
        raise EvaluationInadmissible(f"{label} cannot be negative.")
    return checked


def _validate(request: EvaluationInput, limits: PolicyLimits) -> None:
    if request.population < 1:
        raise EvaluationInadmissible("Eligible customers must be at least one.")
    if request.population > MAX_POPULATION:
        raise EvaluationInadmissible(
            f"{request.population:,} eligible customers is above the "
            f"{MAX_POPULATION:,} this evaluator can build a merchant view for. "
            "That is a limit of this tool, not of the policy."
        )

    aov = _finite(request.aov_inr, "Average order value")
    if aov <= 0.0:
        raise EvaluationInadmissible("Average order value must be greater than zero.")

    margin = _finite(request.margin, "Contribution margin")
    if not 0.0 <= margin <= 1.0:
        raise EvaluationInadmissible("Contribution margin must be in [0, 1].")

    conversion = _finite(request.observed_conversion, "Baseline conversion")
    if not 0.0 < conversion <= 1.0:
        raise EvaluationInadmissible(
            "Baseline conversion must be above 0% and at most 100%."
        )

    budget = _finite(request.budget_inr, "Budget")
    if budget < 0.0:
        raise EvaluationInadmissible("Budget cannot be negative.")

    if request.cohort_id != "ALL":
        raise EvaluationInadmissible(
            "This evaluator has no merchant-supplied cohort data, so it can only "
            "price the full eligible population."
        )

    if request.offer_kind is OfferKind.FLAT_DISCOUNT:
        _non_negative(request.flat_discount_inr, "Flat discount")
    elif request.offer_kind is OfferKind.PERCENTAGE_DISCOUNT:
        discount = _non_negative(request.discount_pct, "Percentage discount")
        violation = check_discount(discount, limits)
        if violation is not None:
            raise EvaluationInadmissible(
                "The percentage discount is above the standing policy ceiling.",
                violation,
            )
    elif request.offer_kind is OfferKind.FREE_SHIPPING:
        _non_negative(request.shipping_fee_waived_inr, "Shipping fee waived")
    elif request.offer_kind is OfferKind.BUNDLE:
        _non_negative(request.discount_pct, "Bundle discount")
        _non_negative(request.bundle_added_value_inr, "Bundle added value")
        raise EvaluationInadmissible(
            "Bundles cannot be priced through this evaluator: the pre-experiment "
            "policy brief does not account for bundle-added order value."
        )


def _intervention(request: EvaluationInput) -> Intervention:
    """Create exactly the intervention type the merchant selected."""
    common: dict[str, Any] = {
        "intervention_id": GENERIC_INTERVENTION_ID,
        "name": {
            OfferKind.FLAT_DISCOUNT: "Flat discount",
            OfferKind.PERCENTAGE_DISCOUNT: "Percentage discount",
            OfferKind.FREE_SHIPPING: "Free shipping",
            OfferKind.BUNDLE: "Bundle offer",
        }[request.offer_kind],
        "description": "Merchant-stated promotion evaluated without a recorded case.",
        "target_product_ids": ("merchant_order",),
    }
    if request.offer_kind is OfferKind.FLAT_DISCOUNT:
        return Intervention(
            kind=InterventionKind.FLAT_DISCOUNT,
            flat_discount_inr=request.flat_discount_inr,
            **common,
        )
    if request.offer_kind is OfferKind.PERCENTAGE_DISCOUNT:
        return Intervention(
            kind=InterventionKind.PERCENTAGE_DISCOUNT,
            discount_pct=request.discount_pct,
            **common,
        )
    if request.offer_kind is OfferKind.FREE_SHIPPING:
        return Intervention(
            kind=InterventionKind.FREE_SHIPPING,
            shipping_fee_waived_inr=request.shipping_fee_waived_inr,
            **common,
        )
    raise AssertionError("bundle requests are refused before an intervention is built")


def _merchant_view(request: EvaluationInput, intervention: Intervention) -> MerchantView:
    """Build the smallest honest merchant view from the merchant's own facts."""
    customers = tuple(
        CustomerView(
            customer_id=f"merchant_customer_{index:06d}",
            segment_id="all_eligible",
            tenure_days=0,
            orders_last_90d=0,
            days_since_last_order=0,
            historical_aov_inr=request.aov_inr,
        )
        for index in range(request.population)
    )
    product = Product(
        product_id="merchant_order",
        name="Merchant reference order",
        category="merchant_stated",
        description="A reference order constructed from the merchant's stated AOV.",
        unit_price_inr=request.aov_inr,
        unit_cost_inr=request.aov_inr * (1.0 - request.margin),
        inventory_units=0,
        inventory_age_days=0,
        stock_status="steady",
    )
    return MerchantView(
        world_id="merchant_promotion_evaluation",
        population=request.population,
        budget_inr=request.budget_inr,
        observed_conversion=request.observed_conversion,
        observed_aov_inr=request.aov_inr,
        observed_margin=request.margin,
        experiment_window_days=28,
        semantic=SemanticContext(
            merchant_name="Merchant promotion evaluation",
            vertical="not supplied",
            merchant_description="Merchant-stated economics with no response hypothesis.",
            seasonal_events=(),
            competitor_events=(),
            customer_service_themes=(),
            inventory_notes=(),
            trading_notes=(),
        ),
        products=(product,),
        segments=(),
        customers=customers,
        interventions=(intervention,),
        history=(),
    )


def _screen(brief: MerchantBrief, limits: PolicyLimits) -> None:
    """Apply the existing depth gate before a clamped intervention is priced."""
    depth = brief.intervention(GENERIC_INTERVENTION_ID).depth_at_observed_aov
    violation = check_discount(depth, limits)
    if violation is not None:
        raise EvaluationInadmissible(
            "The offer is above the standing policy discount ceiling.", violation
        )


def _offer_payload(brief: MerchantBrief) -> dict[str, Any]:
    intervention = brief.intervention(GENERIC_INTERVENTION_ID)
    economics = brief.economics_for("ALL", GENERIC_INTERVENTION_ID)
    return {
        "intervention_id": intervention.intervention_id,
        "kind": intervention.kind,
        "name": intervention.name,
        "description": intervention.description,
        "depth_at_observed_aov": intervention.depth_at_observed_aov,
        "incentive_cost_per_order_inr": economics.incentive_cost_per_order_inr,
        "contribution_per_order_inr": economics.contribution_per_order_inr,
        "cohort_id": "ALL",
        "cohort_customers": brief.population,
    }


def _unavailable(reason: str, *, source: str | None = None) -> dict[str, Any]:
    """No hypothesis, said plainly. Never a lift, never an evidence basis."""
    return {
        "status": "UNAVAILABLE",
        "expected_lift_absolute": None,
        "evidence_basis": "NONE",
        "hypothesis": None,
        "mechanism": None,
        "citations": [],
        "source": source,
        "reason": (
            f"{reason} A measured experiment is required before promotion can be "
            "recommended."
        ),
    }


def _assessment(brief: MerchantBrief, limits: PolicyLimits) -> tuple[dict[str, Any], Any]:
    """Ask the existing proposer for a hypothesis, then let the policy price it.

    Three outcomes, and each one is reported as what it is:

    * a proposer answered and the reply validated — the assessment is that
      reply, and ``recommend_from_raw`` decides what it is worth;
    * a proposer answered and the reply did not validate — the rejection is
      surfaced, and the policy's own fail-closed INSUFFICIENT_EVIDENCE stands;
    * no proposer could be constructed — nothing is claimed at all.

    The raw reply is what reaches the policy in every case. Nothing is repaired
    here, and no substitute payload is ever supplied.
    """
    proposer, why_none = _proposer()
    if proposer is None:
        return _unavailable(why_none or "No growth hypothesis is available."), \
            recommend_from_raw(brief, {}, limits=limits)

    source = getattr(proposer, "name", "proposer")
    try:
        raw = proposer.propose(brief)
    except Exception as exc:  # transport, rate limit, unparseable reply
        logger.warning("proposer %s failed: %s: %s", source, type(exc).__name__, exc)
        return (
            _unavailable(
                f"MarginPilot's reasoner did not return a usable hypothesis "
                f"({type(exc).__name__}).",
                source=source,
            ),
            recommend_from_raw(brief, {}, limits=limits),
        )

    # The policy is the authority on this reply; validating here only decides
    # what the panel is allowed to display beside the verdict.
    #
    # A ValueError from here is the engine refusing to price the *model's*
    # figure — a claimed lift that puts treatment conversion outside [0, 1], for
    # instance. That is an unusable reply, not an inadmissible request, so it is
    # reported as no assessment rather than as a refusal of what the merchant
    # asked.
    try:
        recommendation = recommend_from_raw(brief, raw, limits=limits)
    except ValueError as exc:
        logger.warning("proposer %s produced an unpriceable reply: %s", source, exc)
        return (
            _unavailable(
                f"MarginPilot's reasoner replied with a figure the engine will "
                f"not price ({exc}).",
                source=source,
            ),
            recommend_from_raw(brief, {}, limits=limits),
        )

    try:
        proposal = validate_proposal(raw)
    except ProposalRejected as exc:
        return (
            _unavailable(
                f"MarginPilot's reasoner replied, but the proposal was refused "
                f"by the validator: {exc}.",
                source=source,
            ),
            recommendation,
        )

    # No experiment has been run on this merchant — this endpoint has no route to
    # one — so an EXPERIMENT basis cannot be true here whatever the reply says.
    # The policy already refuses to act on the claim; this stops the panel from
    # *displaying* it, which would be the same lie in a more convincing place.
    if proposal.evidence_basis is EvidenceBasis.EXPERIMENT:
        return (
            _unavailable(
                "MarginPilot's reasoner claimed measured evidence for a promotion "
                "no experiment has been run on, so the assessment is not shown.",
                source=source,
            ),
            recommendation,
        )

    return (
        {
            "status": "AVAILABLE",
            "expected_lift_absolute": proposal.expected_lift_absolute,
            "evidence_basis": proposal.evidence_basis.value,
            "hypothesis": proposal.hypothesis,
            "mechanism": proposal.mechanism,
            "citations": list(proposal.citations),
            "source": source,
            "reason": None,
        },
        recommendation,
    )


def evaluate(
    request: EvaluationInput, *, limits: PolicyLimits | None = None
) -> dict[str, Any]:
    """Evaluate a custom promotion without borrowing a recorded assessment."""
    limits = limits or PolicyLimits()
    _validate(request, limits)
    intervention = _intervention(request)
    brief = build_brief(_merchant_view(request, intervention))
    _screen(brief, limits)

    assessment, recommendation = _assessment(brief, limits)

    return {
        "status": (
            "EVALUATED" if assessment["status"] == "AVAILABLE"
            else "ASSESSMENT_UNAVAILABLE"
        ),
        "offer": _offer_payload(brief),
        "merchant": {
            "population": brief.population,
            "budget_inr": brief.budget_inr,
            "observed_conversion": brief.observed_conversion,
            "observed_aov_inr": brief.observed_aov_inr,
            "observed_margin": brief.observed_margin,
            "cohort_id": "ALL",
        },
        "assessment": assessment,
        "recommendation": recommendation.to_dict(),
        "policy_limits": {
            "max_discount_pct": limits.max_discount_pct,
            "min_contribution_margin": limits.min_contribution_margin,
        },
    }


def inadmissible_payload(exc: EvaluationInadmissible) -> dict[str, Any]:
    """Shape failed requests without presenting them as policy decisions."""
    violation = exc.violation
    return {
        "status": "EVALUATION_INADMISSIBLE",
        "recommendation": None,
        "refusal": {
            "reason": exc.reason,
            "engine_message": violation.message if violation else None,
            "rule": violation.rule.value if violation else None,
            "observed": violation.observed if violation else None,
            "limit": violation.limit if violation else None,
            "refused_by": (
                "src/policy/gates.py::check_discount" if violation else "api/evaluate.py"
            ),
        },
    }
