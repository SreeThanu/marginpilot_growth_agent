"""The final evaluation. Opens the sealed holdout worlds, once.

CLAUDE.md invariant 4: the 20 holdout worlds are read exactly once, at final
evaluation. Everything here goes through ``src/eval/guard.py`` with an explicit
``final_eval=True``, so ``git log -S final_eval`` shows every occasion the seal
was opened and when. Regenerating the worlds from their seeds in memory would
produce identical data while leaving no trace — which is why this loads them
from disk instead.

Nothing in this module may be run before the code is frozen. Results produced
here are reported as measured, favourable or not (invariant 9), and no
parameter, prompt, threshold or rule may change in response to them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np

from src.audit.log import AuditLog
from src.eval.contracts import ScalingRule
from src.eval.guard import iter_world_paths
from src.eval.harness import WorldResult, _true_population_net, run_world
from src.eval.oracle import best_intervention_id, run_oracle_selector
from src.eval.replay import DECISION_RULES, replay
from src.world.persistence import load_ground_truth, load_world
from src.world.schema import GroundTruth, World


def open_holdout(root: str | Path = "worlds") -> Iterator[tuple[World, GroundTruth]]:
    """Yield the sealed worlds, one at a time.

    The only function in the project that passes ``final_eval=True``. One world
    resident at a time — 20 of these do not fit in 8GB together.
    """
    for path in iter_world_paths("holdout", root=root, final_eval=True):
        world = load_world(path, final_eval=True)
        truth = load_ground_truth(path, final_eval=True)
        yield world, truth
        del world, truth


@dataclass
class StrategySummary:
    """One strategy's holdout performance. Every field is a measured count."""

    name: str
    realized_net_inr: float = 0.0
    promotion_spend_inr: float = 0.0
    cost_of_learning_inr: float = 0.0
    incremental_conversion: list[float] = field(default_factory=list)
    incremental_revenue_inr: float = 0.0
    experiments_run: int = 0
    experiments_scaled: int = 0
    untested_campaigns: int = 0
    refusals: int = 0
    false_positives_scaled: int = 0
    true_positives_missed: int = 0
    budget_overruns: int = 0
    policy_violations: int = 0
    estimation_errors: list[float] = field(default_factory=list)
    per_world_net: dict[str, float] = field(default_factory=dict)

    def absorb(self, result: WorldResult) -> None:
        self.realized_net_inr += result.incremental_contribution_inr
        self.promotion_spend_inr += result.promotion_spend_inr
        self.cost_of_learning_inr += result.cost_of_learning_inr
        self.incremental_revenue_inr += result.incremental_revenue_inr
        if result.incremental_conversion:
            self.incremental_conversion.append(result.incremental_conversion)
        self.experiments_run += result.experiments_launched
        self.experiments_scaled += result.experiments_scaled
        self.untested_campaigns += result.untested_campaigns
        self.refusals += result.experiments_refused
        self.false_positives_scaled += result.false_positives_scaled
        self.true_positives_missed += result.true_positives_killed
        self.budget_overruns += int(result.budget_overrun)
        # A policy violation is a spend the gate should have stopped. The gate
        # binds on both pilot and rollout, so any overrun is one by definition.
        self.policy_violations += int(result.budget_overrun)
        if result.estimation_error_inr:
            self.estimation_errors.append(result.estimation_error_inr)
        self.per_world_net[result.world_id] = result.incremental_contribution_inr

    @property
    def romi(self) -> float:
        if self.promotion_spend_inr <= 0:
            return 0.0
        return (self.realized_net_inr + self.promotion_spend_inr) / self.promotion_spend_inr

    @property
    def mean_incremental_conversion(self) -> float:
        return float(np.mean(self.incremental_conversion)) if self.incremental_conversion else 0.0

    @property
    def mean_estimation_error_inr(self) -> float:
        return float(np.mean(self.estimation_errors)) if self.estimation_errors else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "realized_net_inr": self.realized_net_inr,
            "promotion_spend_inr": self.promotion_spend_inr,
            "cost_of_learning_inr": self.cost_of_learning_inr,
            "incremental_conversion": self.mean_incremental_conversion,
            "incremental_revenue_inr": self.incremental_revenue_inr,
            "romi": self.romi,
            "experiments_run": self.experiments_run,
            "experiments_scaled": self.experiments_scaled,
            "untested_campaigns": self.untested_campaigns,
            "refusals": self.refusals,
            "false_positives_scaled": self.false_positives_scaled,
            "true_positives_missed": self.true_positives_missed,
            "budget_overruns": self.budget_overruns,
            "policy_violations": self.policy_violations,
            "mean_estimation_error_inr": self.mean_estimation_error_inr,
            "per_world_net": self.per_world_net,
        }


def truth_table(world: World, truth: GroundTruth) -> dict[str, float]:
    """True population net contribution for every intervention in a world.

    Ground truth, used to score decisions after they are made. Never shown to a
    strategy.
    """
    return {
        i.intervention_id: _true_population_net(world, truth, i)
        for i in world.interventions
    }


def calibration_entry(
    result: WorldResult, world: World, truth: GroundTruth
) -> list[dict[str, Any]]:
    """Did the pre-committed prediction land inside the realized interval?

    Hypothesis calibration. A system that predicts confidently and is wrong as
    often as it is right has learned nothing, however good its prose reads —
    and this is checkable only because the prediction was fixed before launch
    and fingerprinted (invariant 7).
    """
    rows = []
    for outcome in result.outcomes:
        if not outcome.launched or outcome.untested or not outcome.n_treatment:
            continue
        realized_per_customer = outcome.true_rollout_net_inr / max(
            len(world.customers) - outcome.n_control - outcome.n_treatment, 1
        )
        estimated_per_customer = outcome.estimated_net_inr / outcome.n_treatment
        ci_low = outcome.ci_low_inr / outcome.n_treatment
        ci_high = outcome.ci_high_inr / outcome.n_treatment
        rows.append(
            {
                "world_id": result.world_id,
                "intervention_id": outcome.intervention_id,
                "estimated_per_customer_inr": estimated_per_customer,
                "true_per_customer_inr": realized_per_customer,
                "ci_low_per_customer_inr": ci_low,
                "ci_high_per_customer_inr": ci_high,
                "truth_inside_interval": ci_low <= realized_per_customer <= ci_high,
                "absolute_error_inr": abs(estimated_per_customer - realized_per_customer),
                "scaled": outcome.scaled,
            }
        )
    return rows
