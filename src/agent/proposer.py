"""Turning a merchant brief into a model proposal.

Deliberately separate from :mod:`src.agent.reasoner`. That module carries the
Cycle-2 Fix A ablation switch and the three reasoners the research ran on;
extending its Protocol would put a product concern inside a research artifact.
This module wraps a plain ``ask`` callable instead, so any client — the existing
Gemini or Claude reasoner, a stub, or something else entirely — can be adapted
without the research code changing.

Nothing here decides anything. A proposal is a hypothesis with citations; it
goes to :mod:`src.agent.decision_policy`, which recomputes every rupee from the
brief and may overrule it.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol, runtime_checkable

from src.agent.brief import MerchantBrief

#: What the model is asked for, and what it is told it cannot do.
PROPOSAL_PROMPT = """\
You are advising a merchant on whether a promotion is worth running.

You do NOT decide. A deterministic economic policy recomputes every figure you
mention and may overrule you. Your job is to read this merchant's situation and
propose the single most plausible campaign to consider, or to say plainly that
none is plausible.

Reason about NET contribution, never conversion alone. The incentive is paid on
every treated order, including the customers who would have bought anyway, so a
campaign can lift conversion and still destroy margin.

Here is everything known about the merchant:

{brief}

Reply with JSON only, in exactly this shape:

{{
  "intervention_id": "<one of the intervention ids above>",
  "cohort_id": "<one of the cohort ids above, or ALL>",
  "expected_lift_absolute": <absolute conversion lift you expect, e.g. 0.03>,
  "evidence_basis": "PRIOR" | "HISTORY",
  "hypothesis": "<what you predict, in one sentence>",
  "mechanism": "<why, grounded in the merchant's own data>",
  "citations": ["<brief fields you read>"],
  "requested_decision": "PROMOTE" | "RUN_EXPERIMENT_FIRST" | "DO_NOT_PROMOTE"
}}

Rules:
- Cite only fields present above. Do not invent merchant data.
- "evidence_basis" is PRIOR unless a past campaign in `history` supports you,
  in which case it is HISTORY. You may not claim EXPERIMENT: no experiment has
  been run on this merchant yet.
- Do not mention customer response parameters, segment names, or any outcome
  you were not shown. You have not been shown them.
"""


@runtime_checkable
class Proposer(Protocol):
    """Anything that can turn a brief into a raw proposal payload."""

    def propose(self, brief: MerchantBrief) -> dict[str, Any]:
        ...


class StubProposer:
    """Returns a fixed payload. Used by the demo and the tests.

    The deterministic path is identical whether the payload came from a model or
    from here, which is what makes the demo runnable without API credits — and
    what makes the adversarial tests meaningful, since they need to control
    exactly what the "model" said.
    """

    name = "stub"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)

    def propose(self, brief: MerchantBrief) -> dict[str, Any]:
        return dict(self._payload)


class LLMProposer:
    """Adapts any ``ask(prompt) -> dict`` client into a :class:`Proposer`.

    Malformed replies are returned as-is rather than repaired. Validation and
    refusal belong to :func:`src.agent.recommendation.validate_proposal`, which
    fails closed — repairing a reply here would hide the fact that the model
    produced something unusable.
    """

    def __init__(self, ask: Callable[[str], dict[str, Any]], *, name: str = "llm") -> None:
        self._ask = ask
        self.name = name

    def propose(self, brief: MerchantBrief) -> dict[str, Any]:
        prompt = PROPOSAL_PROMPT.format(
            brief=json.dumps(brief.to_dict(), indent=1, default=str)
        )
        return self._ask(prompt)
