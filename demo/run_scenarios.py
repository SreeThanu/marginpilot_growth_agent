"""Run the three demonstration scenarios end to end.

DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE.

No LLM is called here: each scenario supplies the proposal payload a model would
have produced, and that payload goes through the same validation a live reply
would. The point of the demo is the deterministic path, which is identical
either way.

Scenario C is the one that matters architecturally. It reaches PROMOTE only by
running a real experiment through the project's own machinery —
``design_experiment_on_contribution`` sizes it, ``assign`` would randomise it,
``evaluate`` reads it at the pre-committed horizon, ``assess_scale`` applies the
scaling rule, and ``gate_rollout`` checks the standing limits. There is no
branch in this file that can set ``PROMOTE`` directly.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from demo.fixtures import (
    FIXTURE_LABEL,
    FIXTURES,
    FixtureExecutor,
    FixtureSpec,
    build_view,
    proposal_payload,
)
from src.agent.brief import build_brief
from src.agent.decision_policy import decide_after_experiment, recommend_from_raw
from src.agent.recommendation import (
    RecommendationDecision,
    validate_proposal,
)
from src.experiment.evaluator import evaluate
from src.experiment.registry import (
    ExperimentRegistry,
    design_experiment_on_contribution,
)


#: Scenarios that carry on and actually run the pilot they recommend.
#:
#: For A and B the recommendation *is* the deliverable — the merchant is told to
#: refuse, or to test before spending — so the demo stops where the merchant
#: would. C is the scenario that demonstrates the full learning loop, so it runs
#: its experiment and takes the result back through the gates.
SCENARIOS_WITH_EXPERIMENT = frozenset({"C"})


def _comparison_payload(result: Any) -> dict[str, Any] | None:
    """The evaluator's ``ArmComparison``, flattened for serialization.

    A read, not a calculation. Every field and every property below is owned by
    ``src/experiment/evaluator.py``; this function names them and nothing else,
    so a view can show the interval and the posterior without a second
    implementation of either.
    """
    comparisons = getattr(result, "comparisons", ())
    if not comparisons:
        return None
    c = comparisons[0]
    return {
        "conversion_control": c.conversion_control,
        "conversion_treatment": c.conversion_treatment,
        "absolute_difference": c.absolute_difference,
        "difference_ci_low": c.difference_ci_low,
        "difference_ci_high": c.difference_ci_high,
        "p_value": c.p_value,
        "net_contribution_inr": c.net_contribution_inr,
        "contribution_ci_low": c.contribution_ci_low,
        "contribution_ci_high": c.contribution_ci_high,
        "contribution_se_inr": c.contribution_se_inr,
        "net_per_treated_customer_inr": c.net_per_treated_customer_inr,
        "probability_net_positive": c.probability_net_positive,
        "scale_eligible": c.scale_eligible,
    }


def run_scenario(spec: FixtureSpec, *, run_experiment: bool | None = None) -> dict[str, Any]:
    """Decide for one fixture, running the experiment path when it is required."""
    if run_experiment is None:
        run_experiment = spec.scenario_id in SCENARIOS_WITH_EXPERIMENT
    view = build_view(spec)
    brief = build_brief(view)
    raw = proposal_payload(spec)

    first = recommend_from_raw(brief, raw)
    record: dict[str, Any] = {
        "scenario": spec.scenario_id,
        "title": spec.title,
        "label": FIXTURE_LABEL,
        "initial": first.to_dict(),
        "experiment": None,
        "final": None,
    }

    if first.decision is not RecommendationDecision.RUN_EXPERIMENT_FIRST or not run_experiment:
        record["final"] = first.to_dict()
        return record

    proposal = validate_proposal(raw)
    economics = brief.economics_for(proposal.cohort_id, proposal.intervention_id)
    intervention = brief.intervention(proposal.intervention_id)

    design = design_experiment_on_contribution(
        experiment_id=f"{brief.merchant_id}_demo",
        world_id=brief.merchant_id,
        intervention_id=proposal.intervention_id,
        hypothesis_id=f"hyp_{spec.scenario_id}",
        prediction=proposal.hypothesis,
        reasoning=proposal.mechanism,
        baseline_conversion=brief.observed_conversion,
        expected_effect_absolute=proposal.expected_lift_absolute,
        contribution_per_incremental_order_inr=economics.contribution_per_order_inr,
        incentive_cost_per_treated_order_inr=economics.incentive_cost_per_order_inr,
        mde_contribution_per_customer_inr=(
            economics.contribution_per_order_inr * 0.02
        ),
        success_condition=(
            "P(net > 0) >= 0.80 and the projected 5th percentile stays above the "
            "tolerable loss."
        ),
        failure_condition="Either condition fails.",
        budget_inr=brief.budget_inr,
    )

    registry = ExperimentRegistry()
    registry.register(design)
    launched = registry.launch(design.experiment_id)

    executor = FixtureExecutor(spec)
    observations = executor.observe(launched, proposal.intervention_id)
    result = evaluate(launched, observations)

    pilot_orders = sum(o.n_converted for o in observations if o.arm == 1)
    pilot_spend = pilot_orders * economics.incentive_cost_per_order_inr

    record["experiment"] = {
        "experiment_id": launched.experiment_id,
        "horizon_per_arm": launched.horizon_per_arm,
        "intervention_id": proposal.intervention_id,
        "arms": [
            {
                "name": o.name,
                "n_assigned": o.n_assigned,
                "n_converted": o.n_converted,
                "conversion_rate": round(o.conversion_rate, 5),
                "contribution_mean_inr": round(o.contribution_mean_inr, 4),
            }
            for o in observations
        ],
        "verdict_eligible": result.verdict_eligible,
        "pilot_spend_inr": round(pilot_spend, 2),
        "depth": intervention.depth_at_observed_aov,
        # The evaluator's own comparison, read verbatim. Nothing is recomputed
        # here: a renderer that wants the interval, the p-value or the posterior
        # must be given the numbers the engine produced, not its own arithmetic
        # over the arm means.
        "comparison": _comparison_payload(result),
    }

    final = decide_after_experiment(
        brief,
        proposal,
        result,
        rollout_population=executor.population_not_in_experiment(launched),
        spent_inr=pilot_spend,
    )
    record["final"] = final.to_dict()
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(FIXTURES), default=None)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--with-experiment",
        action="store_true",
        help="run the pilot for every scenario that recommends one, not just C",
    )
    args = parser.parse_args()

    chosen = [FIXTURES[args.scenario]] if args.scenario else list(FIXTURES.values())
    override = True if args.with_experiment else None
    records = [run_scenario(spec, run_experiment=override) for spec in chosen]

    if args.json:
        print(json.dumps(records, indent=1))
        return

    for record in records:
        final = record["final"]
        print("=" * 78)
        print(f"SCENARIO {record['scenario']} — {record['title']}")
        print(f"  {record['label']}")
        print("-" * 78)
        print(f"  initial decision : {record['initial']['decision']}")
        if record["experiment"]:
            exp = record["experiment"]
            print(f"  experiment       : {exp['horizon_per_arm']:,} per arm, "
                  f"spend Rs.{exp['pilot_spend_inr']:,.0f}")
            for arm in exp["arms"]:
                print(f"      {arm['name']:<10} n={arm['n_assigned']:,} "
                      f"conv={arm['conversion_rate']:.4f} "
                      f"contribution/customer=Rs.{arm['contribution_mean_inr']:,.2f}")
        print(f"  FINAL DECISION   : {final['decision']}")
        print(f"    incremental contribution : Rs.{final['expected_incremental_contribution_inr']:,.0f}")
        print(f"    incentive cost           : Rs.{final['expected_incentive_cost_inr']:,.0f}")
        print(f"    net contribution         : Rs.{final['expected_net_contribution_inr']:,.0f}")
        if final["required_break_even_lift_absolute"] is not None:
            print(f"    break-even lift needed   : {final['required_break_even_lift_absolute']:.2%}")
        if final["binding_constraints"]:
            print(f"    binding constraint       : {', '.join(final['binding_constraints'])}")
        if final["unresolved"]:
            print(f"    unresolved               : {', '.join(final['unresolved'])}")
        print(f"    gates passed             : {', '.join(final['gates_passed']) or '-'}")
        print(f"    rationale: {final['rationale']}")
    print("=" * 78)


if __name__ == "__main__":
    main()
