# Post-hoc Targeting Analysis

**Post-hoc. Not pre-registered.** Conducted 1 September 2026, after Cycle 2 closed. See `../README.md` for what that means and what is true of every analysis here.

This report exists to record **corrected attributions**. Several figures from this work were, at the time, credited to the wrong script or the wrong world set, and two claims were stated more strongly than the evidence supports. The numbers themselves reproduced exactly; the labels did not survive review.

---

## 1. The four scripts, and exactly what each produced

| script | question | world set | information set | output |
|---|---|---|---|---|
| `hetero.py` | Is there per-customer treatment-effect heterogeneity to target at all? | `worlds_cycle2` dev **20001–20010**, all 4 interventions (40 world×arm rows) | none — descriptive; groups by `segment_id` | **stdout only** |
| `targeting.py` | Can realistic signal support profitable targeting under one experiment per world? | `worlds_cycle2` dev **20001–20020** | MerchantView; Baseline-5 experiment sizing; Cycle-1 cost accounting | `outputs/targeting.json` |
| `predict.py` | Do the observable customer fields predict individual treatment effect? | TRAIN **20021–20050** → TEST **20051–20080** | six `CustomerView` fields (model uses four; see §3) | **stdout only** |
| `policy.py` | What does a frozen observable-based targeting policy earn on held-out worlds? | TRAIN **20021–20050** → TEST **20051–20080** | four numeric fields | **stdout only** |

All four read `Y(0)`/`Y(1)` **to score outcomes only** — never to inform a predictor, choose an intervention, or size an experiment. None touches the sealed holdout. None runs the LLM.

`predict.py` and `policy.py` deliberately **exclude worlds 20001–20020**, because the earlier diagnostics examined those worlds and they are therefore contaminated for a transfer question.

---

## 2. Corrected attributions

These are the errors, stated plainly so they are not repeated.

| figure | was credited to | **actually produced by** | world set |
|---|---|---|---|
| mean per-segment estimation error **₹10.20** | `hetero.py` | **`targeting.py` → `outputs/targeting.json`** (mean of `mean_seg_err` = 10.1955) | **20001–20020** |
| true between-segment SD **₹6.27** | `hetero.py` | **`targeting.py` → `outputs/targeting.json`** (mean of `true_seg_sd` = 6.2739) | **20001–20020** |
| frozen predictor top-5% TEST net **−₹72,983** | `predict.py` | **`policy.py`** | **20051–20080** |

`hetero.py` prints no estimation-error or between-segment-SD figure at all — `grep` for `seg_err|true_seg_sd|estimation error` returns nothing. `predict.py` computes no net contribution at all; it reports correlations and η² only.

**The two mis-attributed segment figures also come from a different world set than the metrics they were listed beside** — 20 worlds, not the 10 that `hetero.py` used. They must not be quoted alongside `hetero.py`'s statistics as though they shared a scope.

---

## 3. `η² = 0.702%` is `segment_id` alone

`predict.py` computes a one-way η² of individual net effect **on `segment_id`**, on TEST worlds. It is **not** the variance explained by the six `CustomerView` fields jointly, and it must never be described that way.

Two facts make the distinction load-bearing:

- `segment_id` was the **strongest** of the five fields measured (mean |Spearman ρ| 0.0714, vs 0.0398 for `historical_aov_inr` and 0.0057–0.0073 for the three RFM fields).
- The frozen cross-world predictor **could not use `segment_id` at all** — it is a per-world positional label, so it does not transfer. `FIELDS` in both `predict.py` and `policy.py` is four items: `tenure_days`, `orders_last_90d`, `days_since_last_order`, `log1p(historical_aov_inr)`.

So the 0.702% describes a field the −₹72,983 model never had.

---

## 4. Scope of the heterogeneity statistics

`hetero.py`'s figures — mean net **−₹7.88**, within-world SD **₹74.48**, **3.4%** positive-net, **3.78%** genuinely persuaded, segment mean-net spread **₹26.88**, **28/40** world×arm pairs with ≥1 positive segment, **1/40** all-positive, **12/40** none — are computed on **10 dev worlds (20001–20010) × 4 interventions**.

They are **descriptive statistics of the training-side corpus**. They are **not** held-out transfer evidence and must not be presented as such.

