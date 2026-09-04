# MarginPilot

**Most growth agents optimize conversion. MarginPilot optimizes what actually makes the merchant money.**

MarginPilot is an autonomous merchant growth agent that runs controlled promotion experiments and allocates a bounded promotion budget based on **incremental contribution** — not conversion lift, not predicted response.

Submitted to the Razorpay AI Buildathon, Track 1 (AI Growth & Agentic Commerce).

### The separation this project is built on

> **The LLM forms and revises hypotheses. The deterministic system proves whether those hypotheses deserve economic action.**

| Role | Component |
|---|---|
| Hypothesis scientist | LLM agent |
| Evidence | Randomized experiments and statistics |
| Authority | Deterministic policy engine |
| Actuator | Razorpay test mode |
| **Judge** | **Sealed holdout worlds** |

The judge is the load-bearing role. The other four are architecture; the holdout is the only component that can tell you the architecture was wrong.

### The loop

```
semantic context → falsifiable hypothesis → bounded experiment
   → causal measurement → failure diagnosis → revised hypothesis
   → economic decision
```

---

## The finding

**In an environment where testing costs more than most campaigns return, every strategy loses to doing nothing.**

MarginPilot loses least, by an order of magnitude — **₹85,430 against ₹921,902–₹1,330,481** — because it runs **9 experiments where the unreasoning engine runs 77**. The reasoning is genuinely reading the merchant: strip the semantic context and half its decisions flip. It is also what makes selection worse.

**That was predicted before the holdout was opened, and it happened exactly as predicted.**

---

## The problem

A merchant runs a ₹100-off campaign. Conversion goes from 12% to 18% — a 50% lift. Every dashboard in the market calls this a win and scales it.

It lost money.

The discount is paid to *every* buyer in the treatment arm, including the ones who would have bought at full price. Only the genuinely incremental buyers add contribution:

| | Control | Treatment (₹100 off) |
|---|---|---|
| Customers | 1,000 | 1,000 |
| Conversion | 12.0% | 18.0% |
| Orders | 120 | 180 |

- Incremental orders: **60**
- Contribution from incremental orders: 60 × ₹800 AOV × 30% margin = **₹14,400**
- Discount cost across *all* treatment buyers: 180 × ₹100 = **₹18,000**
- **Net incremental contribution: −₹3,600**

A +50% conversion lift that destroys ₹3,600 of contribution at pilot scale, and a projected **−₹36,000** if scaled to the full customer base.

MarginPilot detects this and kills the campaign. It spent ₹18,000 of budget to avoid a ₹36,000 loss — buying information cheaply is the point.

## What it does

```
Merchant events + semantic context
      ↓
Opportunity detection        ← agent
      ↓
Falsifiable hypothesis       ← agent: prediction, reasoning, expected effect,
      ↓                         required sample, success/failure condition
Experiment design            ← agent proposes
      ↓
Policy gate                  ← deterministic: budget, discount ceiling, margin floor
      ↓
Randomized assignment        ← deterministic: hash(customer_id + experiment_id)
      ↓
Offer / intervention
      ↓
Razorpay test-mode payment   ← financial actuator
      ↓
Experiment measurement       ← deterministic: fixed horizon, no peeking
      ↓
Economic evaluation          ← incremental contribution, not conversion
      ↓
KEEP / KILL / SCALE          ← agent recommends, policy gate executes
      ↓
Failure diagnosis            ← agent: why did the prediction fail?
      ↓
Revised hypothesis           ← back to the top, better informed
      ↓
Budget reallocation
```

The agent does not just execute campaigns. It forms falsifiable predictions, learns from the ones that turn out wrong, and is held accountable for the economic consequences of both.

**Why this is not a bandit.** A bandit updates a distribution over a fixed set of arms. It cannot read a failed experiment, reason about *why* the prediction failed given the merchant's semantic context, and propose an intervention that was never in the arm set. That capability is the LLM's job here, and `Baseline 5` exists to test whether it is worth anything.

## What the agent is actually allocating

