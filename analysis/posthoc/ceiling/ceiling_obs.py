"""Legitimate feature-based targeting ceiling: V*(X) = sum_i max(0, E[net_i | X_i]).

No realized Y(0)/Y(1), no u_i, no oracle latent, nothing fitted to outcomes.
E[net|X] is a structural integral over the generator's OWN priors for whatever
X does not contain. Ground truth is never loaded: this script imports
src.world.persistence.load_world only, never load_ground_truth.

Information ladder:
  A   the six CustomerView fields alone
  B   A + SegmentView.name/tags/notes (archetype identity)
  C1  B + world scalars: observed_margin, seasonality decode, recovered baseline conversion
  C2  C1 + the four coupled semantic signals (Bayes at 0.78 TP / 0.18 FP)
  C3  C2 + InterventionHistory (importance weighting on the world scenario)

Intervention is fixed per world by the same observable rule policy.py used
(cheapest incentive per treated order at observed AOV), so the output is
comparable with the recorded -Rs.72,983 / +Rs.3,595,677 on these worlds.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

import numpy as np
from scipy import stats
from scipy.stats import qmc

from src.eval.contracts import merchant_view
from src.policy.gates import PolicyLimits
from src.world import vocabulary as vocab
from src.world.persistence import load_world
from src.world.schema import Intervention, InterventionKind

ROOT = Path("worlds_cycle2/dev")
OUT = Path("analysis/posthoc/ceiling/outputs/ceiling_obs.json")
LO, HI = 20051, 20080          # the TEST split policy.py used. Nothing is fitted, so nothing is tuned.
N_HALF = 2048                  # per Sobol half; 4096 scenarios total
N_GRID = 32
LIMITS = PolicyLimits()

# --------------------------------------------------------------------------- #
# Generator constants, mirrored (read from source, never re-derived)
# --------------------------------------------------------------------------- #
ARCHE = vocab.SEGMENT_ARCHETYPES
N_ARCHE = len(ARCHE)
CONV_M = np.array([float(a["conversion_multiplier"]) for a in ARCHE])
ELAS_M = np.array([float(a["elasticity_multiplier"]) for a in ARCHE])
RESP_M = np.array([float(a["responsiveness_mean"]) for a in ARCHE])
NAME_TO_IDX = {str(a["name"]): i for i, a in enumerate(ARCHE)}

SEASON = {t: m for t, m in vocab.SEASONAL_EVENTS}
AFFINITY_SIGMA, AFFINITY_CLIP, AFF_THRESH = 0.45, (0.5, 2.2), 1.25
SIG_TP, SIG_FP = 0.78, 0.18
LATENT_PREVALENCE = 0.35
RESPONSE_ASYMPTOTE, SAT = 3.0, 2.0
P0_SIGMA, BASKET_SIGMA = 0.25, 0.20


def seasonality_prior(n=40000, seed=11):
    """Empirical prior for seasonality_index, from _sample_calendar's own process."""
    rng = np.random.default_rng(seed)
    mults = np.array([m for _, m in vocab.SEASONAL_EVENTS])
    out = np.empty(n)
    for k in range(n):
        j = rng.integers(1, 4)
        out[k] = np.clip(rng.choice(mults, size=j, replace=False).mean(), 0.85, 1.35)
    return np.sort(out)


SEASON_PRIOR = seasonality_prior()


# --------------------------------------------------------------------------- #
# Vectorized response model. Verified against the project's own functions below.
# --------------------------------------------------------------------------- #
def depth_and_cost(iv: Intervention, tb):
    """effective_depth and incentive_cost, vectorized. Mirrors schema.py:261-295."""
    tb = np.maximum(tb, 1e-9)
    if iv.kind is InterventionKind.FLAT_DISCOUNT:
        d = (iv.flat_discount_inr or 0.0) / tb
    elif iv.kind is InterventionKind.PERCENTAGE_DISCOUNT:
        d = np.full_like(tb, iv.discount_pct or 0.0)
    elif iv.kind is InterventionKind.FREE_SHIPPING:
        d = (iv.shipping_fee_waived_inr or 0.0) / tb
    else:
        d = np.full_like(tb, iv.discount_pct or 0.0)
    d = np.clip(d, 0.0, 0.5)
    return d, d * tb


