# Submission reproducibility audit — inspection only

**Date:** 1 September 2026
**Snapshot:** `/Volumes/thanu's T7/margin_pilot_artifact_snapshot_2026-09-01/` (created 18:26 today)
**Repo:** `/Volumes/thanu's T7/margin_pilot` @ `main` `4942af6`, working tree clean
**Constraints honoured:** nothing modified, nothing committed, no LLM run, no sealed holdout opened, no diagnostic "fixed", no assumption/world-set/estimator/accounting altered.

---

## 0. Two findings that govern everything below

**Finding 1 — the Cycle-2 corpus is reproducible from committed source.** The seeds are hardcoded constants in tracked code:

```
src/world/__main__.py:37-38
DEV_SEEDS     = range(20_001, 20_081)
HOLDOUT_SEEDS = range(29_001, 29_021)
```

I regenerated three dev worlds in memory (first, middle, last) and compared to disk. `GENERATOR_VERSION = "4.0.0"` on both sides:

| world | disk schema | sha256(canonical JSON) disk vs fresh | match |
|---|---|---|---|
| `world_20001` | 4.0.0 | `5379490f76738983` / `5379490f76738983` | **yes** |
| `world_20051` | 4.0.0 | `99f539d377bb820e` / `99f539d377bb820e` | **yes** |
| `world_20080` | 4.0.0 | `fe745dc6c9e996bf` / `fe745dc6c9e996bf` | **yes** |

The regeneration command is recorded verbatim in `cycle2_report.txt`: `--out worlds_cycle2`, 80 dev + 20 holdout, "holdout worlds written and sealed — not inspected". So `worlds_cycle2/` being gitignored is **not** a reproducibility blocker; it is a regeneration step.

**Finding 2 — the recorded results were produced in an environment that does not match `requirements.txt`.**

| package | pinned in `requirements.txt` | installed under `make`'s default `python` (`/opt/anaconda3/bin/python`) |
|---|---|---|
| numpy | **2.3.5** | 1.26.4 |
| scipy | **1.17.1** | 1.13.1 |
| scikit-learn | **1.9.0** | 1.5.1 |

Every recorded number in the snapshot was produced under the *installed* versions, not the pinned ones. This matters only for the two scripts that use scikit-learn (`predict.py`, `policy.py`); the rest are pure numpy arithmetic. A clean-clone reviewer following `requirements.txt` would be running different library versions from the ones that produced the artifacts.

---

## 1. Cross-cutting facts, verified across all 15 scripts

| check | result |
|---|---|
| **LLM imports** (`src.agent`, `reasoner`, `genai`, `gemini`, `openai`) | **NONE** in any snapshot script |
| **Sealed-holdout references** (`open_holdout`, `final_eval`, `worlds/holdout`, `29xxx`) | **NONE** in any snapshot script |
| **Writes into the repository** | **NONE.** Every write targets `/private/tmp/…`. The only in-repo file accesses are *reads* of committed `results/*.json` |
| **Repo symbols imported** | all present — `EngineWithoutLLM`, `DEFAULT_ORDER`, `merchant_view`, `open_dev`, `assign`, `design_experiment_on_contribution`, `PolicyLimits`, `_true_population_net`, `vocabulary`, `load_world`, `_print_report`, `_world_summary`. **10/10 modules import clean, 0 missing attributes** |
| **RNG** | only `predict.py` and `policy.py` use any — both `GradientBoostingRegressor(random_state=0)`. Every other script is RNG-free and fully deterministic given the corpus |
| **Data access route** | all twelve corpus-reading scripts use `open_dev("worlds_cycle2", …)`, which routes through `src/eval/devcorpus.py` — never passes `final_eval`, cannot reach a sealed world |

**The shared blocker.** Nine scripts hardcode their output path to the *previous session's* scratchpad:

```
/private/tmp/claude-501/-Volumes-thanu-s-T7-margin-pilot/25d21d0d-01ac-48e1-99bd-88ce9debd1c3/scratchpad/<name>.json
```

Two consequences, both stated rather than fixed:

1. **It is environment-specific and volatile.** `/private/tmp` is cleared on reboot. A reviewer on another machine cannot run these unmodified.
2. **Rerunning them today would overwrite the originals in place.** That directory still exists and is writable. The snapshot is a *copy*, so the originals are preserved there — but the live files would be clobbered by any rerun.

All scripts also open with `sys.path.insert(0, ".")`, so they must be invoked with the working directory set to the repository root.

---

## 2. Diagnostic-by-diagnostic inventory

### 2.1 The targeting family (Sep 1, 00:31–12:32)

