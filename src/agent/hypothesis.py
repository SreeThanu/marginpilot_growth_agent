"""What the agent commits to before it spends anything.

Two objects, and the second one matters as much as the first:

* :class:`AgentHypothesis` — a falsifiable prediction about one intervention,
  with its reasoning tied to specific quoted lines of the merchant's context.
* :class:`SkipDecision` — the agent's conclusion that **no** experiment is worth
  its cost here.

A skip is a decision, not the absence of one. It carries the same reasoning
burden as a launch and is logged the same way, because on this corpus one
experiment costs roughly 2.8x the profit pool of the world it runs in and
declining is frequently the correct answer. A system that only records what it
did, never what it declined to do, cannot be audited for restraint.

CLAUDE.md invariant 7: once attached to a launched experiment the hypothesis is
immutable and fingerprinted. The agent may diagnose a failure and propose a
*new* hypothesis; it may never edit the old one to match what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.experiment.registry import Hypothesis as RegistryHypothesis


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Decision(str, Enum):
    """The agent's primary decision: spend on a question, or decline to."""

    RUN = "run"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class ContextCitation:
    """A specific line of merchant context the agent is reasoning from.

    Quoted rather than summarised so that a reader can check whether the agent
    actually read the situation or was pattern-matching on numbers and dressing
    it up afterwards. An unquotable justification is a tell.
    """

    field: str
    quote: str
    inference: str

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "quote": self.quote, "inference": self.inference}


@dataclass(frozen=True, slots=True)
class AgentHypothesis:
    """A falsifiable prediction, formed before any data exists.

    Frozen. The registry fingerprints it at launch, so a later edit is
    detectable even though this object cannot itself be mutated.
    """

    hypothesis_id: str
    intervention_id: str
    prediction: str
    reasoning: str
    #: The specific context lines the reasoning rests on.
    citations: tuple[ContextCitation, ...]
    #: Predicted absolute lift in conversion.
    expected_effect_absolute: float
    #: Smallest per-customer contribution effect worth resolving, in rupees.
    mde_contribution_per_customer_inr: float
    success_condition: str
    failure_condition: str
    #: Why this question rather than the others available.
    selection_rationale: str
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        for name in ("prediction", "reasoning", "success_condition", "failure_condition"):
            if not str(getattr(self, name)).strip():
                raise ValueError(
                    f"AgentHypothesis.{name} must be non-empty — a prediction that "
                    "cannot fail cannot be scored (CLAUDE.md invariant 7)."
                )
        if self.mde_contribution_per_customer_inr <= 0:
            raise ValueError("mde_contribution_per_customer_inr must be positive")

    def to_registry_hypothesis(self, required_sample_per_arm: int) -> RegistryHypothesis:
        """Convert for the registry, which fingerprints and freezes it at launch.

        The citations are folded into the reasoning text so they are inside the
        fingerprint: if the agent later claims it reasoned from something else,
        the hash will not match.
        """
        grounding = " | ".join(f"{c.field}: \"{c.quote}\" -> {c.inference}" for c in self.citations)
        return RegistryHypothesis(
            hypothesis_id=self.hypothesis_id,
            prediction=self.prediction,
            reasoning=f"{self.reasoning}\nGrounded in: {grounding}\nChosen because: {self.selection_rationale}",
            expected_effect_absolute=self.expected_effect_absolute,
            required_sample_per_arm=required_sample_per_arm,
            success_condition=self.success_condition,
            failure_condition=self.failure_condition,
            created_at=self.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "intervention_id": self.intervention_id,
            "prediction": self.prediction,
            "reasoning": self.reasoning,
            "citations": [c.to_dict() for c in self.citations],
            "expected_effect_absolute": self.expected_effect_absolute,
            "mde_contribution_per_customer_inr": self.mde_contribution_per_customer_inr,
            "success_condition": self.success_condition,
            "failure_condition": self.failure_condition,
            "selection_rationale": self.selection_rationale,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class SkipDecision:
    """The agent declining to spend. A first-class outcome.

    Recorded with the same detail as a launch: what it looked at, what it
    concluded, and what would have had to be true for it to spend instead. The
    last field is what makes a skip falsifiable rather than merely cautious —
    Day 9 can check whether the stated condition actually held.
    """

    reasoning: str
    citations: tuple[ContextCitation, ...]
    #: What would have changed the decision. Makes the skip checkable later.
    would_run_if: str
    #: The best option considered, and why it still was not worth it.
    best_option_considered: str
    expected_value_reasoning: str
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.reasoning.strip():
            raise ValueError(
                "a skip must carry its reasoning — declining to spend is a decision "
                "and is audited like one"
            )
        if not self.would_run_if.strip():
            raise ValueError(
                "a skip must state what would have changed it, or it cannot be "
                "checked against what was actually true"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": Decision.SKIP.value,
            "reasoning": self.reasoning,
            "citations": [c.to_dict() for c in self.citations],
            "would_run_if": self.would_run_if,
            "best_option_considered": self.best_option_considered,
            "expected_value_reasoning": self.expected_value_reasoning,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class Assessment:
    """The agent's answer to "is any experiment worth its cost here?"."""

    decision: Decision
    hypothesis: AgentHypothesis | None = None
    skip: SkipDecision | None = None

    def __post_init__(self) -> None:
        if self.decision is Decision.RUN and self.hypothesis is None:
            raise ValueError("a RUN assessment must carry a hypothesis")
        if self.decision is Decision.SKIP and self.skip is None:
            raise ValueError("a SKIP assessment must carry its reasoning")

    def to_dict(self) -> dict[str, Any]:
        if self.decision is Decision.SKIP:
            return self.skip.to_dict()  # type: ignore[union-attr]
        return {"decision": Decision.RUN.value, **self.hypothesis.to_dict()}  # type: ignore[union-attr]


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """Why the prediction missed. Written after the result, before the revision.

    Kept separate from the next hypothesis on purpose. Diagnosing and
    re-proposing in one step is how a system ends up quietly rewriting what it
    predicted; separating them means the revision has to stand on its own.
    """

    what_was_predicted: str
    what_happened: str
    why_it_differed: str
    what_this_rules_out: str
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "what_was_predicted": self.what_was_predicted,
            "what_happened": self.what_happened,
            "why_it_differed": self.why_it_differed,
            "what_this_rules_out": self.what_this_rules_out,
            "created_at": self.created_at,
        }
