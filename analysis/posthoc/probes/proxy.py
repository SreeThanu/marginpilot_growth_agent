"""Is opportunity SIZE inferable from decision-time observables?

Proxies are declared before they are scored. Both use only MerchantView fields
plus Baseline 5's pre-committed assumed lift (0.03) and MDE rule (2% of
contribution per order) -- assumptions already in the repo, not new ones.

Ground-truth opportunity is used ONLY to score the proxies.
"""
import json, sys
sys.path.insert(0, ".")
import numpy as np
from scipy import stats
from src.baselines.engine_without_llm import EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.experiment.registry import design_experiment_on_contribution

E = EngineWithoutLLM()
truth_rows = {r["world"]: r for r in json.load(open(
    "analysis/posthoc/probes/outputs/learncost.json"))}
WORTH = ["world_20007","world_20011","world_20013","world_20015","world_20018","world_20020"]

out = []
for world, _truth in open_dev("worlds_cycle2", limit=20):
    if world.world_id not in truth_rows:
        del world; continue
    view = merchant_view(world)
    cpo = view.observed_aov_inr * view.observed_margin
    pool = view.population * view.observed_conversion * cpo          # observable
    # Cheapest intervention: the agent cannot know the best, but CAN see costs.
    ivs = sorted(view.interventions, key=lambda i: i.incentive_cost_inr(view.observed_aov_inr))
    iv = ivs[0]
    cost_per_treated = iv.incentive_cost_inr(view.observed_aov_inr)
    d = design_experiment_on_contribution(
        experiment_id=f"proxy_{world.world_id}", world_id=world.world_id,
        intervention_id=iv.intervention_id, hypothesis_id="h", prediction="p", reasoning="r",
        baseline_conversion=view.observed_conversion,
        expected_effect_absolute=E.assumed_lift_absolute,
        contribution_per_incremental_order_inr=cpo,
        incentive_cost_per_treated_order_inr=cost_per_treated,
        mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
        success_condition="s", failure_condition="f", budget_inr=view.budget_inr)
    H = d.horizon_per_arm
    # PROXY 1 (primary): expected net opportunity under Baseline 5's assumed lift.
    #   rollout gain  = remaining pop x assumed_lift x cpo
    #   rollout cost  = remaining pop x (conv+lift) x incentive
    #   pilot cost    = H x (conv+lift) x incentive
    rem = max(view.population - 2 * H, 0)
    lift = E.assumed_lift_absolute
    gain = rem * lift * cpo
    rollout_cost = rem * (view.observed_conversion + lift) * cost_per_treated
    pilot_cost = H * (view.observed_conversion + lift) * cost_per_treated
    p1 = gain - rollout_cost - pilot_cost
    out.append(dict(world=world.world_id, pool=pool, p1=p1, p2=pool,
                    budget=view.budget_inr, pop=view.population, H=H,
                    pilot_est=pilot_cost, true=truth_rows[world.world_id]["diff"],
                    worth=world.world_id in WORTH))
    del world

def spear(xs, ys):
    r = stats.spearmanr(xs, ys)
    return r.statistic, r.pvalue

for label, keys in (("the 6 worth-testing worlds", WORTH), ("all 12 profitable worlds", None)):
    rows = [r for r in out if (keys is None or r["world"] in keys)]
    print(f"\n=== {label} (n={len(rows)}) ===")
    print(f"{'world':<13}{'TRUE opp Rs':>14}{'proxy1 Rs':>14}{'proxy2 pool Rs':>17}{'p1>0?':>8}")
    for r in sorted(rows, key=lambda r: -r["true"]):
        print(f"{r['world']:<13}{r['true']:>14,.0f}{r['p1']:>14,.0f}{r['p2']:>17,.0f}"
              f"{('YES' if r['p1']>0 else 'no'):>8}")
    for nm, k in (("proxy1 (expected net opportunity)", "p1"), ("proxy2 (contribution pool)", "p2")):
        rho, p = spear([r[k] for r in rows], [r["true"] for r in rows])
        print(f"  Spearman {nm:<36} rho={rho:+.3f}  p={p:.3f}")
json.dump(out, open("analysis/posthoc/probes/outputs/proxy.json","w"), indent=1)