def expected_net(eov, arche_idx, iv, draws, known):
    """E[net | X] for a grid of (archetype, eov), integrating everything unknown.

    eov       : (G,) observed order value grid
    arche_idx : (A,) archetype rows in play, or None when the archetype is unknown
                (then draws['arche'] supplies one per scenario)
    draws     : dict of (N,) scenario draws
    known     : dict of scalars X actually contains

    Returns (A, G, N) is too large, so the scenario axis is reduced inside:
    returns mean over scenarios -> (A, G), plus the same for expected cost.
    """
    G = eov.shape[0]
    rows = arche_idx if arche_idx is not None else np.array([0])
    A = rows.shape[0]
    N = draws["R"].shape[0]

    out = np.empty((A, G))
    out_cost = np.empty((A, G))
    out_h1 = np.empty((A, G))
    out_h2 = np.empty((A, G))
    half = N // 2

    for ai in range(A):
        if arche_idx is None:
            cm, em, rm = draws["cm"], draws["em"], draws["rm"]           # (N,)
        else:
            r = rows[ai]
            cm = np.full(N, CONV_M[r]); em = np.full(N, ELAS_M[r]); rm = np.full(N, RESP_M[r])

        base = known.get("baseline_conversion", draws["bc"])
        seas = known.get("seasonality", draws["seas"])
        marg = known.get("margin", draws["marg"])

        p0 = np.clip(base * seas * cm * draws["nu_p"], 0.005, 0.60)      # (N,)
        eps = np.clip(-np.abs(draws["elast_mean"] * em + draws["nu_e"]), -5.0, -0.30)
        r_i = np.clip(rm * draws["R"] * draws["nu_r"], 0.05, 12.0)

        # (N, G): one basket-noise draw per scenario, applied across the grid (CRN)
        b = eov[None, :] * draws["L"][:, None]
        tb = b + (iv.bundle_added_value_inr or 0.0) if iv.kind is InterventionKind.BUNDLE else b
        d, cost = depth_and_cost(iv, tb)

        lift = np.power(np.maximum(1.0 - d, 1e-12), eps[:, None]) - 1.0
        raw = r_i[:, None] * draws["a"][:, None] * np.maximum(lift, 0.0)
        m = 1.0 + SAT * (1.0 - np.exp(-raw / SAT))
        p1 = 1.0 - np.power(np.maximum(1.0 - p0[:, None], 0.0), m)
        p1 = np.clip(p1, 0.0, 1.0)

        bundle_gain = (iv.bundle_added_value_inr or 0.0) * marg if iv.kind is InterventionKind.BUNDLE else 0.0
        if np.ndim(bundle_gain):
            bundle_gain = bundle_gain[:, None]
        margc = marg[:, None] if np.ndim(marg) else marg

        # E[net | scenario] = p0*(bundle_gain - cost) + (p1-p0)*((1-cann)*tb*M - cost)
        always = p0[:, None] * (bundle_gain - cost)
        comply = (p1 - p0[:, None]) * ((1.0 - draws["cann"][:, None]) * tb * margc - cost)
        net = always + comply                                            # (N, G)
        exp_cost = p1 * cost                                             # charged iff converted under treatment

        w = draws.get("w")
        if w is None:
            out[ai] = net.mean(0); out_cost[ai] = exp_cost.mean(0)
            out_h1[ai] = net[:half].mean(0); out_h2[ai] = net[half:].mean(0)
        else:
            ws = w / w.sum()
            out[ai] = (net * ws[:, None]).sum(0)
            out_cost[ai] = (exp_cost * ws[:, None]).sum(0)
            w1 = w[:half] / w[:half].sum(); w2 = w[half:] / w[half:].sum()
            out_h1[ai] = (net[:half] * w1[:, None]).sum(0)
            out_h2[ai] = (net[half:] * w2[:, None]).sum(0)
    return out, out_cost, out_h1, out_h2


