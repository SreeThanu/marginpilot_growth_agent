# MarginPilot — Build Plan

**Start:** Tue 25 Aug · **Submit:** Thu 4 Sep · **Deadline:** Fri 5 Sep (buffer only, do not plan to use it)

11 working days. Every day has a **done-criterion** — a thing that either runs or doesn't. If a day's criterion isn't met by end of day, read the Fallback Gates section rather than pushing the whole schedule right.

---

## Day 1 — Tue 25 Aug · Foundations

Today is setup and design, not simulator code. Resist starting the generator before the schema is decided.

1. `git init`, commit `README.md` and `CLAUDE.md` as the first commit.
2. `conda create -n marginpilot python=3.11`, `requirements.txt`, `.env.example`, `.gitignore`.
3. Create the full `src/` skeleton with empty `__init__.py` files, matching the module layout in CLAUDE.md.
4. Register for a Razorpay test-mode account and confirm the keys work with one trivial API call. **Do this today** — account/verification friction on Day 8 would be a disaster.
5. Write `docs/simulator.md`: the world schema and the parameter ranges, with citations to published retail price-elasticity literature. This document is the defense against "you built the world to win," so it gets written before the code it describes.

**Done when:** the repo skeleton is committed, a Razorpay test API call returns 200, and `docs/simulator.md` names every world parameter with a sourced range.

---

## Day 2 — Wed 26 Aug · World generator

1. `src/world/schema.py` — dataclasses for World, Customer, Product, Segment, Intervention.
2. `src/world/generator.py` — samples a world from the parameter distributions. Seeded and reproducible: `generate_world(seed)` must return identical output on every run.
3. **Semantic context — mandatory.** Every world carries product names, categories and descriptions; inventory age per SKU; qualitative segment notes ("bulk buyers, price-insensitive, order on salary week"); seasonal and competitor events; customer-service themes. This is what gives the LLM a reasoning problem instead of a menu. It cannot be retrofitted later — worlds the agent has already been tuned against are contaminated.
4. **Potential outcomes — mandatory.** For every customer and every intervention type, generate both `Y(0)` and `Y(1)`. The simulator knows both; the agent will only ever observe one. Exposed to `eval/` only, never to an agent tool. This is what lets you report estimation error against known truth on Day 9.
5. Generate 100 worlds. Write 80 to `worlds/dev/` and 20 to `worlds/holdout/`.
6. **Seal the holdout.** Add `worlds/holdout/` to a path-guard in `src/eval/` that raises unless an explicit `--final-eval` flag is set. Make it mechanically annoying to peek, not just a promise to yourself.

**Done when:** `make worlds` produces 100 reproducible worlds, each with populated semantic fields and hidden potential outcomes, plus a sanity report (conversion rates, AOV distributions, margin ranges) that looks like plausible retail, not noise.

---

## Day 3 — Thu 27 Aug · Experiment engine

1. `src/experiment/registry.py` — an experiment record: arms, horizon, MDE, budget, created-at, immutable after launch.
2. `src/experiment/randomize.py` — `assign(customer_id, experiment_id, n_arms)` via stable hash. Test that assignment is deterministic, balanced, and independent across experiments.
3. `src/experiment/power.py` — given baseline conversion, MDE, alpha and power, return required sample size per arm. This computes the fixed horizon written into the registry at launch.
4. `src/experiment/evaluator.py` — at horizon, compute the treatment-control difference with confidence intervals. Before horizon, refuse to return a verdict-eligible result.
5. **Uncertainty-aware scaling.** An experiment is scale-eligible only when the *lower bound* of the CI on incremental contribution clears zero. A positive point estimate is not authority to spend. Ten lines; large rigor signal.

**Done when:** you can create an experiment, assign 10,000 simulated customers, and the horizon-refusal path is covered by a passing test.

---

## Day 4 — Fri 28 Aug · Economics + eval spine

This is the most important day in the plan. By tonight the measurement spine runs end to end with no LLM anywhere in it.

