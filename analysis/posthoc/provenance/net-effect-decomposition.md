# Structural inspection — what part of customer-level net treatment effect is predictable from merchant-observable features

**Date:** 1 September 2026
**Method:** read-only source inspection. No simulation run, no diagnostic created or rerun, no correlation computed, no `Y(0)`/`Y(1)` read, no seal opened, nothing modified.
**Sources:** `src/world/generator.py`, `src/world/schema.py`, `src/world/vocabulary.py`, `src/eval/contracts.py`, `src/eval/harness.py` at `main` @ `4942af6`.

Everything below is derived from the generating code alone. Where a statement rests on a prior measurement rather than on structure, it is marked as such and moved to the second section at the end.

---

## 0. The generation path, in order

`generate_world(seed)` (`generator.py:677-708`) spawns **7 independent RNG child streams** from one `SeedSequence` (`generator.py:66-79`), then samples in a fixed order:

```
calendar (SEMANTIC) → seasonality_index
    ↓
params (PARAMS)          ← seasonality_index
    ↓
catalogue (CATALOGUE)    ← params.aov_median, params.margin_mean/sd
    ↓
semantic (SEMANTIC)      ← params (4 latents emitted at partial fidelity)
    ↓
segments (SEGMENTS)      ← 4-6 archetypes drawn from a fixed 7-row table
    ↓
customers (CUSTOMERS)    ← params + segment archetype
    ↓
interventions (INTERV.)  ← params.margin_mean, params.aov_median/sigma
```

then `generate_ground_truth(world)` (`generator.py:710-780`) draws the outcome-level randomness from the **OUTCOMES** stream and applies the response model.

The streams are independent by construction, so nothing sampled in one stream carries information about another beyond what is passed explicitly as an argument.

---

## 1. The response model and the outcome definition, exactly as coded

**Per-customer latents** (`_sample_customers`, `generator.py:394-446`):

```
p0_i  = clip( baseline_conversion · seasonality_index · seg.conversion_multiplier · LN(0, 0.25),  0.005, 0.60 )
ε_i   = clip( −|elasticity_mean · seg.elasticity_multiplier + N(0, elasticity_sd)|,  −5.0, −0.30 )
r_i   = clip( seg.responsiveness_mean · promo_response_scale · LN(0, responsiveness_sigma),  0.05, 12.0 )
eov_i = clip( aov_median · seg.aov_multiplier · LN(0, aov_sigma),  99, 50_000 )
tenure_days_i        = U{1, …, 1459}
orders_last_90d_i    = Poisson(2.0)
days_since_order_i   = U{0, …, 399}
```

**Outcome draws** (`generate_ground_truth`, `generator.py:715-720`), all from the OUTCOMES stream:

```
u_i   ~ U(0,1)                      one per customer, common random number for BOTH arms
L_i   ~ LN(0, 0.20)                 one per customer, basket noise
PF_ij ~ U(0,1)                      one per customer × intervention
```

**Response** (`treated_conversion_probability`, `generator.py:643-669`; `response_multiplier`, `:611-623`):

```
b_i        = eov_i · L_i                                  (basket)
tb_ij      = b_i + bundle_added_value_j   if kind = BUNDLE, else b_i
d_ij       = effective_depth_j(tb_ij)                     (schema.py:261-286, capped at 0.5)
lift_ij    = (1 − d_ij)^{ε_i} − 1
m_ij       = 1 + A(1 − exp(−r_i · a_j · max(lift_ij,0) / A)),   A = 2.0
p1_ij      = 1 − (1 − p0_i)^{m_ij}                        ⟹ p1 ≥ p0 always
```

**Contribution and net** (`generator.py:722-763`; `harness.py:279-293`):

```
M          = mean over catalogue of contribution_margin          (one scalar per world)
conv0_i    = u_i < p0_i
conv1_ij   = u_i < p1_ij
Y0.contrib = b_i · M              if conv0 else 0
Y1.contrib = tb_ij · M            if conv1 else 0,  FORCED TO 0 if (conv1 ∧ ¬conv0 ∧ PF_ij < cann)
τ_ij       = Y1.contrib − Y0.contrib
cost_ij    = d_ij · tb_ij                                  charged iff conv1
net_ij     = τ_ij − cost_ij · 1{conv1}
```

