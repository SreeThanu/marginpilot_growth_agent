# The MarginPilot world generator

This document specifies the world model **before** the code that implements it, and exists to answer one criticism: *"you built the world so your agent would look good."*

Every structural parameter MarginPilot's worlds sample from is listed below with its range and the basis for that range. Each row is labelled:

- **Sourced** — the range is anchored on a published empirical estimate, cited.
- **Derived** — follows arithmetically from a sourced row or from the README's worked example.
- **Assumption** — chosen by me. No citation is claimed. These are the rows a sceptical reviewer should attack first, and they are marked so that attack is easy.

Nothing here was tuned after seeing evaluation output. If a range changes after Day 9, that change is recorded in git history and reported.

---

## 1. What a "world" is

A world is one merchant: a catalogue, a customer base with segment structure, a promotion budget, a trading calendar, and a set of latent behavioural parameters that determine how customers respond to promotions. Worlds are sampled i.i.d. from the distributions below.

100 worlds are generated. 80 go to `worlds/dev/` and are used for all design, tuning and prompt iteration. 20 go to `worlds/holdout/`, are sealed by `src/eval/guard.py`, and are opened once at final evaluation.

Two properties are mandatory in every world from the first one generated (CLAUDE.md invariant 8), because neither can be retrofitted onto worlds an agent has already been tuned against:

**Semantic context.** Worlds carry human-readable business context — product names, categories and descriptions, inventory age per SKU, qualitative segment notes, seasonal and competitor events, customer-service themes. This exists so the LLM faces a genuine reasoning problem over unstructured merchant context rather than a menu of enumerable options. It is generated from templates and a controlled vocabulary; **no LLM is called inside the generator**, so worlds stay deterministic, free and offline.

**Hidden potential outcomes.** For every customer × intervention the generator draws both `Y(0)` (outcome if untreated) and `Y(1)` (outcome if treated). An experiment observes exactly one per customer, as in reality; the harness knows both, which is what lets Day 9 report estimation error against the true individual effect `τᵢ = Yᵢ(1) − Yᵢ(0)` separately from decision quality. `Y(0)`/`Y(1)` are written to a separate file, are visible to `src/eval/` only, and no agent tool may ever return them.

---

## 2. Response model

A customer `i` offered intervention `j` converts with probability

```
liftᵢⱼ = (1 − dᵢⱼ)^εᵢ − 1                       # constant-elasticity demand
xᵢⱼ    = sᵢ · aⱼ · max(liftᵢⱼ, 0)               # raw response
mᵢⱼ    = 1 + A·(1 − exp(−xᵢⱼ / A)),  A = 2      # demand saturation
p₁ᵢⱼ   = 1 − (1 − p₀ᵢ)^mᵢⱼ                      # probability transform
```

where `p₀ᵢ` is the customer's untreated purchase probability over the experiment window, `dᵢⱼ` is the effective discount depth the intervention represents for that customer's basket, `εᵢ < 0` is the customer's own price elasticity, `sᵢ > 0` is a promo-responsiveness multiplier carrying **treatment-effect heterogeneity**, and `aⱼ` is the world's **hidden affinity** for intervention kind `j` — see §3.5.

**Demand saturation — assumption, stated explicitly.** Constant-elasticity demand is unbounded: a deep discount priced by an elastic customer implies conversion multiples no retailer has measured. The response multiplier is therefore passed through a saturating curve with asymptote **3.0** — no promotion more than triples a customer's conversion probability — using the exponential form `m(x) = 1 + A(1 − exp(−x/A))` with `A = 2`.

The form is chosen for three properties:

- `m(0) = 1` and `m′(0) = 1`. Weak promotions behave *exactly* as the unsaturated constant-elasticity model says they do, so the elasticity ranges taken from the literature still mean what those papers measured. Saturation only bites where the linear extrapolation was already implausible.
- `m(x) → 3` as `x → ∞`, never reaching it.
- Strictly increasing everywhere. **Nothing clips.**

That last property is the reason for the form. An earlier version used a hard `min(x, 3.0)`, which bounded the tail by *flattening* it: every customer past the threshold received an identical response, erasing individual variation precisely where it was largest. Measured on the Day-2 corpus, that cap was binding on 5.2% of customer × intervention cells overall and on up to 47.8% within a single world. Since heterogeneity in the responsive tail is the signal uplift modelling exists to find, bounding it by flattening destroyed the thing being measured. The asymptote is unchanged; only the approach to it is.

The probability transform `p₁ = 1 − (1 − p₀)^m` applies the multiplier to the *no-purchase* probability rather than to `p₀` directly. For small `p₀` this equals `p₀ · m` to first order, so the multiplicative reading holds where it matters; for large `p₀` it approaches 1 smoothly rather than requiring a clip. The probability bound is then a property of the functional form, not a second ceiling that flattens whoever reaches it.

**Common random numbers.** For each customer a single uniform draw `uᵢ` decides both outcomes: `Yᵢ(0)` converts iff `uᵢ < p₀ᵢ`, and `Yᵢ(1)` converts iff `uᵢ < p₁ᵢⱼ`. This makes the individual effect well-defined and monotone rather than an artefact of two independent coin flips, and it is the standard construction for potential outcomes in simulation.

Because there is only one untreated state, `Yᵢ(0)` is identical across interventions by construction. It is stored per intervention anyway so that the ground-truth record is complete and self-describing, and a test asserts the consistency.

---

## 3. Parameter ranges

### 3.1 Demand and response

| Parameter | Range | Basis |
|---|---|---|
| `baseline_conversion` (world mean `p₀`, per targeted customer over the experiment window) | 0.06 – 0.20 | **Assumption**, anchored on the README's worked example (12%). Published e-commerce benchmarks (~1.6–2.8% global average) are *per session*; the unit here is a targeted customer over a multi-week window, so the session figure is a lower bound on a different quantity, not this one. Cited only to make that distinction explicit. |
| `price_elasticity` (world mean `ε`) | −3.5 – −1.2, or ×1.35 (to −5.0) under `competitive_pressure` | **Sourced.** Tellis (1988): mean −1.76 across 367 elasticities. Bijmolt, van Heerde & Pieters (2005): mean −2.62 across 1,851 elasticities from 81 studies, and finds sales elasticities have grown in magnitude over four decades. The range brackets both means. |
| `elasticity_sd` (customer-level dispersion within a world) | 0.30 – 0.90 | **Assumption.** Bijmolt et al. report substantial between-study dispersion; within-population dispersion is not identified by those meta-analyses, so this is chosen, not sourced. |
| `responsiveness_sigma` (lognormal σ of `sᵢ`, i.e. **treatment-effect heterogeneity**) | 0.25 – 0.60 | **Assumption.** Set deliberately wide enough that effects vary meaningfully *within* a world and not only across worlds. Uplift modelling and any heterogeneity finding are vacuous without this; a reviewer should read the range as a design requirement, openly stated, rather than an empirical claim. |
| `seasonality_index` (multiplier on `p₀` for the trading window) | 0.85 – 1.35 | **Assumption.** Paired with the named seasonal events in the semantic context so the qualitative and quantitative sides of a world agree. |

### 3.2 Basket economics

| Parameter | Range | Basis |
|---|---|---|
| `aov_median_inr` (lognormal median order value) | ₹500 – ₹2,500 | **Derived/Assumption.** README worked example uses ₹800 AOV; the range brackets it. |
| `aov_sigma` (lognormal σ) | 0.35 – 0.75 | **Assumption.** Produces a right-skewed basket distribution, which is the shape retail order values take. |
| `contribution_margin` (per SKU) | 0.15 – 0.50, world mean 0.22 – 0.38 | **Derived/Assumption.** README worked example uses 30%. |
| `n_customers` | 12,000 – 28,000 | **Derived**, from the sample an experiment actually needs. See below. |
| `budget_share_of_revenue` | 5% – 15% of projected window revenue | **Assumption**, in the range trade press reports for retail promotional spend. Replaces a flat rupee budget. |
| `promotion_budget_inr` | derived: `projected_revenue × budget_share` | Typical worlds land at ₹300,000 – ₹600,000 (p25–p75), median ≈ ₹425,000. |
| `projected_revenue_inr` | derived: `n_customers × baseline_conversion × seasonality × mean_basket` | Median ≈ ₹4.0M per experiment window. |

**Why the budget is a share of revenue, and why the population moved with it.** An earlier version fixed the budget at ₹25,000–₹75,000. That figure was invented before world scale was settled and never checked against it: it is roughly 1% of a typical world's revenue, where retail promotional spend runs 5–15%.

The consequence was not merely unrealistic, it was disabling. The decision rule is a confidence interval on incremental contribution, and at 1,000 customers per arm the CI half-width on net contribution is around ₹5,900 while a typical profitable campaign in this corpus nets ₹264–₹1,249. Almost nothing could ever clear the lower bound, so an agent obeying the rule would scale nothing and collapse into Baseline 1 — not because it reasoned poorly but because it was never funded to resolve the question. Detecting an effect of roughly ₹2,600 needs about 5,100 customers per arm, which the old budget could not pay for and, at 2,000–6,000 customers per world, the population could not supply either. Population and budget therefore move together.

