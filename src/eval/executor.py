"""Feeds the agent observed experiment data, and nothing else.

The agent asks for results through :class:`~src.agent.tools.ExperimentExecutor`;
this is the implementation that knows the world. It reads ``Y(0)``/``Y(1)`` —
which is why it lives in ``src/eval/`` (CLAUDE.md invariant 8) — and returns
only what a merchant's own reporting would contain: per-arm counts and
per-customer contribution, one outcome per customer.

The agent holds this object behind a Protocol with two methods. It cannot reach
the truth through either, and it never sees the object's fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.economics.contribution import customer_contribution_inr, summarise_arm
from src.experiment.evaluator import ArmObservation
from src.experiment.randomize import assign
from src.experiment.registry import LaunchedExperiment
from src.world.schema import GroundTruth, World


@dataclass(frozen=True, slots=True)
class GroundTruthExecutor:
    """Runs an experiment against a world and reports what was observed."""

    world: World
    truth: GroundTruth
    margin: float

    def _arms(self, experiment: LaunchedExperiment) -> list[list[str]]:
        arms: list[list[str]] = [[] for _ in experiment.design.arms]
        horizon = experiment.horizon_per_arm
        for customer in self.world.customers:
            arm = assign(customer.customer_id, experiment.experiment_id, experiment.n_arms)
            if len(arms[arm]) < horizon:
                arms[arm].append(customer.customer_id)
        return arms

    def observe(
        self, experiment: LaunchedExperiment, intervention_id: str
    ) -> Sequence[ArmObservation]:
        intervention = next(
            i for i in self.world.interventions if i.intervention_id == intervention_id
        )
        observations = []
        for index, (name, ids) in enumerate(zip(experiment.design.arms, self._arms(experiment))):
            treated = index > 0
            orders = 0
            contributions: list[float] = []
            for customer_id in ids:
                pair = self.truth.outcomes[customer_id][intervention_id]
                outcome = pair.y1 if treated else pair.y0
                incentive = (
                    intervention.incentive_cost_inr(outcome.order_value_inr)
                    if (treated and outcome.converted)
                    else 0.0
                )
                if outcome.converted:
                    orders += 1
                contributions.append(
                    customer_contribution_inr(
                        converted=outcome.converted,
                        order_value_inr=outcome.order_value_inr,
                        contribution_margin=self.margin,
                        incentive_inr=incentive,
                    )
                )
            summary = summarise_arm(contributions, orders)
            observations.append(
                ArmObservation(
                    index, name, len(ids), orders,
                    contribution_mean_inr=summary.mean_inr,
                    contribution_sd_inr=summary.sd_inr,
                )
            )
        return observations

    def population_not_in_experiment(self, experiment: LaunchedExperiment) -> int:
        used = sum(len(a) for a in self._arms(experiment))
        return max(len(self.world.customers) - used, 0)
