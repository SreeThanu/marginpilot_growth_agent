"""Baseline 3 — the conversion optimizer. The naive-AI baseline.

Runs proper experiments with proper randomization and a proper fixed horizon,
then reads the wrong number: it scales whenever the confidence interval on
*conversion* clears zero, and never looks at contribution.

This is the most important baseline to get right, because it is not a strawman.
It is statistically rigorous. Its failure is economic, not methodological, and
that is precisely the failure the project exists to demonstrate — a campaign can
lift conversion unambiguously and still destroy contribution, because the
discount is paid to everyone who converts rather than only to those the discount
persuaded.

Intervention choice is the naive one too: pick whichever offer is deepest, since
a deeper discount produces a larger conversion lift. It is the right move for the
metric it is optimising and the wrong one for the merchant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.eval.contracts import ExperimentProposal, MerchantView, Proposal, ScalingRule


@dataclass(frozen=True, slots=True)
class ConversionOptimizer:
    name: str = "3_conversion_optimizer"
    scaling_rule: ScalingRule = ScalingRule.CONVERSION_LIFT
    max_experiments: int = 1
    mde_fraction_of_order_contribution: float = 0.02
    assumed_lift_absolute: float = 0.03

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        # Deepest offer first: more discount, more conversion.
        deepest = max(
            view.interventions,
            key=lambda i: i.effective_depth(view.observed_aov_inr),
        )
        contribution_per_order = view.observed_aov_inr * view.observed_margin

        return [
            ExperimentProposal(
                intervention_id=deepest.intervention_id,
                hypothesis_id=f"hyp_conv_{view.world_id}",
                prediction=(
                    f"{deepest.name} produces a statistically significant lift in "
                    "conversion against control."
                ),
                reasoning=(
                    "Deepest available discount maximises expected conversion. "
                    "Contribution is not considered."
                ),
                expected_effect_absolute=self.assumed_lift_absolute,
                mde_contribution_per_customer_inr=(
                    contribution_per_order * self.mde_fraction_of_order_contribution
                ),
                success_condition="Lower bound of the CI on conversion lift is above zero.",
                failure_condition="CI on conversion lift contains or lies below zero.",
            )
        ]
