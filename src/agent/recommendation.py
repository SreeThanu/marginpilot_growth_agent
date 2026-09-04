"""What the LLM may propose, and what the deterministic layer returns.

Two objects with a deliberate asymmetry between them.

:class:`Proposal` is what the model is allowed to say: a hypothesis, a cohort, a
mechanism, an expected lift, and where in the brief it read each claim. It may
*request* a decision, and that request carries no weight — the field exists so
the request can be recorded and then overruled, which is the behaviour ADV-1
tests for.

:class:`MerchantRecommendation` is what the merchant sees. Every rupee on it is
computed by :mod:`src.agent.decision_policy` from the brief, never copied from
the model's reply.

``G4_VALUE_OF_INFORMATION_UNRESOLVED`` is carried explicitly rather than assumed
away. Whether an experiment costs less than the information it buys is an open
scientific question in this project (SCI-3), and a recommendation that quietly
took a side on it would be inventing precision it does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

#: Surfaced whenever an experiment is recommended. Not an internal flag: the
#: demo renderer asserts it reaches the merchant (ADV-11).
UNRESOLVED_VALUE_OF_INFORMATION = "G4_VALUE_OF_INFORMATION_UNRESOLVED"

#: Vocabulary that may never appear in a model reply. A proposal containing any
#: of these is rejected rather than sanitised (ADV-9) — a model that has seen
#: ground truth cannot be trusted on the rest of its answer either.
FORBIDDEN_PROPOSAL_TOKENS = (
    "y0", "y1", "potential_outcome", "potentialoutcome", "ground_truth",
    "groundtruth", "tau_contribution", "tau_converted", "true_population_net",
    "best_intervention", "responsiveness", "price_elasticity", "affinity",
    "promo_response_scale", "cannibalization", "baseline_purchase_prob",
    "segment_name", "behaviour_tags", "archetype",
)


class RecommendationDecision(str, Enum):
    """The four states the product may return."""

    PROMOTE = "PROMOTE"
    DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
    RUN_EXPERIMENT_FIRST = "RUN_EXPERIMENT_FIRST"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceBasis(str, Enum):
    """Where a claim's confidence comes from. Ordered weakest to strongest.

    Only ``EXPERIMENT`` can support a rollout. ``PRIOR`` and ``HISTORY`` are
    enough to justify *asking*, never enough to justify *spending* — which is
    the distinction the whole product is built around.
    """

    NONE = "NONE"
    PRIOR = "PRIOR"
    HISTORY = "HISTORY"
    EXPERIMENT = "EXPERIMENT"


class ProposalRejected(ValueError):
    """The model's reply cannot be used. The system fails closed."""


@dataclass(frozen=True, slots=True)
class Proposal:
    """A validated model proposal. Advisory in every respect."""

    intervention_id: str
    cohort_id: str
    #: Absolute conversion lift the model believes the intervention produces.
    expected_lift_absolute: float
    evidence_basis: EvidenceBasis
    hypothesis: str
    mechanism: str
    #: Brief fields the model read. At least one is required.
    citations: tuple[str, ...]
    #: What the model would like to happen. Recorded, then overruled if the
    #: economics disagree.
    requested_decision: RecommendationDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_id": self.intervention_id,
            "cohort_id": self.cohort_id,
            "expected_lift_absolute": self.expected_lift_absolute,
            "evidence_basis": self.evidence_basis.value,
            "hypothesis": self.hypothesis,
            "mechanism": self.mechanism,
            "citations": list(self.citations),
            "requested_decision": (
                self.requested_decision.value if self.requested_decision else None
            ),
        }