# --------------------------------------------------------------------------- #
# Scenario construction per information level
# --------------------------------------------------------------------------- #
def make_draws(level, view, iv, seed):
    """Sobol scenarios over exactly the variables X does NOT contain."""
    dim = 15
    sob = qmc.Sobol(d=dim, scramble=True, seed=seed)
    u = sob.random(2 * N_HALF)
    u = np.clip(u, 1e-9, 1 - 1e-9)
    N = u.shape[0]
    d = {}

    d["R"] = 0.9 + 1.2 * u[:, 0]                                  # promo_response_scale
    sig_r = 0.25 + 0.35 * u[:, 1]                                 # responsiveness_sigma
    em_raw = -3.5 + 2.3 * u[:, 2]                                 # elasticity_mean

    # competitive pressure: prior 0.35, or Bayes on the price-war string at C2+
    p_war = LATENT_PREVALENCE
    if level in ("C2", "C3"):
        seen = vocab.SIGNAL_COMPETITOR_PRICE_WAR in view.semantic.competitor_events
        tp, fp = (SIG_TP, SIG_FP) if seen else (1 - SIG_TP, 1 - SIG_FP)
        p_war = tp * LATENT_PREVALENCE / (tp * LATENT_PREVALENCE + fp * (1 - LATENT_PREVALENCE))
    war = u[:, 3] < p_war
    d["elast_mean"] = np.where(war, em_raw * 1.35, em_raw)
    elast_sd = 0.30 + 0.60 * u[:, 4]
    d["nu_e"] = stats.norm.ppf(u[:, 8]) * elast_sd
    d["nu_r"] = np.exp(sig_r * stats.norm.ppf(u[:, 9]))
    d["nu_p"] = np.exp(P0_SIGMA * stats.norm.ppf(u[:, 7]))
    d["L"] = np.exp(BASKET_SIGMA * stats.norm.ppf(u[:, 10]))
    d["cann"] = 0.15 + 0.30 * u[:, 6]

    # intervention affinity, with the coupled semantic signal at C2+
    z = stats.norm.ppf(u[:, 5])
    if level in ("C2", "C3"):
        kind_signal = {
            InterventionKind.FREE_SHIPPING: vocab.SIGNAL_SHIPPING_THRESHOLD in view.semantic.customer_service_themes,
            InterventionKind.FLAT_DISCOUNT: any(vocab.SIGNAL_CLEARS_WHEN_DISCOUNTED in n
                                                for n in view.semantic.inventory_notes),
        }.get(iv.kind)
        if kind_signal is not None:
            cut = np.log(AFF_THRESH) / AFFINITY_SIGMA
            prior_high = 1.0 - stats.norm.cdf(cut)
            tp, fp = (SIG_TP, SIG_FP) if kind_signal else (1 - SIG_TP, 1 - SIG_FP)
            post_high = tp * prior_high / (tp * prior_high + fp * (1 - prior_high))
            hi = u[:, 5] < post_high                     # reuse column 5 as the mixture selector
            zh = stats.norm.ppf(1 - (1 - stats.norm.cdf(cut)) * u[:, 11])   # truncated above
            zl = stats.norm.ppf(stats.norm.cdf(cut) * u[:, 11])             # truncated below
            z = np.where(hi, zh, zl)
    d["a"] = np.clip(np.exp(AFFINITY_SIGMA * z), *AFFINITY_CLIP)

    # world scalars: known exactly at C1+, integrated at A/B
    d["marg"] = 0.22 + 0.16 * u[:, 12]
    d["seas"] = SEASON_PRIOR[(u[:, 13] * (SEASON_PRIOR.size - 1)).astype(int)]
    d["bc"] = 0.06 + 0.14 * u[:, 14]

    if level == "A":                                  # archetype unknown -> integrate uniformly
        ai = (u[:, 11] * N_ARCHE).astype(int) if level == "A" else None
        d["cm"], d["em"], d["rm"] = CONV_M[ai], ELAS_M[ai], RESP_M[ai]
    return d, N


def known_for(level, view):
    if level in ("A", "B"):
        return {}
    seas = np.clip(np.mean([SEASON[t] for t in view.semantic.seasonal_events
                            if t in SEASON] or [1.0]), 0.85, 1.35)
    shares = np.array([s.share for s in view.segments], float); shares /= shares.sum()
    idx = [NAME_TO_IDX[s.name] for s in view.segments]
    mean_cm = float((shares * CONV_M[idx]).sum())
    bc = view.observed_conversion / max(seas * mean_cm * np.exp(P0_SIGMA ** 2 / 2), 1e-9)
    return {"margin": float(view.observed_margin), "seasonality": float(seas),
            "baseline_conversion": float(np.clip(bc, 0.01, 0.40))}


