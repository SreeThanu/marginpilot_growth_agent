# Reproducibility record

**Post-hoc packaging.** See `../README.md`.

Companion documents: `environment.md` (which interpreter produced what), `repro-audit.md` (the full artifact audit), `rerun-reconciliation.md` (the one-shot rerun of the three stdout-only scripts).

---

## 1. The corpus reproduces from committed seeds

Seeds are committed constants (`src/world/__main__.py:37-38`):

```python
DEV_SEEDS     = range(20_001, 20_081)
HOLDOUT_SEEDS = range(29_001, 29_021)
```

Three dev worlds were regenerated in memory and compared to the corpus on disk. `GENERATOR_VERSION = "4.0.0"` on both sides:

| world | disk schema | sha256(canonical JSON), disk vs fresh | match |
|---|---|---|---|
| `world_20001` | 4.0.0 | `5379490f76738983` / `5379490f76738983` | **yes** |
| `world_20051` | 4.0.0 | `99f539d377bb820e` / `99f539d377bb820e` | **yes** |
| `world_20080` | 4.0.0 | `fe745dc6c9e996bf` / `fe745dc6c9e996bf` | **yes** |

3 of 80 sampled (first, middle, last). Regeneration command: `python -m src.world --out worlds_cycle2`.

## 2. Scripts reproduced exactly

`hetero.py`, `predict.py` and `policy.py` were each run **once, unmodified**, on 1 September 2026 with the working directory at the repository root. All three exited 0. **Every reported figure reproduced to the last printed digit** — including the two scikit-learn gradient-boosting outputs. Console output: `../targeting/stdout/rerun-2026-09-01.log`. Full comparison: `rerun-reconciliation.md`.

Caveat, stated in the open: this was the environment that originally produced them, not the `requirements.txt` pins. See `environment.md`.

## 3. Diagnostic categories

| category | meaning | members |
|---|---|---|
| **A — safe to reproduce and cite** | deterministic, dev-only, no LLM, no seal, all dependencies present | `targeting.py`+`targeting.json`, `predictability.py`+`pred.json`, `learncost.py`+`learncost.json`, `proxy.py`+`proxy.json`, `ceiling.py`/`ceiling2.py`/`ceiling3.py`+outputs, `history_leak.py`+`history_leak.json`, `confound.py`+`confound.json`, `ceiling_obs.py`+`ceiling_obs.json`, `reanalyse.py`, `render_arms.py`, `report_from_disk.py` |
| **B — result preserved, reproduction needs care** | `hetero.py`, `predict.py`, `policy.py` — no machine-readable output was ever written; figures reproduced but exist on disk only as captured stdout. `predict.py`/`policy.py` additionally version-sensitive |
| **C — do not use in the submission** | `win.json` (LLM run on the Cycle-1 sealed holdout; cite the committed `data/holdout_results.json` instead) · `smoke.json`, `arm_smoke.json`, `err_smoke.json`, `rep_smoke_rep{1,2}.json` (1–2-world LLM smoke tests) · `cycle2_*.log`, `cycle3_*.log`, `fixa_c1.log` (LLM run logs; the committed `results/*.json` carry this evidence) · `baselines20.json` (no recoverable provenance) · `cc2/`, `cc3/`, `cleanclone/`, `codexcheck/` (sandboxes). All remain in the durable snapshot; none is committed |

A category-A classification means the artifact is safe to *reproduce and cite*. For the five probes in `../probes/`, it does **not** mean the contents have been read — they have not. See `../probes/README.md`.

## 4. Packaging-only path corrections

Committed scripts must not depend on a machine-specific temporary directory. **In each script below, only a path string changed.** Computation, inputs, world sets, features, thresholds, random seeds and policy logic are untouched.

Every patch was verified by **reversing the substitution and diffing against the snapshot original** — all reversals produced a byte-identical file.

