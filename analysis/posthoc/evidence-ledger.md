# MarginPilot — Final Evidence Ledger

**Date:** 1 September 2026 · **Repo:** `main` @ `4942af6`, working tree clean · **Compiled read-only.** Nothing modified, nothing run, nothing committed.

---

## 1. EXECUTIVE VERDICT

The project has a **defensible negative-result submission** and does not have a positive one. Every number below has a named script, a named world set, and a reproducibility status. Three things must change in how the work is described, all of them corrections of attribution rather than of value:

1. **+₹3,595,677 is a hindsight figure, not a ceiling.** It selects on `u_i`, a draw independent of every feature *and every latent*. It must never again be called the targeting ceiling.
2. **0.702% is `segment_id`'s η², not "the six fields".** And it does not prove economic impossibility — R² is scale-free in a way rupees are not.
3. **Two figures were mis-attributed** (₹10.20 / ₹6.27 to `hetero.py`; −₹72,983 to `predict.py`). Values survive; labels do not.

The pre-registered spine (Cycle 1 holdout prediction held; Cycle 2 fixes did not produce a reasoning improvement) is the strongest evidence in the project. The targeting work is **post-hoc** and must be labelled as such throughout.

**Submission blockers exist (§9). None is scientific; all are packaging.**

---

## 2. EVIDENCE LEDGER TABLE

Columns: claim · numerical evidence · source · world set · information set · GT used · pre-reg? · split · repro · limitation.

### 2.1 Pre-registered cycle work

| # | Claim | Evidence | Source | World set | Info set | GT | Pre-reg | Split | Repro | Limitation |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | MarginPilot lost to Baseline 1 on the sealed holdout, exactly as predicted before the seal was opened | prediction in §4h; result in §4i; `int_shipping` chosen in 7 of 9 holdout runs | `docs/simulator.md` §4h/§4i; `data/holdout_results.json` (**committed**) | Cycle-1 sealed holdout, 20 worlds (seeds 9001–9020), opened **once** | agent MerchantView | scoring only | **YES** — §4h written before opening | holdout | not re-runnable (LLM + seal already spent) | absolute rupee figures have no external validity (§5 of simulator.md) |
| E2 | Fix A's false-act rate does **not** differ from control — a *resolved null*, not an unresolved one | control K=8: 4,5,4,5,5,3,6,4 (mean 4.500); Fix A K=3: 5,5,5 (mean 5.000); diff **+0.500**, 95% CI **[−1.377, +2.377]**, MDE 2.82 worlds | §4n; `results/cycle3_fixa_rep{1,2}.json`, `results/cycle3_noise_neither_rep{1..8}.json` (**committed**) | `worlds_cycle2` dev, 20 worlds | agent prompt arms | scoring only | **YES** — §4l pre-registered the contrast and the stopping rule | dev | committed JSONs | Fix A reached K=3, not the specified 8 (credits exhausted); powered anyway at 2.68 < 2.82 |
| E3 | Fix A raises run-rate, and the increase is almost entirely avoided false skips | run_count 11.250 → 15.333, diff **+4.083** CI [+1.116, +7.050]; false_skip 5.250 → 1.667, diff **−3.583** CI [−5.882, −1.285] | §4n | `worlds_cycle2` dev, 20 worlds | as above | scoring only | YES | dev | committed | intervals computed under the worst-case structural SD (conservative) |
| E4 | Fix B never found an answer its lookup table did not already hold | `cwhd = 0` in both Fix-B arms; history-match 6/6 and 6/8; `cwhd = 2` for Fix A (an arm shown no table) | §4n; `results/cycle2_dev_*.json` (**committed**) | `worlds_cycle2` dev, 20 worlds | Fix-B arms carry `InterventionHistory` | scoring only | YES — §4j set the disqualifying condition in advance | dev | committed | **Fix-B arms measured at K=1 each**; the eight zero-variance replicates are the *control*, which does not carry Fix B |
| E5 | A distribution-free variance bound applies to `false_act`; §4m's chi-square upper bound was misspecified | `Var ≤ n/4 = 2`, `SD ≤ √2 = 1.414`; §4m's chi-square upper was **1.884** — beyond what the statistic can reach; required K corrected 8 → **4** | §4n; `src/eval/power.py`, `tests/eval/test_power_bound.py` (**committed**) | property of the corpus (8 skip-optimal of 20) + metric definition | — | no | derived during the cycle | — | committed code + test | corpus-specific: 8 of 20 skip-optimal |
| E6 | Realized-net and `int_shipping` contrasts are **beyond feasible resolution**, reported as such rather than chased | 38.3 s per world-run measured; realized_net needs K=32 ≈ 25 h; int_shipping K=24 ≈ 19 h; `int_shipping` diff −0.042 worlds | §4m/§4n | `worlds_cycle2` dev | — | — | **YES** — §4l committed to reporting infeasibility | dev | throughput measured | a statement about this evaluation's budget, not about the effects |
| E7 | The Cycle-2 sealed holdout was never opened | §4n, §4k, §4m; `worlds_cycle2/holdout/` mtime 28 Aug 16:02 (generation time), unmodified; no diagnostic references `open_holdout`/`final_eval`/`29xxx` | filesystem + source scan | — | — | no | pre-committed stopping rule | — | verified this session | — |

