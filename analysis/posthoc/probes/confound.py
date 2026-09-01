"""Realistic confounding: each past campaign targeted differently, as merchants do.

The previous check applied ONE selection rule to all four interventions. Because
this simulator has a single untreated state (Y(0) identical across
interventions, docs/simulator.md §2), a common selection bias is an additive
constant that cancels from the RANKING -- an artifact of the corpus, not a
property of observational data.

A real merchant's campaigns are targeted differently, at different times, to
different customer sets. Here each intervention gets its own selection rule, so
the bias no longer cancels. Ground truth scores only.
"""
import json, sys
sys.path.insert(0, ".")
import numpy as np
from src.eval.devcorpus import open_dev

rows = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    ivs = {i.intervention_id: i for i in world.interventions}
    cust = world.customers
    aov = np.array([c.expected_order_value_inr for c in cust])
    freq = np.array([c.orders_last_90d for c in cust])
    recency = np.array([c.days_since_last_order for c in cust])
    elas = np.array([c.price_elasticity for c in cust])
    # One plausible targeting rule per campaign kind. Each selects a different
    # half of the base, as different campaigns genuinely would.
    rules = {
        "int_flat": aov <= np.median(aov),           # flat Rs. off -> small baskets
        "int_pct":  aov >= np.median(aov),           # % off -> big baskets
        "int_shipping": freq <= np.median(freq),     # shipping -> infrequent buyers
        "int_bundle": recency <= np.median(recency), # bundle -> recently active
    }
    naive, true_ate = {}, {}
    for iid, iv in ivs.items():
        sel = rules.get(iid, elas <= np.median(elas))
        y1 = np.array([truth.outcomes[c.customer_id][iid].y1.contribution_inr
                       - (iv.incentive_cost_inr(truth.outcomes[c.customer_id][iid].y1.order_value_inr)
                          if truth.outcomes[c.customer_id][iid].y1.converted else 0.0)
                       for c in cust])
        y0 = np.array([truth.outcomes[c.customer_id][iid].y0.contribution_inr for c in cust])
        naive[iid] = float(y1[sel].mean() - y0[~sel].mean())   # what the merchant sees
        true_ate[iid] = float((y1 - y0).mean())                # population causal truth
    nb, tb = max(naive, key=naive.get), max(true_ate, key=true_ate.get)
    rows.append(dict(world=world.world_id, naive_best=nb, true_best=tb, ok=nb == tb,
                     naive_val=naive[nb], true_of_naive_pick=true_ate[nb],
                     signflip=naive[nb] > 0 and true_ate[nb] < 0,
                     bias=naive[nb] - true_ate[nb]))
    del world, truth

n = len(rows)
b = np.array([r["bias"] for r in rows])
print("OBSERVATIONAL history, no controls, per-campaign targeting (realistic)")
print(f"  naive winner == true winner            : {sum(r['ok'] for r in rows)}/{n}"
      f"   (chance = {n/4:.0f}/{n})")
print(f"  naive says PROFITABLE, truth says LOSS : {sum(r['signflip'] for r in rows)}/{n}")
print(f"  bias of the naive estimate, Rs./customer: median {np.median(b):+,.2f}"
      f"  mean {b.mean():+,.2f}  max {b.max():+,.2f}")
print()
print(f"{'world':<13}{'naive picks':<14}{'truth':<14}{'naive Rs/cust':>15}{'true Rs/cust':>14}{'flip':>7}")
for r in rows:
    print(f"{r['world']:<13}{r['naive_best']:<14}{r['true_best']:<14}"
          f"{r['naive_val']:>15,.2f}{r['true_of_naive_pick']:>14,.2f}"
          f"{('YES' if r['signflip'] else ''):>7}")
json.dump(rows, open("analysis/posthoc/probes/outputs/confound.json","w"), indent=1)