---

## 5. `k = 0` is an inference, not an output

`policy.py` prints a seven-point TRAIN grid and the frozen `k* = 5%`:

| treated fraction | TRAIN net |
|---|---|
| top 5% | **−₹39,747** ← frozen |
| top 10% | −₹135,723 |
| top 20% | −₹305,465 |
| top 30% | −₹470,018 |
| top 50% | −₹772,460 |
| top 75% | −₹1,361,822 |
| top 100% | −₹2,560,856 |

Every tested fraction loses, and net rises monotonically as the treated fraction falls. The statement that the true argmax over k ∈ [0,1] is therefore **k = 0** is a **reading of that grid**, not a value the script emits — 5% was simply where the grid stopped. The monotonicity is measured; the extrapolation to k = 0 is an inference and should be labelled one.

## 6. Held-out results (`policy.py`, TEST 20051–20080)

| policy | net contribution |
|---|---|
| do-nothing | ₹0 |
| treat everyone | −₹1,094,562 |
| realistic segment targeting (1 experiment, cost ₹1,093,492 included) | −₹77,209 |
| frozen observable predictor, top 5% | **−₹72,983** |
| hindsight selection on realized outcomes | +₹3,595,677 — **see `../ceiling/README.md`; this is not a ceiling** |

And on worlds **20001–20020** (`targeting.py`, a different set — do not merge with the above):

| policy | net contribution |
|---|---|
| treat everyone | −₹1,216,639 |
| realistic segment targeting | −₹183,653 |
| same, CI-gated per segment | −₹290,211 |
| pilot spend inside those figures | ₹887,199 |

---

## 7. Two claims are retired

**Retired claim 1 — "0.7% of variance proves targeting is information-theoretically impossible."**

Invalid. R² is a ratio whose denominator is irreducible outcome noise that no policy has to fight. Adding independent noise to the outcome leaves every policy's expected value **exactly unchanged** while driving R² toward zero, so no threshold on R² implies an economic conclusion on its own. The measurement (η² = 0.702% for `segment_id` on TEST worlds) stands; the inference drawn from it does not.

**Retired claim 2 — "₹3.6M is the targeting ceiling."**

Invalid. That figure selects on `u_i`, a single `U(0,1)` draw per customer shared across both arms and independent of every feature **and every latent** (`src/world/generator.py:717`). It is a bound on hindsight, not on targeting. See `../ceiling/README.md` for the legitimate quantity.

---

## 8. Durable provenance for the three stdout-only scripts

`hetero.py`, `predict.py` and `policy.py` wrote **no machine-readable output**. Their figures existed only in a session transcript until 1 September 2026, when each was re-run **once, unmodified**, and the captured console output was preserved at `stdout/rerun-2026-09-01.log`.

**That log is historically recorded stdout, not machine-readable diagnostic output.** No JSON has been fabricated for these three scripts, and none should be: inventing a structured artifact and presenting it as an original output would misrepresent what the scripts produced.

| | |
|---|---|
| **scripts** | `hetero.py`, `predict.py`, `policy.py` (unmodified; `predict.py` carries an output-path correction for its `_ok.npy` sentinel only) |
| **historical metrics** | §1, §4, §5, §6 above |
| **world sets** | `hetero` 20001–20010 · `predict`/`policy` TRAIN 20021–20050, TEST 20051–20080 |
| **feature sets** | `hetero` none (descriptive) · `predict`/`policy` four numeric fields; `segment_id` measured separately in `predict.py`, never modelled |
| **execution environment** | numpy 1.26.4, scipy 1.13.1, scikit-learn 1.5.1 — see `../reproducibility/environment.md` |
| **reproducibility result** | every printed figure reproduced **exactly**, to the last digit; all three exited 0 |
| **original provenance** | first executed 1 September 2026 in a Claude Code session; console output preserved in that session's transcript and re-captured in `stdout/rerun-2026-09-01.log` |
| **limitations** | reproduced in the environment that originally produced them, **not** under the newer `requirements.txt` pins; `predict.py` and `policy.py` use scikit-learn gradient boosting and are the version-sensitive ones. `hetero.py` is pure numpy with no RNG |
