"""``python -m src.eval`` — the final evaluation. What ``make eval`` runs.

CLAUDE.md invariant 4: the holdout worlds are opened once, by ``make eval``.
This is that entry point, and every read goes through the guard with an explicit
``final_eval=True``.

By default this runs the five deterministic strategies plus the oracle
diagnostic. **MarginPilot itself is opt-in** (``--with-agent``): it needs
credentials and costs money per world, and a judge reproducing the deterministic
half should not be forced into an API bill to do it. The recorded agent run is
in ``data/holdout_results.json`` and is what the README reports.

Writes a JSON summary to ``results/`` and prints the table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.audit.log import AuditLog
from src.baselines import (
    ConversionOptimizer,
    DoNothing,
    EngineWithoutLLM,
    LearnOnly,
    RuleBasedMarketer,
)
from src.eval.harness import run_world
from src.eval.holdout import StrategySummary, calibration_entry, open_holdout, truth_table
from src.eval.oracle import run_oracle_selector

RESULTS_DIR = Path("results")
AUDIT_DB = Path("data/holdout_eval_audit.db")

DETERMINISTIC = (
    DoNothing(),
    LearnOnly(),
    RuleBasedMarketer(),
    ConversionOptimizer(),
    EngineWithoutLLM(),
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval", description=__doc__)
    parser.add_argument(
        "--with-agent",
        action="store_true",
        help="also run MarginPilot (needs GEMINI_API_KEY; makes one API call per world)",
    )
    parser.add_argument("--out", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--worlds-root",
        type=Path,
        default=Path("worlds"),
        help="corpus to evaluate. Cycle 2 is a labelled follow-up on its own "
             "corpus (worlds_cycle2), not a replacement for the Cycle 1 result.",
    )
    args = parser.parse_args()

    agent = None
    if args.with_agent:
        # Imported lazily: the deterministic path must not require an LLM client
        # or credentials to be present at all.
        from src.agent.agent import MarginPilotAgent
        from src.agent.reasoner import GeminiReasoner
        from src.eval.contracts import merchant_view
        from src.eval.executor import GroundTruthExecutor

        agent = MarginPilotAgent(GeminiReasoner(), max_experiments=1, max_cycles=2)

    AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)
    if AUDIT_DB.exists():
        AUDIT_DB.unlink()
    audit = AuditLog(AUDIT_DB)

    summaries = {s.name: StrategySummary(s.name) for s in DETERMINISTIC}
    summaries["oracle_selector"] = StrategySummary("oracle_selector")
    calibration: list[dict] = []
    truths: dict[str, dict[str, float]] = {}
    agent_log: list[dict] = []
    worlds = 0

    print("Opening the sealed holdout worlds. This happens once.\n", flush=True)
    for world, truth in open_holdout(args.worlds_root):
        worlds += 1
        truths[world.world_id] = truth_table(world, truth)
        print(f"[{worlds}] {world.world_id}", flush=True)

        for strategy in DETERMINISTIC:
            result = run_world(strategy, world, truth, audit=audit)
            summaries[strategy.name].absorb(result)
            calibration.extend(calibration_entry(result, world, truth))

        summaries["oracle_selector"].absorb(run_oracle_selector(world, truth))

        if agent is not None:
            from src.eval.contracts import merchant_view
            from src.eval.executor import GroundTruthExecutor

            view = merchant_view(world)
            run = agent.run(view, GroundTruthExecutor(world, truth, view.observed_margin))
            cycle = run.cycles[0]
            agent_log.append(
                {
                    "world_id": world.world_id,
                    "decision": cycle.assessment.decision.value,
                    "intervention_id": (
                        cycle.assessment.hypothesis.intervention_id
                        if cycle.assessment.decision.value == "run"
                        else None
                    ),
                    "assessment": cycle.assessment.to_dict(),
                }
            )
            print(f"    marginpilot: {agent_log[-1]['decision']}", flush=True)

    if worlds == 0:
        print(
            "No holdout worlds found. Generate the corpus first:\n\n    make worlds\n",
            file=sys.stderr,
        )
        return 1

    payload = {
        "worlds": worlds,
        "summaries": {k: v.to_dict() for k, v in summaries.items()},
        "calibration": calibration,
        "truths": truths,
        "agent_log": agent_log,
        "audit_entries": len(audit),
        "audit_chain_intact": audit.verify(),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    destination = args.out / f"holdout_evaluation_{args.worlds_root.name}.json"
    destination.write_text(json.dumps(payload, indent=1, default=str))

    header = f"{'strategy':<24}{'realized net':>15}{'spend':>13}{'exp':>6}{'scaled':>8}"
    print("\n" + "=" * len(header))
    print(f"HOLDOUT EVALUATION — {worlds} sealed worlds")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for name, summary in summaries.items():
        print(
            f"{name:<24}{summary.realized_net_inr:>15,.0f}"
            f"{summary.promotion_spend_inr:>13,.0f}"
            f"{summary.experiments_run:>6}{summary.experiments_scaled:>8}"
        )
    print("-" * len(header))
    print(f"audit: {len(audit)} entries, chain intact: {audit.verify()}")
    print(f"written to {destination}")
    if agent is None:
        print(
            "\nMarginPilot was not run (pass --with-agent, needs GEMINI_API_KEY).\n"
            "The recorded agent run is in data/holdout_results.json and is what the\n"
            "README reports."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