| # | script | question tested | worlds | output artifact |
|---|---|---|---|---|
| 1 | `hetero.py` | Is there per-customer treatment-effect heterogeneity to target at all? | `limit=10` → **20001–20010**, ×4 arms | **none — stdout only** |
| 2 | `targeting.py` | Can realistic signal support profitable targeting? One experiment per world, Baseline-5 sizing, Cycle-1 cost accounting | `limit=20` → **20001–20020** | `targeting.json` |
| 3 | `predict.py` | Do the six observable fields predict individual treatment effect? | TRAIN **20021–20050**, TEST **20051–20080** (20001–20020 excluded as contaminated) | **none** — only `_ok.npy` sentinel |
| 4 | `policy.py` | Net contribution of the frozen observable predictor on held-out worlds | TRAIN **20021–20050**, TEST **20051–20080** | **none — stdout only** |

### 2.2 The earlier probe family (Aug 31–Sep 1, 00:31–01:07)

| # | script | question tested | worlds | output artifact |
|---|---|---|---|---|
| 5 | `predictability.py` | Was the profitable choice inferable at decision time, or only from the oracle? | `limit=20` → 20001–20020 + reads committed `results/cycle3_noise_neither_rep1.json` | `pred.json` |
| 6 | `learncost.py` | Could ONE bounded experiment pay for itself, per world? | `limit=20` + same committed results file | `learncost.json` |
| 7 | `proxy.py` | Is opportunity SIZE inferable from decision-time observables? | `limit=20` → 20001–20020 | `proxy.json` |
| 8 | `ceiling.py` | Economic ceiling of learning-by-experiment (idealised updating) | `limit=N_WORLDS` → 20001–200xx | `ceiling.json` |
| 9 | `ceiling2.py` | Honest ceiling: perfect updating, **no foresight** about which arm to test; `DEFAULT_ORDER` fixed in advance | `limit=20` | `ceiling2.json` |
| 10 | `ceiling3.py` | Order-agnostic honest ceiling, averaged over all 4! test orders | `limit=20` | `ceiling3.json` |
| 11 | `history_leak.py` | Is intervention response recoverable from realistically-available history? (randomized / required-n / observational) | `limit=20` | `history_leak.json` |
| 12 | `confound.py` | Realistic confounding — each past campaign targeted differently | `limit=20` | `confound.json` |

### 2.3 Pure re-readers of committed data (no corpus access)

| # | script | question | inputs | LLM |
|---|---|---|---|---|
| 13 | `reanalyse.py` | Re-report Cycle 2's ablation on a fixed denominator. "No new runs." | `results/cycle2_dev_{neither,break_even_only,history_only,both}.json` — **all four committed** | no |
| 14 | `render_arms.py` | Render the Cycle 2 2×2 ablation as one table | same four committed files | no |
| 15 | `report_from_disk.py` | Print the world sanity report from disk without regenerating | world dir passed as `sys.argv[1]` | no |

### 2.4 Non-script artifacts in the snapshot

| artifact | provenance | LLM | sealed data |
|---|---|---|---|
| `win.json` | self-describes: *"generated_from: the 20 sealed holdout worlds, opened once at final evaluation"*, `model: gemini-3.6-flash` | **yes** | **yes — Cycle-1 holdout, legitimately opened once** |
| `smoke.json`, `arm_smoke.json`, `err_smoke.json`, `rep_smoke_rep1/2.json` | `src/eval/devrun.py` outputs (1–2 worlds). `devrun` imports `src.agent.reasoner` | **yes** | no |
| `cycle2_dev.log`, `cycle2_arms.log`, `cycle2_both.log`, `cycle3_noise{,2,3,4}.log`, `fixa_c1.log` | LLM run logs; three contain Gemini/rate-limit strings | **yes** | no |
| `baselines20.json` | five baseline nets + cost-of-learning. **No producing script or command recorded anywhere in the snapshot** | unclear | unclear |
| `cycle1_report.txt`, `cycle2_report.txt` | world-generation sanity reports (`python -m src.world`) | no | no — `cycle2_report.txt` explicitly records the holdout as written-and-sealed, not inspected |
| `cc2/`, `cc3/`, `cleanclone/` | three full git clones — clean-clone verification sandboxes from Aug 28 | — | — |
| `codexcheck/` | `note.txt` = "verification sandbox", `err.txt` | — | — |
| `_ok.npy`, `tests_after_ablation.log`, `__pycache__/` | run sentinels and build detritus | — | — |

---

## 3. Comparison against independently recoverable outputs (item 12)