| script | original sha256 | what changed |
|---|---|---|
| `targeting/targeting.py` | `063a5adb789220a895feb8eacc47fe13f98a0ea51f378b2c636bde50e3a68364` | output → `analysis/posthoc/targeting/outputs/targeting.json` |
| `targeting/predict.py` | `72740c0865e7284f523744866fae7abd7e4ad93078b9e1bf0762ff5eb92cd0f4` | `_ok.npy` sentinel destination → `analysis/posthoc/targeting/outputs/_ok.npy` |
| `ceiling/ceiling.py` | `579a2acea08210766ffdb06896841f197376ddd74b97ef0ac55147f49d792d07` | output → `analysis/posthoc/ceiling/outputs/ceiling.json` |
| `ceiling/ceiling2.py` | `233ae2eda91642a1deb304ed8795273953c3eb79817a570a90bf6b023c6d4be9` | output → `…/ceiling2.json` |
| `ceiling/ceiling3.py` | `5b36e6eebe250f7449d699312f7eb396f365ec2dab79975946ea15ebc767a42a` | output → `…/ceiling3.json` |
| `probes/confound.py` | `a9739ba4050c6b7d04d9f0d771c93849051ee5d4097902ae72e3b6fa72aa208f` | output → `analysis/posthoc/probes/outputs/confound.json` |
| `probes/history_leak.py` | `0db2979cb0b4295ce068913918e5787c4189001c53276217a866624146c6a14f` | output → `…/history_leak.json` |
| `probes/learncost.py` | `2ded90f660fe4932d6f8de66db4b359aaab21390058bf3da6c8ddee642cc7b69` | output → `…/learncost.json` |
| `probes/predictability.py` | `10f93c12e967a21a8c76a92773282b8303e46cea33c0dfde26555b0fc72ccb21` | output → `…/pred.json` |
| `probes/proxy.py` | `f19a5bafdfc60d848f9928d537cbca65d145a191b696d60beccc8ceaeabe995d` | output → `…/proxy.json`, **and** its `learncost.json` **input** → the committed copy at `…/outputs/learncost.json` |
| `ceiling/ceiling_obs.py` | `760cbd8581516a71532e3d6db6f428cdb371bf62ba3b1450cb62b38db34aba0b` | output → `analysis/posthoc/ceiling/outputs/ceiling_obs.json`; corpus root → relative `worlds_cycle2/dev`; `sys.path.insert` → `"."` (matching every other diagnostic) |

**The one input-path change** is `proxy.py`'s. It is called out separately because it is an input rather than an output: `proxy.py` reads `learncost.json`, and the committed copy is **byte-identical** to the one it originally read (sha256 `9f237b2c567b847ce299d6d85d4a5e2f95bc212ef6c4494c60da01a21d9d8fe7` on both). Identical bytes in, identical computation out.

**Unmodified, byte-identical to the snapshot originals:** `hetero.py`, `policy.py`, `reanalyse.py`, `render_arms.py`, `report_from_disk.py`.

## 5. Volatile paths

No committed **script** contains a `/private/tmp` path. Some committed **markdown** does — those are historical records of where artifacts were produced and why they were fragile, which is the subject matter of `repro-audit.md`. They are records, not runtime dependencies.

## 6. Provenance corrections carried forward

| figure | correct source | world set |
|---|---|---|
| ₹10.20 (per-segment estimation error), ₹6.27 (between-segment SD) | `targeting.py` / `targeting.json` — **not** `hetero.py` | 20001–20020 |
| −₹72,983 (frozen predictor, top 5%) | `policy.py` — **not** `predict.py` | TEST 20051–20080 |
| η² = 0.702% | `segment_id` alone, **not** the six `CustomerView` fields | TEST 20051–20080 |
| +₹3,595,677 | **hindsight** selection on realized outcomes — **not** a targeting ceiling | TEST 20051–20080 |

## 7. Remaining limitations

1. Only 3 of 80 worlds were hash-checked.
2. The rerun used the original environment, not the pinned versions (`environment.md`).
3. `hetero.py`, `predict.py`, `policy.py` still have no machine-readable output; captured stdout is the durable record, and no JSON has been fabricated for them.
4. The five probe outputs in `../probes/outputs/` have never been read.
5. `worlds_cycle2/` is gitignored; a reviewer must regenerate it before running anything here.
