"""Run MarginPilot on dev worlds and report what it selected, and why that matched.

The Cycle 2 gate. §4j of ``docs/simulator.md`` commits in advance that the new
sealed holdout is opened **only if** the two fixes changed selection behaviour on
dev worlds. This is the measurement that decides that, so it runs on dev worlds
and passes ``final_eval=False`` — it cannot reach the sealed split.

Three numbers come out, and the third is the one that matters most:

* **selection accuracy** — how often the chosen intervention is the one with the
  highest true population net contribution.
* **intervention mix** — §4j predicts ``int_shipping`` falls and ``int_bundle``
  rises.
* **history-match rate** — how often the choice is simply the best-performing
  entry in the supplied history. §4j records the risk that Fix B replaces
  reasoning with table-reading; if accuracy and history-match are the same
  number, that is what happened, and it is the finding.

Run with ``python -m src.eval.devrun --worlds 20``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.agent.reasoner import RateLimitExceededError, ReasonerError
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.eval.executor import GroundTruthExecutor
from src.eval.harness import _true_population_net
from src.eval.oracle import best_intervention_id

#: Attempts per world before it is recorded as an error. Bounded so a persistent
#: failure is reported rather than retried forever.
MAX_ATTEMPTS = 3


def _best_in_history(view) -> str | None:
    """The intervention the merchant's own past campaigns favour, noise included."""
    if not view.history:
        return None
    return max(view.history, key=lambda h: h.net_per_treated_customer_inr).intervention_id


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.devrun", description=__doc__)
    parser.add_argument("--worlds", type=int, default=20)
    parser.add_argument("--root", type=Path, default=Path("worlds"))
    parser.add_argument("--out", type=Path, default=Path("results/cycle2_dev.json"))
    parser.add_argument(
        "--arm",
        choices=("both", "break_even_only", "history_only", "neither"),
        default="both",
        help="which Cycle 2 fixes the agent gets. 'neither' is the Cycle 1 prompt "
             "and is the control: without it, a change measured on a fresh corpus "
             "cannot be attributed to the fixes rather than to the worlds.",
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=1,
        help="run the arm this many times over the same worlds, changing nothing "
             "between runs. Measures instrument noise: the spread across "
             "replicates is what an arm's metric does when the arm does not.",
    )
    parser.add_argument(
        "--replicate-offset",
        type=int,
        default=0,
        help="number replicates from here, so an interrupted replication can be "
             "continued without renumbering or discarding what already ran.",
    )
    parser.add_argument("--heuristic", action="store_true",
                        help="use the offline stand-in instead of the model (pipeline check only)")
    args = parser.parse_args()

    from src.agent.agent import MarginPilotAgent
    if args.heuristic:
        from src.agent.reasoner import HeuristicReasoner as Reasoner
    else:
        from src.agent.reasoner import GeminiReasoner as Reasoner
    arms = {
        "both": (True, True),
        "break_even_only": (True, False),
        "history_only": (False, True),
        "neither": (False, False),
    }
    break_even, merchant_history = arms[args.arm]
    reasoner = (
        Reasoner()
        if args.heuristic
        else Reasoner(break_even=break_even, merchant_history=merchant_history)
    )
    agent = MarginPilotAgent(reasoner, max_experiments=1, max_cycles=2)
    print(f"arm={args.arm}  break_even={break_even}  merchant_history={merchant_history}\n")

    out_paths = []
    for rep in range(args.replicates):
        out = (
            args.out
            if args.replicates == 1
            else args.out.with_name(
                f"{args.out.stem}_rep{rep + 1 + args.replicate_offset}{args.out.suffix}"
            )
        )
        if args.replicates > 1:
            print(f"\n--- replicate {rep + 1 + args.replicate_offset} "
                  f"(this run: {rep + 1}/{args.replicates}) ---", flush=True)
        _run_once(agent, args, out)
        out_paths.append(out)
    if len(out_paths) > 1:
        print(f"\n{len(out_paths)} replicates written; analyse with "
              f"python -m src.eval.power")
    return 0


