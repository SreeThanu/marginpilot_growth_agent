"""Do the six observable fields predict INDIVIDUAL treatment effect?

TRAIN = dev worlds 20021-20050, TEST = 20051-20080. Worlds 20001-20020 are
excluded entirely: every prior diagnostic in this thread examined them, so they
are contaminated for a transfer test. The sealed holdout is untouched.
"""
import sys; sys.path.insert(0, ".")
import numpy as np
from scipy import stats
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev

FIELDS = ["tenure_days", "orders_last_90d", "days_since_last_order", "historical_aov_inr"]

def load(lo, hi):
    out = []
    for w, t in open_dev("worlds_cycle2", limit=80):
        wid = int(w.world_id.split("_")[1])
        if not (lo <= wid <= hi):
            del w, t; continue
        v = merchant_view(w)
        iv = min(w.interventions, key=lambda i: i.incentive_cost_inr(v.observed_aov_inr))
        recs = {c.customer_id: c for c in v.customers}
        X, y, seg = [], [], []
        for c in w.customers:
            r = recs[c.customer_id]
            p_ = t.outcomes[c.customer_id][iv.intervention_id]
            inc = iv.incentive_cost_inr(p_.y1.order_value_inr) if p_.y1.converted else 0.0
            y.append(p_.y1.contribution_inr - p_.y0.contribution_inr - inc)
            X.append([r.tenure_days, r.orders_last_90d, r.days_since_last_order,
                      np.log1p(r.historical_aov_inr)])
            seg.append(r.segment_id)
        out.append(dict(world=w.world_id, X=np.array(X, float), y=np.array(y, float),
                        seg=np.array(seg)))
        del w, t
    return out

train, test = load(20021, 20050), load(20051, 20080)
print(f"TRAIN worlds {len(train)}   TEST worlds {len(test)}   (20001-20020 excluded as contaminated)\n")

print("Correlation of each observable with TRUE individual net uplift, per world")
print(f"{'field':<26}{'mean |Spearman rho|':>22}{'worlds p<0.05':>16}")
print("-" * 64)
for j, f in enumerate(FIELDS):
    rs, sig = [], 0
    for d in test:
        r = stats.spearmanr(d["X"][:, j], d["y"])
        rs.append(abs(r.statistic)); sig += int(r.pvalue < 0.05)
    print(f"{f:<26}{np.mean(rs):>22.4f}{sig:>10}/{len(test)}")
# segment_id, the one field with designed signal
rs, sig = [], 0
for d in test:
    codes = {s: i for i, s in enumerate(sorted(set(d["seg"])))}
    r = stats.spearmanr([codes[s] for s in d["seg"]], d["y"])
    rs.append(abs(r.statistic)); sig += int(r.pvalue < 0.05)
print(f"{'segment_id (ordinal)':<26}{np.mean(rs):>22.4f}{sig:>10}/{len(test)}")
print(f"\nfraction of individual variance explainable BY SEGMENT (eta^2), TEST worlds:")
e2 = []
for d in test:
    gm = d["y"].mean()
    ssb = sum(((d["y"][d["seg"] == s].mean() - gm) ** 2) * (d["seg"] == s).sum()
              for s in set(d["seg"]))
    e2.append(ssb / ((d["y"] - gm) ** 2).sum())
print(f"  mean eta^2 = {np.mean(e2):.5f}  -> segment explains {np.mean(e2)*100:.3f}% of individual variance")

# Frozen cross-world predictor: fit on TRAIN, never refit.
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor
Xtr = np.vstack([d["X"] for d in train])
ytr = np.concatenate([(d["y"] - d["y"].mean()) / (d["y"].std() + 1e-9) for d in train])
for name, model in (("ridge", Ridge(alpha=1.0)),
                    ("gradient boosting", GradientBoostingRegressor(random_state=0))):
    model.fit(Xtr, ytr)
    rs = []
    for d in test:
        pred = model.predict(d["X"])
        r = stats.spearmanr(pred, d["y"])
        rs.append(r.statistic)
    print(f"\nFROZEN {name}: predicted vs true uplift on TEST worlds")
    print(f"  mean Spearman rho = {np.mean(rs):+.4f}   (sd {np.std(rs):.4f}, n={len(rs)} worlds)")
    print(f"  worlds with rho > 0: {sum(1 for r in rs if r>0)}/{len(rs)}")
    t = stats.ttest_1samp(rs, 0.0)
    print(f"  t-test vs zero: t={t.statistic:+.2f}  p={t.pvalue:.3f}")
np.save("analysis/posthoc/targeting/outputs/_ok.npy", np.array([1]))