### 2.2 Post-hoc heterogeneity and targeting

| # | Claim | Evidence | Source | World set | Info set | GT | Pre-reg | Split | Repro | Limitation |
|---|---|---|---|---|---|---|---|---|---|---|
| E8 | Per-customer net effect is heterogeneous and mostly zero | mean net **−₹7.88**; within-world SD **₹74.48** (9.4×); net>0 for **3.4%**; genuinely persuaded **3.78%**; segment mean-net spread **₹26.88**; **28/40** world×arm pairs have ≥1 positive segment; **1/40** all-positive; **12/40** none | `hetero.py` (**stdout only, no JSON**) | `worlds_cycle2` dev **20001–20010**, ×4 interventions (40 rows) | none (descriptive) | **YES — reads `Y(0)`/`Y(1)` to score** | **POST-HOC** | dev | **reproduced exactly**, 1 Sep rerun | 10 worlds only; no output artifact — result lived in transcript until the rerun |
| E9 | One experiment per world cannot fund segment targeting on these worlds | realistic **−₹183,653**; CI-gated variant **−₹290,211**; treat-everyone **−₹1,216,639**; pilot spend **₹887,199** | `targeting.py` → **`targeting.json`** (artifact on disk) | `worlds_cycle2` dev **20001–20020** | MerchantView; Baseline-5 sizing; Cycle-1 cost accounting | scoring only | **POST-HOC** | dev | sums re-verified from the JSON | intervention fixed by an observable cheapest-cost rule; single policy family |
| E10 | Per-segment estimation error exceeds the between-segment signal | mean per-segment estimation error **₹10.1955**; true between-segment SD **₹6.2739** (noise ≈ 1.6× signal) | **`targeting.py` / `targeting.json`** — **NOT `hetero.py`** | `worlds_cycle2` dev **20001–20020** | as E9 | scoring only | POST-HOC | dev | recomputed from JSON | **attribution previously stated wrongly**; different script *and* different world set from E8 |
| E11 | Three of the six CustomerView fields carry no individual signal; two do, weakly | mean \|Spearman ρ\|: tenure **0.0057** (2/30 worlds p<.05), orders_90d **0.0066** (2/30), recency **0.0073** (3/30), historical_aov **0.0398** (21/30), segment_id **0.0714** (28/30) | `predict.py` (**stdout only**) | TEST **20051–20080** (20001–20020 excluded as contaminated) | six CustomerView fields | scoring only | POST-HOC | test | **reproduced exactly** | — |
| E12 | `segment_id` explains 0.702% of individual net-effect variance | mean η² = **0.00702** | `predict.py` | TEST **20051–20080** | **`segment_id` alone** | scoring only | POST-HOC | test | reproduced exactly | **this is `segment_id`'s η², not the six fields jointly**; and the frozen predictor could not use `segment_id` |
| E13 | A frozen four-field cross-world predictor transfers with real but tiny rank signal | ridge ρ **+0.0354** (sd .0425, 23/30 worlds ρ>0, t=+4.48, p<.001); GB ρ **+0.0365** (sd .0370, 26/30, t=+5.31, p<.001) | `predict.py` | TRAIN 20021–20050 → TEST 20051–20080 | four numeric fields (`segment_id` excluded — world-specific) | scoring only | POST-HOC | train→test | reproduced exactly | sklearn-version-sensitive (§2.5) |
| E14 | The frozen top-5% policy loses money on held-out worlds | TEST: do-nothing **₹0**; treat everyone **−₹1,094,562**; realistic segment targeting **−₹77,209** (experiment cost ₹1,093,492 inside it); **frozen predictor top-5% −₹72,983**; hindsight oracle **+₹3,595,677** | **`policy.py`** — **NOT `predict.py`** | TEST **20051–20080** | four numeric fields | scoring only | POST-HOC | test | **reproduced exactly** | **attribution previously stated wrongly** |
| E15 | The TRAIN threshold grid is monotone in treated fraction | top 5% **−₹39,747**; 10% −₹135,723; 20% −₹305,465; 30% −₹470,018; 50% −₹772,460; 75% −₹1,361,822; 100% −₹2,560,856; frozen k*=5% | `policy.py` | TRAIN **20021–20050** | four numeric fields | scoring only | POST-HOC | train | reproduced exactly | "k=0 is the optimum" is an **inference from the grid**, not a printed value; 5% was the grid floor |

