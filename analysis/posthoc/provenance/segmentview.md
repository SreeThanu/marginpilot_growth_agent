# Provenance — `SegmentView.name`, `.behaviour_tags`, `.notes`

**Date:** 1 September 2026
**Method:** source inspection only. Nothing modified, no diagnostic created or run, no simulation, no LLM, no sealed data, no `Y(0)`/`Y(1)` used as input to anything.
**No realism judgment is made anywhere in this document.**

---

## 1. Where each field is generated

All three are assigned in one expression, `_sample_segments`:

```
src/world/generator.py:374-391

374  def _sample_segments(rng: np.random.Generator) -> tuple[Segment, ...]:
375      n_segments = int(rng.integers(4, 7))
376      archetypes = _choose(rng, vocab.SEGMENT_ARCHETYPES, n_segments)
377      shares = rng.dirichlet(np.full(n_segments, 2.5))
378      return tuple(
379          Segment(
380              segment_id=f"seg_{index}",
381              name=str(archetype["name"]),                        # <- name
382              share=_round(float(share)),
383              notes=str(archetype["notes"]),                      # <- notes
384              behaviour_tags=tuple(archetype["tags"]),            # <- tags
385              conversion_multiplier=float(archetype["conversion_multiplier"]),
386              elasticity_multiplier=float(archetype["elasticity_multiplier"]),
387              aov_multiplier=float(archetype["aov_multiplier"]),
388              responsiveness_mean=float(archetype["responsiveness_mean"]),
389          )
390          for index, (archetype, share) in enumerate(zip(archetypes, shares))
391      )
```

| field | generated at | value source |
|---|---|---|
| `name` | `generator.py:381` | `archetype["name"]`, verbatim |
| `notes` | `generator.py:383` | `archetype["notes"]`, verbatim |
| `behaviour_tags` | `generator.py:384` | `archetype["tags"]`, verbatim |

Storage type: `src/world/schema.py:156-175`. Projection into the merchant-facing view: `src/eval/contracts.py:360-369`, a verbatim copy —

```
360          segments=tuple(
361              SegmentView(
362                  segment_id=s.segment_id,
363                  name=s.name,
364                  share=s.share,
365                  notes=s.notes,
366                  behaviour_tags=s.behaviour_tags,
367              )
368              for s in world.segments
369          ),
```

`SegmentView` is defined at `contracts.py:116-127` and carries exactly `segment_id, name, share, notes, behaviour_tags` — the four multipliers at `generator.py:385-388` are **not** copied. The docstring states the intent (`contracts.py:119-120`):

> `Deliberately without the behaviour multipliers. ``elasticity_multiplier`` would hand the agent a number it is supposed to estimate.`

§5 establishes what that withholding does and does not accomplish.

## 2. Complete upstream variable list

For all three fields the ancestor set is identical and **closed at three items**:

| ancestor | definition | is it a hidden response variable? |
|---|---|---|
| `vocab.SEGMENT_ARCHETYPES` | `src/world/vocabulary.py:181-265`, a module-level `Final` tuple of 7 literal dicts | **No** — a compile-time constant. Has no inputs at all |
| `rng` = `streams[_STREAM_SEGMENTS]` | `generator.py:684` → `_streams(seed)` at `:77-79`, child stream **index 3** of `SeedSequence(seed).spawn(7)` (`:69-75`) | **No** — a function of the integer world seed only |
| `n_segments`, the `_choose` index draw, `shares` | `generator.py:375-377`, all from that same stream | **No** — same seed-only provenance |

`_choose` (`generator.py:177-185`) resolves to `rng.choice(len(items), size=..., replace=False)` — a uniformly random ordered sample of table rows.

## 3. Full transitive dependency trace

Chasing every ancestor to a root:

```
name / notes / tags
  └── archetype  (one row of SEGMENT_ARCHETYPES)
        ├── SEGMENT_ARCHETYPES ......... literal constant, vocabulary.py:181-265  [ROOT]
        └── streams[_STREAM_SEGMENTS] .. SeedSequence(seed).spawn(7)[3]           [ROOT: world seed]
```

**Checked against the contamination list, hop by hop:**