def validate_proposal(raw: Mapping[str, Any]) -> Proposal:
    """Turn a model reply into a :class:`Proposal`, or refuse it.

    Refusal is the safe outcome and is never softened into a default proposal:
    a malformed reply means the model's state is unknown, and guessing what it
    meant is how a system starts inventing merchant data.
    """
    if not isinstance(raw, Mapping):
        raise ProposalRejected(f"proposal must be a mapping, got {type(raw).__name__}")

    blob = repr(dict(raw)).lower()
    for token in FORBIDDEN_PROPOSAL_TOKENS:
        if token in blob:
            raise ProposalRejected(
                f"proposal references forbidden information: {token!r}"
            )

    required = ("intervention_id", "cohort_id", "expected_lift_absolute",
                "evidence_basis", "hypothesis", "mechanism", "citations")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ProposalRejected(f"proposal is missing {missing}")

    try:
        lift = float(raw["expected_lift_absolute"])
    except (TypeError, ValueError) as exc:
        raise ProposalRejected(f"expected_lift_absolute is not a number: {exc}") from exc
    if not 0.0 <= lift <= 1.0:
        raise ProposalRejected(
            f"expected_lift_absolute must be an absolute rate in [0, 1], got {lift}"
        )

    try:
        basis = EvidenceBasis(str(raw["evidence_basis"]).upper())
    except ValueError as exc:
        raise ProposalRejected(f"unknown evidence_basis: {raw['evidence_basis']!r}") from exc

    citations = tuple(str(c) for c in raw["citations"] or ())
    if not citations:
        raise ProposalRejected("a proposal must cite at least one brief field")

    requested = raw.get("requested_decision")
    if requested is not None:
        try:
            requested = RecommendationDecision(str(requested).upper())
        except ValueError as exc:
            raise ProposalRejected(f"unknown requested_decision: {requested!r}") from exc

    for key in ("intervention_id", "cohort_id", "hypothesis", "mechanism"):
        if not str(raw[key]).strip():
            raise ProposalRejected(f"{key} is empty")

    return Proposal(
        intervention_id=str(raw["intervention_id"]),
        cohort_id=str(raw["cohort_id"]),
        expected_lift_absolute=lift,
        evidence_basis=basis,
        hypothesis=str(raw["hypothesis"]).strip(),
        mechanism=str(raw["mechanism"]).strip(),
        citations=citations,
        requested_decision=requested,
    )


@dataclass(frozen=True, slots=True)
class MerchantRecommendation:
    """The deterministic answer. Serializable for the demo UI."""

    decision: RecommendationDecision
    diagnosis: str
    rationale: str
    intervention_id: str | None
    cohort_id: str | None
    #: Economics, all recomputed from the brief. Never the model's arithmetic.
    expected_incremental_contribution_inr: float
    expected_incentive_cost_inr: float
    expected_net_contribution_inr: float
    #: The conversion lift at which net contribution crosses zero. ``None`` when
    #: no lift can reach it, which is itself the finding (G2).
    required_break_even_lift_absolute: float | None
    evidence_basis: EvidenceBasis
    experiment_required: bool
    experiment_cost_inr: float = 0.0
    experiment_horizon_per_arm: int = 0
    customers_treated: int = 0
    binding_constraints: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    model_requested: RecommendationDecision | None = None
    gates_passed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def overruled_the_model(self) -> bool:
        """True when the deterministic layer disagreed with the model."""
        return (
            self.model_requested is not None
            and self.model_requested is not self.decision
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "diagnosis": self.diagnosis,
            "rationale": self.rationale,
            "intervention_id": self.intervention_id,
            "cohort_id": self.cohort_id,
            "expected_incremental_contribution_inr": round(
                self.expected_incremental_contribution_inr, 2
            ),
            "expected_incentive_cost_inr": round(self.expected_incentive_cost_inr, 2),
            "expected_net_contribution_inr": round(self.expected_net_contribution_inr, 2),
            "required_break_even_lift_absolute": self.required_break_even_lift_absolute,
            "evidence_basis": self.evidence_basis.value,
            "experiment_required": self.experiment_required,
            "experiment_cost_inr": round(self.experiment_cost_inr, 2),
            "experiment_horizon_per_arm": self.experiment_horizon_per_arm,
            "customers_treated": self.customers_treated,
            "binding_constraints": list(self.binding_constraints),
            "unresolved": list(self.unresolved),
            "citations": list(self.citations),
            "assumptions": list(self.assumptions),
            "model_requested": (
                self.model_requested.value if self.model_requested else None
            ),
            "overruled_the_model": self.overruled_the_model,
            "gates_passed": list(self.gates_passed),
        }
