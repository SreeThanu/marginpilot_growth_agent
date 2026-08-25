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