| candidate contaminant | present anywhere in the chain? | evidence |
|---|---|---|
| `Y(0)`, `Y(1)` | **No** | produced in `generate_ground_truth`, `generator.py:710-780`, which runs *after* `generate_world` returns (`:783-786`) and takes the world as input |
| realized conversion / realized net | **No** | `converted0`/`converted1` at `generator.py:726,745`; strictly downstream |
| `u_i`, `PF_ij`, basket noise `L_i` | **No** | drawn from `streams[_STREAM_OUTCOMES]` = index 6 (`generator.py:715-720`), a different child stream |
| `responsiveness` `r_i`, `price_elasticity` `ε_i`, `baseline_purchase_prob` `p0_i` | **No** | drawn in `_sample_customers` from `streams[_STREAM_CUSTOMERS]` = index 4, at `generator.py:405-424` — **after** segments are built (`generate_world` order, `:685-686`) |
| intervention affinity `a_j`, `promo_response_scale` | **No** | `_sample_params`, `streams[_STREAM_PARAMS]` = index 0, `generator.py:151-157`; never passed to `_sample_segments`, whose only argument is `rng` (`:374`) |
| any post-campaign outcome | **No** | nothing in the chain postdates world construction |

**Result: no ancestor of `name`, `notes` or `tags` is a hidden response variable.** The contamination test as posed returns clean on every hop.

**But the direction of dependency is the finding, not the absence of contamination.** The archetype row is not *derived from* the response parameters — it is their **common ancestor**. In the same object literal that supplies `name`/`notes`/`tags`, the same row supplies `conversion_multiplier`, `elasticity_multiplier`, `aov_multiplier` and `responsiveness_mean` (`generator.py:385-388`), and those propagate into every customer latent:

```
generator.py:405-431   (inside _sample_customers, per customer)

405   p0 = ( params.baseline_conversion * params.seasonality_index
408          * segment.conversion_multiplier * lognormal(0, 0.25) )
413   elasticity = -abs( params.elasticity_mean * segment.elasticity_multiplier + N(0, elasticity_sd) )
419   responsiveness = ( segment.responsiveness_mean
421                      * params.promo_response_scale * lognormal(0, responsiveness_sigma) )
426   order_value = ( params.aov_median_inr * segment.aov_multiplier * lognormal(0, aov_sigma) )
```

So the graph is:

```
                     archetype row
                    /              \
       name/notes/tags          conversion_multiplier, elasticity_multiplier,
       (published)              aov_multiplier, responsiveness_mean  (withheld)
                                        |
                                 p0, ε, r, eov   (generator.py:405-431)
                                        |
                                    p1  ->  Y(0), Y(1)
```

`name`/`notes`/`tags` are **siblings of the response parameters, not descendants of them**. That is a *stronger* informational relationship than descent would be: a descendant is noisy, a sibling emitted from the same constant row is exact.

## 4. The literal `notes` strings, as required

Quoted verbatim from `src/world/vocabulary.py`. Each row's multipliers are shown beside its text so the correspondence is visible rather than asserted.

**`vocabulary.py:183-192` — "Bulk regulars"** · conv 1.6 · elas **0.45** · aov 1.5 · resp **0.5**
> "Bulk buyers, price-insensitive, order on salary week. They buy the same four or five SKUs on a near-fixed cycle and rarely browse."
> tags: `("high_frequency", "price_insensitive", "salary_week_cycle")`

**`vocabulary.py:195-204` — "Deal seekers"** · conv 0.55 · elas **1.7** · aov 0.85 · resp **1.9**
> "Wait for sales and stack coupons where they can. High traffic, low conversion at full price, and they clear the cart the moment a code lands."
> tags: `("coupon_stacking", "price_sensitive", "sale_waiting")`

**`vocabulary.py:207-216` — "New arrivals"** · conv 0.8 · elas 1.25 · aov 0.75 · resp 1.3
> "First order placed in the last 30 days, mostly from social ads. Undecided on the brand; a bad first delivery loses them permanently."
> tags: `("first_purchase", "ad_sourced", "undecided")`

**`vocabulary.py:219-228` — "Lapsing loyalists"** · conv 0.45 · elas 0.9 · aov 1.15 · resp 0.9
> "Two years of steady orders, then nothing for a quarter. They know the catalogue well, so a discount tells them little they do not already know."
> tags: `("lapsing", "long_tenure", "catalogue_literate")`

**`vocabulary.py:231-240` — "Gift buyers"** · conv 0.9 · elas **0.6** · aov 1.35 · resp **0.7**
> "Order in festival windows, ship to addresses other than their own, and care more about delivery date than price."
> tags: `("seasonal", "gifting", "delivery_sensitive")`