# --------------------------------------------------------------------------- #
# Self-check: the vectorized model must equal the project's own functions
# --------------------------------------------------------------------------- #
def self_check(world, iv):
    from src.world.generator import response_multiplier, treated_conversion_probability
    rng = np.random.default_rng(0)
    for c in [world.customers[i] for i in rng.integers(0, len(world.customers), 12)]:
        b = c.expected_order_value_inr
        tb = b + (iv.bundle_added_value_inr or 0.0) if iv.kind is InterventionKind.BUNDLE else b
        d_vec, cost_vec = depth_and_cost(iv, np.array([tb]))
        assert abs(float(d_vec[0]) - iv.effective_depth(tb)) < 1e-12
        assert abs(float(cost_vec[0]) - iv.incentive_cost_inr(tb)) < 1e-9
        lift = (1 - iv.effective_depth(tb)) ** c.price_elasticity - 1
        m_mine = 1 + SAT * (1 - np.exp(-(c.responsiveness * 1.0 * max(lift, 0.0)) / SAT))
        assert abs(m_mine - response_multiplier(c.responsiveness * 1.0 * max(lift, 0.0))) < 1e-10
        p1_mine = 1 - (1 - c.baseline_purchase_prob) ** m_mine
        p1_proj = treated_conversion_probability(c, iv, tb, affinity=1.0)
        assert abs(p1_mine - p1_proj) < 1e-10
    return True


# --------------------------------------------------------------------------- #
LEVELS = ["A", "B", "C1", "C2", "C3"]
rows = []
checked = False

for wid in range(LO, HI + 1):
    path = ROOT / f"world_{wid:05d}.world.json"
    if not path.exists():
        continue
    world = load_world(path)
    view = merchant_view(world)
    iv = min(view.interventions, key=lambda i: i.incentive_cost_inr(view.observed_aov_inr))
    if not checked:
        checked = self_check(world, iv)
    del world

    eov = np.array([c.historical_aov_inr for c in view.customers])
    seg_of = {s.segment_id: NAME_TO_IDX[s.name] for s in view.segments}
    cust_arche = np.array([seg_of[c.segment_id] for c in view.customers])
    rows_present = np.array(sorted(set(cust_arche)))
    grid = np.exp(np.linspace(np.log(eov.min()), np.log(eov.max()), N_GRID))

    hist = view.history_for(iv.intervention_id)
    rec = {"world": view.world_id, "iv": iv.intervention_id, "kind": iv.kind.value,
           "n": len(view.customers), "budget": view.budget_inr,
           "observed_margin": view.observed_margin, "levels": {}}

    for level in LEVELS:
        draws, N = make_draws(level, view, iv, seed=wid * 100 + LEVELS.index(level))
        known = known_for(level, view)
        idx = None if level == "A" else rows_present

        if level == "C3" and hist is not None and hist.standard_error_inr > 0:
            # Importance weight scenarios by the observed past-campaign statistic.
            # _intervention_history uses eov with NO basket noise, NO pull-forward,
            # treated = customers[:300], control = customers[300:600].
            hsub = np.concatenate([np.arange(0, min(300, len(eov))),
                                   np.arange(300, min(600, len(eov)))])
            gsub = np.exp(np.linspace(np.log(eov[hsub].min()), np.log(eov[hsub].max()), N_GRID))
            dh = dict(draws); dh["L"] = np.ones_like(draws["L"]); dh["cann"] = np.zeros_like(draws["cann"])
            # per-scenario implied history mean, on the same grid machinery
            tb_g = gsub + (iv.bundle_added_value_inr or 0.0) if iv.kind is InterventionKind.BUNDLE else gsub
            d_g, cost_g = depth_and_cost(iv, tb_g)
            marg = known.get("margin", dh["marg"])
            base = known.get("baseline_conversion", dh["bc"])
            seas = known.get("seasonality", dh["seas"])
            tre = np.arange(0, min(300, len(eov))); ctl = np.arange(300, min(600, len(eov)))
            acc_t = np.zeros(N); acc_c = np.zeros(N)
            for r in rows_present:
                cm, em, rm = CONV_M[r], ELAS_M[r], RESP_M[r]
                p0 = np.clip(base * seas * cm * dh["nu_p"], 0.005, 0.60)
                eps = np.clip(-np.abs(dh["elast_mean"] * em + dh["nu_e"]), -5.0, -0.30)
                ri = np.clip(rm * dh["R"] * dh["nu_r"], 0.05, 12.0)
                lift = np.power(np.maximum(1 - d_g, 1e-12), eps[:, None]) - 1
                m = 1 + SAT * (1 - np.exp(-(ri[:, None] * dh["a"][:, None] * np.maximum(lift, 0)) / SAT))
                p1 = np.clip(1 - np.power(np.maximum(1 - p0[:, None], 0), m), 0, 1)
                mg = marg[:, None] if np.ndim(marg) else marg
                t_val = p1 * (tb_g * mg - cost_g)
                c_val = p0[:, None] * (gsub * mg)
                # vectorized interp over scenarios
                for arr, sel, acc in ((t_val, tre, acc_t), (c_val, ctl, acc_c)):
                    mask = cust_arche[sel] == r
                    if mask.any():
                        xs = eov[sel][mask]
                        pos = np.clip(np.searchsorted(gsub, xs) - 1, 0, N_GRID - 2)
                        frac = (xs - gsub[pos]) / (gsub[pos + 1] - gsub[pos])
                        acc += (arr[:, pos] * (1 - frac) + arr[:, pos + 1] * frac).sum(1)
            mu = acc_t / max(len(tre), 1) - acc_c / max(len(ctl), 1)
            ll = -0.5 * ((hist.net_per_treated_customer_inr - mu) / hist.standard_error_inr) ** 2
            draws["w"] = np.exp(ll - ll.max())

        g, gcost, g1, g2 = expected_net(grid, idx, iv, draws, known)

        if level == "A":
            gi = np.interp(eov, grid, g[0]); gci = np.interp(eov, grid, gcost[0])
            g1i = np.interp(eov, grid, g1[0]); g2i = np.interp(eov, grid, g2[0])
        else:
            gi = np.empty_like(eov); gci = np.empty_like(eov)
            g1i = np.empty_like(eov); g2i = np.empty_like(eov)
            for k, r in enumerate(rows_present):
                m = cust_arche == r
                gi[m] = np.interp(eov[m], grid, g[k]); gci[m] = np.interp(eov[m], grid, gcost[k])
                g1i[m] = np.interp(eov[m], grid, g1[k]); g2i[m] = np.interp(eov[m], grid, g2[k])

        sel = gi > 0
        crossfit = 0.5 * (float(g2i[g1i > 0].sum()) + float(g1i[g2i > 0].sum()))
        rec["levels"][level] = {
            "ceiling_plugin": float(gi[sel].sum()),
            "ceiling_crossfit": crossfit,
            "treat_everyone_expected": float(gi.sum()),
            "n_selected": int(sel.sum()),
            "share_selected": float(sel.mean()),
            "expected_spend_selected": float(gci[sel].sum()),
            "mc_halfgap": float(np.abs(g1i - g2i).mean()),
        }
    rows.append(rec)
    print(f"{rec['world']} {iv.intervention_id:<13} " +
          "  ".join(f"{L}:{rec['levels'][L]['ceiling_plugin']:>+10,.0f}" for L in LEVELS), flush=True)

