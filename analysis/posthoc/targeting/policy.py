"""Net contribution of the FROZEN observable-based targeting policy on held-out worlds.

Threshold chosen on TRAIN (20021-20050), frozen, applied to TEST (20051-20080).
Nothing is refit or retuned against TEST. Intervention held fixed per world by an
observable rule (cheapest incentive per treated order), so this measures targeting
alone. Ground truth scores only.
"""
import sys; sys.path.insert(0, ".")
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from src.baselines.engine_without_llm import EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.experiment.randomize import assign
from src.experiment.registry import design_experiment_on_contribution
from src.policy.gates import PolicyLimits

E, L = EngineWithoutLLM(), PolicyLimits()

def load(lo, hi):
    out = []
    for w, t in open_dev("worlds_cycle2", limit=80):
        wid = int(w.world_id.split("_")[1])
        if not (lo <= wid <= hi):
            del w, t; continue
        v = merchant_view(w)
        iv = min(w.interventions, key=lambda i: i.incentive_cost_inr(v.observed_aov_inr))
        recs = {c.customer_id: c for c in v.customers}
        X, y, seg, ids = [], [], [], []
        for c in w.customers:
            r = recs[c.customer_id]
            p_ = t.outcomes[c.customer_id][iv.intervention_id]
            inc = iv.incentive_cost_inr(p_.y1.order_value_inr) if p_.y1.converted else 0.0
            y.append(p_.y1.contribution_inr - p_.y0.contribution_inr - inc)
            X.append([r.tenure_days, r.orders_last_90d, r.days_since_last_order,
                      np.log1p(r.historical_aov_inr)])
            seg.append(r.segment_id); ids.append(c.customer_id)
        out.append(dict(world=w.world_id, X=np.array(X, float), y=np.array(y, float),
                        seg=np.array(seg), ids=ids, view=v, iv=iv,
                        n=len(w.customers),
                        aovs={c.customer_id: t.outcomes[c.customer_id][iv.intervention_id]
                              for c in w.customers}))
        del w, t
    return out

train, test = load(20021, 20050), load(20051, 20080)
Xtr = np.vstack([d["X"] for d in train])
ytr = np.concatenate([(d["y"] - d["y"].mean()) / (d["y"].std() + 1e-9) for d in train])
model = GradientBoostingRegressor(random_state=0).fit(Xtr, ytr)

# threshold chosen on TRAIN only
grid = [0.05, 0.10, 0.20, 0.30, 0.50, 0.75, 1.00]
tr_net = {}
for k in grid:
    s = 0.0
    for d in train:
        p = model.predict(d["X"]); cut = np.quantile(p, 1 - k)
        s += float(d["y"][p >= cut].sum())
    tr_net[k] = s
k_star = max(tr_net, key=tr_net.get)
print("TRAIN net by treated fraction (threshold selection, TRAIN only):")
for k in grid:
    print(f"   top {k:>4.0%}: Rs.{tr_net[k]:>13,.0f}" + ("   <- frozen" if k == k_star else ""))
print(f"\nFROZEN treated fraction k* = {k_star:.0%}\n")

# ---- evaluate on TEST ---------------------------------------------------
frozen = everyone = oracle_ind = 0.0
seg_target = seg_cost = 0.0
for d in test:
    p = model.predict(d["X"]); cut = np.quantile(p, 1 - k_star)
    frozen += float(d["y"][p >= cut].sum())
    everyone += float(d["y"].sum())
    oracle_ind += float(d["y"][d["y"] > 0].sum())

    # realistic segment targeting, one experiment, same accounting as before
    v, iv = d["view"], d["iv"]
    cpo = v.observed_aov_inr * v.observed_margin
    des = design_experiment_on_contribution(
        experiment_id=f"pol_{d['world']}", world_id=d["world"], intervention_id=iv.intervention_id,
        hypothesis_id="h", prediction="p", reasoning="r",
        baseline_conversion=v.observed_conversion, expected_effect_absolute=E.assumed_lift_absolute,
        contribution_per_incremental_order_inr=cpo,
        incentive_cost_per_treated_order_inr=iv.incentive_cost_inr(v.observed_aov_inr),
        mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
        success_condition="s", failure_condition="f", budget_inr=v.budget_inr)
    H = min(des.horizon_per_arm, int(L.max_customer_exposure_share * d["n"]) // 2)
    blk = np.arange(min(2 * H, d["n"]))
    arm = np.array([assign(d["ids"][i], f"pol_{d['world']}", 2) for i in blk])
    tr_i, ct_i = blk[arm == 1], blk[arm == 0]
    treated_val = np.array([d["aovs"][d["ids"][i]].y1.contribution_inr
                            - (iv.incentive_cost_inr(d["aovs"][d["ids"][i]].y1.order_value_inr)
                               if d["aovs"][d["ids"][i]].y1.converted else 0.0) for i in blk])
    control_val = np.array([d["aovs"][d["ids"][i]].y0.contribution_inr for i in blk])
    pilot_net = float(d["y"][tr_i].sum())
    seg_cost += float(sum(iv.incentive_cost_inr(d["aovs"][d["ids"][i]].y1.order_value_inr)
                          for i in tr_i if d["aovs"][d["ids"][i]].y1.converted))
    rest = np.arange(len(blk), d["n"])
    pick = set()
    for s in set(d["seg"]):
        a = tr_i[d["seg"][tr_i] == s]; b = ct_i[d["seg"][ct_i] == s]
        if len(a) >= 2 and len(b) >= 2 and treated_val[np.isin(blk, a)].mean() > control_val[np.isin(blk, b)].mean():
            pick.add(s)
    sel = np.array([d["seg"][i] in pick for i in rest])
    seg_target += pilot_net + float(d["y"][rest][sel].sum())

print(f"HELD-OUT worlds: {len(test)}  (20051-20080, never examined, never tuned against)")
print(f"{'policy':<44}{'net contribution':>18}")
print("-" * 62)
print(f"{'do-nothing':<44}{0:>18,.0f}")
print(f"{'treat everyone':<44}{everyone:>18,.0f}")
print(f"{'realistic SEGMENT targeting (1 experiment)':<44}{seg_target:>18,.0f}")
print(f"{f'FROZEN observable predictor, top {k_star:.0%}':<44}{frozen:>18,.0f}")
print(f"{'oracle INDIVIDUAL targeting (ceiling)':<44}{oracle_ind:>18,.0f}")
print(f"\n  segment-targeting experiment cost inside the above: Rs.{seg_cost:,.0f}")
print(f"  frozen predictor needs no per-world experiment (cost Rs.0)")
