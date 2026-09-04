"""Honest ceiling: perfect updating, NO foresight about which arm to test.

Testing order is Baseline 5's DEFAULT_ORDER, fixed before any world was seen.
The learner tests as many interventions as the exposure cap and budget allow, in
that fixed order, paying Cycle 1 pilot cost for each; then -- with perfect
updating among the arms it actually tested -- rolls out the best if positive.

The clairvoyant variant (free choice of which single arm to test) is computed too
and reported as a strict upper bound that no real learner can reach.
"""
import itertools, json, sys
sys.path.insert(0, ".")
from src.baselines.engine_without_llm import DEFAULT_ORDER, EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.experiment.randomize import assign
from src.experiment.registry import design_experiment_on_contribution
from src.policy.gates import PolicyLimits

E, L = EngineWithoutLLM(), PolicyLimits()

def arm_net(ids, truth, iv):
    net = spend = 0.0
    for cid in ids:
        p = truth.outcomes[cid][iv.intervention_id]
        net += p.y1.contribution_inr - p.y0.contribution_inr
        if p.y1.converted:
            c = iv.incentive_cost_inr(p.y1.order_value_inr); spend += c; net -= c
    return net, spend

rows = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    view = merchant_view(world)
    cpo = view.observed_aov_inr * view.observed_margin
    by_id = {i.intervention_id: i for i in world.interventions}
    H = {}
    for iv in world.interventions:
        d = design_experiment_on_contribution(
            experiment_id=f"c2_{world.world_id}_{iv.intervention_id}", world_id=world.world_id,
            intervention_id=iv.intervention_id, hypothesis_id="h", prediction="p", reasoning="r",
            baseline_conversion=view.observed_conversion,
            expected_effect_absolute=E.assumed_lift_absolute,
            contribution_per_incremental_order_inr=cpo,
            incentive_cost_per_treated_order_inr=iv.incentive_cost_inr(view.observed_aov_inr),
            mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
            success_condition="s", failure_condition="f", budget_inr=view.budget_inr)
        H[iv.intervention_id] = d.horizon_per_arm

    cust = [c.customer_id for c in world.customers]
    cap = int(L.max_customer_exposure_share * len(cust))

    def run(order):
        cursor = pilot_net = pilot_spend = 0.0; cursor = 0
        tested, n_tested = {}, 0
        for iid in order:
            if iid not in by_id: continue
            need = 2 * H[iid]
            if cursor + need > cap or cursor + need > len(cust): break
            block = cust[cursor:cursor + need]
            arms = [[], []]
            for cid in block:
                arms[assign(cid, f"c2_{world.world_id}_{iid}", 2)].append(cid)
            n, s = arm_net(arms[1], truth, by_id[iid])
            if pilot_spend + s > view.budget_inr: break
            cursor += need; pilot_net += n; pilot_spend += s; n_tested += 1
            tested[iid] = None
        rest = cust[cursor:]
        for iid in tested:                       # perfect updating, tested arms only
            tested[iid] = arm_net(rest, truth, by_id[iid])[0]
        roll = 0.0
        if tested:
            pick = max(tested, key=tested.get)
            if tested[pick] > 0:
                rn, rs = arm_net(rest, truth, by_id[pick])
                if pilot_spend + rs <= view.budget_inr: roll = rn
        return dict(k=n_tested, pilot_net=pilot_net, pilot_spend=pilot_spend,
                    roll_net=roll, total=pilot_net + roll)

    honest = run(DEFAULT_ORDER)
    # strict upper bound: free choice of which single arm to test
    clair = max((run((i,)) for i in by_id), key=lambda r: r["total"])
    clair = max(clair, dict(k=0, pilot_net=0.0, pilot_spend=0.0, roll_net=0.0, total=0.0),
                key=lambda r: r["total"])
    rows.append(dict(world=world.world_id, honest=honest, clair=clair))
    print(f"{world.world_id}  honest: k={honest['k']} cost=Rs.{honest['pilot_spend']:>9,.0f} "
          f"TOTAL=Rs.{honest['total']:>11,.0f}   | clairvoyant TOTAL=Rs.{clair['total']:>11,.0f}", flush=True)
    del world, truth

json.dump(rows, open("analysis/posthoc/ceiling/outputs/ceiling2.json","w"), indent=1)
h = [r["honest"] for r in rows]; c = [r["clair"] for r in rows]
print()
print(f"HONEST ceiling (no selection foresight, fixed test order):")
print(f"  cumulative experimentation cost : Rs.{sum(x['pilot_spend'] for x in h):,.0f}")
print(f"  cumulative pilot net            : Rs.{sum(x['pilot_net'] for x in h):,.0f}")
print(f"  cumulative rollout (exploit)    : Rs.{sum(x['roll_net'] for x in h):,.0f}")
print(f"  CUMULATIVE NET                  : Rs.{sum(x['total'] for x in h):,.0f}")
print(f"  mean interventions tested/world : {sum(x['k'] for x in h)/len(h):.2f} of 4")
print()
print(f"CLAIRVOYANT upper bound (free choice of arm): Rs.{sum(x['total'] for x in c):,.0f}")
