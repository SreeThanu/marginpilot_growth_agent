"""Q2-Q4: can REALISTIC signal support profitable targeting?

Signal budget: ONE experiment per world, sized by Baseline 5's fixed rule, cost
charged by Cycle 1 accounting. Per-segment uplift estimated from that experiment
with the project's own two-sample estimator. Ground truth scores only.
Intervention chosen by an observable rule (cheapest incentive per treated order)
so this measures TARGETING, not intervention selection.
"""
import json, sys; sys.path.insert(0, ".")
import numpy as np
from src.baselines.engine_without_llm import EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.experiment.randomize import assign
from src.experiment.registry import design_experiment_on_contribution
from src.policy.gates import PolicyLimits

E, L = EngineWithoutLLM(), PolicyLimits()
rows = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    view = merchant_view(world)
    cpo = view.observed_aov_inr * view.observed_margin
    iv = min(world.interventions, key=lambda i: i.incentive_cost_inr(view.observed_aov_inr))
    iid = iv.intervention_id
    cust = world.customers
    n = len(cust)
    segs = np.array([c.segment_id for c in cust])

    treated_val = np.empty(n); control_val = np.empty(n); net = np.empty(n)
    for k, c in enumerate(cust):
        p = truth.outcomes[c.customer_id][iid]
        inc = iv.incentive_cost_inr(p.y1.order_value_inr) if p.y1.converted else 0.0
        treated_val[k] = p.y1.contribution_inr - inc
        control_val[k] = p.y0.contribution_inr
        net[k] = p.y1.contribution_inr - p.y0.contribution_inr - inc

    d = design_experiment_on_contribution(
        experiment_id=f"tgt_{world.world_id}", world_id=world.world_id, intervention_id=iid,
        hypothesis_id="h", prediction="p", reasoning="r",
        baseline_conversion=view.observed_conversion,
        expected_effect_absolute=E.assumed_lift_absolute,
        contribution_per_incremental_order_inr=cpo,
        incentive_cost_per_treated_order_inr=iv.incentive_cost_inr(view.observed_aov_inr),
        mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
        success_condition="s", failure_condition="f", budget_inr=view.budget_inr)
    H = min(d.horizon_per_arm, int(L.max_customer_exposure_share * n) // 2)

    block = np.arange(min(2 * H, n))
    arm = np.array([assign(cust[i].customer_id, f"tgt_{world.world_id}", 2) for i in block])
    tr = block[arm == 1]; ct = block[arm == 0]
    pilot_net = float(net[tr].sum())
    pilot_spend = float(sum(
        iv.incentive_cost_inr(truth.outcomes[cust[i].customer_id][iid].y1.order_value_inr)
        for i in tr if truth.outcomes[cust[i].customer_id][iid].y1.converted))
    rest = np.arange(len(block), n)

    # per-segment estimate from the experiment only
    est, se, true_seg, errs = {}, {}, {}, []
    for s in set(segs):
        t = tr[segs[tr] == s]; c_ = ct[segs[ct] == s]
        true_seg[s] = float(net[rest][segs[rest] == s].mean()) if (segs[rest] == s).any() else 0.0
        if len(t) >= 2 and len(c_) >= 2:
            est[s] = float(treated_val[t].mean() - control_val[c_].mean())
            se[s] = float(np.sqrt(treated_val[t].var(ddof=1)/len(t)
                                  + control_val[c_].var(ddof=1)/len(c_)))
            errs.append(abs(est[s] - true_seg[s]))
        else:
            est[s] = float("nan"); se[s] = float("inf")

    pick = {s for s in est if est[s] > 0}
    # The project's own scaling discipline, applied per segment: require the CI
    # lower bound to clear zero rather than the point estimate.
    pick_ci = {s for s in est if est[s] - 1.959964 * se[s] > 0}
    sel = np.array([segs[i] in pick for i in rest])
    realistic = pilot_net + float(net[rest][sel].sum())
    sel_ci = np.array([segs[i] in pick_ci for i in rest])
    realistic_ci = pilot_net + float(net[rest][sel_ci].sum())

    everyone = float(net.sum())
    oracle_seg = float(net[np.array([true_seg.get(segs[i], 0.0) > 0 for i in range(n)])].sum())
    oracle_ind = float(net[net > 0].sum())

    rows.append(dict(world=world.world_id, iv=iid, pilot_spend=pilot_spend,
                     realistic=realistic, everyone=everyone,
                     oracle_seg=oracle_seg, oracle_ind=oracle_ind,
                     realistic_ci=realistic_ci, n_pick=len(pick),
                     n_pick_ci=len(pick_ci), n_seg=len(est),
                     mean_seg_err=float(np.mean(errs)) if errs else float("nan"),
                     true_seg_sd=float(np.std(list(true_seg.values()), ddof=1))))
    print(f"{world.world_id}  picked {len(pick)}/{len(est)} segs  "
          f"realistic=Rs.{realistic:>11,.0f}  everyone=Rs.{everyone:>11,.0f}  "
          f"oracle_seg=Rs.{oracle_seg:>10,.0f}  oracle_ind=Rs.{oracle_ind:>11,.0f}", flush=True)
    del world, truth

json.dump(rows, open("analysis/posthoc/targeting/outputs/targeting.json","w"), indent=1)
S = lambda k: sum(r[k] for r in rows)
print()
print(f"AGGREGATE over {len(rows)} dev worlds (net contribution, Rs.)")
print(f"  do-nothing                         :            0")
print(f"  treat everyone                     : {S('everyone'):>12,.0f}")
print(f"  REALISTIC targeting, CI-gated segs : {S('realistic_ci'):>12,.0f}")
print(f"  REALISTIC targeting (1 experiment) : {S('realistic'):>12,.0f}   "
      f"(experimentation cost already inside: Rs.{S('pilot_spend'):,.0f})")
print(f"  oracle SEGMENT targeting (ceiling) : {S('oracle_seg'):>12,.0f}")
print(f"  oracle INDIVIDUAL targeting (ceil) : {S('oracle_ind'):>12,.0f}")
print()
print(f"  per-segment estimation error: mean Rs.{np.nanmean([r['mean_seg_err'] for r in rows]):.2f} "
      f"vs true between-segment SD Rs.{np.nanmean([r['true_seg_sd'] for r in rows]):.2f}")
print(f"  worlds where realistic beats treat-everyone: "
      f"{sum(1 for r in rows if r['realistic']>r['everyone'])}/{len(rows)}")
print(f"  worlds where realistic > 0                : "
      f"{sum(1 for r in rows if r['realistic']>0)}/{len(rows)}")
