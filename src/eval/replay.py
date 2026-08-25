"""Counterfactual replay: what would the other decision rules have done?

A single realized number tells you what happened, not whether the decision was
any good. Replay answers the second question by holding the world and the
experiment fixed and swapping only the rule that reads the result — so the
comparison isolates the decision rule from the luck of the draw.

The rules compared are the ones the project is actually arguing between:

* ``never_scale`` — Baseline 1. Never spends, never loses.
* ``always_scale`` — spends on everything. The "growth at any cost" strawman.
* ``point_estimate`` — scale whenever the estimate is positive. This is what most
  dashboards do, and it is the rule MarginPilot claims to beat.
* ``ci_lower_bound`` — MarginPilot's rule: scale only when the whole interval
  clears zero.
* ``oracle`` — scale iff the intervention truly pays, from ground truth. Not
  achievable; it bounds what any rule could have earned.

**Eval-only.** This module reads ``Y(0)``/``Y(1)`` (CLAUDE.md invariant 8). No
agent tool may return anything computed here.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.eval.harness import ExperimentOutcome, WorldResult

DECISION_RULES = ("never_scale", "always_scale", "point_estimate", "ci_lower_bound", "oracle")


@dataclass(frozen=True, slots=True)
class ReplayRow:
    """What one decision rule would have realized on one experiment."""

    world_id: str
    intervention_id: str
    rule: str
    scaled: bool
    realized_net_inr: float
    spend_inr: float
    correct: bool


def _would_scale(rule: str, outcome: ExperimentOutcome) -> bool:
    if rule == "never_scale":
        return False
    if rule == "always_scale":
        return True
    if rule == "point_estimate":
        return outcome.estimated_net_inr > 0
    if rule == "ci_lower_bound":
        return outcome.ci_low_inr > 0
    if rule == "oracle":
        return outcome.true_full_population_net_inr > 0
    raise ValueError(f"unknown decision rule: {rule}")


def replay_outcome(outcome: ExperimentOutcome, rule: str) -> ReplayRow:
    """Re-decide one experiment under a different rule.

    The pilot has already been paid for under every rule — the experiment was
    run. What differs is the rollout, which is where the money is.
    """
    scaled = _would_scale(rule, outcome)

    # The pilot was run and paid for under every rule that runs the experiment.
    # What the rules disagree about is the rollout, which is where the money is.
    pilot_net = outcome.pilot_net_inr if outcome.launched else 0.0
    pilot_spend = outcome.pilot_spend_inr if outcome.launched else 0.0

    # Rollout economics come from ground truth over the untested remainder, so a
    # counterfactual scale is priced at what it would really have earned.
    rollout_net = outcome.true_rollout_net_inr if scaled else 0.0
    rollout_spend = outcome.true_rollout_spend_inr if scaled else 0.0

    truly_pays = outcome.true_rollout_net_inr > 0
    return ReplayRow(
        world_id=outcome.world_id,
        intervention_id=outcome.intervention_id,
        rule=rule,
        scaled=scaled,
        realized_net_inr=pilot_net + rollout_net,
        spend_inr=pilot_spend + rollout_spend,
        correct=(scaled == truly_pays),
    )


def replay(results: list[WorldResult]) -> dict[str, list[ReplayRow]]:
    """Replay every experiment under every rule."""
    return {
        rule: [replay_outcome(o, rule) for r in results for o in r.outcomes]
        for rule in DECISION_RULES
    }


def replay_table(results: list[WorldResult]) -> str:
    """Rules ranked by realized contribution. The comparison Day 9 publishes."""
    rows = replay(results)
    lines = [
        f"{'decision rule':<18}{'realized net':>15}{'spend':>13}{'scaled':>8}{'correct':>9}",
        "-" * 63,
    ]
    for rule in DECISION_RULES:
        entries = rows[rule]
        net = sum(e.realized_net_inr for e in entries)
        spend = sum(e.spend_inr for e in entries)
        scaled = sum(1 for e in entries if e.scaled)
        correct = sum(1 for e in entries if e.correct)
        lines.append(
            f"{rule:<18}{net:>15,.0f}{spend:>13,.0f}{scaled:>8}{correct:>6}/{len(entries)}"
        )
    return "\n".join(lines)
