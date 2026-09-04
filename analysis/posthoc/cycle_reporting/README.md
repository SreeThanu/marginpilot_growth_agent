# Cycle-2 re-reporting scripts

**Post-hoc. Not pre-registered.** See `../README.md`.

Three scripts that **re-render already-committed results**. They read files under `results/` and `worlds/`, compute no new evidence, read no ground truth, touch no sealed data, and run no LLM. All three are byte-identical to the artifact-snapshot originals — no path correction was needed.

| script | what it does | inputs |
|---|---|---|
| `reanalyse.py` | Re-reports Cycle 2's 2×2 ablation on a fixed denominator — the correction recorded in `docs/simulator.md` §4k. *"No new runs."* | `results/cycle2_dev_{neither,break_even_only,history_only,both}.json` (committed) |
| `render_arms.py` | Renders the same 2×2 ablation as one table | the same four committed files |
| `report_from_disk.py` | Prints the world sanity report from a corpus already on disk, without regenerating it. Dev worlds only | a world directory passed as `argv[1]` |

`src/eval/devreport.py` already re-derives §4k's corrected table from the same committed files without calling a model; these scripts are the scratch versions that preceded it, preserved so the path from raw results to the reported table is visible.

Run from the repository root.
