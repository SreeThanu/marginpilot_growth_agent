# Source-inspection provenance

**Post-hoc. Not pre-registered.** See `../README.md`. These are read-only findings about what the committed generator actually does — no simulation was run to produce them, and nothing was modified.

| document | subject |
|---|---|
| `segmentview.md` | full dependency trace of `SegmentView.name`, `.behaviour_tags`, `.notes` |
| `net-effect-decomposition.md` | which components of customer-level net effect are predictable from merchant-observable features, and which are irreducible randomness |

---

## The SegmentView finding, in short

`SegmentView` publishes `name`, `notes` and `behaviour_tags` while deliberately withholding the four behaviour multipliers (`src/eval/contracts.py:116-127`, whose docstring says *"`elasticity_multiplier` would hand the agent a number it is supposed to estimate"*).

**Contamination test: clean.** The ancestor set of all three fields closes at exactly two roots — the constant table `src/world/vocabulary.py:181-265`, and the world seed via `streams[_STREAM_SEGMENTS]`. No `Y(0)`, `Y(1)`, realized conversion, `u_i`, `responsiveness`, `elasticity`, affinity, or post-campaign outcome appears at any depth.

**But the direction of dependency is the finding.** In the same object literal (`src/world/generator.py:381-388`), the archetype row supplies `name`/`notes`/`tags` **and** `conversion_multiplier`, `elasticity_multiplier`, `aov_multiplier`, `responsiveness_mean` — which then generate every customer latent at `generator.py:405-431`. The published fields are **siblings** of the withheld response parameters, not descendants. Seven distinct names map one-to-one onto seven distinct multiplier quadruples in a module constant, so **publishing `name` is informationally identical to publishing the four multipliers exactly.**

**Archetype assignment** is seed-only (`generator.py:376` world-level, `:399` customer-level) and causally *upstream* of the latents. It is not drawn from any hidden response variable.

**Surface prose vs encoded information.** The `notes` strings mix explicit response statements (*"price-insensitive"*, *"they clear the cart the moment a code lands"*, *"a discount tells them little"*) with RFM claims (*"then nothing for a quarter"*, *"order on salary week"*) that the generator **does not implement** — `tenure_days`, `orders_last_90d` and `days_since_last_order` are drawn from fixed distributions with no segment dependence (`generator.py:436-438`). Only basket size has a realized counterpart. Regardless of what the prose says, any one of the seven strings identifies the row exactly.

**`segment_id` alone carries zero cross-world information**: it is `f"seg_{index}"` over a uniformly random sample of archetypes, so the archetype at each position is exchangeable. The information lives in the `SegmentView` join, not the label.

---

## The separation that must be preserved

> **Provenance in this simulator is established. Real-world merchant availability is not.**

Everything above is a statement about what this generator does, derived from committed source. **Nothing in this project establishes whether a real merchant possesses information equivalent to `SegmentView.name`/`notes`/`tags`.** That is a separate judgement, to be made by a human on sourced grounds, and it has not been made.

In particular, the submission must not silently convert *"exists in the simulator"* into *"available to a real merchant"*, and must not treat these fields as merchant-realistic merely because they read like customer descriptions. Where a result depends on this information — notably the Level-B and higher ceilings in `../ceiling/` — that dependence is stated rather than assumed away.