**`vocabulary.py:243-252` — "Cart abandoners"** · conv 0.5 · elas 1.35 · aov 0.95 · resp 1.5
> "Reach checkout and stop. Support tickets from this group mention shipping cost more than product price."
> tags: `("checkout_dropoff", "shipping_sensitive")`

**`vocabulary.py:255-264` — "Small-basket regulars"** · conv 1.25 · elas 1.0 · aov **0.6** · resp 1.15
> "Order often but small — single items, rarely bundles. Free-shipping thresholds are the main thing standing between them and a bigger basket."
> tags: `("high_frequency", "small_basket", "threshold_sensitive")`

### 4.1 Fragment-level classification of the text

| fragment | kind | reconstructible from pre-campaign observables in **this** generator? |
|---|---|---|
| "price-insensitive" (Bulk regulars) | **response/elasticity** | No |
| "they clear the cart the moment a code lands" (Deal seekers) | **explicit treatment response** | No |
| "a discount tells them little they do not already know" (Lapsing loyalists) | **explicit treatment response** | No |
| "care more about delivery date than price" (Gift buyers) | **response/elasticity** | No |
| "Free-shipping thresholds are the main thing standing between them and a bigger basket" (Small-basket regulars) | **explicit intervention response** | No |
| tags `price_insensitive`, `price_sensitive`, `shipping_sensitive`, `threshold_sensitive`, `delivery_sensitive`, `coupon_stacking` | **response descriptors** | No |
| "order on salary week", "near-fixed cycle", "Order often" | frequency behaviour | **No** — `orders_last_90d = Poisson(2.0)` for every customer in every world (`generator.py:437`) |
| "First order placed in the last 30 days", "then nothing for a quarter", "lapsing", "long_tenure" | recency / tenure behaviour | **No** — `tenure_days = U{1,…,1459}` (`:436`), `days_since_last_order = U{0,…,399}` (`:438`), both independent of segment |
| "Bulk buyers" / "small — single items" | basket size | **Partially yes** — `aov_multiplier` (1.5 vs 0.6) enters `order_value` at `generator.py:426-429`, and `expected_order_value_inr` is published verbatim as `historical_aov_inr` (`contracts.py:340`) |
| "Reach checkout and stop", "mostly from social ads", "ship to addresses other than their own", "rarely browse" | channel / funnel behaviour | **No** — no such field exists anywhere in the schema |

**The decisive line.** The `notes` text makes RFM claims — cycle, recency, tenure, frequency — that **the generator does not implement**. `tenure_days`, `orders_last_90d` and `days_since_last_order` are drawn from fixed distributions with no dependence on the segment (`generator.py:436-438`). A "Lapsing loyalist" in this simulator is *not* lapsed in the transaction record. So the behavioural half of the prose cannot be recovered from the transaction record, because it is not true of it.

The only fragment that survives contact with the data is basket size, via `aov_multiplier`. Everything else the text asserts is either a response statement or an unimplemented behavioural claim.

## 5. Answer to question 4 — can these fields be reconstructed from pre-campaign observables?

**No, for any of the three.** Two independent reasons, both from source:

1. **The behavioural content is not realized in the observable fields** (§4.1). RFM in the notes is decorative with respect to the generator.
2. **The fields are a bijective key to the withheld multipliers.** The 7 rows of `SEGMENT_ARCHETYPES` have 7 distinct `name` values, 7 distinct `notes` strings and 7 distinct `tags` tuples, and each row carries a distinct `(conversion_multiplier, elasticity_multiplier, aov_multiplier, responsiveness_mean)` quadruple. The table is a module constant. Therefore

   ```
   name  <-->  row  <-->  (conv_mult, elas_mult, aov_mult, resp_mean)
   ```

   is one-to-one in both directions. **Publishing `name` is informationally identical to publishing the four multipliers exactly.** The withholding at `contracts.py:361-367` removes the numerals; it does not remove the information, because the lookup key is published alongside and the table is in the repository.

This answers the "natural-language alias for observable behaviour, or something only the generator knows" question directly: **it is neither an alias for observable behaviour nor merely correlated with generator state — it is an exact, lossless encoding of generator state**, wearing behavioural prose.

## 6. Archetype assignment

