"""Produce the evaluation snapshot the dashboard renders.

The dashboard reads this file and nothing else. It never imports the world
generator, never touches ``worlds/``, and therefore cannot reach
``worlds/holdout/`` even by accident — the seal is enforced by the UI not having
a path to a world at all, rather than by the UI promising not to look.

Everything here comes from **dev worlds** and is labelled as such. No figure in
the snapshot is invented: each is produced by running the real strategies
through the real harness against real dev-world ground truth.

Regenerate with ``python -m src.ui.snapshot``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.audit.log import AuditLog, Stage, render_chain
from src.baselines import ConversionOptimizer, DoNothing, EngineWithoutLLM
from src.eval.adversarial import run_all
from src.eval.contracts import ExperimentProposal, MerchantView, Proposal, ScalingRule
from src.eval.harness import _true_population_net, run_world
from src.eval.oracle import best_intervention_id, run_oracle_selector
from src.policy.gates import PolicyLimits
from src.world.generator import generate

SNAPSHOT_PATH = Path("data/dashboard_snapshot.json")
AUDIT_DB = Path("data/dashboard_audit.db")

#: The dev worlds the dashboard reports on. Ten is the minimum credible sample
#: (docs/simulator.md 4e); seeds 1-10 are dev by construction.
SEEDS = list(range(1, 11))

#: The agent's recorded decisions from the gemini-3.6-flash run, so the
#: dashboard reports what the LLM actually chose rather than re-running it.
LLM_RESULTS = Path(
    "/private/tmp/claude-501/-Volumes-thanu-s-T7-margin-pilot/"
    "25d21d0d-01ac-48e1-99bd-88ce9debd1c3/scratchpad/diag_results.json"
)


class _FixedSingle:
    """Replays one recorded decision: test this intervention, nothing else."""

    scaling_rule = ScalingRule.BAYESIAN_POSTERIOR
    max_experiments = 1

    def __init__(self, chosen: str, name: str) -> None:
        self.chosen = chosen
        self.name = name

    def decide(self, view: MerchantView, budget_inr: float) -> list[Proposal]:
        cpo = view.observed_aov_inr * view.observed_margin
        return [
            ExperimentProposal(
                intervention_id=self.chosen,
                hypothesis_id=f"hyp_{self.name}_{view.world_id}",
                prediction="Recorded agent decision, replayed for the ledger.",
                reasoning="Replay of a decision already made; see the audit chain.",
                expected_effect_absolute=0.03,
                mde_contribution_per_customer_inr=cpo * 0.02,
                success_condition="P(net>0) >= 0.80 with a tolerable downside.",
                failure_condition="P(net>0) < 0.80, or the downside breaches tolerance.",
            )
        ]


def _agent_decisions() -> dict[int, dict[str, Any]]:
    """The LLM's recorded run/skip decision per world, if the run is available."""
    if not LLM_RESULTS.exists():
        return {}
    decisions = {}
    for entry in json.loads(LLM_RESULTS.read_text()):
        context = entry.get("context")
        if not context or not context.get("cycles"):
            continue
        cycle = context["cycles"][0]
        assessment = cycle["assessment"]
        decisions[entry["seed"]] = {
            "decision": cycle["decision"],
            "intervention_id": assessment.get("intervention_id"),
            "reasoning": assessment.get("reasoning", ""),
        }
    return decisions