OUT.write_text(json.dumps(rows, indent=1))

print("\n" + "=" * 108)
print(f"WORLDS {LO}-{HI}   n={len(rows)}   scenarios per cell = {2*N_HALF} (Sobol, scrambled)")
print("=" * 108)
hdr = f"{'level':<5}{'ceiling (plug-in)':>20}{'ceiling (cross-fit)':>21}{'treat-everyone E[net]':>23}{'share treated':>15}{'spend':>16}"
print(hdr); print("-" * 108)
for L in LEVELS:
    p = sum(r["levels"][L]["ceiling_plugin"] for r in rows)
    c = sum(r["levels"][L]["ceiling_crossfit"] for r in rows)
    e = sum(r["levels"][L]["treat_everyone_expected"] for r in rows)
    s = np.mean([r["levels"][L]["share_selected"] for r in rows])
    sp = sum(r["levels"][L]["expected_spend_selected"] for r in rows)
    print(f"{L:<5}{p:>+20,.0f}{c:>+21,.0f}{e:>+23,.0f}{s:>14.1%}{sp:>16,.0f}")
print("-" * 108)
print(f"total budget across worlds      : Rs.{sum(r['budget'] for r in rows):,.0f}")
print(f"exposure cap (max_customer_exposure_share) = {LIMITS.max_customer_exposure_share:.0%}")
print(f"total customers                 : {sum(r['n'] for r in rows):,}")
print("\nrecorded on these same worlds (policy.py, measured, NOT recomputed here):")
print("  treat everyone                        -1,094,562")
print("  frozen observable predictor top 5%       -72,983")
print("  hindsight oracle  sum max(0, net_i)   +3,595,677")