**The three-region decomposition.** Because `u_i` is shared across arms and `p1 ≥ p0`, every customer falls in exactly one region:

| region | probability | τ | net |
|---|---|---|---|
| **always-buyer** `u < p0` | `p0` | `bundle_value·M` (BUNDLE) or **0** | `bundle_value·M − cost` / **−cost** |
| **complier** `p0 ≤ u < p1` | `p1 − p0` | `tb·M`, or **0** if `PF < cann` | `tb·M − cost`, or `−cost` if pulled forward |
| **never-taker** `u ≥ p1` | `1 − p1` | 0 | **0** |

Hence the conditional mean, which is the only quantity a policy can act on:

```
E[net_ij | latents, b_i] =  p0_i · ( bundle_term_j·M − cost_ij )
                          + (p1_ij − p0_i) · ( (1 − cann)·tb_ij·M − cost_ij )
```

---

## 2. Variable tables

Legend for the last column: **U** = causally upstream of treatment response; **D** = causally downstream of it; **⊥** = independent of it; **N** = noise entering the realization only.

### 2.1 Customer fields exposed in `CustomerView` (`contracts.py:53-70`)

| variable | observable to agent? | generated from | affects treatment response? | cross-world stable? | causal/predictive status |
|---|---|---|---|---|---|
| `customer_id` | yes | `f"cust_{index:05d}"` — positional index (`generator.py:433`) | no | identifier reused across worlds, carries no information | ⊥ — index only. Determines which `u_i` slot is used, but the mapping is a fresh RNG stream per world, so it is not learnable across worlds |
| `segment_id` | yes | `f"seg_{index}"`, index = position in a random sample of 4–6 archetypes (`generator.py:375-381`) | **yes, indirectly** — the archetype behind it sets `conversion_multiplier`, `elasticity_multiplier`, `responsiveness_mean`, `aov_multiplier` | **NO** — `seg_0` is a different archetype in every world | **U** within a world; **zero transferable content** as a label |
| `historical_aov_inr` | yes, **exactly** — `= c.expected_order_value_inr` verbatim (`contracts.py:340`) | `aov_median · seg.aov_multiplier · LN(0, aov_sigma)` (`generator.py:426-430`) | **yes** — enters `d_ij` for rupee-denominated kinds, hence `lift`, `p1`; and scales contribution and cost | value is world-scaled; the *relationship* is stable | **U** — a true latent exposed without noise |
| `tenure_days` | yes | `U{1,…,1459}` (`generator.py:436`) | **no** | distribution identical in every world | **⊥** — independent of every latent and of `segment_id` |
| `orders_last_90d` | yes | `Poisson(2.0)` (`generator.py:437`) | **no** | identical in every world | **⊥** |
| `days_since_last_order` | yes | `U{0,…,399}` (`generator.py:438`) | **no** | identical in every world | **⊥** |

### 2.2 Customer latents NOT exposed (`schema.py:205-223`)

| variable | observable? | generated from | affects treatment response? | cross-world stable? | status |
|---|---|---|---|---|---|
| `baseline_purchase_prob` `p0_i` | **no** | `baseline_conversion · seasonality · seg.conversion_multiplier · LN(0,0.25)` | yes — sets always-buyer share and the base of `p1` | relationship stable | **U**. World and segment components are observable-adjacent (§3.2); the `LN(0,0.25)` factor is unobserved |
| `price_elasticity` `ε_i` | **no** | `−|elasticity_mean · seg.elasticity_multiplier + N(0, elasticity_sd)|` | yes — exponent in `lift` | relationship stable | **U**. `elasticity_mean` is hinted only through the price-war signal at 0.78/0.18 |
| `responsiveness` `r_i` | **no** | `seg.responsiveness_mean · promo_response_scale · LN(0, responsiveness_sigma)` | **yes — this is the heterogeneity knob** | relationship stable | **U**. *No observable is downstream of `r_i`.* The only route to it is the segment archetype |
| `expected_order_value_inr` | **yes** (as `historical_aov_inr`) | see above | yes | — | **U**, and the one latent published exactly |

