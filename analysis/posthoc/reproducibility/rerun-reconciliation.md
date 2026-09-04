# Reproducibility reconciliation — `hetero.py`, `predict.py`, `policy.py`

**Date:** 1 September 2026 · **Repo:** `main` @ `4942af6`, working tree clean before and after
**Run:** each script executed **once**, unmodified, from the snapshot copy, CWD = repo root
**Log:** `rerun.log` (this session's scratchpad) · hetero 3 s · predict 103 s · policy 111 s · **all exit 0**

Scripts were verified byte-identical between the snapshot and the live scratchpad before running (sha256 `25ab3e2a…`, `72740c08…`, `bcea0a1c…`).

**Headline: every historical figure reproduced exactly, to the last printed digit.** No metric landed in status B or C on numerical grounds. Two provenance corrections are required, and one scope caveat about the environment.

---

## A. Static inspection

| | `hetero.py` | `predict.py` | `policy.py` |
|---|---|---|---|
| **worlds** | `open_dev("worlds_cycle2", limit=10)` → **20001–20010**, all 4 interventions (40 world×arm rows) | `limit=80`, filtered TRAIN **20021–20050** / TEST **20051–20080**; 20001–20020 excluded as contaminated | identical to `predict.py` |
| **target variable** | per-customer `net = y1.contribution − y0.contribution − incentive_cost·1{y1.converted}` | same `net`, per customer, for one intervention per world | same `net` |
| **features** | none — descriptive only; groups by `segment_id` | `tenure_days`, `orders_last_90d`, `days_since_last_order`, `log1p(historical_aov_inr)`; `segment_id` measured separately, **not** in the model | same four numeric fields |
| **policy definition** | none | none (correlation / η² only) | rank by frozen GB prediction, treat top-k; k chosen on TRAIN over grid {5,10,20,30,50,75,100}%, frozen, applied to TEST. Intervention fixed per world by `min(incentive_cost at observed AOV)` |
| **random seeds** | none — no RNG | `GradientBoostingRegressor(random_state=0)`; `Ridge` closed-form | `GradientBoostingRegressor(random_state=0)`; `np.quantile`; `assign()` is blake2b-keyed |
| **version-sensitive ops** | none (pure numpy arithmetic) | **scikit-learn gradient boosting**; `scipy.stats.spearmanr` | **scikit-learn gradient boosting**; `np.quantile` |
| **reads ground truth** | **yes** — `truth.outcomes[...]`, to score only | **yes** — scores only; never informs the predictor | **yes** — scores only |
| **touches sealed data** | **no** — `open_dev` cannot reach a sealed world; no `open_holdout`/`final_eval`/`29xxx` reference | **no** | **no** |
| **modifies anything** | **no writes at all** | writes `_ok.npy` sentinel to the old scratchpad | **no writes at all** |

None of the three imports `src.agent`, a reasoner, or any LLM client.

---

## C/D. Metric-by-metric comparison

| script | metric | historical | regenerated | status | reason |
|---|---|---|---|---|---|
| hetero | mean net / customer | −₹7.88 | **Rs.-7.88** | **A** | exact |
| hetero | within-world customer SD | ₹74.48 | **Rs.74.48** | **A** | exact |
| hetero | positive-net customers | 3.4% | **3.4%** | **A** | exact |
| hetero | genuinely persuaded | 3.78% | **3.78%** | **A** | exact |
| hetero | segment mean-net spread | ₹26.88 | **Rs.26.88** | **A** | exact |
| hetero | ≥1 positive segment | 28/40 | **28/40** | **A** | exact |
| hetero | all segments positive | 1/40 | **1/40** | **A** | exact |
| hetero | mean per-segment estimation error | ₹10.20 | **10.1955** | **A\*** | reproduces, but **not a `hetero.py` output** — see §E1 |
| hetero | true between-segment SD | ₹6.27 | **6.2739** | **A\*** | reproduces, but **not a `hetero.py` output** — see §E1 |
| predict | ridge Spearman ρ | +0.0354 | **+0.0354** | **A** | exact (sd 0.0425, 23/30 worlds ρ>0, t=+4.48) |
| predict | gradient-boosting Spearman ρ | +0.0365 | **+0.0365** | **A** | exact (sd 0.0370, 26/30 worlds ρ>0, t=+5.31) |
| predict | frozen predictor top-5% TEST net | −₹72,983 | **−72,983** | **A\*** | reproduces, but **produced by `policy.py`, not `predict.py`** — see §E2 |
| policy | TRAIN top-5% | −₹39,747 | **−39,747** | **A** | exact |
| policy | TRAIN top-10% | −₹135,723 | **−135,723** | **A** | exact |
| policy | TRAIN top-20% | −₹305,465 | **−305,465** | **A** | exact |
| policy | TRAIN top-50% | −₹772,460 | **−772,460** | **A** | exact |
| policy | TRAIN top-100% | −₹2,560,856 | **−2,560,856** | **A** | exact |
| policy | grid monotonicity → k=0 optimum over tested grid | (stated) | grid reproduces monotone; **k=0 is an inference, not a printed value** | **A (basis)** | see §E3 |

### Additional figures reproduced, not on the submitted list

| script | metric | regenerated |
|---|---|---|
| hetero | SD / \|mean\| ratio | 9.4× |
| hetero | segments per world | 5.1 |
| hetero | arms where NO segment net>0 | 12/40 |
| predict | per-field mean \|Spearman ρ\| | tenure 0.0057 (2/30), orders_90d 0.0066 (2/30), recency 0.0073 (3/30), historical_aov 0.0398 (21/30), segment_id 0.0714 (28/30) |
| predict | segment η² on TEST | 0.00702 |
| policy | TRAIN top-30% / top-75% | −470,018 / −1,361,822 |
| policy | TEST treat-everyone | −1,094,562 |
| policy | TEST realistic segment targeting | −77,209 |
| policy | TEST oracle individual (hindsight) | 3,595,677 |
| policy | segment-targeting experiment cost | 1,093,492 |

All match the transcript verbatim.

---

## E. Explanations for every non-clean entry

**E1 — ₹10.20 and ₹6.27 are not `hetero.py` outputs.** `hetero.py` prints no estimation-error or between-segment-SD figure; `grep` for `seg_err|true_seg_sd|estimation error` returns nothing. These two numbers are aggregates of the `mean_seg_err` and `true_seg_sd` columns of **`targeting.json`** (from `targeting.py`, worlds **20001–20020**): means of 10.1955 and 6.2739. They therefore rest on a **different script and a different world set** (20 worlds, not 10) from the metrics they were listed beside. The values are correct and the artifact exists on disk; only the attribution was wrong.

**E2 — −₹72,983 is not a `predict.py` output.** `predict.py` computes no net contribution at all — it reports correlations and η² only. The figure is printed by **`policy.py`**, whose TRAIN grid appears in the same list. Again: value correct, artifact reproduced, attribution wrong.

**E3 — the "k=0 is the optimum" line is an inference, not an output.** `policy.py` prints the seven-point TRAIN grid and the frozen `k* = 5%`. The monotone ordering reproduces exactly. The statement that the true argmax over k ∈ [0,1] is k = 0 is a reading of that grid, not a number the script emits. Its numeric basis is status A; per constraint G I make no scientific assessment of the reading itself.

**E4 — environment scope caveat (applies to `predict.py` and `policy.py` only).** The rerun used the same interpreter as the original run: **numpy 1.26.4, scipy 1.13.1, scikit-learn 1.5.1**. `requirements.txt` pins **numpy 2.3.5, scipy 1.17.1, scikit-learn 1.9.0**. So these reproductions confirm determinism **within this environment**; they do **not** establish that the gradient-boosting figures (+0.0365, −₹39,747 … −₹2,560,856, −₹72,983) hold under the pinned versions. `hetero.py` is unaffected — pure numpy arithmetic with no RNG and no sklearn.

---

## Side effects of the rerun

| | |
|---|---|
| repository | **unchanged** — `git status --porcelain` empty, HEAD still `4942af6` |
| `_ok.npy` | rewritten by `predict.py` at 19:58:36 in the old scratchpad. Content **byte-identical** to the snapshot copy (both sha256 `fc44e6ca…`). No information lost |
| all other scratchpad JSONs | untouched — `targeting.json` still 12:23:51, `pred.json` still 00:31:59 |
| sealed holdout | not read |
| LLM | not run |

---

## 1. Safe to cite

**All nineteen figures**, with two attribution fixes:

- Every `hetero.py` metric (−₹7.88, ₹74.48, 3.4%, 3.78%, ₹26.88, 28/40, 1/40) — cite as `hetero.py`, **worlds 20001–20010, 10 worlds × 4 arms**.
- ₹10.20 and ₹6.27 — cite as **`targeting.py` / `targeting.json`, worlds 20001–20020**, not `hetero.py`.
- ρ = +0.0354, ρ = +0.0365, η² = 0.00702 and the per-field correlations — cite as `predict.py`, **TEST 20051–20080**.
- −₹72,983 and the whole TRAIN grid — cite as **`policy.py`**, TRAIN 20021–20050 / TEST 20051–20080.
- For the two sklearn-dependent scripts, the citation should record the library versions actually used (§E4) rather than the pinned ones.

## 2. Must be excluded

**None on reproducibility grounds.** Nothing failed to reproduce and no provenance is unestablished. The only things that must not be carried forward as stated are the two **attributions** in E1/E2 — the numbers survive, the labels do not.

## 3. Is any difference material enough to change a scientific conclusion?

**No difference exists to be material.** Every regenerated value equals its historical counterpart at printed precision. The two provenance corrections change which script and which world set a figure is credited to; they change no value. The one open item is scope, not disagreement: the sklearn-derived figures are confirmed deterministic in the environment that produced them and are untested under `requirements.txt`'s pins.

Per constraint G, this report makes no assessment of what any of these numbers imply about targeting.

*Three scripts run once each, unmodified. No file in the repository was modified. Nothing committed. Stopped here.*
