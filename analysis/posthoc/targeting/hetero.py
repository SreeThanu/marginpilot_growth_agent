"""Q1: is there per-customer treatment-effect heterogeneity to target at all?"""
import sys; sys.path.insert(0, ".")
import numpy as np
from src.eval.devcorpus import open_dev

rows = []
for world, truth in open_dev("worlds_cycle2", limit=10):
    ivs = {i.intervention_id: i for i in world.interventions}
    for iid, iv in ivs.items():
        net = np.empty(len(world.customers))
        flip = np.zeros(len(world.customers), dtype=bool)
        for k, c in enumerate(world.customers):
            p = truth.outcomes[c.customer_id][iid]
            v = p.y1.contribution_inr - p.y0.contribution_inr
            if p.y1.converted:
                v -= iv.incentive_cost_inr(p.y1.order_value_inr)
            net[k] = v
            flip[k] = p.y1.converted and not p.y0.converted     # persuaded
        # segment-level
        segs = np.array([c.segment_id for c in world.customers])
        seg_means = {s: float(net[segs == s].mean()) for s in set(segs)}
        rows.append(dict(world=world.world_id, iv=iid,
                         mean=float(net.mean()), sd=float(net.std(ddof=1)),
                         frac_pos=float((net > 0).mean()),
                         persuaded=float(flip.mean()),
                         seg_spread=max(seg_means.values()) - min(seg_means.values()),
                         seg_any_pos=sum(1 for v in seg_means.values() if v > 0),
                         n_seg=len(seg_means)))
    del world, truth

import statistics as st
print("PER-CUSTOMER treatment effect, contribution net of incentive (10 dev worlds x 4 arms)")
print(f"  mean net per customer        : Rs.{st.mean(r['mean'] for r in rows):+.2f}")
print(f"  SD across customers (within) : Rs.{st.mean(r['sd'] for r in rows):.2f}")
print(f"  -> SD / |mean| ratio         : {st.mean(r['sd'] for r in rows)/abs(st.mean(r['mean'] for r in rows)):.1f}x")
print(f"  share of customers with net>0: {st.mean(r['frac_pos'] for r in rows):.1%}")
print(f"  share genuinely persuaded    : {st.mean(r['persuaded'] for r in rows):.2%}")
print()
print("SEGMENT-level (what a targeting policy can actually address)")
print(f"  segments per world           : {st.mean(r['n_seg'] for r in rows):.1f}")
print(f"  spread of segment mean net   : Rs.{st.mean(r['seg_spread'] for r in rows):.2f}")
print(f"  arms where >=1 segment net>0 : {sum(1 for r in rows if r['seg_any_pos']>0)}/{len(rows)}")
print(f"  arms where ALL segments net>0: {sum(1 for r in rows if r['seg_any_pos']==r['n_seg'])}/{len(rows)}")
print(f"  arms where NO segment net>0  : {sum(1 for r in rows if r['seg_any_pos']==0)}/{len(rows)}")