### 2.3 World latents (`WorldParams`, `schema.py:331-385`) — none in any view

| variable | observable? | generated from | affects response? | cross-world stable? | status |
|---|---|---|---|---|---|
| `promo_response_scale` | **no** | `U(0.9, 2.1)` | yes — multiplies every `r_i` | no | **U**, unhinted. Docstring: "Hidden: never exposed" |
| `shipping_affinity`, `clearance_affinity` | **no** | `clip(LN(0,0.45), 0.5, 2.2)` | yes — `a_j` for shipping / flat | no | **U**, hinted at **0.78 TP / 0.18 FP** via a support-ticket or inventory string (`generator.py:321,349`) |
| `pct_affinity`, `bundle_affinity` | **no** | same | yes — `a_j` for pct / bundle | no | **U**, **no signal at all** |
| `competitive_pressure` | **no** | `Bernoulli(0.35)`; multiplies `elasticity_mean` by 1.35 | yes, via elasticity | no | **U**, hinted at 0.78/0.18 |
| `elasticity_mean`, `elasticity_sd` | **no** | `U(−3.5,−1.2)` (×1.35 if price war), `U(0.30,0.90)` | yes | no | **U** |
| `responsiveness_sigma` | **no** | `U(0.25, 0.60)` | yes — within-world spread of `r_i` | no | **U** |
| `cannibalization_rate` | **no** | `U(0.15, 0.45)` | **no** — does not touch `p1`; zeroes contribution *after* an incremental conversion | no | **N on the payoff**, unhinted. Enters `E[net]` linearly and is unobservable |
| `baseline_conversion` | **no** directly | `U(0.06, 0.20)` | yes | no | **U**, and recoverable — see §3.2 |
| `seasonality_index` | **no** directly | product of drawn `SEASONAL_EVENTS` multipliers | yes, via `p0` | no | **U**, and decodable — see §3.2 |
| `aov_median_inr`, `aov_sigma` | **no** directly | `U(500,2500)`, `U(0.35,0.75)` | yes, via `eov` → depth | no | **U**, recoverable from the observed `eov` distribution |
| `margin_mean`, `margin_sd` | **no** directly | `U(0.22,0.38)`, `U(0.03,0.08)` | no | no | affects payoff only; the realized catalogue mean is published exactly (§3.2) |

### 2.4 Outcome-level random variables (OUTCOMES stream, `generator.py:715-720`)

| variable | observable? | generated from | affects response? | cross-world stable? | status |
|---|---|---|---|---|---|
| `u_i` | **no, never** | `rng.random(n)`, one per customer, **shared by both arms** | decides which region the customer lands in | no | **N — pure realization noise, independent of every feature and every latent.** This is the variable that makes individual `τ` unpredictable in principle |
| `L_i` (`basket_noise`) | **no** | `LN(0, 0.20)` per customer | yes — perturbs `b`, hence `d`, `lift`, cost, payoff | no | **N**, but with a *known* distribution, so `E[·|eov_i]` is computable |
| `PF_ij` (`pull_forward_draws`) | **no** | `U(0,1)` per customer × intervention | no — applied after conversion | no | **N**. Zeroes the payoff of an incremental conversion with prob. `cann` |

### 2.5 Intervention parameters (`schema.py:243-260`; `generator.py:466-535`) — all in `MerchantView`

