"""Is intervention response recoverable from realistically-available history?

Three measurements on existing dev worlds. Ground truth scores only.
  (a) RANDOMIZED history with a control arm at a realistic size (the Cycle 2
      Fix B construction, 300 treated + 300 control per intervention).
  (b) The n-per-arm actually required to separate the best intervention from the
      second best, by the same two-sample estimator the project already uses.
  (c) OBSERVATIONAL history with no control -- a merchant that targets customers
      it believes are price-sensitive -- scored for confounding bias.
"""
import json, sys
sys.path.insert(0, ".")
import numpy as np
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev

Z = 1.959964 + 0.841621
rows = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    view = merchant_view(world)
    ivs = {i.intervention_id: i for i in world.interventions}
    cust = world.customers

    # ---- ground truth: per-customer incremental net, per intervention -------
    per = {}
    for iid, iv in ivs.items():
        v = np.empty(len(cust))
        for k, c in enumerate(cust):
            p = truth.outcomes[c.customer_id][iid]
            inc = p.y1.contribution_inr - p.y0.contribution_inr
            if p.y1.converted:
                inc -= iv.incentive_cost_inr(p.y1.order_value_inr)
            v[k] = inc
        per[iid] = v
    means = {i: float(v.mean()) for i, v in per.items()}
    order = sorted(means, key=means.get, reverse=True)
    best, second = order[0], order[1]
    gap = means[best] - means[second]
    sd = float(np.sqrt((per[best].var(ddof=1) + per[second].var(ddof=1)) / 2))
    n_needed = 2 * (Z ** 2) * sd ** 2 / gap ** 2 if gap > 0 else float("inf")

    # ---- (a) randomized history at 300/arm: does it pick the winner? --------
    hist_best = max(view.history, key=lambda h: h.net_per_treated_customer_inr).intervention_id
    hse = {h.intervention_id: h.standard_error_inr for h in view.history}

    # ---- (c) observational, no control, selection on price sensitivity -----
    #  merchant targets the most price-sensitive half; naive read compares
    #  treated-group outcomes against the untreated group's outcomes.
    elas = np.array([c.price_elasticity for c in cust])
    sel = elas <= np.median(elas)                      # most elastic half
    naive, true_on_sel = {}, {}
    for iid, iv in ivs.items():
        y1 = np.array([truth.outcomes[c.customer_id][iid].y1.contribution_inr
                       - (iv.incentive_cost_inr(truth.outcomes[c.customer_id][iid].y1.order_value_inr)
                          if truth.outcomes[c.customer_id][iid].y1.converted else 0.0)
                       for c in cust])
        y0 = np.array([truth.outcomes[c.customer_id][iid].y0.contribution_inr for c in cust])
        naive[iid] = float(y1[sel].mean() - y0[~sel].mean())   # association
        true_on_sel[iid] = float((y1[sel] - y0[sel]).mean())   # causal, same people
    naive_best = max(naive, key=naive.get)
    true_sel_best = max(true_on_sel, key=true_on_sel.get)

    rows.append(dict(world=world.world_id, best=best, gap=gap, sd=sd, n_needed=n_needed,
                     hist_best=hist_best, hist_ok=hist_best == best,
                     hist_se=hse.get(best, float("nan")),
                     naive_best=naive_best, naive_ok=naive_best == true_sel_best,
                     naive_val=naive[naive_best], true_val=true_on_sel[naive_best],
                     bias=naive[naive_best] - true_on_sel[naive_best]))
    del world, truth

json.dump(rows, open("analysis/posthoc/probes/outputs/history_leak.json","w"), indent=1)
n = len(rows)
print(f"(a) RANDOMIZED history, 300 treated + 300 control per intervention")
print(f"    picks the truly best intervention : {sum(r['hist_ok'] for r in rows)}/{n}"
      f"   (chance = {n/4:.0f}/{n})")
print()
print(f"(b) n PER ARM required to separate best from second-best (80% power, a=0.05)")
q = np.percentile([r['n_needed'] for r in rows if np.isfinite(r['n_needed'])], [25,50,75])
print(f"    p25 {q[0]:,.0f}   median {q[1]:,.0f}   p75 {q[2]:,.0f}")
print(f"    worlds needing > 5,000 per arm    : "
      f"{sum(1 for r in rows if r['n_needed']>5000)}/{n}")
print(f"    worlds needing > 50,000 per arm   : "
      f"{sum(1 for r in rows if r['n_needed']>50000)}/{n}")
print()
print(f"(c) OBSERVATIONAL history, no control, targeting the price-sensitive half")
print(f"    naive winner == true winner on the treated group : "
      f"{sum(r['naive_ok'] for r in rows)}/{n}")
b = np.array([r['bias'] for r in rows])
print(f"    bias of the naive estimate, Rs. per customer: "
      f"median {np.median(b):+,.2f}   mean {b.mean():+,.2f}")
print(f"    naive estimate positive while truth negative     : "
      f"{sum(1 for r in rows if r['naive_val']>0 and r['true_val']<0)}/{n}")
