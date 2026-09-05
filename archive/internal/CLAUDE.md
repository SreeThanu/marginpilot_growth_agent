# CLAUDE.md — MarginPilot

Instructions for Claude Code working in this repository. Read fully before writing code.

## What this project is

An autonomous merchant growth agent that runs controlled promotion experiments and allocates a bounded budget based on **incremental contribution**, not conversion lift. Built for the Razorpay AI Buildathon, Track 1.

The submission is judged on the repo, a 5-minute video, and the architecture. **The evaluation methodology is the differentiator, not the feature count.** When trading off, protect the evaluation.

## Hard invariants — never violate these

These are not style preferences. Violating any of them invalidates the project's central claim.

1. **The LLM never assigns customers to arms.** Randomization is `hash(customer_id + experiment_id) mod n_arms` inside `src/experiment/`. No agent tool may accept an arm assignment as an argument or move a customer between arms.
2. **The LLM never executes a payment, sets a budget, or sets a discount ceiling.** It proposes; `src/policy/` disposes. Every money-adjacent action passes through the policy gate.
3. **No peeking.** The experiment horizon is computed at design time from a minimum detectable effect and written immutably into the registry. `get_experiment_results()` must refuse to return a KEEP/KILL-eligible verdict before the horizon is reached. Do not add an "early stop if significant" path. If sequential testing is added later, it uses a pre-specified alpha-spending or Bayesian rule fixed before data is seen.
4. **Holdout worlds are sealed.** Never read, print, tune against, or inspect the structural parameters of the 20 holdout worlds during development. They are opened once, by `make eval`. If you need a world to debug against, generate a new dev world.
5. **Never fabricate a result.** Do not write example numbers into the README results table, docstrings, or the dashboard as if measured. Placeholders stay `TBD` until the harness produces real values. If a target is missed, report it missed.
6. **The audit log is append-only.** No update or delete paths. Ever.
7. **Hypotheses are pre-committed and immutable.** Every hypothesis states its prediction, reasoning, expected effect size, required sample, and success/failure condition *before* the experiment launches, and is written to the registry unchanged. The agent may not revise a hypothesis after seeing results — it may only diagnose the failure and propose a *new* hypothesis. Retroactively editing a prediction to match an outcome invalidates the calibration analysis.
8. **The world generator must emit semantic context and hidden potential outcomes from the first world.** Both are unrecoverable if skipped — a later retrofit cannot produce worlds the agent was already tuned against. `Y(0)`/`Y(1)` are visible to `eval/` only; no agent tool may ever return them.
9. **Success and failure are both results.** If MarginPilot loses to a baseline — including Baseline 5, the no-LLM ablation — that outcome gets reported, not tuned away. Tuning against holdout results to reverse an unfavourable finding is the one unrecoverable mistake in this project.

## Build order

`BUILD_PLAN.md` is authoritative on scheduling. This table mirrors it — if the two ever disagree, follow `BUILD_PLAN.md`.

Build in this sequence. The evaluation spine comes first, deliberately — it is the differentiator and must not be what gets cut if time runs short.

| Day | Date | Deliverable |
|---|---|---|
| 1 | Tue 25 Aug | Repo skeleton, `requirements.txt`, `.env.example`, `Makefile`. Razorpay test keys verified. `docs/simulator.md` with sourced elasticity ranges. |
| 2 | Wed 26 Aug | `src/world/` — generator, schemas, simulator. **Semantic context fields** and **hidden `Y(0)`/`Y(1)`** are both mandatory today. Generate 100 worlds, seal 20. |
| 3 | Thu 27 Aug | `src/experiment/` — registry, randomization, power/horizon, evaluator with confidence intervals. **Uncertainty-aware scaling: CI lower bound must clear zero.** |
| 4 | Fri 28 Aug | `src/economics/` + `src/eval/` harness + **counterfactual replay**, driven by a hardcoded stub agent. **The measurement spine must work before anything intelligent exists.** |
| 5 | Sat 29 Aug | `src/baselines/` — 1, 2, 3 and 5. Cheap, and they de-risk the headline claim. |
| 6 | Sun 30 Aug | `src/agent/` — **falsifiable hypothesis objects**, **diagnose→revise loop**, tool layer, Baseline 4. **MVP complete; tag the commit `mvp`.** |
| 7 | Mon 31 Aug | `src/policy/` + `src/audit/` — gates, rejection logging, append-only decision chain. Uplift modeling only if Day 6 landed clean. |
| 8 | Tue 1 Sep | `src/payments/` — Razorpay test mode, webhooks, idempotency, reconciliation. |
| 9 | Wed 2 Sep | Freeze code. Full holdout evaluation. **Cost-of-learning analysis.** **Counterfactual validation: estimated effects vs. true `τ`.** Failure taxonomy. |
| 10 | Thu 3 Sep | `src/ui/` dashboard, adversarial scenarios, demo rehearsal, video script. |
| 11 | Fri 4 Sep | README final pass, architecture doc, record video, **submit**. |