| variable | observable? | generated from | affects response? | cross-world stable? | status |
|---|---|---|---|---|---|
| `kind` | yes | one per kind, always four | yes — selects `a_j` and the depth formula | yes, the four kinds are fixed | **U**, fully observable |
| `flat_discount_inr` | yes | `j·margin_mean·mean_basket`, `j ~ U(0.07,0.29)`, clipped ₹20–2,000 | yes — `d = flat/tb` | value world-scaled | **U**, observable |
| `discount_pct` | yes | `j·margin_mean`, `j ~ U(0.07,0.30)` | yes — `d = pct`, **independent of basket** | — | **U**, observable |
| `shipping_fee_waived_inr` | yes | `j·margin_mean·mean_basket`, `j ~ U(0.06,0.25)`, clipped ₹20–250 | yes — `d = fee/tb` | — | **U**, observable |
| `bundle_added_value_inr` | yes | `ratio · breakeven_uplift`, `ratio ~ U(0.3,0.9)` (`generator.py:530-535`) | yes — raises `tb` | — | **U**, observable |

### 2.6 World-level observables (`MerchantView`, `contracts.py:130-155`)

| variable | observable? | generated from | affects response? | cross-world stable? | status |
|---|---|---|---|---|---|
| `observed_conversion` | yes | `mean(baseline_purchase_prob)` — **exact population mean of the latent** (`contracts.py:322`) | — | — | **exact functional of a latent** |
| `observed_aov_inr` | yes | `mean(expected_order_value_inr)` — exact | — | — | exact |
| `observed_margin` | yes | `mean(contribution_margin)` — **the identical scalar `M` used in the outcome draw** (`generator.py:713`) | payoff scale | — | **exact** |
| `budget_inr` | yes | `round(projected_revenue · budget_share, −3)` | no | no | deterministic in world scale |
| `SegmentView.name` / `notes` / `behaviour_tags` | yes | copied from the **fixed 7-row `SEGMENT_ARCHETYPES` table** (`vocabulary.py:181-263`) | yes — identifies the archetype, hence all four multipliers | **YES — the table is a module constant, identical in every world** | **U**, and the only cross-world-stable segment identifier |
| `SegmentView.share` | yes | Dirichlet(2.5) over segments | no | no | ⊥ |
| `semantic.customer_service_themes` etc. | yes | 4 strings emitted from latents at 0.78/0.18 (`generator.py:267-278`) | — | signal strings are fixed constants | **D** — text downstream of a latent, at partial fidelity |
| `semantic.seasonal_events` | yes | drawn from a **fixed 12-row table pairing each string with its exact multiplier** (`vocabulary.py:270-283`) | yes, via `seasonality_index` → `p0` | **yes, table is constant** | **D**, and a *deterministic* decode of the latent |
| `products[*]` (price, cost, margin, stock_status, age) | yes | sampled from `aov_median`, `margin_mean/sd` | payoff scale via `M` | no | exact for `M` |
| `InterventionHistory.net_per_treated_customer_inr`, `.standard_error_inr` | yes | **simulated past campaign through the same response model** (`contracts.py:245-320`), 300 treated + 300 control, blake2b-seeded on `world_id` | — | relationship stable, value world-specific | **D — the only field in any view that is causally downstream of the latent treatment response.** Uses the response model, never `Y(0)`/`Y(1)` |

---

## 3. The six questions

### A. Which components of individual net effect are deterministic/predictable functions of merchant-visible features?

Take the conditional mean from §1 and mark each factor:

```
E[net_ij | X] = p0_i·( bundle_term_j·M − cost_ij )  +  (p1_ij − p0_i)·( (1−cann)·tb_ij·M − cost_ij )
                ↑                        ↑    ↑        ↑                        ↑    ↑
              latent              observable observable  latent            latent  observable-in-expectation
```

**Exactly observable, with no estimation:**

- **`M`** — `observed_margin` is byte-identical to the `catalogue_margin` scalar used in the outcome draw. Compare `generator.py:713` with `contracts.py:324`. The payoff scale is published exactly.
- **`eov_i`** — published exactly as `historical_aov_inr`.
- **All intervention parameters** — `kind`, `flat_discount_inr`, `discount_pct`, `shipping_fee_waived_inr`, `bundle_added_value_inr`.

**Computable in expectation from observables, because the noise distribution is a source constant:**