| recorded artifact | independent counterpart in repo | comparison |
|---|---|---|
| `targeting.json` | none — but internally checkable | I summed its columns directly: `realistic = −183,653`, `oracle_seg = +506,876`, `oracle_ind = +1,939,978` over 20 worlds. **Exact match** to the three figures reported in conversation |
| `reanalyse.py` / `render_arms.py` inputs | `results/cycle2_dev_*.json` — **committed** (`.gitignore:71` carries the explicit `!results/cycle2_dev_*.json` exception) | fully recoverable; these scripts add no data, only a re-rendering |
| `predictability.py` / `learncost.py` inputs | `results/cycle3_noise_neither_rep1.json` — **committed** | recoverable |
| `win.json` | `data/holdout_results.json` — **committed** (`.gitignore:47` exception) | the durable holdout evidence is already in the repo; `win.json` is a scratch copy of the same run |
| `hetero.py`, `predict.py`, `policy.py` results | **none** | no file was ever written. The recorded values survive only as text in the session transcript `~/.claude/projects/-Volumes-thanu-s-T7-margin-pilot/25d21d0d-….jsonl` |

Tracked evidence in the repo: `results/cycle2_dev_*.json` (4), `results/cycle3_fixa_rep{1,2}.json`, `results/cycle3_noise_neither_rep{1..8}.json`, `data/holdout_results.json`. Untracked/ignored: `results/holdout_evaluation.json`.

---

## 4. Accidental dependencies (explicitly requested)

| dependency class | present? | detail |
|---|---|---|
| **`/private/tmp` paths** | **YES — 9 scripts** | `ceiling.py:112`, `ceiling2.py:89`, `ceiling3.py:76`, `confound.py:65`, `history_leak.py:71`, `learncost.py:72`, `predictability.py:57`, `proxy.py:74`, `targeting.py:95` all hardcode the `25d21d0d-…` scratchpad. `predict.py:84` writes `_ok.npy` there too |
| **uncommitted files** | **YES** | `worlds_cycle2/` (gitignored) — but regenerable, see §0 Finding 1. No diagnostic depends on any *irreproducible* uncommitted file |
| **non-reproducible generated worlds** | **NO** | seeds are committed constants; three worlds verified byte-identical |
| **environment-specific state** | **YES** | (a) `sys.path.insert(0, ".")` requires CWD = repo root; (b) library versions diverge from `requirements.txt` (§0 Finding 2), affecting `predict.py` and `policy.py` |
| **files outside the repository** | **YES** | the nine output paths above; `report_from_disk.py` takes an arbitrary path argument. Note also that `predictability.py` and `learncost.py` read `results/…` by **relative** path, so they are repo-anchored, not external |

---

## 5. Gap in the snapshot itself

The snapshot is a copy of the **previous** session's scratchpad (`25d21d0d-…`) as of 18:26 today. It therefore does **not** contain this session's artifacts:

- `AUDIT-targeting-claim.md`, `RECONCILIATION-targeting-artifacts.md`, `STRUCTURE-net-effect-decomposition.md`, `PROVENANCE-segmentview.md`, `HILLSTROM-feasibility.md`
- `ceiling_obs.py` + `ceiling_obs.json` (the legitimate-ceiling diagnostic)
- `hillstrom.csv` (sha256 `0e5893…aece`)

Those live only in `/private/tmp/claude-501/…/4f08ccbf-…/scratchpad/` and are subject to the same volatility. Flagged for completeness; no action taken.

---

## 6. Summary table