1. `src/economics/contribution.py` — pure functions: incremental orders, incremental contribution, discount cost across *all* treatment buyers, ROMI. Unit-test each against hand-computed values, including the README's worked example (1,000/arm → 60 incremental orders → ₹14,400 − ₹18,000 = **−₹3,600**).
2. `src/eval/harness.py` — run a strategy across a set of worlds, collect the five primary metrics plus the secondaries.
3. `src/eval/replay.py` — **counterfactual replay.** Given a completed experiment and the world's `Y(0)`/`Y(1)`, compute what each alternative strategy would have decided and what it would have cost. Nearly free now that potential outcomes exist, and it produces the best beat in the demo.
4. `src/agent/stub.py` — a hardcoded non-LLM "agent" that proposes one fixed experiment. Purely to exercise the pipeline.
5. Run the stub across 5 dev worlds. Get real numbers out.

**Done when:** `make eval --strategy=stub --worlds=dev[:5]` prints a metrics table. Ugly output is fine. Numbers that exist are the point.

---

## Day 5 — Sat 29 Aug · Baselines

All strategies share one interface: `decide(world_state, budget) -> list[Intervention]`.

1. Baseline 1 — do nothing.
2. Baseline 2 — rule-based: 10% off where P(purchase) < 0.4.
3. Baseline 3 — conversion optimizer: maximize expected conversions, ignore contribution.
4. Baseline 5 — engine without LLM: fixed hypothesis set, same experiment machinery, same economic gate. **This is the ablation. Build it now, not later.**
5. Run all four across 10 dev worlds.

**Done when:** four baselines produce comparable metrics on the same worlds. You now have something to beat, before you've built the thing meant to beat it.

---

## Day 6 — Sun 30 Aug · The agent · **MVP COMPLETE**