- **`b_i = eov_i · L_i`** with `L ~ LN(0, 0.20)` fixed in the generator, so `E[b_i | eov_i] = eov_i · e^{0.02}`.
- **`cost_ij`** — a deterministic function `d_j(tb)·tb` of the basket and published intervention parameters. Note the structural split (`schema.py:261-286`):
  - `PERCENTAGE_DISCOUNT` / `BUNDLE`: `d = pct`, constant ⟹ `cost = pct · tb`, **proportional to basket**.
  - `FLAT_DISCOUNT` / `FREE_SHIPPING`: `d = fixed/tb`, so `cost = min(fixed, 0.5·tb)` — **a constant in rupees for every basket above `2·fixed`**, and capped below that.
- **`tb_ij`** — `b_i` plus a published constant for bundles.

**Not observable at the individual level:** `p0_i`, `p1_ij`, and therefore the always-buyer share and the complier share; `cann`; `r_i`; `ε_i`; `a_j`.

**Conclusion.** The **payoff and cost sides of the conditional mean are exactly or near-exactly determined by merchant-visible features.** The **probability side — which region a customer falls into — is not.** The individual latents `p0_i`, `ε_i`, `r_i` reach the observables only through the segment archetype and through world-level aggregates; their idiosyncratic factors `LN(0,0.25)`, `N(0, elasticity_sd)`, `LN(0, responsiveness_sigma)` have **no observable descendant anywhere in the code.**

### 3.2 A related structural fact, stated because it is a property of the code

Several world latents are **recoverable, not merely hinted**, from published aggregates:

- `M` — published exactly.
- `aov_median`, `aov_sigma` — the full `eov` vector is published, so its distribution is observable.
- `seasonality_index` — `SEASONAL_EVENTS` is a fixed table of `(string, multiplier)` pairs (`vocabulary.py:270-283`) and the drawn strings are published in `semantic.seasonal_events`.
- `seg.conversion_multiplier` / `elasticity_multiplier` / `aov_multiplier` / `responsiveness_mean` — `SEGMENT_ARCHETYPES` is a fixed 7-row table and `SegmentView.name` identifies the row exactly.
- `baseline_conversion` — `observed_conversion` is the exact mean of `p0_i`, and the segment shares, segment multipliers and `seasonality_index` are all observable, so the remaining unknown is only the mean of `LN(0,0.25)`, itself a constant.

This is a statement about the *simulator's information structure*, and it depends on the archetype and seasonal tables being module constants. It is not a claim about what a real merchant knows, and I make no such claim.

**Still unrecoverable after all of the above:** `promo_response_scale`, the four `*_affinity` values, `responsiveness_sigma`, `cannibalization_rate`, and every per-customer idiosyncratic factor. `cannibalization_rate` in particular enters `E[net]` as a direct linear discount on the complier payoff and has **no signal of any kind** anywhere in any view.

### B. Which components are independent customer-level randomness?

Three, all drawn in the OUTCOMES stream, all independent of every feature observed or latent:

1. **`u_i ~ U(0,1)`** — the single common random number deciding both arms. This alone converts a smooth conditional mean into a three-valued spike. **No feature set, including full knowledge of every `WorldParams` field and every customer latent, has any information about `u_i`.**
2. **`L_i ~ LN(0,0.20)`** — basket noise. Independent, but with a source-constant distribution, so it is integrable rather than merely unknown.
3. **`PF_ij ~ U(0,1)`** — pull-forward. Independent, gated by the unobservable `cann`.

Plus three **latent-level** idiosyncratic draws with no observable descendant: `LN(0,0.25)` on `p0`, `N(0, elasticity_sd)` on `ε`, `LN(0, responsiveness_sigma)` on `r`.

And three **observable** fields that are independent of everything and therefore contribute no signal by construction: `tenure_days`, `orders_last_90d`, `days_since_last_order` (`generator.py:436-438`).

### C. Does `historical_aov_inr` affect both incentive cost and treatment response — and is raw τ therefore the wrong objective?

