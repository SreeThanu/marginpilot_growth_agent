# Environment provenance

**Two environments are involved, and they are not the same one.** This file records both, so no reader has to guess which produced a given number.

## Historical diagnostic environment

Every post-hoc diagnostic under `analysis/posthoc/` was executed with `/opt/anaconda3/bin/python` — the interpreter `make` resolves to via `PYTHON ?= python` — carrying:

```
numpy         1.26.4
scipy         1.13.1
scikit-learn  1.5.1
```

## Current `requirements.txt` pins

```
numpy         2.3.5
scipy         1.17.1
scikit-learn  1.9.0
```

## The precise statement

> **The historical diagnostics reproduced exactly in the environment in which they were originally executed. They were not independently revalidated under the newer `requirements.txt` pins.**

Nothing stronger than that may be claimed.

## What is and is not exposed to the difference

| script | version-sensitive? | why |
|---|---|---|
| `hetero.py` | **no** | pure numpy arithmetic, no RNG, no scikit-learn |
| `targeting.py`, `ceiling*.py`, `confound.py`, `history_leak.py`, `learncost.py`, `predictability.py`, `proxy.py` | **no** | numpy arithmetic; no model fitting. `assign()` is blake2b-keyed and interpreter-independent |
| `ceiling_obs.py` | **partly** | uses `scipy.stats.qmc.Sobol` and `scipy.stats.norm.ppf`; no scikit-learn |
| `predict.py` | **yes** | `GradientBoostingRegressor(random_state=0)` — seeded, but gradient-boosting output can shift across scikit-learn versions. `Ridge` is closed-form and `scipy.stats.spearmanr` is stable |
| `policy.py` | **yes** | same gradient-boosting model; the **−₹72,983** headline is one of its outputs and is therefore the figure most exposed |

## Why `requirements.txt` was not changed

It would have been trivial to edit the pins down to the versions that produced the results and thereby make the diagnostics look reproducible under the stated environment. That would be backwards: the pins record the environment the project intends a reviewer to install, and the diagnostics record what actually ran. **The gap is real and is reported rather than closed.** `requirements.txt` and `requirements.lock.txt` are untouched by this packaging work.

## Reproducing the corpus

Diagnostics need `worlds_cycle2/`, which is gitignored. Seeds are committed constants in `src/world/__main__.py`:

```
DEV_SEEDS     = range(20_001, 20_081)
HOLDOUT_SEEDS = range(29_001, 29_021)
```

Regenerate with `python -m src.world --out worlds_cycle2`. Worlds 20001, 20051 and 20080 were verified to regenerate **byte-for-byte identical** to the corpus that produced these results (`GENERATOR_VERSION 4.0.0`). Regenerating writes the holdout worlds and seals them; nothing here reads them.
