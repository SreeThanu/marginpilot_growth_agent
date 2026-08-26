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

> ### ⚠️ Results status
>
> Every number in the Results section below is a **pre-registered target**, written before the evaluation was run. Actual measured values replace them once `make eval` completes on the holdout worlds. Targets that were missed are reported as missed. See [Pre-registration](#pre-registration).
>
> **Delete this box before submitting, and make sure every `TBD` is filled with a real number.**

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
REJECTED — expected contribution ₹-3,600 < minimum threshold ₹0
REJECTED — discount 22% > max_discount 15%
REJECTED — projected spend ₹180,000 > remaining budget ₹50,000
```

Every rejection is logged with the rule that fired, the value that violated it, and the agent's original intent.

## Why not just a bandit?

This is the sharpest objection to the project, so it is answered empirically rather than argued.

`Baseline 5` is the **experimentation engine with the LLM removed** — the same statistical machinery, the same policy gates, driven by a fixed hypothesis set. If the LLM adds nothing over that, this README says so and the finding stands as a result. Assertions that "the agent is intelligent" are not evidence; the ablation is.

## Statistical design

The parts that are easy to get wrong, and how they're handled:

**No peeking.** The agent cannot repeatedly check an experiment and stop when it likes the p-value. Experiments run to a pre-computed fixed horizon derived from a minimum detectable effect on incremental contribution. The horizon is written into the experiment registry at launch and is immutable. (Sequential testing with alpha spending is a post-MVP extension, not a shortcut.)

**Randomization the agent cannot influence.** Assignment is `hash(customer_id + experiment_id) mod n_arms`, computed in the experiment engine. The agent has no tool that can move a customer between arms.

**Known ground truth.** The simulator generates both potential outcomes `Y(0)` and `Y(1)` for every customer. The experiment observes only one per customer, exactly as in reality — but the evaluation harness knows the true individual treatment effect `τᵢ = Yᵢ(1) − Yᵢ(0)`. This lets the harness report not just whether the agent made money, but whether its *estimates* were accurate: estimation error against known truth, separate from decision quality.

**Scaling requires confidence, not a positive point estimate.** An experiment is only scaled when the lower bound of the confidence interval on incremental contribution clears zero. A promising-looking mean is not sufficient authority to spend money.

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

Measured on the 80 development worlds (not the holdout), the four intervention types are not equally good ideas, and deliberately have not been made so:

| Intervention | Best choice in |
|---|---|
| Free shipping | 48% of worlds |
| Flat discount | 40% |
| Bundle | 8% |
| Percentage discount | 5% |

A percentage discount scales its cost with basket size, so it pays the most to the customers with the largest baskets — the customers most likely to have converted anyway. A flat ₹150 off is a 30% discount to a ₹500 basket and 6% to a ₹2,500 one, concentrating incentive where an incremental order is cheapest to buy. This is the same mechanism as the worked example at the top of this README, applied to the choice between interventions rather than to a single campaign.

All four types produce profitable, marginal and unprofitable cases across the corpus, so none is dominated by construction. The parameters were **not** adjusted to equalize how often each type wins: doing so would mean rigging the worlds so that economically disfavoured strategies succeed more often than the economics allows. Details and the pre-registered Day-2 diagnostic are in [`docs/simulator.md`](docs/simulator.md).

## Baselines

| # | Baseline | Optimizes |
|---|---|---|
| 1 | Do nothing | — (natural business performance) |
| 2 | Rule-based marketer | Fixed rule: 10% off to customers with P(purchase) < 0.4 |
| 3 | Conversion optimizer | Expected conversions — the naive AI approach |
| 4 | LLM strategist | LLM picks campaigns from context, no experiments, no economic gate |
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

## Pre-registration

Targets were fixed before evaluation. Measured values are reported whether or not they were met.

| Metric (holdout worlds) | Target | Measured |
|---|---|---|
| Incremental contribution vs. Baseline 1 | > 0 | `TBD` |
| Incremental contribution vs. Baseline 2 (rules) | beat | `TBD` |
| Incremental contribution vs. Baseline 3 (conversion optimizer) | beat | `TBD` |
| Incremental contribution vs. Baseline 5 (no LLM) | beat | `TBD` |
| Policy violations | **0** | `TBD` |
| Budget overruns | **0** | `TBD` |
| Negative-contribution campaigns scaled | **0** | `TBD` |
| ROMI | > 1.0 | `TBD` |

## Results

`TBD — populated from evaluation output on the 20 holdout worlds.`

### Where MarginPilot loses

`TBD — the failure taxonomy. This section is mandatory and stays in the README even when it is unflattering. World types where the agent underperformed, campaigns it killed that were actually profitable, and estimation failures go here.`

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

**Scope, stated plainly:** experiment mathematics run across simulated customer populations at a scale no sandbox could support. A defined subset of orders is executed end-to-end through Razorpay test mode with real webhook-driven attribution, demonstrating that the full financial loop closes. Which orders are real and which are simulated is recorded per experiment in the audit trail and shown in `docs/razorpay_scope.md`.

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

**Deliberately not used:** Kafka, Kubernetes, Docker, vector databases, multi-agent swarms, reinforcement learning, custom models, MCP layers. The interesting part is the decision architecture and the evaluation, not the technology count.

## Stack

Python 3.11 · FastAPI · SQLite · pandas / NumPy · SciPy / statsmodels · scikit-learn · Razorpay Test APIs · Streamlit

## Running it

```bash
conda create -n marginpilot python=3.11 && conda activate marginpilot
pip install -r requirements.txt
cp .env.example .env          # add RAZORPAY_TEST_KEY_ID, RAZORPAY_TEST_KEY_SECRET, LLM API key

make worlds                   # generate 100 worlds (80 dev / 20 sealed holdout)
make demo                     # single world, full agent loop, dashboard at :8501
make eval                     # all baselines across 20 holdout worlds → results/
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