| DIAGNOSTIC | REPRODUCIBLE | WORLD SET | SEALED DATA | LLM | BLOCKER |
|---|---|---|---|---|---|
| `targeting.py` → `targeting.json` | **Yes** | cycle2 dev 20001–20020 | no | no | hardcoded `/private/tmp` output path |
| `hetero.py` | **Yes (rerun)** / **No (verify)** | cycle2 dev 20001–20010 | no | no | no output file was ever written — nothing to diff a rerun against |
| `predict.py` | **Partial** | TRAIN 20021–20050 / TEST 20051–20080 | no | no | no output file; sklearn 1.5.1 used vs 1.9.0 pinned |
| `policy.py` | **Partial** | TRAIN 20021–20050 / TEST 20051–20080 | no | no | no output file; sklearn 1.5.1 used vs 1.9.0 pinned |
| `predictability.py` → `pred.json` | **Yes** | cycle2 dev 20001–20020 + committed cycle3 rep1 | no | no | `/private/tmp` output path |
| `learncost.py` → `learncost.json` | **Yes** | cycle2 dev 20001–20020 + committed cycle3 rep1 | no | no | `/private/tmp` output path |
| `proxy.py` → `proxy.json` | **Yes** | cycle2 dev 20001–20020 | no | no | `/private/tmp` output path |
| `ceiling.py` → `ceiling.json` | **Yes** | cycle2 dev, `limit=N_WORLDS` | no | no | `/private/tmp` output path |
| `ceiling2.py` → `ceiling2.json` | **Yes** | cycle2 dev 20001–20020 | no | no | `/private/tmp` output path |
| `ceiling3.py` → `ceiling3.json` | **Yes** | cycle2 dev 20001–20020 | no | no | `/private/tmp` output path |
| `history_leak.py` → `history_leak.json` | **Yes** | cycle2 dev 20001–20020 | no | no | `/private/tmp` output path |
| `confound.py` → `confound.json` | **Yes** | cycle2 dev 20001–20020 | no | no | `/private/tmp` output path |
| `reanalyse.py` | **Yes** | none (reads committed results) | no | no | none |
| `render_arms.py` | **Yes** | none (reads committed results) | no | no | none |
| `report_from_disk.py` | **Yes** | any dev dir (argv) | no | no | none |
| `cycle1_report.txt` / `cycle2_report.txt` | **Yes** | corpus generation | no | no | none |
| `win.json` | **No** | Cycle-1 sealed holdout | **yes** | **yes** | would require reopening the Cycle-1 seal and LLM credits (exhausted). Committed counterpart `data/holdout_results.json` exists |
| `smoke/arm_smoke/err_smoke/rep_smoke_*.json` | **No** | cycle2 dev, 1–2 worlds | no | **yes** | LLM non-determinism; smoke tests, not evidence |
| `cycle2_*.log`, `cycle3_*.log`, `fixa_c1.log` | **No** | cycle2 dev | no | **yes** | LLM; Gemini prepayment credits exhausted (§4n). Durable evidence is the committed `results/*.json` |
| `baselines20.json` | **Undetermined** | unrecorded | unknown | unknown | no producing script or command survives anywhere in the snapshot |

---

## 7. Recommended classification

**A — safe to reproduce and later commit** *(deterministic, dev-only, no LLM, no seal, all dependencies present; the only obstacle is a hardcoded output path, which is the human's call to change, not mine)*

`targeting.py` + `targeting.json` · `predictability.py` + `pred.json` · `learncost.py` + `learncost.json` · `proxy.py` + `proxy.json` · `ceiling.py` + `ceiling.json` · `ceiling2.py` + `ceiling2.json` · `ceiling3.py` + `ceiling3.json` · `history_leak.py` + `history_leak.json` · `confound.py` + `confound.json` · `reanalyse.py` · `render_arms.py` · `report_from_disk.py` · `cycle1_report.txt` · `cycle2_report.txt`

**B — result is preserved but reproduction needs investigation**

- `hetero.py` — deterministic and rerunnable, but **no output file exists**; the recorded figures (−₹7.88 / ₹74.48 / 3.78%) survive only in the session transcript. A rerun cannot be diffed against a stored artifact.
- `predict.py` — same missing-output problem, **plus** a gradient-boosting result produced under sklearn 1.5.1 while the repo pins 1.9.0. The eta² and Spearman figures are pure scipy/numpy and should carry across; the two GB ρ values may not.
- `policy.py` — same as `predict.py`. The −₹72,983 headline is a gradient-boosting output, so it is the number most exposed to the version gap.
- `baselines20.json` — plausible content, no recoverable provenance. Investigate which command produced it and on which worlds before any use.

**C — do not use in submission**

- `win.json` — LLM-derived, Cycle-1 sealed-holdout run, not reproducible. **Its committed counterpart `data/holdout_results.json` is the artifact to cite instead.**
- `smoke.json`, `arm_smoke.json`, `err_smoke.json`, `rep_smoke_rep1/2.json` — 1–2-world LLM smoke tests. Development detritus.
- `cycle2_*.log`, `cycle3_*.log`, `fixa_c1.log` — LLM run logs, not reproducible (credits exhausted per §4n). The committed `results/cycle2_dev_*.json` and `results/cycle3_*.json` already carry this evidence.
- `cc2/`, `cc3/`, `cleanclone/`, `codexcheck/`, `__pycache__/`, `_ok.npy`, `tests_after_ablation.log` — sandboxes and build detritus, not diagnostics.

---

## 8. What I did not do

I did not modify, patch, relocate, or rerun any diagnostic. I did not alter a world set, estimator, policy, or accounting rule. The only computation performed was regenerating three dev worlds **in memory** to compare hashes against disk, and summing an existing JSON — neither writes anything, neither touches a seal, neither involves the LLM.

The `/private/tmp` output paths are reported as blockers, not repaired. Changing them would alter the artifacts under audit, and that is your call.

*Stopped here.*