**It affects three distinct channels, and the source shows all three.**

1. **Response.** `d_ij = effective_depth_j(tb_ij)` and `lift = (1−d)^{ε} − 1`. For `FLAT_DISCOUNT` and `FREE_SHIPPING`, `d = fixed/tb`, so **depth falls as basket rises ⟹ lift falls ⟹ `p1 − p0` falls**. `historical_aov_inr` is therefore *negatively* related to complier probability for the two rupee-denominated kinds. For `PERCENTAGE_DISCOUNT` and `BUNDLE`, `d = pct` is constant in basket, so response is **unaffected** by AOV.
2. **Payoff.** The complier payoff is `tb·M`, **increasing in basket for all four kinds**.
3. **Cost.** `cost = d·tb`. For pct/bundle this is `pct·tb`, **increasing in basket**. For flat/shipping it is `min(fixed, 0.5·tb)` — **flat in rupees above `2·fixed`**, i.e. *not* increasing.

So a single observable enters the response channel, the payoff channel and the cost channel, **with kind-dependent and partly opposite signs**.

**Is raw τ the wrong objective for targeting?** Structurally, yes, and for a reason visible in the definitions rather than in any measurement:

- `τ = Y1.contrib − Y0.contrib` **contains no cost term.** `net = τ − cost·1{conv1}` (`harness.py:290-292`) is what `_true_population_net` scores and what a merchant banks.
- The two differ by a quantity that is **near-deterministic in observables** (`cost` is a published function of the basket, and the basket is an exactly-published latent times a source-constant noise term).
- Their **rankings differ**. In the always-buyer region, `τ = 0` for the three non-bundle kinds while `net = −cost < 0`. A τ-objective is *exactly indifferent* to always-buyers; a net-objective assigns them the entire downside of the campaign. Since `P(always-buyer) = p0`, the two objectives disagree precisely on the axis (`p0`) that decides whether a promotion loses money.

**Therefore: ranking by predicted raw τ is not the same problem as ranking by predicted net, the gap between them is concentrated in the region where the loss lives, and part of that gap is observable.** That is established by the definitions in `schema.py:478-509`, `schema.py:288-295` and `harness.py:279-293` — no simulation required.

### D. Is `segment_id` world-specific or cross-world stable?

**`segment_id` is world-specific. `SegmentView.name` is cross-world stable.** Both facts are in `_sample_segments` (`generator.py:374-392`):

```python
n_segments = int(rng.integers(4, 7))                       # 4, 5 or 6
archetypes = _choose(rng, vocab.SEGMENT_ARCHETYPES, n_segments)   # without replacement
... Segment(segment_id=f"seg_{index}", name=str(archetype["name"]), ...)
```

`segment_id` is the **position in a per-world random sample**. `seg_0` is "Deal seekers" in one world and "Gift buyers" in the next. As a cross-world feature it is a permuted label carrying **zero transferable information**.

`name` is copied verbatim from `SEGMENT_ARCHETYPES`, a module-level `Final` tuple of **7 fixed rows** (`vocabulary.py:181-263`). The same name always means the same `conversion_multiplier`, `elasticity_multiplier`, `aov_multiplier` and `responsiveness_mean`. `behaviour_tags` and `notes` are likewise fixed per archetype.

So the within-world segment signal and the cross-world segment signal are carried by **different fields**, and only one of them was in the feature list used by the frozen predictor (§ "Supported by existing measurements").

### E. Does any excluded observable field contain cross-world transferable treatment-effect information?

Structurally, yes — three, and I enumerate without judging whether any is realistic merchant information:

1. **`SegmentView.name` / `behaviour_tags` / `notes`.** Cross-world stable by construction (fixed 7-row table), and the archetype determines `responsiveness_mean` — the segment-level component of `r_i`, the heterogeneity knob. This is the transferable form of the signal that `segment_id` carries only within a world.
2. **`InterventionHistory.net_per_treated_customer_inr` and `.standard_error_inr`.** The only field in any view **causally downstream of the latent treatment response**: it is produced by running the same `treated_conversion_probability` model over 300 treated and 300 control customers (`contracts.py:245-320`). Its *value* is world-specific; the *relationship* between it and the world's response latents is fixed by the code, so it is transferable in the sense that a rule mapping history to expected response has the same meaning in every world. It is a world-level quantity and says nothing about *which* customer to treat.
3. **`semantic.seasonal_events`.** A deterministic decode of `seasonality_index` through a fixed 12-row table, and `seasonality_index` multiplies every `p0_i`. Cross-world stable because the table is constant.

Marginally, the four **coupled signal strings** (`SIGNAL_SHIPPING_THRESHOLD`, `SIGNAL_CLEARS_WHEN_DISCOUNTED`, `SIGNAL_COMPETITOR_PRICE_WAR`, `SIGNAL_CONVERSION_DRIFT`) are fixed constants emitted at 0.78 TP / 0.18 FP, so the *mapping* string → posterior shift is cross-world stable while the *evidence* is deliberately weak. They point at `shipping_affinity`, `clearance_affinity`, `competitive_pressure` and `baseline_conversion` respectively — world-level, not customer-level.

**No excluded field carries cross-world transferable information about *individual* heterogeneity beyond what the segment archetype provides.** The idiosyncratic factors on `p0`, `ε` and `r` have no observable descendant in the code.

### F. Can a legitimate feature-based targeting ceiling be defined without realized `Y(0)`/`Y(1)`?

**Yes. It is definable from the generator's structural form alone, and it is not the quantity the existing diagnostics computed.**

For a feature set `X` and policy `π: X → {0,1}`, value is `V(π) = E[π(X)·net]`, which by the tower property equals `E[π(X)·g(X)]` with `g(X) = E[net | X]`. The optimum over all policies measurable in `X` is

```
V*(X) = Σ_i max( 0, E[net_i | X_i] )
```

where the expectation integrates over `u_i`, `L_i`, `PF_ij` and the posterior of the unobserved latents given `X_i`. Every ingredient is a source constant or a published distribution: the region probabilities come from `p0`/`p1`, the payoff from `tb·M`, the cost from `d_j(tb)·tb`, and the priors from `_sample_params` / `_sample_customers`. **No realized outcome enters.**

Two things follow directly.

1. **`Σ_i max(0, net_i)` computed from realized `Y(0)`/`Y(1)` is not a feature-based ceiling.** It selects on `u_i` and `PF_ij`, which §B establishes are independent of every feature and every latent. It is a bound on hindsight, and its gap to any policy is guaranteed by the presence of conversion noise rather than by anything about this simulator's features. Under the definitions in `generator.py:715-763` this is a structural fact, not an interpretive one.
2. **The full-latent ceiling `V*(Θ)`**, with `Θ` the complete `WorldParams` plus per-customer latents, is the correct upper envelope for *any* feature set, and by the data-processing inequality `V*(X) ≤ V*(Θ) ≤ Σ_i max(0, net_i)` for every `X`. The middle term is the one a targeting claim needs, and the source contains everything required to define it.

**Computing either would be a new diagnostic and is out of scope here.** I state only that the definition is available without touching ground truth.

---

## PROVEN BY GENERATOR STRUCTURE