def _run_once(agent, args, out: Path) -> None:
    """One pass over the worlds. A replicate differs from its siblings only in
    when it ran — same code, same worlds, same prompts."""
    rows: list[dict] = []
    errors: list[dict] = []

    for world, truth in open_dev(args.root, limit=args.worlds):
        view = merchant_view(world)

        # A hard API failure is an infrastructure event, not a decision. Retry it
        # a bounded number of times; if it will not complete, record the world as
        # an error and carry on rather than discarding a multi-hour replication
        # for one bad call. The retry is triggered only by the exception type --
        # never by what the model decided -- so it cannot select for outcomes.
        assessment = None
        last_error = ""
        for attempt in range(MAX_ATTEMPTS):
            try:
                run = agent.run(view, GroundTruthExecutor(world, truth, view.observed_margin))
                assessment = run.cycles[0].assessment
                break
            except (ReasonerError, RateLimitExceededError) as exc:
                last_error = str(exc)
                print(f"    {world.world_id} attempt {attempt + 1}/{MAX_ATTEMPTS} "
                      f"failed: {exc}", flush=True)
        if assessment is None:
            errors.append({"world_id": world.world_id, "error": last_error})
            rows.append({
                "world_id": world.world_id, "decision": "error", "chosen": None,
                "truth_best": best_intervention_id(world, truth), "history_best": None,
                "true_net_of_choice": 0.0, "true_net_of_best": 0.0, "assessment": {},
            })
            print(f"{world.world_id}  ERROR after {MAX_ATTEMPTS} attempts: {last_error}",
                  flush=True)
            del world, truth
            continue

        chosen = (
            assessment.hypothesis.intervention_id
            if assessment.decision.value == "run" and assessment.hypothesis
            else None
        )
        truth_best = best_intervention_id(world, truth)
        rows.append(
            {
                "world_id": world.world_id,
                "decision": assessment.decision.value,
                "chosen": chosen,
                "truth_best": truth_best,
                "history_best": _best_in_history(view),
                "true_net_of_choice": (
                    _true_population_net(
                        world, truth,
                        next(i for i in world.interventions if i.intervention_id == chosen),
                    ) if chosen else 0.0
                ),
                "true_net_of_best": _true_population_net(
                    world, truth,
                    next(i for i in world.interventions if i.intervention_id == truth_best),
                ),
                # The full answer, so a reader can check the break-even
                # arithmetic Fix A asked for against the choice it produced.
                "assessment": assessment.to_dict(),
            }
        )
        print(f"{world.world_id}  {rows[-1]['decision']:<5} "
              f"chose={chosen or '-':<14} truth={truth_best:<14} "
              f"history={rows[-1]['history_best'] or '-'}", flush=True)
        del world, truth

    # Errored worlds are excluded from every denominator and reported in their
    # own right. Substituting a decision for them would be fabrication.
    scored = [r for r in rows if r["decision"] != "error"]
    ran = [r for r in scored if r["decision"] == "run"]
    correct = [r for r in ran if r["chosen"] == r["truth_best"]]
    matched_history = [r for r in ran if r["chosen"] == r["history_best"]]
    summary = {
        "arm": args.arm,
        "worlds": len(scored),
        "errors": len(errors),
        "error_detail": errors,
        "ran": len(ran),
        "skipped": len(scored) - len(ran),
        "selection_accuracy": f"{len(correct)}/{len(ran)}",
        "history_match_rate": f"{len(matched_history)}/{len(ran)}",
        # Reasoning beyond table-reading: right answer, and the history did not
        # already point at it. This is the number Fix B cannot manufacture.
        "correct_where_history_disagreed": sum(
            1 for r in ran if r["chosen"] == r["truth_best"] and r["history_best"] != r["truth_best"]
        ),
        "mix": dict(Counter(r["chosen"] for r in ran)),
        "net_of_choices_inr": sum(r["true_net_of_choice"] for r in ran),
        "net_if_always_best_inr": sum(r["true_net_of_best"] for r in ran),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, default=str))

    print("\n" + "=" * 62)
    for key, value in summary.items():
        print(f"{key:<32}{value}")
    print(f"written to {out}")


if __name__ == "__main__":
    raise SystemExit(main())
