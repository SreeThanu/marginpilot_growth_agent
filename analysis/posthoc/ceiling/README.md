# Post-hoc Ceiling Analysis

**Post-hoc. Not pre-registered.** See `../README.md`.

This directory holds two different kinds of ceiling, and the distinction between them is the point.

---

## 1. The distinction that matters

**A — hindsight selection on realized outcomes.** Take each customer's realized `net_i` from `Y(0)`/`Y(1)` and sum the positive ones: `Σ max(0, net_i)`. On held-out worlds 20051–20080 this is **+₹3,595,677**.

This is **not a targeting ceiling.** In the generator, whether a given customer converts is decided by `u_i` — one `U(0,1)` draw per customer, shared across both arms (`src/world/generator.py:717`) — which is independent of every observable feature **and of every latent parameter**. No information set can recover any part of it: not the six `CustomerView` fields, not the full `WorldParams`, not omniscience over every customer latent. The gap this figure opens is guaranteed by the presence of conversion noise in any stochastic simulator, and says nothing about this one's features.

**B — information-conditioned expected-value ceiling.** For a feature set `X`, the value of the best policy measurable in `X` is

```
V*(X) = Σ_i max( 0, E[net_i | X_i] )
```

with the expectation integrating over everything `X` does not contain — `u_i`, the pull-forward draw, the basket noise, and the unobserved latents — **against the generator's own prior distributions**. This is the quantity a targeting claim needs.

`ceiling_obs.py` computes B. It imports `src.world.persistence.load_world` only and **never imports `load_ground_truth`**; no realized outcome enters it at any point.

---

## 2. Levels actually evaluated

Held-out world set: **`worlds_cycle2` dev 20051–20080** — 30 worlds, 614,109 customers. Intervention fixed per world by the same observable rule `policy.py` used (cheapest incentive per treated order at observed AOV), so the figures are comparable with the targeting results.

| level | information set `X` | ceiling (plug-in) | cross-fit | worlds > 0 |
|---|---|---|---|---|
| **A** | the six `CustomerView` fields alone | **+₹50,133** | +₹50,131 | **2 / 30** |
| **B** | A + `SegmentView.name` / `behaviour_tags` / `notes` | **+₹586,958** | +₹586,954 | 29 / 30 |
| **C1** | B + world scalars: `observed_margin`, seasonality decode, recovered baseline conversion | **+₹697,695** | +₹697,694 | 30 / 30 |
| **C2** | C1 + the four coupled semantic signals (Bayes at 0.78 TP / 0.18 FP) | **+₹733,140** | +₹733,138 | 30 / 30 |
| **C3** | C2 + `InterventionHistory` (importance weighting on the world scenario) | **+₹759,053** | +₹759,049 | 29 / 30 |

Intervention parameters (`kind`, discount magnitudes, bundle value) are included at every level, since without them `net` is undefined.

**The gap.** Hindsight **+₹3,595,677** − legitimate C3 **+₹759,053** = **₹2,836,624**, i.e. **78.9% of the hindsight figure is unreachable by construction**; the hindsight number is **4.74×** the legitimate one.

---

## 3. The two validations that were run

**Forward-expectation check.** `treat-everyone E[net]` is a pure forward prediction of the structural model — it was never an input to it. The best-informed level predicts **−₹1,121,248** (C2) and **−₹1,158,130** (C1) against the **independently measured −₹1,094,562** from `policy.py` on the same worlds: **2.4% and 5.8% apart**. Levels A and B sit further off (−₹1,201,210 and −₹1,296,583) precisely because they integrate over `observed_margin`, seasonality and baseline conversion instead of reading them.

**Cross-fit check.** `Σ max(0, Ê)` is upward-biased when `Ê` is noisy, because `max` rectifies noise. The scenario set was split into two independent scrambled Sobol halves, the treat/skip sign taken from one and the value scored on the other, symmetrized. **Plug-in and cross-fit agree to within ₹5 on a ₹759,053 total** (mean per-customer half-gap ₹0.0203), so rectification bias is not driving the result.

**Constraints.** At the C3 ceiling the expected incentive spend is ₹1,579,389 = **10.0%** of the ₹15,866,000 promotion budget across those 30 worlds, and 41.3% of customers are treated against a 60% `max_customer_exposure_share` cap. Neither constraint binds.

---

## 4. Assumptions the ceiling requires

1. **`E[net|X]` is known exactly.** `V*` is the value of a policy that already knows the conditional expectation. It is an upper bound on what any policy over `X` could achieve, not a description of an achievable one.
2. **No cost of learning is charged.** `V*` contains no experiment, no pilot, and no estimation. Every real policy must pay to learn `E[net|X]`, and that cost is exactly what turned a positive segment-level opportunity into a realized loss elsewhere in this project.
3. **Integration is against the generator's own priors**, read from `_sample_params` and `_sample_customers`.
4. **Levels B and above use the generator's constant tables** — `SEGMENT_ARCHETYPES` and `SEASONAL_EVENTS`. That is simulator information structure. Whether it corresponds to information a real merchant holds is **not** established here; see `../provenance/segmentview.md`.
5. **Two approximations:** `baseline_conversion` recovery inverts the mean of `p0` while ignoring its clip at 0.005/0.60; the C3 history weighting uses a normal likelihood on the reported statistic with its own reported standard error.
6. **No closed form exists** — `clip`, `−|·|` and a random exponent in `p1 = 1 − (1−p0)^m` rule it out. The integral is exactly specified and evaluated by deterministic quasi-Monte-Carlo (scrambled Sobol, 4,096 scenarios, 15 dimensions, common random numbers across the AOV grid).

---

## 5. What this does and does not establish

**Does establish.** A legitimate, information-conditioned ceiling exists and is positive at every level; on the six `CustomerView` fields alone it is +₹50,133 across 30 worlds, positive in 2 of them and zero at the median. Most of the apparent opportunity in the hindsight figure — 78.9% of it — is not recoverable by any information set.

**Does NOT establish — and must never be claimed:**

> **A positive theoretical ceiling does not prove that a real estimator can achieve positive net contribution after experimentation cost.**

`V*` assumes exact knowledge of `E[net|X]` and charges nothing for acquiring it. Nothing in this directory bears on whether an estimator built from data, paying for its own experiments, could clear zero. It also establishes nothing about real merchants — see `docs/simulator.md` §5.

---

## 6. The other ceilings in this directory

`ceiling.py`, `ceiling2.py`, `ceiling3.py` are earlier probes into the **economic ceiling of learning-by-experiment** (idealised updating; honest updating with a fixed test order; order-agnostic average over all 4! orders), on `worlds_cycle2` dev worlds with Baseline-5 accounting. Their outputs are preserved in `outputs/`.

**Their contents were never analysed.** No figure from `ceiling.json`, `ceiling2.json` or `ceiling3.json` appears in the evidence ledger, and none may be cited without first being read. See `../probes/README.md` for the same caveat applied to the other preserved probes.
