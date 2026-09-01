# MarginPilot — architecture

What is actually in this repository, and where each boundary is enforced. Nothing here is aspirational: every component described below exists in `src/`, and the enforcement points are named by file and symbol so a reviewer can check them.

The organising idea is a single separation:

> **The LLM reasons. Deterministic code decides.** The agent proposes experiments and interprets results; randomization, horizons, budgets, discount ceilings and scaling verdicts are computed by modules that contain no model call and cannot be reached by one.

---

## 1. Module map

```
src/
├── world/        world generator, simulator, sealed potential outcomes.  No agent imports.
├── experiment/   registry, randomization, power/horizon, statistical evaluator
├── economics/    contribution arithmetic. Pure functions.
├── policy/       the money gate. Deterministic. No LLM calls.
├── agent/        the ONLY module that may import an LLM client
├── baselines/    five comparison strategies, same interface as the agent
├── eval/         holdout harness, dev harness, replay, oracle diagnostics, seal guard
├── audit/        append-only, hash-chained decision log
├── payments/     Razorpay test-mode client, webhooks, idempotency, reconciliation
└── ui/           Streamlit dashboard
```

`policy/`, `experiment/` and `economics/` import nothing from `agent/`. They are runnable and testable with no model present, which is what makes the separation checkable rather than promised.

---

## 2. World generation and the simulator

`src/world/generator.py` samples a world as a **pure function of an integer seed**. Seven independent RNG child streams are spawned from one `SeedSequence` (params, semantic, catalogue, segments, customers, interventions, outcomes), so reordering sampling cannot silently perturb an unrelated part of a world. `GENERATOR_VERSION` is recorded in every world file; corpora regenerate byte-for-byte from committed seed ranges in `src/world/__main__.py`.

Sampling order — each stage feeds the next, so a world's stated numbers describe the world it actually is:

```
calendar → seasonality_index → structural params → catalogue → semantic context
                                     ↓
                              segments → customers → interventions
```

**Structural parameters** (`WorldParams`, `src/world/schema.py`) are simulator truth: market elasticity, per-intervention response affinities, promo response scale, cannibalization rate, competitive pressure, AOV and margin distributions, budget. **They are never handed to any strategy.**

**Semantic context** (`SemanticContext`) is generated from templates and a controlled vocabulary — never by calling an LLM, which would make worlds non-deterministic. Four strings are emitted from hidden latents at **partial fidelity** (78% true-positive / 18% false-positive, `_emit_signal`): a shipping support-ticket theme, an inventory clearance note, a competitor price-war event, and a conversion-drift trading note. Partial fidelity is deliberate — a signal that fired exactly with its latent would let the agent skip the experiment; one uncorrelated with it would be decoration.

**Response model** (`treated_conversion_probability`, `response_multiplier`) is the single source of truth for treated conversion:

```
depth   = intervention.effective_depth(basket)          capped at 0.5
lift    = (1 − depth) ** price_elasticity − 1
mult    = 1 + A(1 − exp(−(responsiveness · affinity · max(lift,0)) / A)),  A = 2
p1      = 1 − (1 − baseline_purchase_prob) ** mult      so p1 ≥ p0 always
```

## 3. Potential outcomes, and where ground truth lives

`generate_ground_truth` draws `Y(0)` and `Y(1)` for **every customer × every intervention**, using **common random numbers**: one `u ~ U(0,1)` per customer decides both arms, so the counterfactual pair is coherent. One pull-forward draw per customer × intervention implements cannibalization — an order that is merely pulled forward adds no net contribution.

`GroundTruth` is written to a **separate file** from the world (`*.truth.json`), so an agent-facing loader physically cannot read it. `src/world/persistence.load_ground_truth` walks the call stack and admits only callers under `src.eval` (`_assert_caller_may_read_ground_truth`). A script executed with `python -m` is named `__main__` and is refused — which is the guard working, not a nuisance to route around; `src/eval/devcorpus.py` exists precisely so that loading happens where the caller's module name is honestly `src.eval.devcorpus`.

**No agent tool returns `Y(0)`, `Y(1)`, or anything derived from them.**

## 4. The four information tiers

This is the distinction the whole evaluation rests on.

| tier | what it is | who may read it |
|---|---|---|
| **Merchant view** | `MerchantView` / `CustomerView` / `SegmentView` — what a strategy sees before deciding | every strategy, including the LLM agent |
| **Hidden simulator state** | `WorldParams`: true elasticity, response scale, per-intervention affinities, cannibalization rate, competitive pressure | nobody at decision time; only the generator and the outcome draw |
| **Ground truth** | `GroundTruth`: `Y(0)`/`Y(1)` per customer per intervention | `src/eval/` only, to score decisions after the fact |
| **Evaluation-only derived** | `_true_population_net`, `best_intervention_id`, counterfactual replay, oracle diagnostics | `src/eval/` only; never an input to a decision |