Note that under `d = j × margin` the margin cancels out of the *sign* of net contribution entirely (`net = margin·AOV·[incr·(1−c) − treat·j]`), so margin sets the scale of the stakes rather than whether a promotion pays.

One basket-level contribution margin — the catalogue mean — is applied to **both** arms rather than re-weighting the treated basket toward promoted SKUs. Margin-mix shift is real, but modelling it would make measured incremental contribution diverge from the hand-computed arithmetic in the README and in `src/economics/`, and those hand-checks are worth more here than the extra realism. Stated as a simplification, not defended as accuracy.

### 3.3 Leakage — why a conversion win can still lose money

| Parameter | Range | Basis |
|---|---|---|
| `cannibalization_rate` (share of gross lift that is *not* genuinely incremental contribution — pull-forward, stockpiling, switching between the merchant's own SKUs) | 0.15 – 0.45 | **Sourced.** Van Heerde, Gupta & Wittink (2003) find ~33% of the unit sales increase during a promotion is cross-brand loss rather than new demand; Gupta's earlier elasticity decomposition attributes the bulk of the promotion bump to switching and purchase acceleration rather than category expansion. The range brackets 33%. |

Ailawadi, Harlam, César & Trounce (2006) study retailer promotion profitability directly and find promotion profitability varies widely across promotion, brand, category and store characteristics, with the extra margin often failing to cover promotion cost. *No specific percentage from that paper is used to set a range here* — I could not verify a headline figure against the primary text, so none is quoted.

The discount itself is paid to **every** treated buyer, including those who would have bought anyway. That asymmetry — not the cannibalization rate — is the main mechanism by which a positive conversion lift produces negative contribution, and it needs no parameter: it falls out of the arithmetic.

### 3.4 Interventions

Exactly four intervention types exist. CLAUDE.md's locked do-not-build list caps this at ~4; more types would expand the agent's action space without testing anything new.

Depth is sampled as a **multiple of contribution margin**: `d = j × margin`, with `j` drawn per intervention per world.

| Kind | `j` range | Depth at the median 28.7% margin |
|---|---|---|
| `flat_discount` | 0.07 – 0.29 | 2.0% – 8.3% |
| `percentage_discount` | 0.07 – 0.30 | 2.0% – 8.6% |
| `free_shipping` | 0.06 – 0.25 | 1.7% – 7.2% |
| `bundle` | 0.09 – 0.34 | 2.6% – 9.8% |

The offsets keep free shipping trending shallow and bundles deep, as in retail practice, but the ranges overlap heavily and **all four straddle the break-even line**, so no kind is dominated by construction.

Rupee-denominated kinds (flat discount, free shipping) convert through the world's **mean** basket, `aov_median × exp(σ²/2)`, not its median. Order values are lognormal, so anchoring a rupee amount to the median makes its realized depth land systematically shallower than a percentage offer of the same nominal `j` — an advantage that would be an artefact of the parameterization rather than a fact about retail.

**Why depth is anchored to margin and not to break-even.** Break-even depth is `d* = margin × (incremental / treated)`, which *contains the true treatment effect*. Sampling `d = k × d*` would make the observable ratio `d / margin` a direct readout of `incremental/treated` — margin and depth are both visible to the agent, so a baseline could rank the four interventions by profitability without running a single experiment, and the entire experimentation apparatus would be measuring a quantity the world had already disclosed. That artefact is worse than the imbalance it would fix. Anchoring to margin keeps depth expressed in units the merchant genuinely knows while leaking nothing about response.

### 3.4b Bundle uplift is paid for, not granted

A bundle raises the treated basket by `bundle_added_value_inr`. That uplift was originally sampled independently of the bundle's depth, at 15–45% of AOV, which made bundles **a free lunch**: the extra basket earned margin on *every* treated converter while the discount on it cost less than that margin. Measured from ground truth across 30 dev worlds, bundles were profitable in 87% of them and the best of the four interventions in 27 of 30 — dominant by construction, which removes the trade-off the four intervention types exist to pose.

The uplift is now expressed against its own break-even point. For a customer who would have converted anyway, the bundle breaks even when

```
margin × uplift = depth × (basket + uplift)   ⟹   uplift = depth × basket / (margin − depth)
```

and the generator samples `uplift = ratio × breakeven`, with `ratio ~ U(0.3, 0.9)`. A ratio below 1 means the larger basket does not cover the discount applied to it. The range sits below 1 on purpose: a bundle's inframarginal customers should cost the merchant money, exactly as every other intervention's do. **Assumption**; calibrated on dev worlds, not estimated.

**This did not eliminate bundle's dominance, and the reason is worth recording.** Measured from ground truth after the change, bundles still win most worlds — not because bundles are too good, but because flat, percentage and free-shipping offers are unprofitable in 83–87% of worlds by construction. Depth is anchored at `j × margin` with `j` median ≈ 0.2, so a campaign breaks even only when roughly a fifth of treated orders are genuinely incremental, which sits right at the edge of what the corpus's response strengths deliver. Bundle wins by being the least-bad option, not by being free money. Making the three losers profitable enough to compete would mean widening response strength — a world-parameter change, recorded here as a known limitation rather than made silently.

**The best-choice diagnostic is computed from ground truth from now on.** The Day-3 figures ("bundle best in 5–8% of worlds") were wrong: that diagnostic credited the bundle uplift only on incremental orders, while the generator grants it to every treated converter. Where an analytic approximation and `Y(1)−Y(0)` disagree, ground truth is authoritative.

### 3.4a Why percentage discounts and bundles win less often

Measured on the 80 dev worlds, the best of the four interventions is a flat discount in 40% of worlds and free shipping in 48%, but a percentage discount in only 5% and a bundle in 8%.

This is a **finding, not an artefact, and it is deliberately not corrected.** A percentage discount scales its cost with basket size, so it pays the most to the customers with the largest baskets — who are the customers most likely to have converted anyway. Bundles carry the same property with a deeper band on top. Rupee-denominated offers do the opposite: a flat ₹150 off is a 30% discount to a ₹500 basket and a 6% discount to a ₹2,500 one, concentrating incentive on small, price-sensitive baskets where the absolute cost of buying an incremental order is lowest.

That is the project's own thesis restated at the level of intervention design: *the discount is paid to every treated buyer, so an offer that scales with basket size spends the most where it is least needed.* Narrowing the `j` bands until all four kinds won equally often would mean rigging the corpus so that economically disfavoured strategies succeed more than economics allows. All four kinds populate all three profitability regimes (§ Day-2 findings), so none is dominated by construction — they are simply not equally good ideas, which is the point.

### 3.5 Hidden latents and the semantic couplings

Semantic context is only worth having if reading it beats ignoring it. The failure mode is not just "text gives the answer away" — it is also "text restates what the numbers already say", which is what the Day 2 corpus did. Structural features (AOV, margin, depth) already predicted the best intervention at 76% there, while the text predicted at chance: decoration.

So the couplings target latents the agent-facing view does **not** expose, rather than observables like margin or AOV that structural features already carry.

| Latent | Range | What it does | Semantic signal | Status |
|---|---|---|---|---|
| `promo_response_scale` | 0.9 – 2.1 | Scales every customer's promo responsiveness. Decides whether this merchant's promotions can pay at all. | none | **Assumption** |
| `competitive_pressure` | 35% of worlds | Multiplies world elasticity by 1.35 — a price war really does make a market more price-sensitive. | "A larger competitor has been running 20% off sitewide for three weeks." | **Assumption** |
| `shipping_affinity` | lognormal(0, 0.45), clipped 0.5 – 2.2 | Multiplies response to free shipping. | "Repeated questions about whether shipping is free above a threshold." | **Assumption** |
| `clearance_affinity` | as above | Multiplies response to flat discounts. | "…and it cleared fast the last time it was discounted" appended to an ageing-stock note. | **Assumption** |
| `pct_affinity` | as above | Multiplies response to percentage discounts. | **none** — deliberately unsignalled | **Assumption** |
| `bundle_affinity` | as above | Multiplies response to bundles. | **none** — deliberately unsignalled | **Assumption** |
| true `baseline_conversion` | below 0.11 | — | "Revenue is flat quarter on quarter while sessions are up, so conversion is drifting down." | **Assumption** |

**Every intervention kind carries an affinity**, including the two with no signal. Depth is observable; if depth alone decided which promotion pays, a baseline could rank the four without experimenting — the same leak that ruled out break-even anchoring, arriving by a different route.

**Fidelity: ~78% true-positive, ~18% false-positive.** A signal fires with probability 0.78 when its latent is high and 0.18 when it is not. Both numbers are design assumptions, not estimates. Perfect fidelity would turn the text into a lookup table and make the LLM ablation meaningless; zero fidelity would make it decoration. The middle is the only regime in which context shifts the prior and running the experiment is still the rational move. Two of the six couplings carry no signal at all, so reading context helps on some worlds and not others.

The coupled strings are held out of the distractor pools, so a false positive is genuinely uninformative rather than a near-duplicate of the real signal. All remaining competitor events, support themes and trading notes are drawn independently of every latent and correlate with nothing.

## 4. Determinism

`generate_world(seed)` is a pure function of its seed. Same seed → byte-identical serialized world, including all semantic text. Randomness comes from `numpy.random.default_rng` with per-section child streams from a `SeedSequence`; Python's built-in `hash()` is never used for anything generative because string hashing is salted per process. NumPy is pinned in `requirements.txt` for the same reason.

Dev world seeds are 1–80. Holdout seeds are 9001–9020, deliberately far from the dev range so no dev world can be accidentally regenerated as a holdout world or vice versa.

---

## 4a. Day-2 diagnostic — dated pre-holdout finding

**Recorded 26 August 2026, on the 80 dev worlds only. No holdout world was read, printed or summarised. No agent existed at this date.**

This section is a prediction of how hard the corpus is, written before the holdout is opened. It is recorded here because a difficulty estimate produced *after* seeing the Day-9 result would be worthless — and because either Day-9 outcome, favourable or not, is only credible against a difficulty claim that was fixed in advance.

### Can semantic context be read off by a classifier?

Label: the sign of net incremental contribution for a **named** intervention. Structural features are what an agent could compute from observable numbers alone — AOV, contribution margin, realized depth, observed conversion, customer count, segment mix. Protocol: 5-fold × 10-repeat stratified cross-validation, n = 80 worlds.

| Intervention | Base rate | Structural | Structural + text | **Lift from text** | Text only | Oracle (structural + true latent) |
|---|---|---|---|---|---|---|
| flat discount | 58.8% | 63.1% | 62.3% | **−0.9pp** | 58.8% | 67.4% |
| percentage | 66.2% | 78.5% | 78.4% | **−0.1pp** | 66.2% | 82.8% |
| free shipping | 73.8% | 75.6% | 73.4% | **−2.2pp** | 73.8% | 79.1% |
| bundle | 66.2% | 70.1% | 70.6% | **+0.5pp** | 66.2% | 81.4% |

**Mean lift from adding text: −0.7pp.** A bag-of-words classifier extracts nothing from the semantic context at this sample size.

### The coupling is nevertheless real

Measured directly on the same 80 worlds, for the free-shipping affinity:

| | n | P(free shipping profitable) |
|---|---|---|
| latent high (affinity > 1.25) | 25 | **92%** |
| latent low | 55 | **65%** |
| semantic signal shown | 32 | **84%** |
| no signal | 48 | **67%** |

Channel fidelity: `P(signal | latent high) = 80%`, `P(signal | latent low) = 22%`. The signal alone moves the probability that free shipping pays by **17 percentage points**. The oracle column above shows the headroom the text is imperfectly pointing at: **+4 to +12pp** over structural features.

### The learnability caveat

These two results are not in tension. The classifier must *learn* the mapping from text to outcome using 80 labelled examples passed through an 80/22 noisy channel; that is not enough data, and the −0.7pp reflects the sample size and the channel, not an absence of information. An LLM reads "customers keep asking whether shipping is free above a threshold" and connects it to free shipping using prior world knowledge, learning nothing from the corpus at all.

**So this diagnostic is a lower bound on what an LLM can extract, not a measurement of it.** It is recorded as a lower bound, and nothing here should be read as a prediction that the LLM will beat the ablation.

The fidelity was deliberately **not** raised, and the affinity spread deliberately **not** widened, after seeing these numbers. Tuning until a classifier could detect the signal would have reduced how much experimentation was needed to resolve a world — the opposite of what this project is testing. Baseline 4 versus Baseline 5 on the 20 sealed holdout worlds is the only thing that settles whether the LLM adds value, and **whichever way it lands is the finding that gets published** (CLAUDE.md invariant 9).

### What was calibrated, and when

For the record, since all of it happened before the holdout was opened and none of it was informed by holdout data:

- Depth anchored to margin rather than to break-even, after establishing that break-even anchoring leaks the treatment effect into an observable ratio (§3.4).
- A world-level `promo_response_scale` latent added, after measuring that depth cancels from the sign of net contribution and that sweeping depth alone never moved the profitable share above 22%.
- Per-intervention hidden affinities extended from two kinds to all four, after finding that the winner was otherwise decided by which depth band was shallowest — and depth is observable.
- The hard 3× response cap replaced with a smooth saturating curve of the same asymptote (§2), after measuring that the cap was flattening the responsive tail on up to 47.8% of a world's customers.
- A defect in the clearance-signal emission — fired per ageing-stock note, compounding to ~100%/58% effective fidelity instead of 78%/18% — found by measuring the emission rate and fixed before the corpus was accepted.

## 4b. Pre-registered decision rule — dated, 27 August 2026

**Recorded before any holdout world was opened, before any agent existed, on evidence from dev worlds only.** The same change made after seeing holdout results would not be legitimate, and this section exists so that distinction is checkable rather than asserted.

### The rule

A tested campaign may be scaled when **both** hold:

1. `P(net incremental contribution > 0) >= 0.80` under the posterior, and
2. the **5th percentile** of that posterior, projected to the population the rollout would cover, sits above **−2% of the world's promotion budget**.

The posterior is normal, centred on the estimated net contribution with the delta-method standard error as its scale, under a flat prior. With samples in the thousands the likelihood dominates any reasonable prior, so this is numerically the sampling distribution — stated plainly, because the Bayesian framing changes the decision threshold and the downside floor, not the evidence.

Condition 1 is therefore equivalent to a one-sided frequentist test at α = 0.20. That is a deliberate loosening from the previous rule, which required the whole 95% interval above zero (a one-sided bar at α = 0.025). Condition 2 is what makes the loosening safe: a weaker evidence bar with no floor would scale campaigns whose bad tail could consume the entire budget.

The asymmetry is unchanged. **Spending requires evidence; declining requires none.** Nothing in this rule licenses an affirmative claim that a campaign is harmful — that still needs the interval to clear zero on the other side.

### Why 0.80 and −2% of budget

**0.80** — the merchant's question is "will this make money", not "can I reject the null". At 0.80 the expected value of scaling is clearly positive while one campaign in five is still expected to disappoint, which is the correct posture for a bounded, repeatable budget rather than a one-shot irreversible bet.

**−2% of the promotion budget** — the budget is the merchant's own stated appetite for risk across the whole promotion programme, so a per-campaign floor expressed against it scales with the merchant instead of being an invented rupee figure. At 2%, with four candidate interventions per world, aggregate exposure in the bad tail stays under a tenth of the budget: a bad run costs a slice of the promotion programme, never the business.

Both numbers are **assumptions**, chosen for proportionality, not estimated from data.

### Why the previous rule was replaced

The original rule — scale only when the entire 95% confidence interval on incremental contribution clears zero — was measured on Day 5 against an **oracle selector**: a diagnostic that reads ground truth to pick the single best intervention in each world, then runs a normal experiment on it with the full budget.

The oracle **scaled 0 experiments in 10 worlds**, and missed 9 rollouts that were truly profitable. Tightening the minimum detectable effect to buy precision made it worse, because the population cannot seat the resulting sample: at an MDE of 1% of order contribution only 3 of 10 worlds could run the experiment at all, and at 0.5% none could.

That is a diagnosis, not a tuning opportunity. The constraint was statistical power at the scale these worlds can support, so no amount of agent reasoning could have fixed it — a rule that refuses even perfect selection is inoperable rather than conservative. It was changed on that basis, before the agent was built and with the holdout still sealed.

### What is kept

The frequentist interval is still computed and reported alongside every decision, so what the stricter rule *would* have decided remains visible in the results. `src/eval/replay.py` continues to price both rules against ground truth, which means Day 9 can report how much of MarginPilot's performance came from the change in decision threshold rather than from anything the agent did.

## 4c. Estimator defect and correction — dated, 28 August 2026

**Found and fixed on dev worlds, before any agent existed and before any holdout was opened.**

### What the old estimator missed

Incremental contribution was modelled as

```
net = n_t × (Δp × c − p_t × k)
```

— incremental orders times a fixed contribution per order, less the incentive on every treated order. That is correct only when a treatment changes *who* buys and not *what they buy*.

Bundles change both. A bundle raises the basket of every treated buyer, including the ones who would have bought anyway, and the formula above has no term for that: with no incremental orders it scores a real basket gain as exactly zero.

Measured against ground truth on 10 dev worlds, the estimator **had the wrong sign in 5 of them**, reporting −₹0.53 per customer where the truth was +₹1.16. Since the corpus's only reliably profitable intervention is the bundle, this meant no strategy could ever correctly scale the one thing worth scaling.

### The correction

Contribution is now **measured, not modelled**. Each customer's realized contribution — margin on what they actually spent, less any incentive they redeemed, zero if they did not buy — is averaged per arm, and the effect is the difference between arm means:

```
net = n_t × (mean_t − mean_c)
se  = n_t × √(sd_t²/n_t + sd_c²/n_c)
```

Basket effects, mix shifts and incentive costs are inside the measurement rather than assumed away. Nothing here requires knowing a counterfactual: what each customer spent and which discount they used is in the merchant's own order table.

The two estimators **agree exactly when order values are constant across arms** — the canonical README case returns −₹3,600 with a standard error of ₹2,996 under both — and diverge precisely in the case the old one could not represent. Both properties are pinned by tests.

### Which results this invalidated

Every Day 4 and Day 5 figure produced before 28 August 2026 was computed with the broken estimator and has been re-run. The material changes:

| Result | Before | After |
|---|---|---|
| Mean estimation error vs truth | ₹7.67 / customer | ₹4.39 / customer |
| Replay: `point_estimate` rule | −₹333,458, correct 1/5 | −₹59,790, correct 4/5 |
| Oracle selector scale rate | 2/10 | 5/10 |
| Baseline 5 realized net | −₹594,236 | −₹439,452 |
| Baseline 5 false positives | 3 | 1 |

The headline replay result survives: the CI-lower-bound rule still matches the oracle 5/5. **Its margin over the naive point-estimate rule collapsed**, from ₹332,529 to ₹58,861, because most of that gap was the broken estimator's noise rather than the rule's discipline. That is a materially weaker claim than the one the Day 4 report made, and it is recorded here rather than quietly restated.

## 4d. Framing decision — scarce experimentation, dated 28 August 2026

**Pre-holdout, recorded before the agent was built.**

Measured on dev worlds: the median pilot costs **₹55,283**, while the median best-case profit available in a world is **₹19,939**. One experiment costs roughly **2.8× the entire profit pool of the world it runs in**.

This is not a defect and is deliberately **not** being fixed. Making experimentation cheaper — by widening response strength, lowering MDE ambition, or discounting the incentive — would remove the constraint that makes the problem interesting. The economics are honest, so they become the thesis:

> **The agent allocates a scarce experimentation budget.** It can afford roughly one experiment per merchant. Its job is to decide whether any question is worth asking at all, and if so which one — with "run nothing" as a first-class correct answer.

Two consequences follow, and both are testable:

1. **Baseline 5 should lose.** Working through a fixed hypothesis set in a preset order means paying four times for information a well-chosen single experiment would have bought once. Selection headroom against it is **₹519,684** across 10 dev worlds.
2. **Every strategy now declares an explicit experiment allowance** (`max_experiments`), enforced by the harness. Baseline 5's four experiments per world are its own choice, which it pays for, rather than something the harness grants for free. Deciding that only one of the four is worth asking — or that none is — requires exactly the judgement being ablated.

This is where semantic context has to earn its keep. If reading a merchant's situation cannot tell the agent which single question to ask, the LLM adds nothing over the fixed order, and Day 9 will say so.

### Known limitation, recorded not fixed

Bundles win most worlds, and after tying their uplift to their depth (§3.4b) they still do — because flat, percentage and free-shipping offers are unprofitable in 83–87% of worlds by construction. Bundle wins by being least-bad, not by being free money. Fixing that means widening response strength, which §4d declines to do. Documented as a limitation of the corpus, not corrected.

## 4e. Selection is degenerate — dated pre-holdout finding, 28 August 2026

**Measured on 20 dev worlds, before the agent was built. No holdout world was read.**

The question was whether choosing *which* experiment to run is worth anything on this corpus. It is not.

| strategy | realized net | pilot net | rollout net | experiments | scaled |
|---|---|---|---|---|---|
| do nothing | ₹0 | — | — | 0 | 0 |
| fixed_single (flat) | −₹481,826 | −₹534,599 | ₹52,773 | 20 | 1 |
| **always_bundle** | **+₹1,234,478** | ₹111,450 | ₹1,123,028 | 20 | 12 |
| Baseline 5 (engine, no LLM) | −₹20,773 | −₹1,389,390 | ₹1,368,617 | 79 | 14 |
| **oracle selector** | **+₹1,245,953** | ₹111,374 | ₹1,134,579 | 20 | 11 |

**A hardcoded "always test the bundle" captures 99% of the oracle's edge over a badly-chosen single experiment**, leaving **₹11,475** for any amount of reasoning to compete over. The oracle picks the bundle in 18 of 20 worlds. There is almost nothing to select.

### The oracle's advantage over Baseline 5 is not selection quality

| component | value | share |
|---|---|---|
| total gap | ₹1,266,726 | 100% |
| from pilots — which and how many were run | ₹1,500,764 | 118.5% |
| from rollouts — what got scaled | −₹234,037 | −18.5% |

Baseline 5 captures **more** rollout value than the oracle (₹1,368,617 vs ₹1,134,579) — testing four things finds more winners — and still loses overall, because it pays ₹1.5M in pilots to do it. The entire gap is *running 20 experiments instead of 79*. **No part of it may be attributed to choosing better or to declining better**, and Day 9 must not claim it for reasoning.

### What decision remains

`always_bundle` loses money in 6 of 20 worlds, costing ₹96,748. A perfect run/skip decision on top of it would earn ₹1,331,226 instead of ₹1,234,478.

> **The agent's remaining job is whether to run at all — worth ~₹96,748 — not which intervention, worth ~₹11,475.**

Day 6 was re-aimed on this basis: MarginPilot's primary decision is restraint, and "run nothing" is a first-class correct answer with logged reasoning. Intervention choice is still justified against the semantic context, but the claim under test is restraint, not selection.

### Two methodological notes

**Seeds 1–10 are unrepresentative.** On those ten worlds the oracle earned only +₹80,231 and every real strategy lost to do-nothing. Extending to 20 worlds moved the oracle to +₹1,245,953 and put `always_bundle` clearly ahead of do-nothing — the difference is worlds 14, 15 and 18, which earn ₹98k–₹708k each. **Twenty worlds is the minimum credible sample**, and earlier Day-4/Day-5 conclusions drawn from five or ten should be read with that in mind.

**The corpus was not changed in response to this.** Widening response strength would have made selection matter again, but doing so *after* discovering that selection is degenerate is post-hoc tuning toward a more flattering result — still pre-holdout, but exactly the pattern the pre-registration discipline exists to prevent. The known limitation in §4d stands and the corpus is frozen.

## 4f. Model choice — dated, 28 August 2026

**The agent runs on `gemini-3.6-flash`.** Not a quality judgement: no Anthropic credentials were available in the build environment, and an agent that cannot be run cannot be evaluated. Gemini's free tier could be, so it is what the reported results come from.

`ClaudeReasoner` (targeting `claude-opus-5`) stays in the codebase and implements the same interface. Keeping it is the point rather than a leftover — the reasoner is swappable behind one Protocol, the prompts and parsing are shared, and the authority boundary downstream is identical. What changes with the provider is the reasoning; what does not change is that randomisation, the horizon, the scaling rule and every money-adjacent action stay outside the model's reach.

**Which model produced a result is recorded with the result.** "An LLM decided this" is not a claim; "*this* model decided this" is. A result produced by `gemini-3.6-flash` may not be reported as evidence about Claude, or about LLM agents generally.

**Model substitution, recorded.** The intended model was `gemini-2.5-flash`. It is retired for new API keys: it still appears in `models.list()`, but calling it returns

> `404 NOT_FOUND — This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.6-flash for the latest features and improvements.`

`gemini-3.6-flash` is the model Google's own deprecation notice names, so that is what the results come from. `gemini-3.7-flash` and `gemini-3.5-flash` were also reachable on the same key and were not chosen — following the stated migration target is a smaller assumption than picking the newest thing available.

Three constraints follow from the free tier and are handled in `src/agent/reasoner.py`:

- **Pacing.** Requests are spaced to stay under 15 RPM. Discovering the limit by hitting it costs a retry *and* a longer wait.
- **Backoff.** 429s and 5xx retry with exponential backoff and jitter.
- **A rate limit is never a decision.** Exhausted retries raise `RateLimitExceededError`, and an empty or unparseable reply raises `ReasonerError`. Neither is recorded as a skip. An agent scored as having "exercised restraint" because the API was busy would be a fabricated result, and `tests/agent/test_agent_loop.py` asserts the loop propagates both rather than logging a decision.

Neither model client falls back to `HeuristicReasoner` when credentials are missing — both raise. The heuristic exists so the loop and CI run offline, and any evaluation using it measures the pipeline rather than the reasoning.

**Deviation from the original skeleton, recorded:** CLAUDE.md's Day-1 spec called for `requirements.txt` to carry one LLM client library. It now carries two, for the reason above.

## 4g. Semantic reasoning is load-bearing, and it makes selection worse — dated 26 August 2026

**Paired ablation on 10 dev worlds. `gemini-3.6-flash`, temperature 0.0. No holdout world was read.** Each world was run twice: once with the full merchant context, once with the semantic fields stripped and every number preserved (`src/eval/ablation.py`).

### The reasoning is genuinely reading the merchant

| world | context | stripped | result |
|---|---|---|---|
| 00001 | run | skip | **FLIPPED** |
| 00002 | run | skip | **FLIPPED** |
| 00003 | skip | skip | same |
| 00004 | run | skip | **FLIPPED** |
| 00005 | skip | skip | same |
| 00006 | run | skip | **FLIPPED** |
| 00007 | skip | skip | same |
| 00008 | skip | skip | same |
| 00009 | run | skip | **FLIPPED** |
| 00010 | skip | skip | same |

**5/10 decisions flipped.** Every world the agent chose to run, it declined once the situation was withheld.

Citation quality, context arm: **35 semantic citations, 0 numeric, 2 catalogue, 0 unverified**. Every world cited a semantic coupling field; no world cited only numbers; every quote verifies verbatim against the prompt the model was given. There is no fabricated evidence.

Where decisions did not flip (all skip→skip), the stripped arm's reasoning falls back to naming the absence — *"There is no trading context, customer feedback, inventory data, or segment details available"* — while the context arm rejects specific interventions for specific reasons. Semantic citations drop in every pair (4→2, 4→2, 3→2, 4→3, 5→3). Same decision, different route.

**The stripped arm is inert, not a better strategy.** It skipped 10/10: with no situation it never finds a reason to spend. Its apparent "safety" is the absence of any decision at all, and it must not be read as evidence that ignoring context is preferable.

### And it makes selection worse

| world | chose | chosen net | bundle net | difference |
|---|---|---|---|---|
| 00001 | int_shipping | −₹12,242 | ₹779 | −₹13,021 |
| 00002 | int_shipping | −₹1,353 | ₹7,166 | −₹8,519 |
| 00004 | int_shipping | −₹6,623 | −₹1,055 | −₹5,568 |
| 00006 | int_bundle | ₹550 | ₹1,881 | −₹1,331 |
| 00009 | int_shipping | ₹4,949 | ₹8,237 | −₹3,288 |

- agent's chosen interventions: **−₹14,718**
- bundle every time it ran: **+₹17,008**
- **cost of the agent's selection: −₹31,726**
- perfect selection on those worlds: ₹70,949

Separating the two capabilities: **run/skip correct 5/10** (coin-flip; always-run scores 6/10), **selection correct 1/5** of the worlds it ran. It chose `int_shipping` in 4 of 5 runs and lost money in 3 of those 4.

### Mechanism

The generator emits shipping-threshold support themes from the hidden `shipping_affinity` latent at 78%/18% fidelity (§3.5). The agent reads that signal faithfully — its citations are correct and verbatim. But **affinity governs response, not profitability**, and bundle wins on profit in ~90% of worlds regardless of how responsive a merchant's customers are to free shipping.

The agent is reading a *true* signal that does not predict the *target*. This is not hallucination and not a reasoning failure in the ordinary sense; it is a correctly-read cue pointing at the wrong quantity.

### What did NOT happen: the policy gates did not catch this

**A tempting and false framing, recorded here so it cannot creep into the README or the video.**

It is not true that the policy gates "detected the failure and saved ₹31,726". The gates **approved every one of those experiments.** They are contradicted by `src/policy/gates.py`, which checks exactly five things — remaining budget, maximum discount, minimum contribution margin, maximum customer exposure, and minimum experiment power — and has no view whatever on which intervention is more profitable than another. The word `intervention` does not appear in that file.

The agent's `int_shipping` proposals were within budget, within the discount ceiling, above the margin floor, inside the exposure cap and adequately powered. A correct gate approves them. Claiming credit for a refusal that never happened would be inventing a result, and it would be trivially falsified by anyone who opened `gates.py`.

**The honest framing:**

> Grounded reasoning is not the same as good decisions. The agent read the merchant accurately and still chose worse than a fixed rule, because the signals it read predict *response*, not *profitability*. The experimental machinery caught it.

What actually caught it was measurement: the experiment ran to its pre-committed horizon, the posterior on incremental contribution was computed, and the scaling rule declined. The gates constrain *how much* can be spent; the experiment establishes *whether spending pays*. Those are different jobs and only the second one was load-bearing here.

### Scope caveat — do not state this finding without it

**This holds in a corpus where §4d records bundle as dominant by construction.** Flat, percentage and free-shipping offers are unprofitable in 83–87% of worlds because depth is anchored at `j × margin`, and bundle wins by being least-bad. In a corpus where the four interventions were genuinely competitive, a signal about response might well predict profitability, and this result could reverse.

The finding is therefore: *on this corpus*, semantic reasoning is load-bearing and selection-negative. It is **not** evidence that semantic reasoning is useless for promotion selection in general, and reporting it that way would overclaim.

n = 10 on a binary decision. The 95% interval on 5/10 spans roughly 24%–76%. Directional, not conclusive.

## 4h. Day 9 pre-registration — dated 26 August 2026, before any holdout is opened

Recorded now so that the Day 9 result cannot be reinterpreted after the fact.

**Primary hypothesis (from the README):** MarginPilot beats Baseline 1 (do nothing) and Baseline 5 (engine without LLM) on incremental contribution across the 20 holdout worlds.

**What the dev evidence predicts:** it will not.

- Against **Baseline 1**: the agent ran in 5/10 dev worlds and its chosen interventions netted **−₹14,718**. Do-nothing scores exactly zero. On dev evidence MarginPilot loses to doing nothing.
- Against **Baseline 5**: less clear. Baseline 5 runs four experiments per world and pays ~₹1.5M in pilots across 20 worlds (§4e); the agent runs at most one. MarginPilot may beat Baseline 5 on *cost of learning* while losing on selection. If it wins, the win is predicted to come from restraint, not from reasoning.

**Predicted cause of failure:** the `int_shipping` bias described in §4g. The agent reads shipping-affinity signals faithfully and selects on them; profitability is governed by bundle economics instead.

**What would falsify the prediction:** MarginPilot beating Baseline 1 on holdout, or selecting bundle at a materially higher rate on holdout than the 1/5 observed on dev.

**Commitment:** whichever way it lands is what gets reported (CLAUDE.md invariant 9). If the prediction is right, the README's headline claim fails and the failure is the finding. No parameter, prompt or threshold will be changed in response to a holdout result.

## 4i. Holdout result — dated 27 August 2026. The prediction held.

**The 20 sealed worlds were opened once, at commit `857e990` (tag `frozen-for-holdout`), through `src/eval/holdout.py` with `final_eval=True`. No parameter, prompt, threshold or rule changed in response to anything below.**

### §4h predicted this, and it was right

§4h, written before the seal was opened, predicted: *MarginPilot loses to Baseline 1, with the `int_shipping` bias as the mechanism.*

| prediction | outcome |
|---|---|
| loses to Baseline 1 (do nothing) | **Held.** −₹85,430 against ₹0 |
| beats Baseline 5 on cost of learning, not on selection | **Held.** ₹274,435 vs ₹4,426,285; selection cost ₹228,918 |
| shipping bias is the cause | **Held.** `int_shipping` chosen 7/9 times; selection correct 2/9 |
| would be falsified by bundle selection rising above the dev rate of 1/5 | **Not falsified.** 2/9 on holdout, statistically indistinguishable from 1/5 |

The dev-world diagnostic in §4g transferred to unseen worlds without modification. That is the strongest methodological claim available here: the failure was characterised in advance, on different data, and recurred exactly as described.

### The measured result

| strategy | realized net | spend | cost of learning | exp | scaled |
|---|---|---|---|---|---|
| do nothing | ₹0 | ₹0 | ₹0 | 0 | 0 |
| learn only | −₹1,330,481 | ₹4,562,034 | ₹4,562,034 | 77 | 0 |
| rule-based | −₹929,086 | ₹2,194,834 | ₹0 | 0 | 20 |
| conversion optimizer | −₹921,902 | ₹3,004,455 | ₹1,129,051 | 20 | 7 |
| engine without LLM | −₹1,253,786 | ₹4,925,911 | ₹4,426,285 | 77 | 3 |
| **MarginPilot** | **−₹85,430** | ₹365,757 | ₹274,435 | 9 | 1 |
| oracle (cheats) | +₹250,025 | ₹1,506,621 | ₹1,144,478 | 20 | 2 |

Zero policy violations and zero budget overruns across all six strategies.

### What this does and does not establish

**Establishes:** the measurement apparatus works. The scaling rule beats the naive point-estimate rule by ₹2.1M in replay and lands nearest the oracle of any achievable rule. Estimates are accurate to ₹3.96 per customer, better than any baseline. No losing campaign was scaled.

**Does not establish:** that LLM reasoning is useless for promotion selection. It establishes that *this* model, reading *this* corpus's semantic signals, selects worse than a hardcoded bundle rule — in a corpus where §4d records bundles as dominant by construction and §4e measured selection headroom at only ₹11,475. Both caveats are load-bearing and neither may be dropped when this result is quoted.

### One number that should not be quoted without its caveat

**Hypothesis calibration: 74% coverage against a nominal 95%** (135/183). The intervals are too narrow. This was measured after the freeze and nothing was adjusted in response; it is a known defect in the reported results, not a finding about the world. Any future work should start here, because an overconfident interval feeding a scaling rule is a systematic error rather than noise.

## 4j. Cycle 2 pre-registration — dated 28 August 2026, before anything was changed or generated

Cycle 1 is complete and tagged `v1-preregistered`. Its result stands unmodified; this is a **labelled follow-up, not a replacement**, and §4i's numbers are never overwritten by anything below.

**Absolute constraint: the agent changes, the world does not.** `promo_response_scale`, the depth bands, semantic fidelity, the saturation form, the bundle uplift ratio and every other generator parameter stay frozen at their Cycle 1 values. Only the generation *seeds* change, to produce a corpus the agent has never seen. If Cycle 2 looks better because the world got easier, the comparison is worthless — so the world is held fixed and only the seeds move.

### The diagnosed cause

§4g and §4i established it: the agent reads the merchant accurately and selects on signals that predict **response** — shipping-threshold support tickets, segment friction notes — when profitability is decided by **margin against incentive cost**. It chose `int_shipping` in 7 of 9 holdout runs and lost money in most of them. The failure is not hallucination and not poor reading; it is a correctly-read cue pointing at the wrong quantity.

### The two fixes

**Fix A — direct the agent at the ratio, not the response.** The prompt asks which intervention will move customers. It should ask which will move them *at a cost the margin can absorb*. Both numbers are already in the merchant view — contribution per order and cost per treated order — and nothing directed attention to their ratio. The revised prompt states the break-even arithmetic explicitly: an intervention pays only when the share of treated orders that are genuinely incremental exceeds `cost per treated order ÷ contribution per order`. This addresses the diagnosed cause directly, because it names the quantity the agent was substituting a proxy for.

**Fix B — supply margin-adjusted historical performance per intervention.** The agent currently reasons about interventions from their descriptions. A merchant with any promotional history would know which offer types have paid before. The view now carries, per intervention, the realized net contribution per treated customer from a **small past campaign** on that merchant.

The size of that past campaign matters and is stated in advance: **300 treated customers per intervention**, which at these conversion rates and basket variances leaves a standard error large enough that the historical figure is *informative but not decisive*. This is deliberate. A large enough history would make selection arithmetic and the agent would win by reading one number, which would measure nothing about reasoning. The history is drawn from the same generative process as the live world, so it reflects that world's true affinities through the noise — as a real merchant's history would.

**Honest risk, recorded now:** Fix B supplies evidence that points at the answer. If Cycle 2 improves, the improvement may be "the agent can read a table" rather than "the agent reasons better about economics". Cycle 2 therefore reports selection accuracy *and* how often the agent's choice simply matches the best historical performer — if those two are the same number, Fix B replaced reasoning rather than informing it, and that is the finding.

### What I predict

- **Against Baseline 1 (do nothing):** MarginPilot still loses, but by less than Cycle 1's −₹85,430. The binding constraint measured in §4d is that one experiment costs ~2.8× the profit pool of the world it runs in; better selection does not change that arithmetic. Predicted range: a loss between ₹0 and ₹85,430.
- **Against Baseline 5 (engine without LLM):** MarginPilot still wins, and by more than Cycle 1's margin, because better selection compounds with the restraint that already drove that gap.
- **Selection accuracy:** rises from 2/9 to at least 5 of the worlds it runs. Below that, the fixes did not work.
- **Intervention mix:** `int_shipping` falls below 4 of 9 runs, and `int_bundle` rises.

### What would falsify the prediction

- Selection accuracy stays at or below 3 of the worlds run — the fixes changed the prose and not the choices.
- `int_shipping` remains the modal choice.
- MarginPilot beats Baseline 1 outright. That would falsify the cost-of-learning claim in §4d, and would be the more interesting outcome of the two.

### Stopping rule, committed in advance

**If the dev-world ablation shows no change in selection behaviour, the new holdout is not opened.** There is no point spending a sealed set on a fix that did nothing, and opening it anyway would burn the only unbiased measurement Cycle 2 has.

### Commitment

Nothing changes in response to Cycle 2's holdout — not a prompt, not a threshold, not a parameter, not a strategy. Cycle 2 reports whichever way it lands, and a fix that does not work is a result (CLAUDE.md invariant 9).

## 4k. Cycle 2 dev result — dated 28 August 2026. The sealed holdout was NOT opened.

Reported as measured, against the predictions in §4j. Nothing below was tuned in response to anything below.

### Corpus

Seeds moved from `1-80`/`9001-9020` to `20001-20080`/`29001-29020`; every generator parameter unchanged. Cycle 1's corpus stays at `worlds/` so §4i remains reproducible from disk; Cycle 2 generates into `worlds_cycle2/`.

Dev medians, Cycle 1 -> Cycle 2: conversion 0.124 -> 0.126, AOV Rs.1,858 -> Rs.1,814, margin 0.289 -> 0.295, elasticity -2.742 -> -2.573, budget Rs.404,500 -> Rs.369,000. Designed effects: flat 3.835 -> 2.867pp, pct 2.537 -> 2.123pp, shipping 3.144 -> 3.010pp, bundle 2.948 -> 2.650pp. Every effect is *smaller* at the median, so the new corpus is marginally harder. It cannot manufacture an improvement.

### A defect in Fix B, found before any result was read

The past-campaign history seeded its RNG with `abs(hash(world.world_id))`. Python salts string hashing per interpreter, so the same world produced a different history in every process — `world_20001` returned `int_shipping`, `int_bundle` and `int_pct` on three consecutive runs. Fix B's evidence was irreproducible. Re-derived via `blake2b`, the convention `src/experiment/randomize.py` already uses and for the same reason. The first dev run was discarded and re-run.

`tests/eval/test_history_determinism.py` starts a second interpreter under a different `PYTHONHASHSEED`; a same-process assertion cannot catch this, which is why the earlier verification missed it. The test was confirmed to fail against the reverted code.

### The measurement, run as a 2x2 ablation

§4j proposed two fixes together. Measuring them together would not have said which one worked, so both were made switchable and all four combinations were run over the same 20 dev worlds. The `neither` arm is the Cycle 1 prompt byte-for-byte, and is the control: without it, a change measured on a fresh corpus cannot be attributed to the fixes rather than to the worlds.

| arm | ran | skipped | selection accuracy | history-match | correct where history disagreed | int_shipping | realized net |
|---|---|---|---|---|---|---|---|
| neither (Cycle 1 prompt) | 12 | 8 | 3/12 | 4/12 | 0 | 9 | -Rs.701,329 |
| Fix A only (break-even) | 15 | 5 | 3/15 | 2/15 | 2 | 9 | -Rs.894,588 |
| Fix B only (history) | 6 | 14 | 3/6 | 6/6 | 0 | 2 | -Rs.287,901 |
| both fixes | 8 | 12 | 1/8 | 6/8 | 0 | 3 | -Rs.259,265 |

> **Superseded, 28 August 2026 (Cycle 3, Step 1).** The `selection accuracy` column above is reported on a moving denominator — each arm's own run count, which is exactly the quantity the fixes change — so `3/12` and `3/6` are not a like-for-like rate. It has the same defect this section already retracted in `net_if_always_best_inr`. The corrected fixed-denominator decomposition is below and supersedes that column. The table is left in place because the error is part of the record.

Realized net is comparable across arms (a skip contributes zero). The per-arm "always-best ceiling" in `results/cycle2_dev_*.json` is **not** comparable across arms — it sums only over the worlds that arm chose to run.

### Correction: the same decomposition on a fixed denominator

Re-derived from the committed `results/cycle2_dev_*.json`. No new runs.

The optimal action is a property of the world, not of the arm: **run** where the best available intervention has positive population net, **skip** otherwise. Over the 20 dev worlds that is 12 run, 8 skip. This definition is deliberately *generous to running* — it ignores the pilot's own cost of learning, so it under-counts false-act and over-counts false-skip relative to a full accounting. Realized net, which includes every real cost, is the ground truth that does not have that thumb on the scale.

| arm | ran | correct action | false-act | false-skip | correct skip | cwhd | int_shipping | realized net |
|---|---|---|---|---|---|---|---|---|
| neither (Cycle 1 prompt) | 12 | 0/20 | 5/20 | 5/20 | 3/20 | 0 | 9 | -Rs.701,329 |
| Fix A only (break-even) | 15 | 2/20 | 5/20 | 2/20 | 3/20 | 2 | 9 | -Rs.894,588 |
| Fix B only (history) | 6 | 1/20 | 3/20 | 9/20 | 5/20 | 0 | 2 | -Rs.287,901 |
| both fixes | 8 | 1/20 | 2/20 | 6/20 | 6/20 | 0 | 3 | -Rs.259,265 |

A **correct action** is the strict one: ran on a world where running was right, *and* picked the best intervention. Decision-level agreement alone (run/skip, ignoring which intervention) is 10, 13, 8 and 12 of 20 respectively.

**The corrected numbers are not a rescaling of the old ones.** On a fixed denominator the control lands **0** correct actions out of 20, not 3. Its old `3/12` counted worlds where it picked the best intervention while running at all destroyed value — credit for choosing well inside a decision that should not have been made. No arm landed 3 correct actions; the strict counts are 0, 2, 1, 1.

Against a fixed ceiling of **Rs.1,132,582** (take the best intervention wherever it pays, skip elsewhere), regret is Rs.1,833,910 / Rs.2,027,170 / Rs.1,420,482 / Rs.1,391,847 for neither / Fix A / Fix B / both. Decomposing realized net by action class:

| arm | net from false-act | net from correct-act |
|---|---|---|
| neither | -Rs.522,493 | -Rs.178,836 |
| Fix A only | -Rs.905,403 | +Rs.10,815 |
| Fix B only | -Rs.304,072 | +Rs.16,171 |
| both | -Rs.233,213 | -Rs.26,052 |

Every arm's loss is dominated by acting where it should have skipped. That is the same conclusion §4d reached about cost of learning, arrived at from the decision side.

**This also corrects Cycle 2's reading of Fix A.** Under the running-generous optimality definition Fix A has the *best* decision-level agreement (13/20) and the *lowest* false-skip (2/20) — because that definition rewards running and Fix A runs more. It simultaneously has the worst realized net and the worst regret of any arm. The claim that Fix A is harmful stands, but it rests on realized net and regret, not on any accuracy rate. The accuracy rate was never the evidence.

### What survives the noise floor, and what does not

Given the 6-of-16 paired flip rate measured below, at n=20:

- **Unresolved: selection accuracy.** Strict correct actions are 0, 2, 1, 1 out of 20. Those numerators are smaller than the number of decisions that flip between two identical runs of the same arm. No ordering among the arms is established, in either direction.
- **Survives: run-rate.** 12, 15, 6, 8 of 20. Run *counts* matched exactly (6/16 and 6/16) across the two identical replicate runs even as *which* worlds were run changed, so the count is the more stable statistic and the spread across arms is large.
- **Survives: `correct_where_history_disagreed`.** It is 0 in both arms carrying Fix B. Zero is robust to flip in a way a small positive count is not: no reshuffling of which worlds were run can turn "never right when the table disagreed" into evidence of reasoning.
- **Directionally supported, not resolved: realized net and regret.** Both are sums over per-world outcomes and inherit the flip noise, but the spread (Rs.259k to Rs.895k) is wide and the loss decomposition points the same way in every arm.

### The instability that governs how much of the table can be believed

Two runs of the **same** arm (`both`), same code, same worlds, temperature 0.0, disagreed on the run/skip decision for **6 of 16** worlds — 38%. Run *counts* matched (6/16 and 6/16); *which* worlds were run did not.

That is the same order of magnitude as the between-arm differences above. So:

- The large run-rate differences (12 and 15 versus 6 and 8) are plausibly real.
- The selection-accuracy column is **not resolved**. Every numerator is 1 or 3, on top of a 38% per-world flip rate.

This project computes a minimum detectable effect before it runs a merchant experiment, and then ran its own 20-world comparison without asking whether 20 worlds could resolve the difference. That is the same error, committed by the evaluation rather than by the agent, and it is recorded here rather than quietly fixed.

The claim in `src/agent/reasoner.py` that temperature 0.0 makes paired runs reproducible was false. It has been withdrawn at the source.

### Against §4j's predictions

**Fix A failed, and appears actively harmful.** §4j predicted the break-even framing would raise selection accuracy and cut `int_shipping`. `int_shipping` did not move (9 in both arms), experimentation *rose* from 12 to 15 of 20 worlds, and realized net fell from -Rs.701,329 to -Rs.894,588 — the worst of any arm, with the worst regret against the fixed ceiling. The **accuracy** half of that prediction is unresolved at n=20 and neither confirmed nor refuted: see the correction above. The verdict on Fix A rests on run-rate and net, which survive the noise floor, not on the accuracy rate, which does not.

The likely mechanism is legible in the prompt itself: break-even shares render as 12-17%, which reads as easy to clear. Stating the arithmetic argued the agent into *more* spending, not better spending. This is the opposite of the prediction and it is Fix A's own failure — the control ran on the same worlds.

**Fix B changed behaviour, by lookup rather than by reasoning.** It is the only arm that cut experimentation (12 -> 6) and the only one that cut `int_shipping` (9 -> 2). But `correct_where_history_disagreed` is **0** in both arms that carry it: the agent never once identified the best intervention when the history table did not already point at it. §4j named this outcome in advance — *"if those two are the same number, Fix B replaced reasoning rather than informing it, and that is the finding."* It is the finding.

**Falsification conditions from §4j:** `int_shipping` did not remain the modal choice in the Fix B arms, so that condition is not met. §4j's other condition — "selection accuracy stays at or below 3 of the worlds run" — cannot be evaluated as written: it is stated on the moving denominator this section retracts, and on a fixed denominator the strict counts (0, 2, 1, 1 of 20) sit below the instrument's own noise floor. It is recorded as unresolved rather than met, which is the weaker and more honest reading.

### Decision on the pre-committed stopping rule

§4j committed: *"If the dev-world ablation shows no change in selection behaviour, the new holdout is not opened."*

Selection behaviour did change, so the rule's literal condition for stopping is not met. Its *purpose* is still not served by opening. Opening the sealed set would measure whether the agent can read a table it was handed — a question §4j states in advance measures nothing about reasoning — at a per-world noise level that cannot resolve the accuracy differences anyway. A holdout is opened once; spending it on that is the one thing the rule exists to prevent.

**The Cycle 2 holdout (`worlds_cycle2/holdout/`) has not been opened.** It remains sealed. No parameter, prompt, threshold or strategy was changed in response to any number in this section.

## 4l. Cycle 3 pre-registration — dated 29 August 2026, before any new measurement code was written

Cycle 3 repairs the **evaluation instrument**, not the world and not the agent. Cycle 1 stays tagged and unmodified. Cycle 2's dev-stage result stands as corrected in §4k. `worlds_cycle2/holdout/` stays sealed and nothing in Cycle 3 opens it.

**Absolute constraint: change the instrument, not the world and not the agent.** Every generator parameter stays frozen. The four prompt configurations (`neither` / `break_even_only` / `history_only` / `both`) stay exactly as committed in `3cc802c`; they are measured more precisely, not edited. Fix A is not dropped or altered — that is a separate later decision, to be taken on resolved numbers. Drawing additional dev worlds from the frozen generator under new seeds is sampling the world, not changing it, and is permitted **only if** the power calculation in Step 3 requires it.

### Why this cycle exists

§4k established that Cycle 2 committed the project's own central error. It ran a four-arm, 20-world comparison and read differences off it without ever asking whether 20 worlds could resolve those differences — while two runs of the *same* arm, identical code and worlds at temperature 0.0, disagreed on 6 of 16 run/skip decisions. The agent is held to a pre-computed minimum detectable effect before it is allowed to spend; the evaluation was not.

The reasoner's retracted claim that temperature 0.0 makes paired runs reproducible is the direct cause. That assumption is not re-made anywhere in Cycle 3: every quantity that depends on it is measured.

### The target MDE, and how it was derived

**Primary contrast:** the **false-act rate** — the share of worlds, out of a fixed denominator, on which an arm runs an experiment where the optimal action was to skip. §4k's loss decomposition shows this is where every arm's money goes.

The threshold is derived from what would change a decision, in this chain:

1. A prompt fix is worth keeping only if it improves expected realized net **per merchant** by a material amount. Materiality is fixed at **5% of the median dev promotion budget**. The median is Rs.369,000 across the 80 frozen Cycle 2 dev worlds, so the threshold is **Rs.18,450 per merchant**.
2. The cost of one false act, pooled across all four arms, is **Rs.131,012** (15 false acts, Rs.1,965,180 destroyed).
3. Therefore the smallest worth-resolving difference in false-act rate is `18,450 / 131,012` = **14 percentage points**, which is the target MDE. On a 20-world denominator that is 2.8 worlds.

**Certification.** The MDE was derived from the chain above and **not** from the observed between-arm gaps. Only step 2 touches Cycle 2's runs, and it uses a quantity **pooled across all four arms** — a cost scale in rupees per event, carrying no arm-to-arm contrast, in the same role a pooled variance plays in any power calculation. Steps 1 and 3 use only the frozen generator's budget distribution and arithmetic.

**Disclosed coincidence.** The observed false-act rates are 25%, 25%, 15% and 10%, so the largest observed gap is 15 points and sits just above the 14-point MDE. This is disclosed rather than hidden. It was not the source of the threshold: had materiality been set at 3% or 10% of budget the MDE would have been 8 or 28 points, and the derivation would have been written the same way. A reader who thinks 5% is the wrong materiality bar should read the feasibility result in Step 3 against their own number, which is why every input above is stated.

### The variance input, and how it will be measured

The variance that matters is **instrument noise**: how much an arm's measured metric moves when nothing about the arm changes. It will be measured by **replicating the control arm alone** — `neither`, the Cycle 1 prompt — K times over the same dev worlds. Deriving it from the spread *across* arms would confound noise with the very signal being tested; taking it from one arm makes it manifestly noise.

Method, fixed now:

- Replicate `neither` on the same fixed world set, K₀ ≥ 8 times, changing nothing between replicates.
- Report, per world, the proportion of replicates that chose `run`, and the resulting per-world flip probability.
- Report the **standard deviation across replicates of the arm-level false-act count**. That SD, not the per-world flip rate, is the standard error that enters the power calculation, because the metric being compared is arm-level.
- Report the same SD for run-rate, `int_shipping` rate, `cwhd` and realized net.

The existing 6-of-16 figure is a single paired comparison and is treated as a rough prior to be superseded, not as the variance input.

### The design that will be computed, and the commitment to report feasibility

The comparison is **paired**: every arm runs on the identical world set, so world-to-world variation cancels in the between-arm contrast and only replicate noise and the pairing remain. Required replicates K per arm will be computed from (MDE = 14 points, measured SD) for a two-sided paired comparison at α = 0.05 and power 0.80, by the stated normal-approximation formula, with the arithmetic shown. If the world-level base rate rather than replicate noise turns out to dominate, N will be recomputed too and fresh dev worlds drawn from the frozen generator under new seeds.

**Feasibility will be reported honestly whether or not the design is runnable.** If the required K·N exceeds what the budget allows, that is the result: the accuracy contrast is below this evaluation's feasible resolution, and the conclusion rests on the columns that do resolve. No oversized run will be launched to chase significance, and no threshold will be relaxed after seeing the required K.

### Metrics, each reported with a standard error or interval across replicates

- False-act and false-skip counts, on the fixed all-worlds denominator of §4k
- `correct_where_history_disagreed`
- Run-rate
- `int_shipping` share of runs
- Realized net contribution, and regret against the fixed ceiling

### What I predict

- **Run-rate contrasts resolve.** Run counts matched exactly (6/16 and 6/16) across the two identical replicate runs even as which worlds were run changed, so the count should prove the low-variance statistic and the 12/15/6/8 spread should survive.
- **`cwhd` stays 0 in both Fix B arms.** A zero cannot be reshuffled into evidence by flip noise.
- **The accuracy contrast does not resolve at feasible scale.** I expect the required K to exceed the budget, and expect to report the accuracy comparison as below this instrument's resolution.
- **Fix A's run-rate increase survives; its accuracy effect resolves to zero-or-negative, or does not resolve at all.**

### Commitment

Nothing is tuned to what the powered re-run shows. Not a prompt, not a threshold, not a generator parameter, not the MDE, not the materiality bar. Cycle 3 ends at the dev boundary: §4j's disqualifying condition for Fix B (`cwhd` = 0) is already met and is robust to flip noise, so there is nothing about reasoning left for a sealed set to validate even once accuracy resolves. Whether to drop Fix A, and whether any new fix warrants a fresh holdout, is a separate pre-registered decision after this one.

## 4m. Cycle 3, Step 3 — the measured noise floor and the required design, dated 29 August 2026

The control arm (`neither`, the Cycle 1 prompt) was replicated **K₀ = 8** times over the same 20 dev worlds, changing nothing between replicates. Noise is taken from this one arm, never from the spread across arms, so it is manifestly noise rather than the signal under test. Zero errored world-runs across the replicates that recorded the field.

### Decision stability

| quantity | value |
|---|---|
| worlds whose decision is not stable across 8 replicates | **12 / 20 (60%)** |
| expected per-world disagreement between two runs | **20.3%** |

This supersedes both earlier estimates: the single paired comparison in §4k (6 of 16, 38%) and the interim five-replicate figure (12.8%). Neither was reliable, in opposite directions.

### Per-metric noise and the required replicates

MDE for counts is the pre-registered 14.1% of worlds = 2.82 of 20; for realized net it is the materiality bar of Rs.18,450 per merchant across 20 worlds = Rs.369,000.

| metric | mean | SD | K (point) | K (SD 95% upper) |
|---|---|---|---|---|
| false_act | 4.50 | 0.93 | 2 | 8 |
| false_skip | 5.25 | 0.89 | 2 | 7 |
| run_count | 11.25 | 1.49 | 5 | 19 |
| **correct_action** | **0.00** | **0.00** | 1 | 1 |
| **cwhd** | **0.00** | **0.00** | 1 | 1 |
| int_shipping | 9.38 | 1.69 | 6 | 24 |
| realized_net | -Rs.824,814 | Rs.256,872 | 8 | 32 |

An SD estimated from 8 replicates is itself noisy: the 95% interval on the false-act SD is [0.612, 1.884]. Required K scales with SD², so the interval on K is wider still. Both columns are reported because quoting only the point estimate would repeat this cycle's founding error one level up.

### The interim report at K₀ = 5 was wrong, and how

At five replicates the same computation gave SD 0.55 for false-act and 0.55 for run-count, implying **K = 1** for both, and I reported the design as comfortably feasible. At eight replicates those SDs are 0.93 and 1.49, implying K = 2 and K = 5. A variance estimated from a handful of replicates is biased low and unstable, and reporting a required sample size off five points was the same species of error as reading arm differences off one run each. The K₀ = 8 figures supersede it.

### What is settled regardless of K

`correct_action` and `cwhd` are **0.00 with SD 0.00 across all eight replicates** of the control. §4k's `0/20` is a property of the arm, not a sampling accident, and no increase in replicates can move a statistic that has never once been non-zero. §4j's disqualifying condition for Fix B — that the agent is never right where the history table disagreed — rests on this and is not at risk from instrument noise.

### Feasibility

Measured throughput is **38.3 s per world-run**, from the replication itself; a token-based estimate gave 0.7 hours against a measured 4.3, six times optimistic, and is not used.

| design | world-runs | wall clock | verdict |
|---|---|---|---|
| K = 2, primary metric (false-act) only | 3 further passes, 60 | **0.6 h** | feasible |
| K = 8, all metrics, point-estimate SD | 21 further passes, 420 | **4.5 h** | affordable but large |
| K = 32, conservative SD upper bound | 117 further passes, 2,340 | **25 h** | **infeasible** |

The pre-registered primary contrast is affordable. The realized-net and `int_shipping` contrasts are **not resolvable at feasible scale** once the uncertainty in the variance estimate is carried through, and §4l committed in advance to reporting exactly that rather than launching an oversized run to chase significance.

### Instrument defects found, and fixed, during the measurement

Three, each surfaced by a failure rather than by inspection, all recorded because an evaluation that silently loses runs produces biased results:

1. An empty reply (`finish_reason=MAX_TOKENS`) aborted a three-replicate job, discarding 17 completed world-runs. Worlds are now retried a bounded number of times and then recorded as `decision: "error"` — excluded from every denominator, reported, never replaced by a guessed decision. The retry keys on exception type only, never on what the model decided, so it cannot select for outcomes.
2. `httpx.RemoteProtocolError` was not retried at all, and killed the next attempt. Dropped connections now join 429s and 5xx in the reasoner's backoff.
3. Writing the test for (2) exposed a third: retry exhaustion raises `RateLimitExceededError`, which is not a subclass of `ReasonerError`, so a harness catching only the latter would still lose a multi-hour run to one dropped connection. Both are caught now, and a test asserts it stays that way.

None of these touched a prompt, an arm, or a generator parameter.

## 5. What this model does *not* claim

- It is not a calibrated model of any real merchant. It is a generator of plausible retail economies whose parameter ranges are anchored where literature exists and openly labelled where it does not.
- Elasticity meta-analyses are drawn overwhelmingly from packaged goods and store-scanner data, not Indian D2C e-commerce. Transplanting them is a stated assumption.
- Absolute results have no external validity. The comparisons — MarginPilot against five baselines on the same 20 sealed worlds — are the claim.

---

## References

- Tellis, G. J. (1988). *The Price Elasticity of Selective Demand: A Meta-Analysis of Econometric Models of Sales.* Journal of Marketing Research, 25(4), 331–341. <https://journals.sagepub.com/doi/abs/10.1177/002224378802500401>
- Bijmolt, T. H. A., van Heerde, H. J., & Pieters, R. G. M. (2005). *New Empirical Generalizations on the Determinants of Price Elasticity.* Journal of Marketing Research, 42(2), 141–156. <https://journals.sagepub.com/doi/10.1509/jmkr.42.2.141.62296>
- Van Heerde, H. J., Gupta, S., & Wittink, D. R. (2003). *Is 75% of the Sales Promotion Bump Due to Brand Switching? No, Only 33% Is.* Journal of Marketing Research, 40(4), 481–491. <https://journals.sagepub.com/doi/10.1509/jmkr.40.4.481.19386>
- Blattberg, R. C., Briesch, R., & Fox, E. J. (1995). *How Promotions Work.* Marketing Science, 14(3 Supplement), G122–G132. <https://pubsonline.informs.org/doi/10.1287/mksc.14.3.G122>
- Ailawadi, K. L., Harlam, B. A., César, J., & Trounce, D. (2006). *Promotion Profitability for a Retailer: The Role of Promotion, Brand, Category, and Store Characteristics.* Journal of Marketing Research, 43(4), 518–535. <https://journals.sagepub.com/doi/10.1509/jmkr.43.4.518>