| question | answer | source |
|---|---|---|
| **World-level or customer-level?** | **Both, in two stages.** *Which* 4–6 archetypes exist is **world-level** (`generator.py:375-376`). *Which* customer belongs to which is **customer-level** (`generator.py:399`) | `n_segments = rng.integers(4,7)`; `assignments = rng.choice(len(segments), size=params.n_customers, p=shares)` |
| **Deterministic from observable customer behaviour?** | **No.** The customer's segment is a multinomial draw on the Dirichlet shares, taken **before** any of that customer's attributes exist | `generator.py:399` precedes the latent block at `:405-431` |
| **Drawn from a hidden latent?** | **No.** Both stages use only `streams[_STREAM_SEGMENTS]` / `streams[_STREAM_CUSTOMERS]`, i.e. the world seed | `generator.py:376, 399` |
| **Does the archetype depend on responsiveness, elasticity, affinity, conversion probability, or any hidden response variable?** | **No — the dependency runs the other way.** `responsiveness`, `price_elasticity`, `baseline_purchase_prob` and `expected_order_value_inr` are each computed **from** `segment.*_multiplier` | `generator.py:405-431` |

**The conditional flag you specified does not fire, and something stronger applies instead.** You asked me to flag the downstream fields if the archetype were *assigned from* a hidden variable. It is not — it is assigned from the seed. But the archetype **is** the hidden response structure: it is the object that *sets* `responsiveness_mean`, `elasticity_multiplier` and `conversion_multiplier` for every customer in the segment. Inheriting from a common constant ancestor is a tighter coupling than inheriting from a noisy hidden draw, because there is no noise in the link at all.

## 7. The Level-B jump: mechanism A or mechanism B?

**The code supports B: segment identity acting as a proxy for hidden response structure.** Not partially — the entire jump is attributable to it, on the following grounds.

1. The only thing `name`/`notes`/`tags` add over `segment_id` is *which row of the constant table this segment is* (§5). There is nothing else in them: they are verbatim copies of three constant strings.
2. That row determines `responsiveness_mean` (0.5 to 1.9, a 3.8× range), `elasticity_multiplier` (0.45 to 1.7) and `conversion_multiplier` (0.45 to 1.6) — the three latents that set `r_i`, `ε_i` and `p0_i`, hence `p1`, hence the complier and always-buyer shares that decide `E[net]`.
3. The behavioural prose that would support mechanism A — the RFM claims — is **not implemented in the observable fields** (§4.1), so it cannot be the source of predictive power. Only the basket-size fragment has any realized counterpart, and `historical_aov_inr` already supplies that directly at Level A.

**Disclosure about my own prior diagnostic.** The Level-B ceiling I reported (+₹586,958) was computed by mapping `SegmentView.name` through `NAME_TO_IDX` into the constant arrays `CONV_M`, `ELAS_M`, `RESP_M` — that is, by **exercising the bijection directly**. It never parsed a word of `notes` or `tags`. So that figure measures the value of mechanism B exactly, and should be read as *"the value of knowing each customer's archetype row"*, not as *"the value of the segment description"*. The jump from ₹50,133 to ₹586,958 is the value of the lookup, and my method makes that unambiguous.

**What is not established:** whether a policy that reads only the *prose* — without the table — recovers the same value. The prose does rank-order price sensitivity faithfully (`price_insensitive` ↔ elasticity 0.45; `price_sensitive` ↔ 1.7; `delivery_sensitive` ↔ 0.6), so partial recovery is plausible on its face, but nothing in the source establishes how much survives, and I ran nothing to find out. **UNDETERMINED.**

## 8. Verification: bare `segment_id` contributes zero

The claim, re-derived from source rather than restated.

```
generator.py:376   archetypes = _choose(rng, vocab.SEGMENT_ARCHETYPES, n_segments)
generator.py:184   idx = rng.choice(len(items), size=min(size, len(items)), replace=replace)   # replace=False
generator.py:380   segment_id=f"seg_{index}"
generator.py:390   for index, (archetype, share) in enumerate(zip(archetypes, shares))
```

`idx` is a uniformly random **ordered** sample without replacement from `range(7)`. `segment_id` is the *enumeration position* in that ordered sample. Therefore the marginal distribution of the archetype occupying `seg_0` is uniform over all 7 rows, and identically so for `seg_1`, `seg_2`, …

