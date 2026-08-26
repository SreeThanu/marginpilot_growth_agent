"""A hardcoded, non-LLM "agent". Exists only to exercise the measurement spine.

CLAUDE.md build order: the measurement spine must work before anything
intelligent exists. This stub is what proves it does. It reads nothing, reasons
about nothing, and always proposes the same shape of experiment — which makes it
useless as a strategy and ideal as a test instrument, because any number the
harness produces can be traced to the pipeline rather than to cleverness.

Imports no LLM client. ``src/agent/`` is the only module permitted to, and this
file does not exercise the permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.eval.contracts import ExperimentProposal, MerchantView, Proposal, ScalingRule


@dataclass(frozen=True, slots=True)
class StubAgent:
    """Proposes one fixed experiment per world.

    The intervention is chosen by position, not by judgement: whichever
    intervention the world lists first. The MDE is a fixed fraction of the
    contribution one average order produces, so it scales with the merchant
    rather than being a magic rupee figure.
    """

    name: str = "stub"
    #: Same rule as MarginPilot: spend only on a proven gain.
    scaling_rule: ScalingRule = ScalingRule.BAYESIAN_POSTERIOR
    max_experiments: int = 1
    #: Which intervention to always pick, by index in the world's list.
    intervention_index: int = 0
    #: MDE as a fraction of contribution-per-order. 0.02 of a Rs.500 contribution
    #: is Rs.10 per customer — a coarse effect, chosen so the horizon stays
    #: fundable in a typical world rather than because it is optimal.
    mde_fraction_of_order_contribution: float = 0.02
    #: The lift the stub always claims to expect. Fixed, and deliberately not
    #: informed by anything in the view.
    assumed_lift_absolute: float = 0.03

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        intervention = view.interventions[self.intervention_index]
        contribution_per_order = view.observed_aov_inr * view.observed_margin
        mde = contribution_per_order * self.mde_fraction_of_order_contribution

        return [
            ExperimentProposal(
                intervention_id=intervention.intervention_id,
                hypothesis_id=f"hyp_stub_{view.world_id}",
                prediction=(
                    f"{intervention.name} lifts conversion by "
                    f"{self.assumed_lift_absolute:.1%} against control."
                ),
                reasoning=(
                    "Fixed stub policy: always test the first listed intervention. "
                    "No reasoning is performed; this exists to exercise the pipeline."
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
        ]