### 2.3 Post-hoc structural / ceiling work

| # | Claim | Evidence | Source | World set | Info set | GT | Pre-reg | Split | Repro | Limitation |
|---|---|---|---|---|---|---|---|---|---|---|
| E16 | Individual τ is decided by a draw independent of every feature and every latent | `u_i ~ U(0,1)` shared across arms (`generator.py:717`); three-region decomposition; `p1 ≥ p0` always (`:611-623`) | source inspection | — | — | no (source only) | POST-HOC | — | source is committed | — |
| E17 | Three of six CustomerView fields are independent by construction | `tenure_days = U{1,…,1459}`, `orders_last_90d = Poisson(2.0)`, `days_since_last_order = U{0,…,399}` — `generator.py:436-438`, no segment or latent dependence | source inspection | — | — | no | POST-HOC | — | committed source | E11 is the empirical counterpart |
| E18 | `historical_aov_inr` is a latent published with zero noise | `= expected_order_value_inr` verbatim, `contracts.py:340` | source inspection | — | — | no | POST-HOC | — | committed source | — |
| E19 | `observed_margin` is byte-identical to the `M` used in the outcome draw | `contracts.py:324` vs `generator.py:713` | source inspection | — | — | no | POST-HOC | — | committed source | — |
| E20 | τ omits the cost term that decides profitability | `net = τ − cost·1{conv1}` (`harness.py:290-292`); in the always-buyer region τ=0 while net=−cost for the three non-bundle kinds | source inspection | — | — | no | POST-HOC | — | committed source | — |
| E21 | Legitimate ceiling `V*(X) = Σ max(0, E[net|X])` on held-out worlds | **A +₹50,133** (2/30 worlds positive) · **B +₹586,958** (29/30) · **C1 +₹697,695** (30/30) · **C2 +₹733,140** (30/30) · **C3 +₹759,053** (29/30) | `ceiling_obs.py` → `ceiling_obs.json` (**this session's scratchpad, uncommitted**) | `worlds_cycle2` dev **20051–20080**, 30 worlds, 614,109 customers | ladder, §4 below | **NO — `load_ground_truth` never imported** | POST-HOC | test | run once; deterministic QMC | integrates over the generator's own priors and constant tables; §4 assumptions |
| E22 | The ceiling model reproduces an independently measured realization | forward `treat-everyone E[net]`: C2 **−₹1,121,248**, C1 −₹1,158,130 vs **measured −₹1,094,562** (E14) — **2.4%** apart; that number was never an input | `ceiling_obs.py` vs `policy.py` | 20051–20080 | as E21 | no (ceiling side) | POST-HOC | test | — | validation of the structural integral, not of any policy |
| E23 | Rectification bias in the ceiling is negligible | cross-fit (sign from one Sobol half, value from the other) agrees with plug-in **to within ₹5 on ₹759,053**; mean per-customer half-gap **₹0.0203** | `ceiling_obs.py` | 20051–20080 | as E21 | no | POST-HOC | test | — | — |
| E24 | The hindsight/legitimate gap | hindsight **+₹3,595,677** − legitimate C3 **+₹759,053** = **₹2,836,624**, i.e. **78.9%** of the hindsight figure; ratio **4.74×** | E14 + E21 | 20051–20080 | — | hindsight side uses GT | POST-HOC | test | both reproduced | — |
| E25 | Budget and exposure constraints do not bind at the ceiling | spend **₹1,579,389** = **10.0%** of ₹15,866,000 total budget; **41.3%** treated vs **60%** `max_customer_exposure_share`; ceiling = 4.78% of budget (median world 3.22%, max 28.69%) | `ceiling_obs.py`, `src/policy/gates.py` | 20051–20080 | — | no | POST-HOC | test | — | — |

### 2.4 Provenance and real-data boundary

| # | Claim | Evidence | Source | Limitation |
|---|---|---|---|---|
| E26 | `SegmentView.name`/`notes`/`behaviour_tags` have no hidden response variable anywhere in their ancestry | ancestors close at `vocabulary.py:181-265` (a constant) and the world seed (`streams[_STREAM_SEGMENTS]`); `Y(0)`/`Y(1)`, `u_i`, `r_i`, `ε_i`, affinities all live in later/other streams | source inspection | provenance only — see §5 |
| E27 | Those three fields are a bijective key to the withheld response multipliers | same object literal `generator.py:381-388`; 7 distinct names ↔ 7 distinct `(conv, elas, aov, resp)` quadruples; multipliers propagate at `generator.py:405-431` | source inspection | — |
| E28 | `segment_id` is world-specific and carries zero cross-world information | `f"seg_{index}"` over `rng.choice(7, replace=False)`; archetype at each position is uniform → exchangeable | source inspection | within a world it partitions; identifying which partition needs the join or an experiment |
| E29 | The notes' RFM claims are not implemented in the observable fields | "then nothing for a quarter", "order on salary week" vs `generator.py:436-438` | source inspection | only the basket-size fragment has a realized counterpart, via `aov_multiplier` |
| E30 | Hillstrom has no cost side | 64,000 × 12, sha256 `0e5893…aece`; column scan for `cost\|price\|margin\|discount\|coupon\|offer\|fee` → **NONE**; treatment is an email send | `hillstrom.csv` (scratchpad, uncommitted) | §6 |
| E31 | Hillstrom randomization is clean; spend is too sparse for HTE | max SMD **0.0169** across 18 covariates; zero nulls; spend==0 for **99.0969%**, **578 spenders**; conversion ≡ `1{spend>0}` exactly; conversion MDE 35.8% full-arm, **101%** at ⅛ arm | descriptive audit | no model fitted, no cost invented |

### 2.5 Reproducibility status

| # | Claim | Evidence | Limitation |
|---|---|---|---|
| E32 | The Cycle-2 corpus regenerates byte-for-byte from committed seeds | `DEV_SEEDS = range(20_001, 20_081)` at `src/world/__main__.py:37`; worlds 20001 / 20051 / 20080 hash-identical disk vs fresh; `GENERATOR_VERSION 4.0.0` | 3 of 80 sampled |
| E33 | `hetero.py`, `predict.py`, `policy.py` reproduce every figure exactly | one unmodified run each, exit 0, all printed digits identical | **run in the same environment that produced them** |
| E34 | The recording environment does not match the pins | installed numpy 1.26.4 / scipy 1.13.1 / **sklearn 1.5.1**; pinned 2.3.5 / 1.17.1 / **1.9.0** | affects E13/E14/E15 only; E8 is pure numpy |
| E35 | Nine post-hoc diagnostics hardcode `/private/tmp` output paths and are uncommitted | `ceiling.py:112`, `ceiling2.py:89`, `ceiling3.py:76`, `confound.py:65`, `history_leak.py:71`, `learncost.py:72`, `predictability.py:57`, `proxy.py:74`, `targeting.py:95` | see §9 |

### 2.6 Inventoried but NOT read — no claim may rest on these

`ceiling.json`, `ceiling2.json`, `ceiling3.json`, `confound.json`, `history_leak.json`, `learncost.json`, `pred.json`, `proxy.json`, `baselines20.json`.

I read only their **docstrings** (question asked), never their contents. **No number from any of them appears in this ledger, and none may enter the submission without first being read.** `baselines20.json` additionally has no recoverable producing command.

---

## 3. PROVEN

Directly established by source or by reproducible evaluation.

| | |
|---|---|
| P1 | The Cycle-1 holdout prediction, written before the seal was opened, held. **(E1)** |
| P2 | Fix A's false-act rate is a **resolved null** against control — designed for 2.82 worlds, observed 0.500, CI [−1.377, +2.377]. **(E2)** |
| P3 | Fix A's run-rate increase is real and is composed almost entirely of avoided false skips. **(E3)** |
| P4 | `false_act` obeys a distribution-free `SD ≤ √2` bound; §4m's chi-square upper of 1.884 was misspecified, inflating required K from 4 to 8. **(E5)** |
| P5 | The Cycle-2 sealed holdout has never been opened. **(E7)** |
| P6 | `tenure_days`, `orders_last_90d`, `days_since_last_order` are independent of every latent by construction, and cannot carry signal under any method. **(E17, E11)** |
| P7 | `historical_aov_inr` is a latent published with zero noise; `observed_margin` is byte-identical to the outcome-draw margin. **(E18, E19)** |
| P8 | `net = τ − cost·1{converted}`; τ is 0 for always-buyers on the three non-bundle interventions while net is −cost. **(E20)** |
| P9 | `u_i` is independent of every feature **and every latent**, so `Σ max(0, net_i)` is a hindsight bound, not a feature-based ceiling. **(E16)** |
| P10 | `SegmentView.name`/`notes`/`tags` have no hidden response variable in their ancestry, and are a bijective key to the withheld multipliers. **(E26, E27)** |
| P11 | `segment_id` alone carries zero cross-world information (exchangeable positional label). **(E28)** |
| P12 | The Cycle-2 corpus regenerates byte-for-byte from committed seeds. **(E32)** |
| P13 | The three stdout-only diagnostics reproduce exactly in the original environment. **(E33)** |
| P14 | Hillstrom contains no cost column; its treatment is an email send. **(E30)** |
| P15 | Hillstrom is cleanly randomized (max SMD 0.0169), has zero nulls, and `conversion ≡ 1{spend>0}`. **(E31)** |

## 4. SUPPORTED BUT LIMITED

| | Claim | Why limited |
|---|---|---|
| L1 | Fix B never found an answer its table did not hold (`cwhd = 0`) **(E4)** | the Fix-B arms were measured at **K = 1 each**; the eight zero-variance replicates belong to the control, which does not carry Fix B. Cannot be strengthened — credits exhausted |
| L2 | Fix A's realized net is directionally worse (−₹898,820 vs −₹824,814) | **not resolved** — beyond feasible resolution at 38.3 s/world-run **(E6)** |
| L3 | Segment targeting funded by one experiment loses ₹183,653 on 20 dev worlds **(E9)** | one policy family, one observable intervention rule, 20 worlds, post-hoc |
| L4 | Estimation error (₹10.20) exceeds between-segment signal (₹6.27) **(E10)** | a property of the Baseline-5 experiment sizing on **worlds 20001–20020**, not a general statement |
| L5 | The frozen four-field predictor loses ₹72,983 on held-out worlds **(E14)** | one predictor family, one treated-fraction grid whose floor was 5%, four fields — a **subset** of the six. Says nothing about richer information sets |
| L6 | The four-field predictor transfers with ρ ≈ +0.035, p<0.001 **(E13)** | rank signal only; sklearn-version-sensitive **(E34)** |
| L7 | `segment_id` explains 0.702% of individual variance **(E12)** | it is `segment_id`'s η², measured on TEST; the frozen predictor never had this field. **It does not bound economic value** |
| L8 | The legitimate ceiling is +₹50,133 (A) rising to +₹759,053 (C3) **(E21)** | assumes `E[net\|X]` known **exactly**; integrates over the generator's own priors; levels B+ require the archetype and seasonal **constant tables**; `baseline_conversion` recovery ignores clipping; C3 uses a normal likelihood on the history statistic. Validated against one forward quantity **(E22)** and cross-fitted **(E23)** |
| L9 | 78.9% of the old +₹3.6M figure is hindsight **(E24)** | rests on L8's ceiling being the right comparator |
| L10 | Hillstrom could test whether observable pre-campaign features locate a high-uplift cohort **(E31)** | `visit` is the only endpoint with power; conversion is coarse-only; spend at 578 non-zero rows is too sparse. **No model was fitted** |

## 5. NOT ESTABLISHED / DO NOT CLAIM

| | Do not claim | Why |
|---|---|---|
| N1 | "The oracle ceiling is +₹3.6M" | it is hindsight — selects on `u_i`, unreachable by **any** feature set including full latent knowledge **(P9)** |
| N2 | "0.7% of variance proves targeting is economically impossible" | R² is invariant to independent outcome noise while policy value is not; and the Cauchy–Schwarz bound `V* ≤ √(R²·Var(net))` permits a per-world value of the same order as the budget. **The measurement is real; the implication is not** |
| N3 | "The six observable fields carry 0.7% of variance" | 0.702% is **`segment_id`'s** η². The four-field predictor did not have that field **(E12)** |
| N4 | "Merchant-observable behavioural history carries no targeting signal" | in this corpus RFM was *defined* independent of every latent **(P6)**. The result restates the construction |
| N5 | "A positive ceiling means an estimator can earn positive net after experiment cost" | `V*` assumes `E[net\|X]` known exactly and charges no learning cost. **Never assert this** |
| N6 | "SegmentView is realistic merchant information" | provenance is established; **realism was explicitly not judged** and no evidence in this project bears on it |
| N7 | "Hillstrom validates MarginPilot" | no cost side ⟹ `net = τ` ⟹ any positive uplift is profitable; the incrementality-leakage tension cannot be reproduced there **(P14)** |
| N8 | "₹10.20 / ₹6.27 come from `hetero.py`" · "−₹72,983 comes from `predict.py`" | both mis-attributed. Correct sources: `targeting.py` (20001–20020) and `policy.py` (20051–20080) **(E10, E14)** |
| N9 | Any number from `ceiling*.json`, `confound.json`, `history_leak.json`, `learncost.json`, `pred.json`, `proxy.json`, `baselines20.json` | **contents never read** (§2.6) |
| N10 | "The targeting analysis was pre-registered" | all of §2.2–§2.4 is **post-hoc**, performed after Cycle 2 closed |
| N11 | Absolute rupee figures as externally valid | `docs/simulator.md` §5 already disclaims this. The comparisons are the claim |
| N12 | "The sklearn figures reproduce under `requirements.txt`" | reproduced only in the original environment; pins differ **(E34)** |

---

## 6. FINAL SCIENTIFIC CLAIM

**One sentence.**
> On a frozen 20-world simulated corpus with a pre-registered design, an LLM-driven promotion agent that measures *incremental contribution* correctly predicted its own failure against a do-nothing baseline, and two pre-registered fixes did not produce a measurable reasoning improvement; a subsequent post-hoc analysis of customer-level targeting on held-out worlds found that the tested predictor and policy family lost money, while a structural expected-value ceiling shows that most of the apparent targeting opportunity in the naive oracle was hindsight rather than recoverable value.

**Executive summary.**
> MarginPilot is an autonomous merchant-growth agent built around a measurement spine rather than a feature list: randomization, a pre-committed horizon, a policy gate the LLM cannot bypass, and an append-only audit log. Its central pre-registered result is a negative one, and it held — §4h predicted, before the seal was opened, that the agent would lose to do-nothing on the sealed holdout with an `int_shipping` selection bias as the mechanism, and it did. Cycle 2 proposed two fixes and pre-registered a disqualifying condition for each; on 20 dev worlds Fix B never identified a better intervention than its own lookup table (`cwhd = 0`, K=1 per arm), and Fix A's false-act rate resolved as a null against control (+0.500 worlds, 95% CI [−1.377, +2.377]) while its run-rate increase turned out to be avoided false skips. The Cycle-2 holdout was never opened, which was the pre-registered outcome. Afterwards — and explicitly post-hoc — we examined whether customer-level targeting could pay. On held-out dev worlds 20051–20080 a frozen four-field predictor lost ₹72,983 against a do-nothing floor. Source inspection then established that three of the six merchant-visible customer fields are independent of every latent by construction, that `net = τ − cost` while the analysis had regressed τ alone, and that the previously quoted "+₹3.6M oracle ceiling" selects on a per-customer uniform draw independent of every feature *and every latent* — making it a hindsight bound, not a targeting ceiling. A structural expected-value ceiling computed without any ground truth puts the legitimate figure at +₹50,133 on the six fields alone and +₹759,053 on the richest observable set, meaning **78.9% of the earlier figure was hindsight**. A feasibility audit of the Hillstrom e-mail experiment established that it has no cost side and therefore cannot test the net-contribution mechanism at all.

**What we proved.** P1–P15 above.

**What we did NOT prove.** N1–N12 above. In particular: that any estimator can earn positive net contribution after paying for experimentation; that the simulator's negative targeting result generalizes to real merchant data; that `SegmentView` corresponds to information a real merchant holds; and that targeting is economically impossible on information-theoretic grounds.

---

## 7. WHAT THE DEMO CAN SAFELY SAY

Safe, in this order:

1. "The agent proposes; a deterministic policy gate disposes. The LLM never assigns an arm, sets a budget, or sets a discount ceiling." — architecture, verifiable in `src/policy/` and `src/experiment/`.
2. "We pre-registered a prediction that we would lose, and we lost, for the reason we named." — E1.
3. "A +50% conversion lift that destroys ₹3,600 of contribution at pilot scale." — the README's worked example, consistent with the ₹50,000 budget.
4. "We measured our own evaluation's noise floor before trusting its differences, found our conservative bound was itself misspecified, and corrected it." — E5.
5. "We pre-committed a disqualifying condition for each fix, and both fired." — E2/E4, with L1's K=1 caveat stated aloud.
6. "The holdout stayed sealed, because the pre-registered rule said it should." — E7.
7. "Our own headline oracle number was wrong — it measured hindsight. The legitimate ceiling is 4.7× smaller." — E24, presented as a correction we found ourselves.

Do **not** say on stage: any N1–N12 item; any number from §2.6; or any absolute rupee figure without "on this corpus".

---

## 8. TOP 10 JUDGE ATTACKS + ANSWERS

| # | Question | Evidence-backed answer | Status |
|---|---|---|---|
| 1 | **"Isn't the simulator rigged?"** | Parameter ranges are sourced to published elasticity literature (`docs/simulator.md`, five citations) and were fixed before any agent existed. The generator is a pure function of a seed; worlds 20001/20051/20080 regenerate byte-identically from committed constants. Bundles were **de-rigged** when found to be free money: the uplift is now priced against its own break-even (`generator.py:530-535`). And the simulator produced a result *against* us — we predicted our own loss and took it. | **PROVEN** |
| 2 | **"Why not just target using the hidden segment information?"** | Because it is not hidden in the way the code claims. `SegmentView` withholds the four multipliers (`contracts.py:119-120`) but publishes `name`, and 7 names map one-to-one onto 7 multiplier quadruples in a module constant (`vocabulary.py:181-265`). Using it is informationally identical to reading the multipliers. Our Level-B ceiling did exactly that, and we label it as such rather than as a merchant-realistic result. | **PROVEN** (provenance) / **UNKNOWN** (realism, N6) |
| 3 | **"Why does the agent sometimes recommend doing nothing?"** | Because on this corpus one experiment costs roughly 2.8× the profit pool of the world it runs in (`contracts.py`), and the scaling rule requires P(net>0) ≥ 0.80 with a bounded 5th-percentile loss. Do-nothing is a legitimate answer and is Baseline 1. `policy.py`'s TRAIN grid is monotone — every tested treated fraction loses, and the grid floor was 5%. | **PROVEN** (E15) |
| 4 | **"Where is the profitable campaign?"** | There isn't one, and we report that. Cycle 1 lost on the sealed holdout as predicted; the post-hoc frozen predictor lost ₹72,983 on held-out worlds; treat-everyone loses ₹1,094,562. The project's claim is the measurement discipline, not a win. | **PROVEN** |
| 5 | **"How do you know the targeting ceiling is real?"** | It is a structural integral over the generator's own priors — `load_ground_truth` is never imported. Two independent checks: its forward prediction of treat-everyone (−₹1,121,248) lands 2.4% from the separately measured −₹1,094,562, a number that was never an input; and cross-fitting (policy sign from one Sobol half, value from the other) agrees with the plug-in to within ₹5 on ₹759,053. | **LIMITED** (L8 — assumes `E[net\|X]` known exactly, charges no learning cost) |
| 6 | **"Why isn't the ₹3.6M oracle your ceiling?"** | Because it selects on `u_i` — one U(0,1) draw per customer, shared across arms, independent of every feature **and every latent** (`generator.py:717`). No information set can reach it, so the gap it opens is guaranteed by conversion noise rather than informative about targeting. The legitimate ceiling is +₹759,053; **78.9% of the ₹3.6M was hindsight**. We found this error ourselves and corrected it. | **PROVEN** (P9, E24) |
| 7 | **"Why didn't you validate on real data?"** | We tried, and audited the candidate rather than using it. Hillstrom (64,000 × 12, sha256 `0e5893…aece`) is cleanly randomized but has **no cost column** and its treatment is an email send. With free treatment `net = τ`, so any positive uplift is profitable and the incrementality-leakage tension cannot exist. We did not invent a discount cost to manufacture it. | **PROVEN** (P14) |
| 8 | **"Did you tune anything after seeing the results?"** | Not on any sealed corpus. `worlds_cycle2/holdout/` has never been read (E7). Cycle 2's corpus was frozen before §4l was written, so the MDE could not be tuned to the outcome. The targeting work is **post-hoc and labelled as such** (N10). Where a threshold was chosen, it was chosen on TRAIN and frozen before TEST (`policy.py`). | **PROVEN** for seals; **LIMITED** — post-hoc analyses are honestly disclosed, not eliminated |
| 9 | **"How do you know your results reproduce?"** | Worlds regenerate byte-for-byte from committed seeds. The three stdout-only diagnostics were re-run once, unmodified, and returned every figure to the last printed digit. Caveat stated in the open: the rerun used the same environment that produced them (sklearn 1.5.1), which is **not** what `requirements.txt` pins (1.9.0). | **PROVEN** in-environment; **LIMITED** under the pins (E34) |
| 10 | **"Can this generalize to real merchants?"** | No, and we say so. `docs/simulator.md` §5 already states absolute results have no external validity. The specific negative targeting result is *less* generalizable than most, because three of the six fields were generated independent of every latent while the segment prose describes them in RFM language — so the finding partly restates the implementation. | **PROVEN** that it does not generalize as stated; **UNKNOWN** what real data would show |

---

## 9. SUBMISSION BLOCKERS

| # | Blocker | Severity | Note |
|---|---|---|---|
| B1 | **`docs/architecture.md` is 0 lines.** Day 10–11 deliverable and a judged artifact. | **High** | — |
| B2 | **Nine post-hoc diagnostics are uncommitted and hardcode `/private/tmp` output paths** (E35). A reviewer cannot re-run them. | **High** | every prior cycle committed its raw output; `.gitignore:71` even carries a bespoke exception for exactly this reason |
| B3 | **No notebook section (§4o) exists for the targeting cycle.** Eight reported figures, no pre-registration, no committed record. | **High** | breaks the project's own evidentiary standard |
| B4 | **`hetero.py`, `predict.py`, `policy.py` produce no output artifact.** Their figures existed only in a transcript until this session's rerun. | Medium | reproduced, but nothing on disk to diff against |
| B5 | **Environment does not match `requirements.txt`** (E34). A clean-clone reviewer runs different sklearn. | Medium | affects E13/E14/E15 |
| B6 | **This session's artifacts live only in volatile `/private/tmp`** — five reports, `ceiling_obs.py`/`.json`, `hillstrom.csv`. Not in the 18:26 snapshot. | Medium | one reboot from loss |
| B7 | **`results/holdout_evaluation.json` is untracked**, while `data/holdout_results.json` is committed. | Low | clarify which is the citable artifact |
| B8 | **§2.6 artifacts are unread.** Nine JSONs whose contents no one has examined. | Low | fine if excluded; a blocker only if cited |

None of these is a scientific defect. All are packaging, and all are fixable inside the remaining Day 9–11 window before the 5 September deadline.

---

*Compiled read-only from the committed repository and preserved artifacts. No source, simulator, generator, seal, cycle, diagnostic, or result was modified. Nothing was run. Nothing was committed.*