`merchant_view()` (`src/eval/contracts.py`) is built by **explicit field selection**, not by copying and deleting — so a latent added to `WorldParams` later is invisible here by default. The failure mode engineered against is an accidental leak added months on, not a deliberate one written today.

**What the merchant view contains:** world id, population, budget, observed conversion / AOV / margin, experiment window, semantic context, the product catalogue, segments (`segment_id`, `name`, `share`, `notes`, `behaviour_tags`), customers (`customer_id`, `segment_id`, `tenure_days`, `orders_last_90d`, `days_since_last_order`, `historical_aov_inr`), the four interventions, and — from Cycle 2 — `InterventionHistory`: one small past campaign per intervention (300 treated against a held-back control), reporting *incremental* net per treated customer with its standard error.

**What it deliberately omits:** all of `WorldParams`, the per-segment behaviour multipliers, and every potential outcome.

> A source-inspection caveat that belongs with this table: `SegmentView` withholds the four behaviour multipliers but publishes `name`, and the archetype table is a module constant, so the two are informationally linked. See `analysis/posthoc/provenance/segmentview.md`. That is a statement about the simulator's information structure, not a claim about what a real merchant knows.

## 5. Experiment mechanism

- **Randomization** (`src/experiment/randomize.assign`) is `blake2b(customer_id + experiment_id) mod n_arms`. Deterministic across processes, balanced, independent across experiments. Python's salted `hash()` is explicitly refused. **No agent tool accepts an arm assignment as an argument or can move a customer between arms.**
- **Power and horizon** (`src/experiment/power.py`) compute the required sample per arm from baseline conversion, a minimum detectable effect, alpha and power. The horizon is computed **at design time** and written immutably into the registry.
- **Registry** (`src/experiment/registry.py`) records arms, horizon, MDE, budget and creation time; the record is immutable after launch.
- **Evaluator** (`src/experiment/evaluator.py`) computes the treatment–control difference with confidence intervals **at** the horizon. Before the horizon it returns an interim result carrying **no verdict at all** — every scaling rule is unreachable early. There is no "stop early if significant" path.

## 6. Economics — where promotion cost enters

`src/economics/contribution.py` is small pure functions with hand-computed unit tests. The quantity that matters:

```
incremental contribution  = incremental orders × contribution per order
incentive cost            = paid on EVERY treated order, incremental or not
net incremental contribution = incremental contribution − incentive cost
```

The asymmetry is the whole project. A customer who would have bought anyway yields **zero** incremental contribution but still costs the merchant the incentive. `Intervention.incentive_cost_inr` charges it per treated order, and `src/eval/harness._true_population_net` scores ground truth the same way:

```python
total += pair.y1.contribution_inr - pair.y0.contribution_inr
if pair.y1.converted:
    total -= intervention.incentive_cost_inr(pair.y1.order_value_inr)
```

Cost enters at the **order** level, not the customer level — which is why a campaign with a genuine positive conversion lift can still destroy contribution. The four intervention kinds differ in how cost scales: percentage and bundle discounts cost a fraction of basket; flat discounts and free shipping are fixed rupee amounts, so their relative depth falls as basket rises.

## 7. Policy — the money gate

`src/policy/gates.py` is deterministic and contains no model call. `PolicyLimits` carries the merchant's standing constraints, and five rules are checked independently, each returning a `RuleViolation` naming the rule, the observed value and the limit — never a bare boolean:

| rule | default |
|---|---|
| `REMAINING_BUDGET` | spend must fit the remaining promotion budget |
| `MAX_DISCOUNT` | 25% of order value |
| `MIN_CONTRIBUTION_MARGIN` | 15% |
| `MAX_CUSTOMER_EXPOSURE` | 60% of the customer base per campaign |
| `MIN_EXPERIMENT_POWER` | 0.80 |

**Scaling** is a separate discipline (`ScalingRule`). MarginPilot uses `BAYESIAN_POSTERIOR`: `P(net > 0) ≥ 0.80` **and** the posterior 5th percentile, projected to the rollout population, stays above a tolerable loss (2% of budget). A positive point estimate is not authority to spend. The baselines differ precisely along this axis — Baseline 3 scales on conversion lift while ignoring contribution, which is what most growth tooling does.

## 8. The agent boundary

`src/agent/` is the only module permitted to import an LLM client. The reasoner is interface-swappable and the model that produced a result is recorded with it; the project runs on Gemini because no Anthropic credentials were available, and the Claude path stays in the codebase.

The tool surface is closed — `src/agent/tools.py` exposes exactly:

```
get_merchant_metrics()     get_customer_segments()    get_product_context()
propose_experiment()       validate_experiment()      launch_experiment()
get_experiment_results()   evaluate_experiment()
scale_experiment()         stop_experiment()
```

`validate_experiment` returns a policy verdict and **does not execute**. `launch_experiment` executes only an already-validated design. `get_experiment_results` refuses verdict-eligible data before the horizon. `scale_experiment` and `stop_experiment` are policy-gated. Hypotheses are pre-committed objects carrying a prediction, reasoning, expected effect size and explicit success/failure conditions, written to the registry unchanged — the agent may diagnose a failure and propose a *new* hypothesis, never revise an old one after seeing results.

## 9. Evaluation

`src/eval/harness.py` runs any strategy over a world end to end: propose → validate → randomize → execute → evaluate at horizon → scale or stop, recording every money-adjacent step to the audit log, rejections as fully as approvals.

- `src/eval/replay.py` — **counterfactual replay**: given a completed experiment and the world's potential outcomes, what each alternative strategy would have decided and what it would have cost.
- `src/eval/oracle.py` — the **oracle selector**, a diagnostic and never a competitor: it reads ground truth to pick which intervention to test, then pays for its experiment and faces the same scaling rule. It bounds what perfect *selection* could be worth. Perfect selection is not perfect information.
- `src/eval/devrun.py`, `devreport.py`, `devcorpus.py` — dev-world running and reporting.
- `src/eval/power.py` — the evaluation's own power analysis, including the distribution-free `SD ≤ √2` bound on the `false_act` statistic.
- `src/eval/adversarial.py` — the scenarios that must be refused.

## 10. The seal

`src/eval/guard.py` is stdlib-only and imports nothing from the rest of the project, so `src/world/persistence.py` can enforce the seal at the single point where worlds are read without a dependency cycle.

Every read of a world file passes `assert_may_read`. A path under a `holdout/` directory raises `HoldoutSealedError` **unless the caller passes `final_eval=True`** — a flag that has to be typed, by a person, somewhere a reviewer can grep: `git log -S final_eval` shows every time the seal was opened and when.

Two corpora exist. Cycle 1 (`worlds/`, seeds 1–80 dev / 9001–9020 holdout) — its holdout was opened once, at final evaluation, and the recorded run is committed as `data/holdout_results.json`. Cycle 2 (`worlds_cycle2/`, seeds 20001–20080 dev / 29001–29020 holdout) — **its holdout has never been read**, which was the pre-registered outcome once Cycle 2's disqualifying condition fired.

## 11. Audit

`src/audit/log.py` is an append-only, **hash-chained** SQLite log: each row stores the previous row's hash, and every entry hashes `(prev_hash, recorded_at, world_id, experiment_id, stage, actor, payload)` with SHA-256. Deleting or editing any row breaks every hash after it. There are no update or delete paths. Rejections are recorded as fully as approvals — a log that records only what happened cannot show what was prevented. `make audit` verifies the chain.

## 12. Cycles

The project's evidence is organised as pre-registered cycles, each written into `docs/simulator.md` **before** the measurement it governs.

**Cycle 1** — corpus `worlds/`. §4b fixed the decision rule; §4h predicted, before the seal was opened, that MarginPilot would lose to do-nothing on the holdout with an `int_shipping` selection bias as the mechanism. §4i records that the prediction held.

**Cycle 2** — corpus `worlds_cycle2/`, fresh seeds, every generator parameter unchanged. §4j pre-registered two fixes and a disqualifying condition for each: Fix A (break-even prompt) and Fix B (campaign history). A 2×2 ablation over 20 dev worlds produced the committed `results/cycle2_dev_*.json`. §4k reported it; §4l pre-registered Cycle 3, which repaired the **evaluation instrument** rather than the agent, measuring the noise floor before trusting any difference. §4n is the final reading: Fix B never identified a better intervention than its own lookup table, and Fix A's false-act rate resolved as a null. The Cycle-2 holdout stayed sealed.

**Post-hoc work** performed after §4n closed lives under `analysis/posthoc/` and is labelled as post-hoc throughout. It is not part of any pre-registration and must not be described as if it were.

## 13. Payments and UI

`src/payments/` is a Razorpay **test-mode** client with webhook handling, idempotency (duplicate delivery produces one attribution) and reconciliation. Live keys are never used. `src/ui/` is a Streamlit dashboard reading recorded runs; it computes no evidence.

## 14. The product layer

Everything above is the research instrument. The product built on top of it asks
one question — *should this merchant promote, experiment, or do nothing?* — and
answers it in one of four states: `PROMOTE`, `DO_NOT_PROMOTE`,
`RUN_EXPERIMENT_FIRST`, `INSUFFICIENT_EVIDENCE`.