MarginPilot is not an unlimited testing loop. Experimentation is the scarce resource, and the numbers are unforgiving: measured across the development worlds, the median experiment costs **₹55,283** while the median best-case profit available in a world is **₹19,939**. One experiment costs roughly **2.8× the entire profit pool of the merchant it runs on**.

So the agent can afford about **one experiment per merchant**. Its job is not to test everything and keep the winners — it is to decide *whether any question is worth asking at all*, and if so *which one*. **"Run nothing" is a first-class correct answer**, and against a corpus where most promotions lose money it is frequently the right one.

That is what the comparison against `Baseline 5` measures. The ablation works through a fixed hypothesis set in a preset order, paying four times for information a well-chosen single experiment buys once. Every strategy declares an explicit experiment allowance, so those four experiments are its own choice and its own cost, not something granted for free. If reading a merchant's situation cannot tell the agent which single question to ask, the LLM adds nothing over the fixed order — and the results section will say so.

## The model, and why it is swappable

The agent runs on **`gemini-3.6-flash`**. That is an availability decision, not a quality one: no Anthropic credentials were available in the build environment, and an agent that cannot run cannot be evaluated.

A `ClaudeReasoner` targeting `claude-opus-5` ships alongside it and implements the same interface. The reasoner sits behind one Protocol with shared prompts and shared parsing, so the provider is a one-line swap — and everything that matters stays outside it either way. Randomization, the experiment horizon, the scaling rule and every money-adjacent action are enforced by the deterministic layer regardless of which model is reasoning, or whether one is present at all.

