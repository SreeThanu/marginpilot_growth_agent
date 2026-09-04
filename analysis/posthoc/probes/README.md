# Earlier probes — preserved, not analysed

**Post-hoc. Not pre-registered.** See `../README.md`.

Five diagnostics run 31 August – 1 September 2026, preserved here so their scripts and outputs survive and can be re-run. Each reads `worlds_cycle2` dev worlds through `open_dev`, reads `Y(0)`/`Y(1)` to score only, touches no sealed data, and runs no LLM.

| script | question (from its own docstring) | world set | output |
|---|---|---|---|
| `predictability.py` | Was the profitable choice inferable at decision time, or only from the oracle? | dev 20001–20020 + committed `results/cycle3_noise_neither_rep1.json` | `outputs/pred.json` |
| `learncost.py` | Could ONE bounded experiment pay for itself, per world? | dev 20001–20020 + the same committed results file | `outputs/learncost.json` |
| `proxy.py` | Is opportunity SIZE inferable from decision-time observables? | dev 20001–20020 | `outputs/proxy.json` |
| `history_leak.py` | Is intervention response recoverable from realistically-available history? | dev 20001–20020 | `outputs/history_leak.json` |
| `confound.py` | Realistic confounding — each past campaign targeted differently | dev 20001–20020 | `outputs/confound.json` |

## The caveat that governs this directory

> **The contents of these output files were never read.**

During the audit that produced `../evidence-ledger.md`, only the docstrings of these scripts were inspected — enough to record what each asked, not what each found. **No number from `pred.json`, `learncost.json`, `proxy.json`, `history_leak.json` or `confound.json` appears in the evidence ledger, and none may enter the submission, a README, a slide, or a demo without first being read and given the same provenance treatment as everything else.**

They are preserved because a diagnostic that was run and then discarded is worse than one that was run and kept. They are not evidence until someone reads them.

## Not preserved here

`baselines20.json` from the artifact snapshot is **deliberately excluded**. It has no recoverable provenance: no script or command anywhere in the snapshot produces it, so neither its world set nor its method can be established. It remains in the durable snapshot at `margin_pilot_artifact_snapshot_2026-09-01/` and must not be cited.

## Packaging note

`proxy.py` reads `learncost.json`. Both its output path **and** that input path originally pointed at a volatile temporary directory; both were repointed at the committed copies here. The input file is byte-identical to the snapshot original (sha256 `9f237b2c…`), so the computation is unchanged. Details and checksums in `../reproducibility/README.md`.