```
MerchantView ─build_brief()─► MerchantBrief ─► Proposer (LLM or stub)
  src/eval/contracts           src/agent/brief    src/agent/proposer
                                                        │
                                          validate_proposal()  ← fails closed
                                                        ▼
                                        src/agent/decision_policy.recommend()
                                          G1 → G2 → G3 → G4 → G5
                                                        │
                                        RUN_EXPERIMENT_FIRST (never PROMOTE)
                                                        ▼
                              design_experiment_on_contribution() → evaluate()
                                                        ▼
                                     decide_after_experiment(): G3 → G6
                                                        ▼
                                                    PROMOTE
```

**The model never holds authority.** It proposes a cohort, an offer and an
expected lift, with citations to brief fields. `src/agent/decision_policy.py`
recomputes every rupee from the brief and may overrule it; the recommendation
records that it did. `recommend()` cannot return `PROMOTE` under any input,
because a model asserting experimental confidence without an experiment is not
evidence. Only `decide_after_experiment()`, holding a real `FinalResult`, can
open spending.

**The gates**, five of them reused from `src/policy/gates.py` rather than
reimplemented:

| gate | question | mechanism |
|---|---|---|
| G1 | can the proposal be priced at all? | brief lookup |
| G2 | can this campaign reach positive net contribution? | break-even lift `p0·I/(C−I)`; `None` when `C ≤ I` |
| G3 | is the confidence sourced from a measurement? | `assess_scale()` at the horizon |
| G4 | can the merchant afford to find out? | `assess_feasibility()`, budget, exposure |
| G5 | does the pilot pass standing limits? | `gate_experiment()` |
| G6 | does the measured result justify a rollout? | `gate_rollout()` + funded-rollout net > 0 |

**G4 is affordability only.** Whether an experiment costs less than the
information it buys has no committed constant in this project, so every
experiment recommendation carries `G4_VALUE_OF_INFORMATION_UNRESOLVED` through
to the merchant rather than resolving it by invention.

**Two exclusions the product inherits from the research.** No ground truth: the
brief is built by explicit field selection and `src/agent/` imports no
ground-truth loader. No `SegmentView` identity: `build_brief()` reads no segment
field, because `name`/`notes`/`behaviour_tags` are a bijective key to withheld
archetype multipliers (`analysis/posthoc/provenance/segmentview.md`). Targeting
is therefore limited to order-value cohorts over customer records, which is a
weaker representation and the honest price of the exclusion.

`demo/` holds three declared fixtures exercising the path end to end. They are
labelled **DEMONSTRATION FIXTURE — NOT RESEARCH EVIDENCE** and are never scored.

### The boundary tests, and a correction to the record

The strongest guard on the brief is a **sentinel**: perturb every hidden response
latent, and assert the brief does not move. It exempts exactly one field —
`history` — because `InterventionHistory` is a *measured past campaign* and is
downstream of the response model by construction.

A forensic audit established that the exemption is safe. Sweeping
`shipping_affinity` across its full range at a fixed world gives 18 affinities →
**10 distinct histories**, with five collision groups; holding the affinity fixed
and varying only the history's RNG stream gives **12 of 12 distinct histories**,
with an empirical SD of 6.21 against the reported standard error of ~7.06. The
map is many-to-one forward and one-to-many backward, so `InterventionHistory` is
a noisy realized measurement, not an encoding. Contrast `SegmentView.name`: seven
names onto seven multiplier quadruples, zero collisions, no noise — an exact
lookup, which is why SCI-1 keeps it out.

That exemption is now bounded by an **allowlist** in
`tests/agent/test_brief_boundary.py`: `HistoryBrief`'s field set must equal an
enumerated set of realized-history quantities. A denylist would not do — the
`SegmentView` precedent is a legitimate-sounding field carrying hidden
structure, and a latent proxy named `response_index` would pass any name filter.
Equality fails closed on an addition, a rename, a removal, or a same-size swap.

**Correction.** The implementation report stated that *four* boundary tests were
sharpened during implementation. That count was wrong. The diff between
`08cd977` and `57086e4` contains **five changed tests and one added test**; the
omitted item was the segment test, which moved from substring-matching archetype
text to poison-injection plus a structural assertion — a **strengthening**, not a
weakening. The forensic audit accounted for all six. The original miscount is
recorded here rather than quietly amended.

## 15. What this architecture is for

Every boundary above exists so that one claim survives inspection: **the measured result is a property of the world and the decision rule, not of the agent's access to information it should not have.** The seal, the stack-walking ground-truth guard, the explicit-field merchant view, the hash-chained log and the closed tool surface are each cheaper than the alternative — a result nobody can check.
