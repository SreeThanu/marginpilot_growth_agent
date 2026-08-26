"""Baseline 4 — the LLM strategist. Same model, no experiments, no gate.

The ablation in the other direction. Baseline 5 has the machinery and no
reasoning; this has the reasoning and no machinery. It reads the same merchant
context MarginPilot reads, picks a campaign, and runs it on the whole customer
base — no control group, no horizon, no contribution check.

It exists because "the LLM is useful" and "the LLM plus experimentation is
useful" are different claims, and the second is the one this project makes. If
Baseline 4 does well, the experimentation apparatus is not earning its cost; if
it does badly while MarginPilot does well, the difference is the apparatus.

The LLM call itself lives in ``src/agent/reasoner.py`` — CLAUDE.md permits only
``src/agent/`` to import an LLM client, so this module delegates rather than
importing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.eval.contracts import DirectAction, MerchantView, Proposal, ScalingRule


@dataclass
class LLMStrategist:
    """Picks a campaign from context and runs it. Learns nothing."""

    reasoner: object
    name: str = "4_llm_strategist"
    scaling_rule: ScalingRule = ScalingRule.NEVER  # never tests, so never scales
    max_experiments: int = 0

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        choice = self.reasoner.choose_campaign(view)  # type: ignore[attr-defined]
        intervention = view.intervention(choice["intervention_id"])

        # No targeting rule and no economic gate: the whole base, as chosen.
        # Trimmed only to what the budget can pay for, since a campaign that
        # cannot be funded is not a decision the merchant could have made.
        targets = tuple(c.customer_id for c in view.customers)
        expected_cost_each = view.observed_conversion * intervention.incentive_cost_inr(
            view.observed_aov_inr
        )
        if expected_cost_each > 0:
            targets = targets[: int(budget_inr // expected_cost_each)]

        return [
            DirectAction(
                intervention_id=choice["intervention_id"],
                target_customer_ids=targets,
                rationale=choice["rationale"],
            )
        ]