Consequence: for any customer feature vector, `E[net | segment_id = seg_k, ·]` is the **same function** for every `k`, because the archetype is exchangeable across positions. A label with an exchangeable marginal carries no information under prior-only integration. **Confirmed.**

`share` does not rescue it: `shares = rng.dirichlet(np.full(n_segments, 2.5))` (`generator.py:377`) is i.i.d. symmetric across positions and independent of which archetype landed where.

**Where the remaining signal actually lives.** Within a single world `seg_k` is a fixed archetype, so the label does partition the population. Turning that partition into value requires learning which partition is which — obtainable by (i) the `SegmentView` join, which supplies it for free and exactly, or (ii) experimentation, which costs a pilot. The bare label is a partition without a legend. The join is the legend.

---

## Classification

### `SegmentView.name` — **[HIDDEN-DERIVED]**
- `generator.py:381` — `name=str(archetype["name"])`, verbatim from the constant row.
- `generator.py:385-388` — the **same row** supplies `conversion_multiplier`, `elasticity_multiplier`, `aov_multiplier`, `responsiveness_mean`.
- `vocabulary.py:181-265` — 7 distinct names ↔ 7 distinct multiplier quadruples: a bijection.
- `generator.py:405-431` — those multipliers generate `p0`, `ε`, `r`, `eov` for every customer.
- Carries no behavioural content whatsoever beyond the label; it is a pure lookup key into the response parameters.

### `SegmentView.behaviour_tags` — **[HIDDEN-DERIVED]**
- `generator.py:384` — `behaviour_tags=tuple(archetype["tags"])`, verbatim.
- `vocabulary.py:188, 200, 212, 224, 236, 248, 260` — tag tuples are constant per row and mutually distinct, so equally a bijective key.
- Six of the seven tuples contain an explicit response descriptor: `price_insensitive` (`:188`), `price_sensitive` (`:200`), `delivery_sensitive` (`:236`), `shipping_sensitive` (`:248`), `threshold_sensitive` (`:260`), `coupon_stacking` (`:200`).
- The behavioural tags that are not response descriptors — `high_frequency` (`:188`, `:260`), `lapsing`/`long_tenure` (`:224`), `first_purchase` (`:212`) — have **no realized counterpart**: `generator.py:436-438`.

### `SegmentView.notes` — **[HIDDEN-DERIVED]**
*(text content taken alone would be MIXED — see below — but the field as published is not ambiguous.)*
- `generator.py:383` — `notes=str(archetype["notes"])`, verbatim; 7 distinct strings, hence again a bijective key to `generator.py:385-388`. The bijection alone settles the classification regardless of what the prose says.
- **Response content, quoted:** "price-insensitive" (`vocabulary.py:184-187`); "they clear the cart the moment a code lands" (`:196-199`); "a discount tells them little they do not already know" (`:220-223`); "care more about delivery date than price" (`:232-235`); "Free-shipping thresholds are the main thing standing between them and a bigger basket" (`:256-259`).
- **Behavioural content that is not realized:** all cycle/recency/tenure/frequency claims, against `tenure_days = U{1,…,1459}`, `orders_last_90d = Poisson(2.0)`, `days_since_last_order = U{0,…,399}` at `generator.py:436-438` — drawn with no dependence on `segment_id`.
- **Behavioural content that IS realized:** basket size only, via `aov_multiplier` at `generator.py:426-429` → `expected_order_value_inr` → published as `historical_aov_inr` at `contracts.py:340`. This fragment is already available at Level A and adds nothing at Level B.
- Taking the prose in isolation and ignoring its key property, the string is **[MIXED/AMBIGUOUS]**: it interleaves response statements with unimplemented behavioural claims and one implemented one. As an actual field in `MerchantView` it is not ambiguous, because any one of the seven strings identifies the row exactly.

### Additionally

- **Archetype assignment** — **[NOT HIDDEN-DERIVED]**: seed-only, `generator.py:376, 399`. It is causally *upstream* of the response latents (`:405-431`), not downstream. The flag you specified for "assigned from a hidden variable" does not fire; the sibling-of-the-latents relationship in §3 applies instead, and is tighter.
- **Whether the prose alone, without the constant table, carries the Level-B value** — **[UNDETERMINED]**. Nothing in the source settles it and nothing was run.

---

*Provenance only. No realism judgment offered — whether any of this corresponds to information a merchant holds is a separate, human, source-based call. Stopped here.*
