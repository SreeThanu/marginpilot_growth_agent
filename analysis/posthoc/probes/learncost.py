"""Could ONE bounded experiment pay for itself, per world? Existing accounting only.

Design rule: Baseline 5's, fixed before any world was seen (MDE = 2% of
contribution per order, assumed lift 0.03). Inputs are observables.
Cost: Cycle 1's cost_of_learning = pilot incentive spend on the treatment arm.
Ground truth prices the opportunity and the realized pilot spend. It is never
used to size the experiment or to select the intervention the agent would face.
"""
import json, sys
sys.path.insert(0, ".")
from src.baselines.engine_without_llm import EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.eval.harness import _true_population_net
from src.experiment.randomize import assign
from src.experiment.registry import design_experiment_on_contribution

E = EngineWithoutLLM()
rows = json.load(open("results/cycle3_noise_neither_rep1.json"))["rows"]
runopt = {r["world_id"] for r in rows if r["true_net_of_best"] > 0}

print(f"{'world':<13}{'optimal':<13}{'available Rs':>14}{'horizon/arm':>12}"
      f"{'pilot cost Rs':>15}{'avail-cost Rs':>15}{'worth it':>10}")
print("-" * 92)
res = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    if world.world_id not in runopt:
        del world, truth; continue
    view = merchant_view(world)
    nets = {i.intervention_id: _true_population_net(world, truth, i) for i in world.interventions}
    best_id = max(nets, key=nets.get)
    iv = view.intervention(best_id)
    cpo = view.observed_aov_inr * view.observed_margin

    design = design_experiment_on_contribution(
        experiment_id=f"learncost_{world.world_id}", world_id=world.world_id,
        intervention_id=best_id, hypothesis_id="h", prediction="p", reasoning="r",
        baseline_conversion=view.observed_conversion,
        expected_effect_absolute=E.assumed_lift_absolute,
        contribution_per_incremental_order_inr=cpo,
        incentive_cost_per_treated_order_inr=iv.incentive_cost_inr(view.observed_aov_inr),
        mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
        success_condition="s", failure_condition="f",
        budget_inr=world.params.promotion_budget_inr,
    )
    horizon = design.horizon_per_arm

    # Same construction the harness uses: hash-based assignment, first `horizon`
    # of each arm, incentive charged on treated converters only.
    arms = [[], []]
    for c in world.customers:
        a = assign(c.customer_id, design.experiment_id, 2)
        if len(arms[a]) < horizon:
            arms[a].append(c.customer_id)
    spend = 0.0
    for cid in arms[1]:
        pair = truth.outcomes[cid][best_id]
        if pair.y1.converted:
            spend += iv.incentive_cost_inr(pair.y1.order_value_inr)

    avail = nets[best_id]
    diff = avail - spend
    feasible = len(arms[0]) == horizon and len(arms[1]) == horizon
    res.append(dict(world=world.world_id, best=best_id, avail=avail, horizon=horizon,
                    spend=spend, diff=diff, feasible=feasible,
                    pop=len(world.customers), budget=world.params.promotion_budget_inr))
    print(f"{world.world_id:<13}{best_id:<13}{avail:>14,.0f}{horizon:>12,}"
          f"{spend:>15,.0f}{diff:>15,.0f}{('YES' if diff>0 else 'no'):>10}"
          + ("" if feasible else "   <- population too small for the horizon"))
    del world, truth

json.dump(res, open("analysis/posthoc/probes/outputs/learncost.json","w"), indent=1)
n=len(res)
print()
print(f"A. worth it (available > learning cost) : {sum(1 for r in res if r['diff']>0 and r['feasible'])}/{n}")
print(f"B. clearly not worth it                 : {sum(1 for r in res if r['diff']<=0 and r['feasible'])}/{n}")
print(f"C. not identifiable / infeasible design : {sum(1 for r in res if not r['feasible'])}/{n}")
print()
print(f"total available on the 12: Rs.{sum(r['avail'] for r in res):,.0f}")
print(f"total pilot cost of 12 experiments: Rs.{sum(r['spend'] for r in res):,.0f}")