Deadline is Fri 5 Sep. It is buffer, not a working day.

**Fallback gates.** If you fall behind, cut in this order — top first:

1. Streamlit dashboard → console output with a screen recording
2. Adversarial extras beyond the two shown in the video
3. Live Razorpay subset → mocked payment client with the same interface
4. Experiment portfolio / multi-experiment budget allocation
5. Baseline 4 (LLM strategist) — Baseline 5 is the one that matters

**Never cut:** holdout evaluation, baselines, policy gate, audit trail, failure taxonomy.

## The MVP that must exist by Day 6 (Sun 30 Aug)

One world → one product family → one intervention → control/treatment experiment → contribution calculation → agent decides SCALE or KILL.

If that runs end-to-end, there is a valid submission. Everything after is expansion.

## Module boundaries

```
src/
├── world/          # world generator, simulator, potential outcomes. NO agent imports.
├── experiment/     # registry, randomization, power/horizon, statistical evaluator
├── economics/      # contribution math. Pure functions, heavily unit-tested.
├── policy/         # the money gate. Deterministic. NO LLM calls in this module.
├── agent/          # the ONLY module that may import an LLM client
├── payments/       # Razorpay test client, webhooks, idempotency, reconciliation
├── baselines/      # five strategies, same interface as the agent
├── eval/           # holdout harness, metrics, failure taxonomy
├── audit/          # append-only decision log
└── ui/             # Streamlit
```

If an `import` would make `policy/`, `experiment/`, or `economics/` depend on `agent/`, the design is wrong. Those three must be testable and runnable with no LLM present.

## Agent tools — the complete list

Do not add tools beyond these without an explicit reason. Tool sprawl is how the reasoning/authority boundary erodes.

```
get_merchant_metrics()
get_customer_segments()
get_product_context()
propose_experiment()
validate_experiment()      # returns policy verdict; does NOT execute
launch_experiment()        # only executes an already-validated design
get_experiment_results()   # refuses verdict-eligible data before horizon
evaluate_experiment()
scale_experiment()         # policy-gated
stop_experiment()
```

## Environment constraints

- **No sudo, no Docker.** Lab machines are restricted. Everything runs in a user-space conda env. Do not add Docker, Kubernetes, or anything needing root.
- **SQLite, not Postgres.** No server processes.
- Secrets in `.env`, never committed. `.env.example` documents the keys.
- Razorpay **test mode only**. Never touch live keys.

## Anti-patterns — do not do these

- Adding Kafka, Redis, vector DBs, MCP layers, RL, or multi-agent swarms. There is no justification at this scale and a reviewer will read it as padding.
- **The locked do-not-build list:** multi-agent swarm, voice, MCP, RL, elaborate dashboard, more than ~4 intervention types, real-time infrastructure, a full value-of-information framework. This list will feel wrong around Day 8, when the core works and additions look like obvious improvements. It is not wrong. Re-read it then.
- Engineering fake failures to look humble. Run it honestly; the real failures are enough and a manufactured one is detectable.
- Building the dashboard early because it's visible. The dashboard is Day 11.
- Writing plausible-looking numbers into docs "as an example."
- Letting the agent retry an experiment until it gets a favourable read.
- Deleting or rewriting a failed experiment's audit records.
- Making the demo scene numbers inconsistent with the budget. The pilot is **1,000 per arm** (60 incremental orders, ₹14,400 contribution, ₹18,000 discount cost, **−₹3,600 net**, projected −₹36,000 at full scale). The old ₹180,000 figure exceeded the ₹50,000 budget and is wrong — do not reintroduce it anywhere.
- Claiming novelty. The README cites its neighbours (A/B Agent, AgentA/B, SymphonyAI, Cognira, Razorpay Agent Studio). Keep it that way.

## Testing expectations

- `economics/` and `experiment/` need real unit tests with hand-computed expected values. These carry the project's credibility.
- Every policy rule needs a test proving it rejects a violating proposal.
- An integration test proving the agent cannot influence arm assignment.
- Webhook idempotency test: duplicate delivery produces one attribution.

## Style

Python 3.11, type hints on public functions, docstrings explaining *why* not *what*. Small pure functions in `economics/`. Commit in coherent units with real messages — the commit history is read by reviewers as evidence of how the project was built.

## When unsure

Ask rather than assume, especially on anything touching randomization, stopping rules, budget enforcement, or the holdout split. A wrong guess in those four areas is not a bug — it silently invalidates the results.