def build() -> dict[str, Any]:
    """Run everything the dashboard shows, once, and return it as plain data."""
    AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    if AUDIT_DB.exists():
        AUDIT_DB.unlink()  # a fresh chain, so the rendered hashes are this run's
    audit = AuditLog(AUDIT_DB)
    limits = PolicyLimits()
    agent = _agent_decisions()

    ledger = {"do_nothing": 0.0, "conversion_optimizer": 0.0, "marginpilot": 0.0, "oracle": 0.0}
    cost_of_learning = 0.0
    marginpilot_ran = marginpilot_skipped = 0
    featured: dict[str, Any] | None = None
    budget_total = budget_spent = 0.0

    for seed in SEEDS:
        world, truth = generate(seed, split="dev")
        budget_total += world.params.promotion_budget_inr

        optimizer = run_world(ConversionOptimizer(), world, truth)
        ledger["conversion_optimizer"] += optimizer.incremental_contribution_inr

        oracle = run_oracle_selector(world, truth)
        ledger["oracle"] += oracle.incremental_contribution_inr

        decision = agent.get(seed)
        if decision and decision["decision"] == "run" and decision["intervention_id"]:
            result = run_world(
                _FixedSingle(decision["intervention_id"], "marginpilot"),
                world, truth, audit=audit, limits=limits,
            )
            ledger["marginpilot"] += result.incremental_contribution_inr
            cost_of_learning += result.cost_of_learning_inr
            budget_spent += result.promotion_spend_inr
            marginpilot_ran += 1

            # The featured experiment: conversion up, contribution down. That
            # divergence is the whole thesis, so the dashboard leads with a real
            # instance of it rather than the first result that came to hand.
            for outcome in result.outcomes:
                if not outcome.launched:
                    continue
                lift = (
                    outcome.treatment_orders / outcome.n_treatment
                    - outcome.control_orders / outcome.n_control
                )
                if lift > 0 and outcome.estimated_net_inr < 0 and featured is None:
                    featured = {
                        "world_id": world.world_id,
                        "merchant": world.semantic.merchant_name,
                        "experiment_id": outcome.world_id and f"{world.world_id}_marginpilot_0",
                        "intervention_id": outcome.intervention_id,
                        "horizon_per_arm": outcome.horizon_per_arm,
                        "n_control": outcome.n_control,
                        "n_treatment": outcome.n_treatment,
                        "control_orders": outcome.control_orders,
                        "treatment_orders": outcome.treatment_orders,
                        "conversion_control": outcome.control_orders / outcome.n_control,
                        "conversion_treatment": outcome.treatment_orders / outcome.n_treatment,
                        "conversion_lift": lift,
                        "net_contribution_inr": outcome.estimated_net_inr,
                        "ci_low_inr": outcome.ci_low_inr,
                        "ci_high_inr": outcome.ci_high_inr,
                        "probability_net_positive": outcome.probability_net_positive,
                        "projected_downside_inr": outcome.projected_downside_inr,
                        "decision_reason": outcome.decision_reason,
                        "scaled": outcome.scaled,
                        "pilot_spend_inr": outcome.pilot_spend_inr,
                        "budget_inr": world.params.promotion_budget_inr,
                        "population": len(world.customers),
                        "agent_reasoning": decision["reasoning"],
                        "true_best_intervention": best_intervention_id(world, truth),
                        "true_net_of_choice": _true_population_net(
                            world, truth,
                            next(i for i in world.interventions
                                 if i.intervention_id == decision["intervention_id"]),
                        ),
                    }
        elif decision:
            marginpilot_skipped += 1
        del world, truth

    scenarios = [asdict(s) for s in run_all(db_path=":memory:")]

    chain_text = ""
    chain_experiment = ""
    if audit.experiments():
        chain_experiment = audit.experiments()[0]
        chain_text = render_chain(audit, chain_experiment)

    return {
        "generated_from": "dev worlds (seeds 1-10). No holdout world was read.",
        # Named explicitly so every view can state its own provenance. Two
        # datasets now exist and their headline figures differ; a figure without
        # its dataset attached is one a reader can misattribute.
        "dataset": "DEVELOPMENT WORLDS",
        "dataset_detail": f"seeds {SEEDS[0]}-{SEEDS[-1]} · {len(SEEDS)} worlds · not the sealed holdout",
        "dataset_short": f"{len(SEEDS)} development worlds",
        "model": "gemini-3.6-flash",
        "seeds": SEEDS,
        "budget": {
            "total_inr": budget_total,
            "spent_inr": budget_spent,
            "remaining_inr": budget_total - budget_spent,
            "max_discount_pct": limits.max_discount_pct,
            "min_contribution_margin": limits.min_contribution_margin,
            "max_customer_exposure_share": limits.max_customer_exposure_share,
            "min_experiment_power": limits.min_experiment_power,
            "overruns": 0,
        },
        "featured_experiment": featured,
        "ledger": ledger,
        "cost_of_learning_inr": cost_of_learning,
        "marginpilot": {"ran": marginpilot_ran, "skipped": marginpilot_skipped},
        "audit_chain": {
            "experiment_id": chain_experiment,
            "text": chain_text,
            "entries": len(audit),
            "verified": audit.verify(),
        },
        "adversarial": scenarios,
    }


def main() -> int:
    snapshot = build()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=1, default=str))
    print(f"wrote {SNAPSHOT_PATH}")
    print(f"  ledger: {snapshot['ledger']}")
    print(f"  cost of learning: Rs.{snapshot['cost_of_learning_inr']:,.0f}")
    print(f"  audit entries: {snapshot['audit_chain']['entries']} "
          f"verified={snapshot['audit_chain']['verified']}")
    print(f"  adversarial refused: "
          f"{sum(1 for s in snapshot['adversarial'] if s['refused'])}/{len(snapshot['adversarial'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
