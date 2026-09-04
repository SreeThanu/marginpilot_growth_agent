# Post-hoc analysis

**Everything in this directory was produced *after* Cycle 2 closed. None of it was pre-registered.**

`docs/simulator.md` is the project's lab notebook and the record of what was pre-registered: §4b (decision rule), §4h (Day-9 holdout prediction), §4j (Cycle 2), §4l (Cycle 3). Each of those was written **before** the measurement it governs. The analyses under `analysis/posthoc/` were not. They are exploratory work done after the pre-registered cycles were complete, packaged here so a reader can re-run them and check the numbers — **not** so they can be read as hypotheses that were registered in advance.

There is deliberately **no §4o**. Writing one would place post-hoc work inside a notebook whose sections are, by construction, pre-registrations. The absence is the honest record.

## What is true of every analysis in this directory

- **Conducted after Cycle 2.** Dates run 31 August – 1 September 2026; Cycle 2 closed with `docs/simulator.md` §4n on 31 August.
- **Post-hoc and exploratory.** Not part of any pre-registration, and not to be described as such.
- **Cycle 1 and Cycle 2 were not modified.** No prompt, arm, generator parameter, threshold, estimator, or recorded result was changed. `results/cycle2_dev_*.json` and `results/cycle3_*.json` are untouched.
- **The sealed holdout was not accessed.** Every corpus-reading script goes through `src/eval/devcorpus.open_dev`, which never passes `final_eval` and cannot reach a sealed world. No script references `open_holdout`, `final_eval`, or seeds `29xxx`. `worlds_cycle2/holdout/` has never been read.
- **The LLM was not run.** No script here imports `src.agent`, a reasoner, or any model client.
- **Numerical results carry their own provenance.** Every figure in these reports names its script, its world set, and its information set. Numbers from different scripts or different world sets are never merged.
- **The purpose is transparency and reproducibility**, not retroactive hypothesis registration.

## Layout

| path | contents |
|---|---|
| `targeting/` | heterogeneity and targeting diagnostics + the corrected attribution report |
| `ceiling/` | learning-cost ceilings and the information-conditioned expected-value ceiling |
| `probes/` | five earlier probes. **Their outputs are preserved but were never analysed** — see `probes/README.md` |
| `cycle_reporting/` | scripts that re-render committed Cycle-2 results; they read `results/`, compute no new evidence |
| `provenance/` | source-inspection findings (SegmentView, net-effect decomposition) |
| `reproducibility/` | reproducibility audit, rerun reconciliation, environment provenance |
| `external_data/` | the Hillstrom feasibility audit — a boundary result, **not** external validation |
| `evidence-ledger.md` | the consolidated ledger: what may and may not be claimed |

## Running these scripts

All scripts expect the working directory to be the repository root (they use `sys.path.insert(0, ".")`) and the Cycle-2 corpus at `worlds_cycle2/`, which is gitignored and regenerated with:

```
python -m src.world --out worlds_cycle2
```

Seeds are committed constants (`src/world/__main__.py`), and the corpus reproduces byte-for-byte — see `reproducibility/`.

## Packaging note: output paths were corrected

These scripts originally wrote to an absolute temporary directory that no longer belongs to any machine but the one they ran on. In the committed copies, **the output destination string — and nothing else — was changed** to a repository-relative path. Computation, inputs, world sets, features, thresholds, random seeds and policy logic are untouched. Each change is listed with the original checksum in `reproducibility/README.md`, and every patch was verified by reversing the substitution and diffing against the snapshot original.

Markdown files in this directory still mention the original `/private/tmp` locations. Those are **historical records of where the artifacts were produced**, not runtime dependencies. No committed script contains such a path.