1. `tenure_days`, `orders_last_90d`, `days_since_last_order` are drawn from fixed distributions with no dependence on `segment_id` or any latent (`generator.py:436-438`). They are independent of the treatment effect and can carry no signal under any method.
2. `customer_id` is a positional index (`generator.py:433`) with no cross-world content.
3. `historical_aov_inr` is `expected_order_value_inr` copied verbatim, with **no measurement noise** (`contracts.py:340`) — a latent published exactly.
4. `observed_margin` is byte-identical to the `M` used in the outcome draw (`contracts.py:324` vs `generator.py:713`).
5. `u_i` is one U(0,1) shared by both arms, independent of every feature and latent (`generator.py:717`). Individual `τ` is therefore a three-valued spike whose realization is unpredictable in principle.
6. `p1 ≥ p0` always, since `response_multiplier ≥ 1` (`generator.py:611-623`) — no customer is ever harmed into non-conversion.
7. `net = τ − cost·1{conv1}` (`harness.py:290-292`), and `τ` omits the cost term entirely. In the always-buyer region `τ = 0` while `net = −cost` for the three non-bundle kinds.
8. `cost` is a deterministic function of basket and published intervention parameters (`schema.py:288-295`): proportional to basket for pct/bundle, **constant in rupees above `2·fixed`** for flat/shipping.
9. `historical_aov_inr` enters response (via depth, for rupee-denominated kinds only), payoff, and cost — three channels with kind-dependent signs.
10. `segment_id` is a per-world positional label over a random sample of archetypes and is **not** cross-world stable; `SegmentView.name` is drawn from a fixed 7-row constant table and **is** (`generator.py:374-392`, `vocabulary.py:181-263`).
11. `promo_response_scale`, `responsiveness_sigma`, `pct_affinity`, `bundle_affinity` and `cannibalization_rate` have **no emitted signal of any kind**. `shipping_affinity`, `clearance_affinity`, `competitive_pressure` and low `baseline_conversion` are hinted at 0.78 TP / 0.18 FP (`generator.py:267-278`).
12. `InterventionHistory` is the only view field causally downstream of the latent treatment response (`contracts.py:245-320`), and it is world-level.
13. `SEASONAL_EVENTS` and `SEGMENT_ARCHETYPES` are module constants, so `seasonality_index` and the four segment multipliers are decodable from published strings.
14. A feature-based ceiling `V*(X) = Σ max(0, E[net|X])` is definable from the generator's structural form with no reference to realized outcomes; `Σ max(0, net_i)` computed from `Y(0)`/`Y(1)` is not such a ceiling.
15. The seven RNG child streams are independent (`generator.py:66-79`), so no cross-stream information exists beyond explicitly passed arguments.

## SUPPORTED BY EXISTING MEASUREMENTS

*(from the recovered `predict.py` / `policy.py` output; not re-run, not re-verified here)*

- Per-field mean |Spearman ρ| against true individual net on 30 test worlds: `tenure_days` 0.0057, `orders_last_90d` 0.0066, `days_since_last_order` 0.0073, `historical_aov_inr` 0.0398, `segment_id` (ordinal) 0.0714 — consistent with items 1 and 3 above.
- Segment eta² = 0.00702 on those worlds. This measures **`segment_id` within world**, not the six fields jointly.
- The frozen cross-world predictor used four numeric fields only; `segment_id` was excluded because it does not transfer. Item 10 identifies `SegmentView.name` as the field that would transfer — that this was excluded is established; **what it would yield is not measured and is not asserted here.**
- Frozen ridge ρ = +0.0354 and gradient boosting ρ = +0.0365, both p < 0.001 across 30 worlds.

## NOT ESTABLISHED

- **The magnitude of `Var(E[net|X])` for any `X`.** No variance decomposition of the conditional mean is computed here, and none exists in any surviving artifact.
- **The value of `V*(X)` or `V*(Θ)`.** Definable (item 14); not computed. So the fraction of attainable targeting value that any feature set reaches is unknown.
- **Whether any feature-based policy clears an economic threshold.** Nothing above bears on it. Structure says which channels are observable, not what they are worth.
- **How much information `SegmentView.name` carries in practice.** Item 10 establishes it is the cross-world-stable carrier of `responsiveness_mean`; its predictive value is unmeasured.
- **The posterior of the unobserved latents given `X`.** Required by the `V*(X)` definition; deriving it would be new work.
- **Anything about real merchants.** Every statement above is about this generator. `docs/simulator.md` §5 already records that absolute results here have no external validity.
- **Whether `cannibalization_rate`'s unobservability is binding.** It enters `E[net]` linearly on the complier term and has no signal; the size of that effect is not established.

---

**Stopped as instructed.** Source inspection only — nothing modified, nothing run, no metric created, no mechanism proposed, no generator change suggested.
