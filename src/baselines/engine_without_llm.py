"""Baseline 5 — the experimentation engine with the LLM removed. **The ablation.**

Same randomization, same fixed horizon, same contribution-powered sample size,
same CI-lower-bound scaling rule, same policy gates. The only thing missing is
the reasoning: instead of forming a hypothesis about *this* merchant, it works
through a fixed set of interventions in a preset order until the budget runs out.

This is the baseline that matters. "The agent is intelligent" is not evidence;
the gap between this and MarginPilot is. If that gap is zero, the README says so
and the finding stands (CLAUDE.md invariant 9).

**It must not read semantic context.** The whole point of the ablation is that it
has the machinery and not the reasoning, so it sees the merchant's numbers and
never its story. ``tests/baselines/test_baselines.py`` asserts this against the
source, so a later convenience edit cannot quietly weaken the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.eval.contracts import ExperimentProposal, MerchantView, Proposal, ScalingRule

#: A preset order, fixed before any world was seen. Not derived from data, not
#: reordered per merchant — that would be a form of reasoning, which is the
#: thing being ablated.
DEFAULT_ORDER: tuple[str, ...] = ("int_flat", "int_shipping", "int_pct", "int_bundle")


@dataclass(frozen=True, slots=True)
class EngineWithoutLLM:
    name: str = "5_engine_no_llm"
    scaling_rule: ScalingRule = ScalingRule.BAYESIAN_POSTERIOR
    #: Four experiments per world — one per hypothesis in the fixed set.
    #:
    #: This is the ablation's own choice and it pays for it. Working through a
    #: preset list is what a system without merchant-specific reasoning can do;
    #: deciding that only one of the four is worth asking about, or that none
    #: is, requires exactly the judgement being ablated.
    max_experiments: int = 4
    order: tuple[str, ...] = DEFAULT_ORDER
    mde_fraction_of_order_contribution: float = 0.02
    assumed_lift_absolute: float = 0.03

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        contribution_per_order = view.observed_aov_inr * view.observed_margin
        mde = contribution_per_order * self.mde_fraction_of_order_contribution
        available = {i.intervention_id for i in view.interventions}

        proposals = []
        for intervention_id in self.order:
            if intervention_id not in available:
                continue
            intervention = view.intervention(intervention_id)
            proposals.append(
                ExperimentProposal(
                    intervention_id=intervention_id,
                    hypothesis_id=f"hyp_engine_{view.world_id}_{intervention_id}",
                    prediction=(
                        f"{intervention.name} produces incremental contribution "
                        "whose CI lower bound clears zero."
                    ),
                    reasoning=(
                        "Fixed hypothesis set, tested in a preset order. No merchant-"
                        "specific reasoning is performed and no context is read."
                    ),
                    expected_effect_absolute=self.assumed_lift_absolute,
                    mde_contribution_per_customer_inr=mde,
                    success_condition=(
                        "CI lower bound on incremental contribution above zero at horizon."
                    ),
                    failure_condition=(
                        "CI on incremental contribution contains or lies below zero."
                    ),
                )
            )
        return proposals


@dataclass(frozen=True, slots=True)
class LearnOnly:
    """Baseline 1b — experiment, never scale. A diagnostic, not a competitor.

    Runs exactly the experiments Baseline 5 runs and then declines every one of
    them, so its realized net *is* the cost of learning with the winnings removed.
    Comparing it against Baseline 1 gives the price of information; comparing
    Baseline 5 against it gives what the information was worth.
    """

    name: str = "1b_learn_only"
    scaling_rule: ScalingRule = ScalingRule.NEVER
    #: Matches Baseline 5, so the comparison isolates the scaling decision.
    max_experiments: int = 4
    engine: EngineWithoutLLM = field(default_factory=EngineWithoutLLM)

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        return self.engine.decide(view, budget_inr)
