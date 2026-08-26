"""The MarginPilot loop. Restraint first, selection second.

    observe the merchant's situation
      -> is ANY experiment worth its cost here?      <- the primary decision
         -> no: log the skip, with reasoning, and stop. This is a success case.
         -> yes: which single question, justified against the context
      -> falsifiable hypothesis, fixed before launch
      -> contribution-powered design, feasibility-checked
      -> launch, run to the pre-committed horizon, evaluate under the posterior rule
      -> SCALE or KILL
      -> diagnose why the prediction missed
      -> revised assessment, which may itself be "nothing further is worth running"

The second cycle is the point. One cycle is a calculator: it forms a belief,
tests it, and stops. An agent has to do something with what the test taught it,
and the honest something is often to stop spending.

The loop owns no authority. Randomisation, the horizon and the scaling rule are
the engine's; this module decides what to ask and when to stop asking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from src.agent import tools
from src.agent.hypothesis import Assessment, Decision, Diagnosis, SkipDecision
from src.agent.reasoner import Reasoner
from src.agent.tools import ExperimentExecutor, ToolContext
from src.eval.contracts import MerchantView
from src.experiment.evaluator import FinalResult
from src.experiment.registry import ExperimentRegistry

#: One experiment per merchant, from the scarcity economics in docs/simulator.md
#: §4d: a pilot costs roughly 2.8x the profit pool of the world it runs in.
#: The agent may still choose to run zero.
DEFAULT_MAX_EXPERIMENTS = 1


@dataclass
class CycleRecord:
    """One pass of the loop, logged whether it spent anything or not."""

    cycle: int
    assessment: Assessment
    launched: bool = False
    experiment_id: str = ""
    horizon_per_arm: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    scaled: bool = False
    decision_reason: str = ""
    diagnosis: Diagnosis | None = None
    refusal: str = ""

    @property
    def skipped(self) -> bool:
        return self.assessment.decision is Decision.SKIP

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "decision": self.assessment.decision.value,
            "assessment": self.assessment.to_dict(),
            "launched": self.launched,
            "experiment_id": self.experiment_id,
            "horizon_per_arm": self.horizon_per_arm,
            "result": self.result,
            "scaled": self.scaled,
            "decision_reason": self.decision_reason,
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "refusal": self.refusal,
        }


@dataclass
class AgentRun:
    """Everything the agent did on one merchant, including what it declined."""

    world_id: str
    reasoner: str
    cycles: list[CycleRecord] = field(default_factory=list)

    @property
    def experiments_launched(self) -> int:
        return sum(1 for c in self.cycles if c.launched)

    @property
    def skips(self) -> int:
        return sum(1 for c in self.cycles if c.skipped)

    @property
    def scaled(self) -> int:
        return sum(1 for c in self.cycles if c.scaled)

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_id": self.world_id,
            "reasoner": self.reasoner,
            "experiments_launched": self.experiments_launched,
            "skips": self.skips,
            "scaled": self.scaled,
            "cycles": [c.to_dict() for c in self.cycles],
        }


class MarginPilotAgent:
    """Reasoner plus loop. The reasoner decides; the engine disposes."""

    def __init__(
        self,
        reasoner: Reasoner,
        *,
        max_experiments: int = DEFAULT_MAX_EXPERIMENTS,
        max_cycles: int = 2,
    ) -> None:
        self.reasoner = reasoner
        self.max_experiments = max_experiments
        self.max_cycles = max_cycles
        self.name = "marginpilot"

    def run(
        self, view: MerchantView, executor: ExperimentExecutor, *, budget_inr: float | None = None
    ) -> AgentRun:
        budget_remaining = view.budget_inr if budget_inr is None else budget_inr
        registry = ExperimentRegistry()
        run = AgentRun(world_id=view.world_id, reasoner=self.reasoner.name)
        history: list[dict[str, Any]] = []

        for cycle in range(self.max_cycles):
            ctx = ToolContext(
                view=view,
                registry=registry,
                executor=executor,
                budget_remaining_inr=budget_remaining,
                max_experiments=self.max_experiments,
                launched=[c.experiment_id for c in run.cycles if c.launched],
            )

            assessment = self.reasoner.assess(
                view,
                budget_remaining_inr=budget_remaining,
                experiments_remaining=self.max_experiments - len(ctx.launched),
                history=history,
            )
            record = CycleRecord(cycle=cycle, assessment=assessment)

            if assessment.decision is Decision.SKIP:
                # A logged, reasoned decision not to spend. The loop ends here
                # because the agent has concluded there is nothing worth asking,
                # and asking anyway would contradict its own reasoning.
                run.cycles.append(record)
                break

            hypothesis = assessment.hypothesis
            assert hypothesis is not None  # guaranteed by Assessment.__post_init__

            design = tools.propose_experiment(ctx, hypothesis, cycle=cycle)
            verdict = tools.validate_experiment(ctx, design)
            if not verdict["approved"]:
                record.refusal = "; ".join(verdict["rejections"])
                run.cycles.append(record)
                history.append(
                    {
                        "cycle": cycle,
                        "intervention_id": hypothesis.intervention_id,
                        "launched": False,
                        "refused_because": record.refusal,
                    }
                )
                continue

            experiment = tools.launch_experiment(ctx, design)
            record.launched = True
            record.experiment_id = experiment.experiment_id
            record.horizon_per_arm = experiment.horizon_per_arm

            result = tools.get_experiment_results(ctx, experiment)
            decision = tools.evaluate_experiment(ctx, result)

            if isinstance(result, FinalResult) and decision is not None:
                comparison = result.comparisons[0]
                spent = (
                    comparison.n_treatment
                    * comparison.conversion_treatment
                    * view.intervention(hypothesis.intervention_id).incentive_cost_inr(
                        view.observed_aov_inr
                    )
                )
                budget_remaining -= spent
                record.result = {
                    "conversion_control": comparison.conversion_control,
                    "conversion_treatment": comparison.conversion_treatment,
                    "conversion_lift": comparison.absolute_difference,
                    "net_contribution_inr": comparison.net_contribution_inr,
                    "probability_net_positive": comparison.probability_net_positive,
                    "projected_downside_inr": decision.projected_downside_inr,
                    "pilot_spend_inr": spent,
                }
                record.decision_reason = decision.reason

                if decision.scale:
                    tools.scale_experiment(ctx, experiment, decision)
                    record.scaled = True
                else:
                    tools.stop_experiment(ctx, experiment, reason=decision.reason)

                record.diagnosis = self.reasoner.diagnose(
                    view, hypothesis, record.result | {"scaled": record.scaled}
                )

            run.cycles.append(record)
            history.append(
                {
                    "cycle": cycle,
                    "intervention_id": hypothesis.intervention_id,
                    "prediction": hypothesis.prediction,
                    "launched": True,
                    "scaled": record.scaled,
                    "decision_reason": record.decision_reason,
                    **record.result,
                    "diagnosis": record.diagnosis.to_dict() if record.diagnosis else None,
                }
            )

        return run
