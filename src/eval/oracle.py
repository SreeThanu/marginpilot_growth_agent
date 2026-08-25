"""The oracle selector: an upper bound on what experiment *selection* is worth.

This is a diagnostic, not a strategy and not a baseline. It cheats — it reads
``Y(0)``/``Y(1)`` to pick which intervention to test — and so it lives in
``src/eval/`` where ground truth is allowed, and can never be run as a
competitor (CLAUDE.md invariant 8).

**Why it exists.** Day 4's replay showed the cost of learning is the binding
constraint: the stub spent Rs.247,710 to learn and its single winner almost
exactly repaid it, landing at -Rs.929 against a do-nothing floor of zero. That
raises a question that has to be answered before building the agent rather than
after: *is there enough headroom in choosing well to pay for the learning at
all?*

The oracle selector answers it. It knows in advance which single intervention in
each world is most likely to pay, tests only that one, and then decides on the
same CI-lower-bound rule as everyone else. It is not achievable — no agent can
know this — but it bounds what any amount of reasoning about *which* experiment
to run could possibly be worth.

Reading the result:

* If the oracle selector barely beats Baseline 1, selection cannot pay for
  learning, and no LLM can rescue it. Better to know now than on Day 9.
* If it beats Baseline 1 clearly, that gap is the headroom the agent competes
  for, and Baseline 5 versus MarginPilot measures how much of it semantic
  reasoning actually captures.

Note the oracle still has to *pay* for its experiment and can still be refused
by the CI rule: perfect selection does not confer perfect information, only a
perfect starting guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.eval.contracts import ExperimentProposal, MerchantView, Proposal, ScalingRule
from src.eval.harness import WorldResult, _true_population_net, run_world
from src.world.schema import GroundTruth, World


@dataclass(frozen=True, slots=True)
class _OracleSelector:
    """Proposes exactly one experiment: the intervention that truly pays best.

    Constructed per world by :func:`run_oracle_selector`, which is the only
    thing allowed to tell it the answer.
    """

    chosen_intervention_id: str
    name: str = "oracle_selector"
    scaling_rule: ScalingRule = ScalingRule.CI_LOWER_BOUND
    mde_fraction_of_order_contribution: float = 0.02
    assumed_lift_absolute: float = 0.03

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        contribution_per_order = view.observed_aov_inr * view.observed_margin
        intervention = view.intervention(self.chosen_intervention_id)
        return [
            ExperimentProposal(
                intervention_id=self.chosen_intervention_id,
                hypothesis_id=f"hyp_oracle_{view.world_id}",
                prediction=(
                    f"{intervention.name} produces incremental contribution whose CI "
                    "lower bound clears zero."
                ),
                reasoning=(
                    "Selection is oracular: this intervention is known in advance to "
                    "be the best available in this world. Diagnostic only."
                ),
                expected_effect_absolute=self.assumed_lift_absolute,
                mde_contribution_per_customer_inr=(
                    contribution_per_order * self.mde_fraction_of_order_contribution
                ),
                success_condition="CI lower bound on incremental contribution above zero.",
                failure_condition="CI contains or lies below zero.",
            )
        ]


def best_intervention_id(world: World, truth: GroundTruth) -> str:
    """The intervention with the highest true population net contribution.

    Ground truth. Never exposed to a strategy, and never returned by a tool.
    """
    return max(
        world.interventions,
        key=lambda i: _true_population_net(world, truth, i),
    ).intervention_id


def run_oracle_selector(world: World, truth: GroundTruth) -> WorldResult:
    """Run the oracle selector against one world.

    Selection is oracular; measurement is not. The experiment is still paid for,
    still run to its pre-committed horizon, and still read on the same
    CI-lower-bound rule — so a world whose best intervention is only marginally
    profitable can still, correctly, fail to clear the bar.
    """
    selector = _OracleSelector(chosen_intervention_id=best_intervention_id(world, truth))
    result = run_world(selector, world, truth)
    result.strategy = "oracle_selector"
    return result
