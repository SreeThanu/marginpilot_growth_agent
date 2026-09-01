"""Order-agnostic honest ceiling. Averages over all 4! test orders."""
import itertools, json, sys
sys.path.insert(0, ".")
import numpy as np
from src.baselines.engine_without_llm import DEFAULT_ORDER, EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.experiment.randomize import assign
from src.experiment.registry import design_experiment_on_contribution
from src.policy.gates import PolicyLimits

E, L = EngineWithoutLLM(), PolicyLimits()
res = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    view = merchant_view(world)
    cpo = view.observed_aov_inr * view.observed_margin
    ivs = {i.intervention_id: i for i in world.interventions}
    cust = [c.customer_id for c in world.customers]
    n = len(cust)
    # per-customer net and spend, per intervention -> prefix sums
    pre_net, pre_spend, H = {}, {}, {}
    for iid, iv in ivs.items():
        net = np.empty(n); spend = np.empty(n)
        for k, cid in enumerate(cust):
            p = truth.outcomes[cid][iid]
            c = iv.incentive_cost_inr(p.y1.order_value_inr) if p.y1.converted else 0.0
            net[k] = p.y1.contribution_inr - p.y0.contribution_inr - c
            spend[k] = c
        pre_net[iid] = np.concatenate([[0], np.cumsum(net)])
        pre_spend[iid] = np.concatenate([[0], np.cumsum(spend)])
        d = design_experiment_on_contribution(
            experiment_id=f"c3_{world.world_id}_{iid}", world_id=world.world_id,
            intervention_id=iid, hypothesis_id="h", prediction="p", reasoning="r",
            baseline_conversion=view.observed_conversion,
            expected_effect_absolute=E.assumed_lift_absolute,
            contribution_per_incremental_order_inr=cpo,
            incentive_cost_per_treated_order_inr=iv.incentive_cost_inr(view.observed_aov_inr),
            mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
            success_condition="s", failure_condition="f", budget_inr=view.budget_inr)
        H[iid] = d.horizon_per_arm
    # treatment-arm membership masks (hash assignment), as index lists
    treat = {iid: np.array([assign(cid, f"c3_{world.world_id}_{iid}", 2) == 1
                            for cid in cust]) for iid in ivs}
    tnet = {iid: np.concatenate([[0], np.cumsum(np.where(treat[iid], np.diff(pre_net[iid]), 0))])
            for iid in ivs}
    tspend = {iid: np.concatenate([[0], np.cumsum(np.where(treat[iid], np.diff(pre_spend[iid]), 0))])
              for iid in ivs}
    cap = int(L.max_customer_exposure_share * n)

    def run(order):
        cur = 0; pn = ps = 0.0; tested = []
        for iid in order:
            need = 2 * H[iid]
            if cur + need > cap or cur + need > n: break
            s = tspend[iid][cur + need] - tspend[iid][cur]
            if ps + s > view.budget_inr: break
            pn += tnet[iid][cur + need] - tnet[iid][cur]; ps += s; cur += need; tested.append(iid)
        roll = 0.0
        if tested:
            vals = {i: pre_net[i][n] - pre_net[i][cur] for i in tested}
            pick = max(vals, key=vals.get)
            if vals[pick] > 0 and ps + (pre_spend[pick][n] - pre_spend[pick][cur]) <= view.budget_inr:
                roll = vals[pick]
        return pn + roll, ps, len(tested)

    perms = [run(p) for p in itertools.permutations(list(ivs))]
    tot = [x[0] for x in perms]; cost = [x[1] for x in perms]; ks = [x[2] for x in perms]
    fixed = run(tuple(DEFAULT_ORDER))
    res.append(dict(world=world.world_id, mean=float(np.mean(tot)), best=float(np.max(tot)),
                    worst=float(np.min(tot)), mean_cost=float(np.mean(cost)),
                    mean_k=float(np.mean(ks)), fixed=fixed[0]))
    print(f"{world.world_id}  mean=Rs.{np.mean(tot):>11,.0f}  best-order=Rs.{np.max(tot):>11,.0f}  "
          f"worst=Rs.{np.min(tot):>11,.0f}  mean_k={np.mean(ks):.2f}", flush=True)
    del world, truth

json.dump(res, open("analysis/posthoc/ceiling/outputs/ceiling3.json","w"), indent=1)
print()
print(f"ORDER-AVERAGED honest ceiling : Rs.{sum(r['mean'] for r in res):,.0f}")
print(f"  mean experimentation cost   : Rs.{sum(r['mean_cost'] for r in res):,.0f}")
print(f"  mean arms tested per world  : {np.mean([r['mean_k'] for r in res]):.2f} of 4")
print(f"BEST-ORDER (oracle ordering)  : Rs.{sum(r['best'] for r in res):,.0f}")
print(f"WORST-ORDER                   : Rs.{sum(r['worst'] for r in res):,.0f}")
print(f"Baseline-5 fixed order        : Rs.{sum(r['fixed'] for r in res):,.0f}")