Which model produced a result is recorded with that result. A number produced by `gemini-3.6-flash` is evidence about `gemini-3.6-flash`, not about LLM agents in general. (`gemini-2.5-flash` was the intended model; it is retired for new API keys, and Google's deprecation notice names 3.6-flash as its replacement.)

## Reasoning vs. authority

The single most important design rule in this codebase: **the LLM reasons, the deterministic layer decides anything involving money.**

| The agent may | The agent may never |
|---|---|
| Identify opportunities in merchant data | Assign customers to treatment or control |
| Generate growth hypotheses | Set or exceed the promotion budget |
| Propose interventions and experiment designs | Set discount ceilings or margin floors |
| Interpret experiment results | Decide when an experiment has run long enough |
| Recommend SCALE / KILL / MODIFY | Execute a payment or issue an offer directly |
| Read the audit trail | Modify or delete audit records |

The agent can say *"give this segment ₹100 off."* The policy engine answers:

```
REJECTED — discount 40% exceeds max_discount 25%
REJECTED — contribution margin 10.0% below floor 15.0%
REJECTED — would treat 90% of customers (90,000 of 100,000), above the 60% exposure cap
REJECTED — projected spend Rs.999,999 exceeds remaining budget Rs.100,000
REJECTED — design power 0.50 below minimum 0.80; the experiment would spend budget to buy an unreadable answer
```

That is real output from `src/policy/gates.py`, not an illustration. All five rules report at once, because the agent has to re-plan against the verdict and one rule at a time would make that a guessing game.

Every rejection is logged with the rule that fired, the value that violated it, and the agent's original intent.

## Why not just a bandit?

This is the sharpest objection to the project, so it is answered empirically rather than argued.

`Baseline 5` is the **experimentation engine with the LLM removed** — the same statistical machinery, the same policy gates, driven by a fixed hypothesis set. If the LLM adds nothing over that, this README says so and the finding stands as a result. Assertions that "the agent is intelligent" are not evidence; the ablation is.

## Statistical design

The parts that are easy to get wrong, and how they're handled:

**No peeking.** The agent cannot repeatedly check an experiment and stop when it likes the p-value. Experiments run to a pre-computed fixed horizon derived from a minimum detectable effect on incremental contribution. The horizon is written into the experiment registry at launch and is immutable. (Sequential testing with alpha spending is a post-MVP extension, not a shortcut.)

**Randomization the agent cannot influence.** Assignment is `hash(customer_id + experiment_id) mod n_arms`, computed in the experiment engine. The agent has no tool that can move a customer between arms.

**Known ground truth.** The simulator generates both potential outcomes `Y(0)` and `Y(1)` for every customer. The experiment observes only one per customer, exactly as in reality — but the evaluation harness knows the true individual treatment effect `τᵢ = Yᵢ(1) − Yᵢ(0)`. This lets the harness report not just whether the agent made money, but whether its *estimates* were accurate: estimation error against known truth, separate from decision quality.

**Scaling requires confidence, not a positive point estimate.** An experiment is scaled only when both hold: the posterior probability of positive net contribution reaches **0.80**, *and* the posterior's 5th percentile — projected to the population a rollout would cover — stays above a tolerable loss of 2% of the promotion budget. The first asks whether the campaign is probably profitable; the second asks whether being wrong is survivable. A promising-looking mean satisfies neither.

The 95% confidence interval is still computed and reported alongside every decision, so what the stricter earlier rule *would* have decided stays visible in the results. That earlier rule — the whole interval above zero — was replaced before the holdout was opened, because measured against an oracle selector with a full budget it scaled 0 experiments in 10 worlds while missing 9 profitable rollouts. A rule that refuses even perfect selection is inoperable rather than conservative. The reasoning, thresholds and date are pre-registered in [`docs/simulator.md` §4b](docs/simulator.md).

**Counterfactual replay.** Because the simulator holds `Y(0)` and `Y(1)`, every decision can be replayed under alternative strategies: what the conversion optimizer would have done with the same evidence, and what it would have cost.

**Cost of learning.** Experiments spend real budget to buy information, including on hypotheses that turn out wrong. That spend is reported explicitly, against the question of whether the total was still net-positive versus never experimenting at all.

**Generalization, not one lucky world.** See below.

## The world generator

The obvious criticism of any simulated result is *"you built the world so your agent would look good."*

MarginPilot does not have a world. It has a **generator**. Each world samples its own baseline conversion, price elasticity, customer mix, segment structure, seasonality, AOV distribution, contribution margins, treatment effects, treatment-effect heterogeneity, cannibalization, and budget.

Critically, each world also carries **semantic context** — product names, categories and descriptions, inventory age, qualitative segment notes, seasonal and competitor events, customer-service themes. This is what gives the agent a reasoning problem rather than a menu selection, and it is generated from Day 2 rather than retrofitted.

Each world also generates **hidden potential outcomes** `Y(0)` and `Y(1)` for every customer and intervention. The agent never sees them. The evaluation harness does.

```
100 worlds generated
 ├── 80 development worlds  → all design, tuning, prompt iteration
 └── 20 holdout worlds      → sealed; opened once, at final evaluation
```

Structural parameters of the holdout worlds are never inspected during development. Elasticity and response ranges are grounded in published retail price-elasticity literature (see `docs/simulator.md`) rather than chosen to flatter the agent.

Headline results are reported **on the holdout worlds only**.

### An expected property of the generated worlds

**Bundles dominate this corpus, and that scopes every finding below.** Measured from ground truth on the 20 holdout worlds:

| Intervention | Best choice in | Profitable in | Median true net |
|---|---|---|---|
| **Bundle** | **14 / 20 worlds** | **50%** | −₹531 |
| Percentage discount | 4 / 20 | 5% | −₹78,152 |
| Free shipping | 2 / 20 | 20% | −₹64,939 |
| Flat discount | 0 / 20 | 5% | −₹82,282 |

The other three are unprofitable in 80–95% of worlds. Bundle wins largely by being the least-bad option rather than by being good — it is the only one whose median is near break-even.

**This is a known limitation of the world generator, recorded in [`docs/simulator.md` §4d](docs/simulator.md).** Depth is anchored at `j × margin`, so a campaign breaks even only when roughly a fifth of treated orders are genuinely incremental — which sits right at the edge of what the corpus's response strengths deliver. Tying a bundle's basket uplift to its own depth reduced its advantage but did not remove it, and widening response strength to make the four genuinely competitive would have meant changing a world parameter *after* discovering that selection was degenerate. That is post-hoc tuning toward a more flattering result, so it was not done.

**An earlier version of this section reported free shipping winning 48% of worlds and claimed none was dominated.** Those figures came from an analytic approximation that credited a bundle's basket uplift only on incremental orders, while the generator grants it to every treated converter. The Day-5 diagnostic showed the approximation had the wrong sign in half the worlds it was checked against. Ground truth is authoritative and the numbers above replace it.

**Why this matters for the result.** Because bundle dominates, the selection problem is close to degenerate: a hardcoded "always test the bundle" captures 99% of a ground-truth oracle's edge, leaving about ₹11,000 for reasoning to compete over ([§4e](docs/simulator.md)). So MarginPilot's selection failure is real and measured, but it is measured in a corpus where selection was worth little to begin with. In a corpus where the four interventions were genuinely competitive, a signal about customer response might well predict profitability, and this result could reverse.

**Grounded reasoning is not the same as good decisions.** On the development worlds the agent read each merchant accurately — its citations quote the merchant's own support tickets, segment notes and trading commentary verbatim — and still chose worse than a fixed rule, because the signals it read predict *response*, not *profitability*. The experimental machinery caught it: the experiment ran to its pre-committed horizon, the posterior on incremental contribution was computed, and the scaling rule declined.

To be precise about what did *not* happen: the policy gates did not catch this. They approved those experiments, correctly — the gates check budget, discount, margin, exposure and power, and have no view on which intervention is more profitable. Measurement caught it, not the gate.

All four types do produce profitable, marginal and unprofitable cases across the corpus — none is *impossible* — but bundle wins far more often than the rest, as the table above shows. The parameters were **not** adjusted to equalize how often each type wins: doing so would mean rigging the worlds so that economically disfavoured strategies succeed more often than the economics allows. Details and the pre-registered Day-2 diagnostic are in [`docs/simulator.md`](docs/simulator.md).

## Baselines

| # | Baseline | Optimizes |
|---|---|---|
| 1 | Do nothing | — (natural business performance) |
| 2 | Rule-based marketer | Fixed rule: 10% off to customers with P(purchase) < 0.4 |
| 3 | Conversion optimizer | Expected conversions — the naive AI approach |
| 4 | LLM strategist | LLM picks campaigns from context, no experiments, no economic gate — **built, but not run on the holdout; see below** |
| 5 | Engine without LLM | Incremental contribution, fixed hypothesis set (the ablation) |
| — | **MarginPilot** | **Incremental contribution under budget and policy constraints** |

## Metrics

Primary:

1. **Incremental conversion** — `Δ = p_treatment − p_control`
2. **Incremental revenue** — revenue attributable to treatment
3. **Incremental contribution** — the primary business metric
4. **Promotion spend** — incentive budget consumed
5. **ROMI** — `incremental contribution / promotion spend`

Secondary: policy violations, budget overruns, false-positive campaigns scaled, true-positive campaigns killed in error, experiments killed, experiments scaled, estimation error vs. known `τ`.

## Pre-registration, and what happened

Targets were fixed before the holdout was opened, at commit `857e990` (tag `frozen-for-holdout`). Measured values are reported whether or not they were met.

**The prediction beside the outcome is the strongest thing in this project.** [`docs/simulator.md` §4h](docs/simulator.md), dated and written while the 20 worlds were still sealed, predicted the failure *and its mechanism*. Both held.

| §4h predicted, before the seal opened | Measured on the holdout | Held |
|---|---|---|
| MarginPilot loses to Baseline 1 (do nothing) | −₹85,430 against ₹0 | **Yes** |
| It beats Baseline 5 on cost of learning, not on selection | ₹274,435 vs ₹4,426,285; selection cost ₹228,918 | **Yes** |
| The `int_shipping` bias is the cause | Chose shipping 7/9 times; selection correct 2/9 | **Yes** |
| Falsified if bundle selection rose above the dev rate of 1/5 | 2/9 on holdout — not falsified | **Yes** |

The characterisation was made on development worlds, in advance, and recurred unmodified on twenty worlds the agent had never seen. A negative result that was *predicted* is a different claim from one that was merely observed.

| Metric (holdout worlds) | Target | Measured | Met |
|---|---|---|---|
| Incremental contribution vs. Baseline 1 | > 0 | **−₹85,430** vs ₹0 | **No** |
| Incremental contribution vs. Baseline 2 (rules) | beat | −₹85,430 vs −₹929,086 | Yes |
| Incremental contribution vs. Baseline 3 (conversion optimizer) | beat | −₹85,430 vs −₹921,902 | Yes |
| Incremental contribution vs. Baseline 5 (no LLM) | beat | −₹85,430 vs −₹1,253,786 | Yes |
| Policy violations | **0** | **0** | Yes |
| Budget overruns | **0** | **0** | Yes |
| Negative-contribution campaigns scaled | **0** | **0** | Yes |
| ROMI | > 1.0 | **0.77** | **No** |

Two targets missed, and the first one is the headline: **MarginPilot lost money on the holdout.** It beat every baseline and still lost to doing nothing.

## Results

Twenty sealed holdout worlds, opened once. Agent reasoning on `gemini-3.6-flash`;
payments through Razorpay test mode.

| strategy | realized net | spend | cost of learning | exp | scaled | FP | missed | ROMI |
|---|---|---|---|---|---|---|---|---|
| 1 do nothing | **₹0** | ₹0 | ₹0 | 0 | 0 | 0 | 0 | — |
| 1b learn only *(diagnostic)* | −₹1,330,481 | ₹4,562,034 | ₹4,562,034 | 77 | 0 | 0 | 16 | 0.71 |
| 2 rule-based | −₹929,086 | ₹2,194,834 | ₹0 | 0 | 20 | 19 | 0 | 0.58 |
| 3 conversion optimizer | −₹921,902 | ₹3,004,455 | ₹1,129,051 | 20 | 7 | 7 | 3 | 0.69 |
| 5 engine without LLM | −₹1,253,786 | ₹4,925,911 | ₹4,426,285 | 77 | 3 | 2 | 15 | 0.75 |
| **MarginPilot** | **−₹85,430** | ₹365,757 | ₹274,435 | 9 | 1 | 0 | 3 | 0.77 |
| oracle selector *(cheats)* | +₹250,025 | ₹1,506,621 | ₹1,144,478 | 20 | 2 | 0 | 9 | 1.17 |

**Do nothing wins.** MarginPilot is second, ahead of every real strategy by an
order of magnitude, and still ₹85,430 behind an empty campaign calendar.

**Baseline 4 is missing from this table, and that is an omission rather than a decision.** The LLM strategist is built, tested and satisfies the same `Strategy` interface as the others (`src/baselines/llm_strategist.py`); it was simply left out of the holdout harness when that script was written. By the time the gap was noticed the seal was open, and adding a strategy to a sealed evaluation after seeing the results is exactly what the freeze exists to prevent — a number produced that way would not be comparable to the six that were run blind.

What it costs the analysis: Baseline 4 is the *other* ablation. Baseline 5 has the machinery without the reasoning; Baseline 4 has the reasoning without the machinery. Without it, this evaluation can say that reasoning-plus-experimentation beat unreasoning-experimentation, but it cannot separate how much of that came from the experimentation apparatus versus from the model. Its nearest available proxy is Baseline 2, which also acts without testing and lost ₹929,086 — but Baseline 2 chooses by a fixed rule rather than by reading the merchant, so it bounds the question without answering it. This is the single largest hole in the results and it is stated here rather than left to be found.

Its advantage over the other strategies is restraint, not insight: it ran 9
experiments where Baseline 5 ran 77, and skipped 11 of 20 merchants outright.
Spending an eighth as much is what kept its losses small.

### Counterfactual replay — the decision rule, isolated

Holding the worlds and experiments fixed and swapping only the rule that reads
the result (228 decisions):

| rule | realized net | spend | scaled | correct |
|---|---|---|---|---|
| never scale | −₹3,233,129 | ₹14,590,133 | 0 | 177/228 |
| always scale | −₹11,660,742 | ₹54,555,745 | 228 | 51/228 |
| point estimate | −₹4,257,971 | ₹36,882,053 | 105 | 158/228 |
| CI lower bound | −₹2,212,074 | ₹22,983,314 | 32 | 185/228 |
| **Bayesian posterior** *(live rule)* | **−₹2,116,323** | ₹25,383,041 | 44 | 185/228 |
| oracle | −₹1,057,744 | ₹22,632,187 | 50 | 219/228 |

The scaling rule holds up: the live rule beats the naive point estimate by
**₹2.1M** and lands closest to the oracle of any achievable rule. This is the
part of the system that worked.

### Counterfactual validation — estimates against known τ

183 experiments with a measurable estimate, scored against the simulator's true
individual treatment effects:

- mean |estimate − truth|: **₹6.14** per customer
- median: ₹4.24 · 90th percentile: ₹14.20
- MarginPilot's own estimates were the most accurate of any strategy: **₹3.96**
  per customer against ₹6.15–₹7.85 for the baselines

Hypothesis calibration is reported separately below, because it qualifies every
number in this section.

### What worked

Reported alongside the failures rather than instead of them:

- **Zero policy violations, zero budget overruns**, across all six strategies and
  20 worlds. Both the pilot and the rollout pass the gate.
- **Zero negative-contribution campaigns scaled.** The scaling rule refused every
  losing campaign it was offered. Baseline 2 scaled 19.
- **The decision rule beats the naive alternative by ₹2.1M** in replay and lands
  closest to the oracle of any achievable rule.
- **The most accurate estimates of any strategy**, at ₹3.96 per customer.
- **Restraint works.** Nine experiments against Baseline 5's 77, for an eighth of
  the spend and a tenth of the loss.

The apparatus is sound. What it measured is that this agent's reading of merchant
context does not predict which promotion pays — on this corpus, where
[`docs/simulator.md` §4d](docs/simulator.md) records bundles as dominant by
construction. That scope caveat is load-bearing: in a corpus where the four
interventions were genuinely competitive, a signal about response might well
predict profitability, and this result could reverse.

### Where MarginPilot loses

**1. It loses to doing nothing.** −₹85,430 against ₹0. The pre-registered primary
hypothesis fails. This was predicted before the holdout was opened
([`docs/simulator.md` §4h](docs/simulator.md)), and the prediction held.

**2. Selection is where the money went.** On the 9 worlds it chose to run, its
picks returned **−₹327,847**. Testing a bundle every time instead would have
returned −₹98,929, and perfect selection +₹152,848. **Its reasoning cost
₹228,918 against a hardcoded rule.**

Selection was correct in **2 of 9** worlds. It chose `int_shipping` 7 times out of
9 — the same bias measured on dev worlds and named in §4g as the predicted cause.
The mechanism: the world generator emits shipping-threshold support tickets from
a hidden `shipping_affinity` latent, and the agent reads them accurately. But
affinity governs *response*, not *profitability*. It is reading a true signal
that does not predict the target.

The three worst cases are all this failure: `world_09005` (−₹122,795 chosen,
+₹33,566 available), `world_09009` (−₹157,009 chosen), `world_09015` (−₹121,859
chosen). All three chose free shipping. All three had a better option.

**3. Profitable campaigns it declined.** Run/skip was correct in 12 of 20 worlds
— better than a coin flip, worse than useful. It skipped 5 merchants where
something profitable existed, the largest being `world_09019` (₹342,025
available), `world_09002` (₹125,662) and `world_09020` (₹77,064). Those
omissions cost more than its bad experiments did.

**4. Its intervals are overconfident.** 74% coverage against a nominal 95%. The
estimator is more accurate than any baseline's (₹3.96 per customer) but its
uncertainty is understated, so the scaling rule is being fed intervals narrower
than the evidence supports. Worst single estimate: `world_09005`, `int_pct`,
estimated +₹17.45 per customer against a true −₹18.86.

**5. World types where it underperforms.** Worlds whose semantic context
contains shipping-threshold support themes — exactly the ones where its reading
is most confident. Confidence and correctness are anti-correlated here, which is
the most uncomfortable finding in the project and the one most worth carrying
forward.

## A defect in these results: the intervals are too narrow

**Hypothesis calibration: the truth fell inside the 95% confidence interval 135 times out of 183 — 74% coverage against a nominal 95%.**

This is not a finding about merchants. It is a defect in the measurement, and it qualifies every number in this README.

An interval that claims 95% and delivers 74% is **systematic error, not noise**. It does not average out across worlds; it biases in one direction, consistently. And it feeds directly into the thing that decides whether money moves: the scaling rule reads the posterior, and a posterior narrower than the evidence supports will license scaling on weaker grounds than the rule intends. The rule's ₹2.1M advantage over the naive point estimate is real and was measured under these intervals — but it was measured with a ruler that reads short.

What this does *not* invalidate: the realized net contribution figures, which come from ground truth rather than from estimates, and the decision counts, which are observed. What it does qualify: anything resting on the width of an interval, which includes the scaling decisions themselves.

**Measured after the freeze. Nothing was adjusted in response.** Correcting the estimator and re-running would have meant tuning against a sealed holdout, which destroys the only unbiased measurement this project has. It is recorded as a known defect and left standing.

Most likely cause, stated as a hypothesis rather than a conclusion: the per-arm contribution variance is computed from the observed sample, and with a heavy-tailed basket distribution the sample standard deviation understates the population's. That is a testable claim and the first thing future work should check.

## What I would change, and why I did not

The failure is specific and the fix is not mysterious. The agent selects on signals that predict **response** — shipping-threshold support tickets, segment friction notes — when the quantity that decides profitability is **margin against incentive cost**. Two changes would address it directly:

1. **Constrain the agent toward profitability rather than response.** The prompt asks which intervention will move customers; it should ask which will move customers *at a cost the margin can absorb*. The information is already in the merchant view — contribution per order and cost per treated order are both there — but nothing directs attention to their ratio.
2. **Give it margin-adjusted historical performance per intervention.** The agent currently reasons about interventions from their descriptions. A merchant with any promotional history would know which offer types have paid before; supplying that would replace inference with evidence.

**Neither was applied.** The holdout was already open. Changing a prompt or a signal after seeing the sealed result and re-running would produce a number that looks better and means nothing — the evaluation's value comes entirely from the agent having been fixed before the worlds were seen. A tuned second result would not be a better result; it would be the absence of one.

These are recorded as the next experiment, not as a correction to this one.

## Failure and adversarial handling

| Scenario | Detection | Response |
|---|---|---|
| High conversion, negative contribution | Economic evaluator | Campaign killed, reason logged |
| Agent proposes a discount above ceiling | Policy gate | Rejected pre-execution, agent must re-plan |
| Agent proposes spend beyond remaining budget | Policy gate | Rejected, budget state returned to agent |
| Agent tries to stop an experiment early on a favourable reading | Experiment registry | Refused until fixed horizon reached |
| Underpowered experiment (effect too small to detect) | Power check at design time | Experiment refused, MDE reported |
| Payment webhook missing or delayed | Reconciliation job | Attribution held, order state resolved from Razorpay fetch |
| Duplicate webhook delivery | Idempotency key | Single attribution, no double-count |
| LLM proposes an intervention type that doesn't exist | Tool schema validation | Rejected, agent re-grounds on available interventions |

## Razorpay integration

Razorpay test mode is the **financial actuator**, not the project.

```
Offer → Checkout → Payment → Webhook → Experiment attribution
```

**Scope, stated plainly:** experiment mathematics run across simulated customer populations at a scale no sandbox could support. A defined subset of orders is executed through Razorpay test mode — real order creation, real payment links, real order fetch — demonstrating that the financial loop closes. Webhook *receipt* is replayed locally rather than delivered by Razorpay, because this build has no public endpoint for Razorpay to call; the capture event goes through the identical receiver, signature verification and idempotency key that a live delivery would. `client_mode` and `webhook_source` are recorded separately in the audit trail so neither can be read as more than it is. Which orders are real and which are simulated is recorded per experiment in the audit trail and shown in `docs/razorpay_scope.md`.

## Architecture

```
src/
├── world/          # world generator, customer/event simulator, potential outcomes
├── experiment/     # registry, randomization, power/horizon, statistical evaluator
├── economics/      # contribution model, incremental contribution, ROMI
├── policy/         # budget, discount ceilings, margin floors, rejection logging
├── agent/          # LLM agent + tool layer (the only LLM-touching module)
├── payments/       # Razorpay test-mode client, webhooks, idempotency, reconciliation
├── baselines/      # the five comparison strategies
├── eval/           # holdout harness, metrics, failure taxonomy
├── audit/          # append-only decision log
└── ui/             # Streamlit dashboard
```

Full component walkthrough, including where ground truth lives, how the holdout seal is enforced, and where promotion cost enters net contribution: [`docs/architecture.md`](docs/architecture.md).

**Deliberately not used:** Kafka, Kubernetes, Docker, vector databases, multi-agent swarms, reinforcement learning, custom models, MCP layers. The interesting part is the decision architecture and the evaluation, not the technology count.

### Post-hoc analysis

Exploratory analyses performed **after** Cycle 2 closed — targeting, heterogeneity, ceilings, source provenance, reproducibility, and a feasibility audit of an external dataset — live under [`analysis/posthoc/`](analysis/posthoc/), separated from the pre-registered cycle work in [`docs/simulator.md`](docs/simulator.md). None of it was pre-registered, none of it modified Cycle 1 or Cycle 2, none of it opened a sealed holdout, and none of it ran the LLM. [`analysis/posthoc/evidence-ledger.md`](analysis/posthoc/evidence-ledger.md) records what that work does and does not establish.

## Stack

Python 3.11 · SQLite · pandas / NumPy · SciPy / statsmodels · Razorpay Test APIs · Streamlit · `google-genai` (agent reasoning)

## Running it

```bash
conda create -n marginpilot python=3.11 && conda activate marginpilot
pip install -r requirements.lock.txt   # exact frozen environment; use requirements.txt for the readable list
cp .env.example .env          # add RAZORPAY_TEST_KEY_ID, RAZORPAY_TEST_KEY_SECRET, LLM API key

make test                     # 243 tests, ~5 minutes. Needs no corpus.
make adversarial              # the seven refusal scenarios. Needs no corpus.

make worlds                   # generate 100 worlds (80 dev / 20 sealed holdout), ~80s
make eval                     # open the holdout once, evaluate every strategy -> results/
make demo                     # build the dashboard's data, then serve it at :8501

make audit EXPERIMENT=<id>    # one experiment's decision chain
                              #   (needs a prior run; use AUDIT_DB=data/holdout_eval_audit.db
                              #    after make eval, or EXPERIMENT=--list to see what is there)
```

`make eval` runs the five deterministic strategies and the oracle diagnostic. It
reproduces the results table above exactly and needs no API key. **MarginPilot
itself is opt-in**, because it makes one LLM call per world:

```bash
make eval EVAL_ARGS=--with-agent     # also runs MarginPilot; needs GEMINI_API_KEY
```

## Audit trail

Every money-adjacent action writes an append-only record: agent intent → policy decision (with the rule that fired) → randomization seed → execution → payment ID → measured outcome. `make audit EXPERIMENT=<id>` prints the full chain for any experiment.

## Related work

MarginPilot is a student implementation in an active area, and cites its neighbours rather than claiming an empty field.

- **A/B Agent (2026)** — closed-loop agent generating strategies, running experiments, and iterating. Closest published work. *Delta:* MarginPilot gates money actions on incremental contribution under a bounded budget, and reports generalization across held-out economic environments.
- **AgentA/B (2025)** — LLM agents simulating users for e-commerce A/B testing. *Delta:* simulation is the evaluation substrate here, not the subject.
- **Commercial promotion optimization** (SymphonyAI, Cognira PromoAI, CPGvision, BCG X RGM) — enterprise platforms covering promotion lift, incrementality, and budget allocation. *Delta:* not a novelty claim; this is an open, reproducible implementation with a published holdout protocol and an LLM ablation.
- **Razorpay Agent Studio (Mar 2026)** — production agents for cart recovery, subscription recovery, disputes, and cashflow forecasting. MarginPilot addresses promotion-budget allocation, which those agents do not cover, and publishes the measurement layer they do not.

## License

MIT
