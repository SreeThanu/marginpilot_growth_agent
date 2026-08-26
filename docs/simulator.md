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
