# Demo — the product decision, on declared fixtures

> **DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE.**
> The three merchants here are hand-declared for the demo. They are not drawn
> from `worlds/` or `worlds_cycle2/`, they are never scored, and no number they
> produce is evidence about anything — least of all about real merchants.

The research lives in `docs/simulator.md` (pre-registered) and
`analysis/posthoc/` (post-hoc). This directory is the product.

## Running it

```
python -m demo.run_scenarios                 # all three, text output
python -m demo.run_scenarios --scenario C    # just the learning loop
python -m demo.run_scenarios --json          # machine-readable
python -m streamlit run demo/recommendation_app.py
```

No API key and no LLM call. Each scenario supplies the payload a model would
have produced, and it passes through the same validation a live reply would.
`src/agent/proposer.py` adapts a real client when one is available.

## The three scenarios

| | merchant | decision | why |
|---|---|---|---|
| **A** | thin margin, Rs.120 flat discount | `DO_NOT_PROMOTE` | Contribution per order is Rs.132 and the incentive takes Rs.120 of it. No lift repays that, so the campaign is refused before an experiment is contemplated. |
| **B** | plausible 12% offer, one small past campaign | `RUN_EXPERIMENT_FIRST` | The economics could work, but the confidence comes from 300 customers with an error bar wide enough to contain zero. Test before spending. |
| **C** | 45% margin, Rs.60 delivery fee waived | `RUN_EXPERIMENT_FIRST` → `PROMOTE` | Break-even is near one point of lift. The pilot measures it, the result clears the scaling rule and the rollout gate, and only then does spending open. |

Scenario C is the architectural one. `PROMOTE` is not reachable from the initial
reasoning at all: `recommend()` tops out at `RUN_EXPERIMENT_FIRST` by
construction, and only `decide_after_experiment()` — reading a real
`FinalResult` through `assess_scale()` and `gate_rollout()` — can approve a
rollout.

## What the model is shown, and what it is not

**Shown:** merchant aggregates, catalogue, the offers and their per-order costs,
past campaign results with standard errors, customers grouped into order-value
cohorts, and the merchant's written context.

**Not shown:** any hidden simulator parameter, any customer's true response,
any realized outcome, and no `SegmentView` name, tag or note. Those last are a
bijective key to withheld archetype multipliers in the research simulator
(`analysis/posthoc/provenance/segmentview.md`), so they are excluded from the
product entirely — `build_brief()` reads no segment field at all.

## The open question the demo does not hide

Every experiment recommendation carries
**`G4_VALUE_OF_INFORMATION_UNRESOLVED`** through to the merchant-facing output.

The system can tell you deterministically whether a pilot is *affordable*.
Whether it costs less than the information it buys is an unresolved question in
this project, with no committed constant behind it. Rather than invent a
threshold and present the matter as settled, the recommendation names it. A
visible open question is worth more than a fabricated precision, and a test
(`ADV-11`) fails if it is ever quietly dropped from the merchant's view.

## Fixture integrity

Scenario C's parameters and random seed were committed at `08cd977`, **before**
its first execution, with their fingerprint recorded in
`fixtures/SCENARIO_C.lock`. `ADV-12` recomputes that fingerprint and fails if
either changed afterwards. The fixture reached `PROMOTE` on its first run; there
was no second attempt, no seed search, and no gate was adjusted.

Each fixture declares its own true response (`declared_true_lift_absolute`) so
its executor can generate experiment observations. That value is never read by
the brief, the model, or the policy — only by `FixtureExecutor`, standing in for
the world.