1. `src/agent/hypothesis.py` — the **falsifiable hypothesis object**: prediction, reasoning (grounded in the world's semantic context), expected effect size, required sample, success/failure condition. Written to the registry at launch and immutable thereafter.
2. `src/agent/tools.py` — the ten tools listed in CLAUDE.md. No more.
3. `src/agent/agent.py` — the loop: observe semantic context → hypothesize → propose → gate → launch → wait for horizon → evaluate → SCALE/KILL → **diagnose why the prediction failed** → **propose a revised hypothesis** → repeat.
4. Baseline 4 — the same LLM choosing campaigns with no experiments and no economic gate.
5. Run MarginPilot on a single dev world, end to end, through at least two hypothesis cycles.

**Done when:** one world → hypothesis → experiment → contribution computed → SCALE or KILL → diagnosis → a *second, different* hypothesis that visibly reflects what the first one learned. The second cycle is the point; one cycle is a calculator. **At this point you have a valid submission even if everything after this fails.** Tag the commit `mvp`.

---

## Day 7 — Mon 31 Aug · Policy engine + audit

1. `src/policy/gates.py` — budget remaining, max discount %, minimum contribution margin, max customer exposure, experiment power minimum. Each returns a structured verdict, never a bare boolean.
2. Wire `validate_experiment()` so nothing reaches `launch_experiment()` ungated.
3. `src/audit/log.py` — append-only: agent intent → policy verdict (with the rule that fired) → randomization seed → execution → payment ID → measured outcome.
4. Write the rejection tests: one per rule, each proving a violating proposal is refused.
5. **Uplift modeling — only if Day 6 landed clean.** T-learner or causal forest over customer features to estimate individual treatment effects; target only positive-effect customers. Validate against known `τ` on Day 9. This is a day-plus of work, unlike items 11–13 which are hours — it is the first thing to drop if you are behind.

**Done when:** `make audit EXPERIMENT=<id>` prints a complete decision chain, and every policy rule has a test proving it rejects.

---

## Day 8 — Tue 1 Sep · Razorpay integration

1. `src/payments/razorpay_client.py` — order creation and payment link generation in test mode.
2. Webhook receiver, with an idempotency key so duplicate delivery produces exactly one attribution.
3. Reconciliation job: if a webhook is missing after N seconds, resolve order state via Razorpay fetch.
4. Wire the executed subset into experiment attribution.
5. Write `docs/razorpay_scope.md` — state plainly which orders are executed live in test mode and which are simulated, and why. Stating this yourself is a strength; having it discovered is a hole.

**Done when:** a real test-mode payment flows through to an experiment's attribution, and the duplicate-webhook test passes.

---

## Day 9 — Wed 2 Sep · Holdout evaluation

The day the project either works or teaches you something. Don't schedule anything else.

1. Freeze the code. No tuning after this point.
2. Run all six strategies across the 20 holdout worlds.
3. Populate the README's pre-registration table with measured values. **Report misses as misses.**
4. Write the failure taxonomy: which world types MarginPilot underperformed in, profitable campaigns it killed in error, where its effect estimates were furthest from known `τ`.
5. **Counterfactual validation.** Compute estimation error against the simulator's ground-truth treatment effects. This is the answer to "your data is synthetic" — no real-data project can do it.
6. **Cost-of-learning.** Total budget spent on experiments that were killed, versus total contribution created. Was learning net-positive against never experimenting? Report either way.
7. **Hypothesis calibration.** Across all pre-committed hypotheses, how often did the predicted effect fall inside the realized CI? Cheap, and almost nobody else will have it.

**Done when:** every `TBD` in the README is a real number and "Where MarginPilot loses" is written honestly.

> **If MarginPilot loses to a baseline:** do not tune and re-run. Report it, analyze why, and say what you'd change. A published negative result with a clear diagnosis reads as engineering maturity. A quietly reversed one is the only unrecoverable mistake available to you.

---

## Day 10 — Thu 3 Sep · Dashboard + adversarial

1. Streamlit dashboard: budget, live experiments, arm counts, the contribution breakdown, the kill/scale decision, the audit trail panel. Show real counts — no fake green dashboards.
2. The adversarial scenarios from the README table: over-ceiling discount, over-budget spend, early-stop attempt, underpowered experiment, missing webhook, invalid intervention type.
3. Rehearse the demo flow twice, timed.

**Done when:** the −₹3,600 kill screen renders cleanly and the six adversarial scenarios each produce a visible, logged refusal.

---

## Day 11 — Fri 4 Sep · Submit

1. README final pass: delete the results-status warning box, verify no `TBD` survives, confirm the Related Work section is intact.
2. `docs/architecture.md` with the loop diagram and the reasoning/authority split.
3. Record the video (script below). Two or three takes, pick one, don't chase perfection.
4. Repo hygiene: no secrets, `make demo` works from a clean clone, README install steps followed literally on a fresh env.
5. **Submit the form.** Repo link, video link, architecture doc.

---

## The video — script it Day 10, record Day 11

Five minutes, structured so the differentiator lands before any explanation:

- **0:00–0:30** — The kill screen. +50% conversion, −₹3,600 contribution, CAMPAIGN KILLED, projected −₹36,000 avoided. No title card, no "meet our agent."
- **0:30–1:00** — Why that happens: the discount is paid to buyers who'd have converted anyway.
- **1:00–2:00** — The agent working: opportunity → hypothesis → experiment design → policy gate → randomized launch.
- **2:00–2:45** — Adversarial: an over-ceiling proposal rejected, an early-stop attempt refused.
- **2:45–4:00** — Results: the holdout table against all five baselines, including the no-LLM ablation. Say the numbers out loud, including anything you missed.
- **4:00–5:00** — Where it loses, and the methodology: 100 worlds, 20 sealed, pre-registered targets.

---

## Fallback gates

If you're behind, cut in this order — top first:

1. Streamlit dashboard → console output with a screen recording
2. Adversarial extras beyond the two shown in the video
3. Live Razorpay subset → mocked payment client with the same interface
4. Experiment portfolio / multi-experiment budget allocation
5. Baseline 4 (LLM strategist) — Baseline 5 is the one that matters

**Never cut:** the holdout evaluation, the baselines, the policy gate, the audit trail, the failure taxonomy. Those are the submission.

---

## Authority

This file is authoritative on scheduling. `CLAUDE.md` mirrors this table for Claude Code's benefit; if the two ever disagree, this one wins.
