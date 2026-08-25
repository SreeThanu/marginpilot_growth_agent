"""``python -m src.world`` — generate the world corpus and print a sanity report.

Generates 80 dev worlds and 20 holdout worlds, writing each to disk as it goes
and holding at most one in memory.

The sanity report covers **dev worlds only**. Its purpose is to let a human
eyeball whether the generated economies look like plausible retail or like noise,
before anything is built on top of them. It reports structural parameters and the
*designed* treatment effect implied by the response model — never ``Y(0)``/
``Y(1)``, which stay sealed for ``src/eval/`` (CLAUDE.md invariant 8).

Holdout worlds are written and then left alone. Nothing in this module reads,
summarises or prints a holdout world (invariant 4).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from src.eval.guard import DEV_SPLIT, HOLDOUT_SPLIT
from src.world.generator import (
    GENERATOR_VERSION,
    generate,
    intervention_affinity,
    treated_conversion_probability,
)
from src.world.persistence import write_world
from src.world.schema import World

#: Dev and holdout seeds are far apart so a dev world can never be regenerated
#: as a holdout world by an off-by-one, and a misfiled file is obvious by name.
DEV_SEEDS = range(1, 81)
HOLDOUT_SEEDS = range(9001, 9021)


def _world_summary(world: World) -> dict[str, float]:
    """Per-world scalars for the report. Observable structure only, no outcomes."""
    p0 = np.array([c.baseline_purchase_prob for c in world.customers])
    aov = np.array([c.expected_order_value_inr for c in world.customers])
    elasticity = np.array([c.price_elasticity for c in world.customers])
    margins = np.array([p.contribution_margin for p in world.products])

    summary = {
        "mean_conversion": float(p0.mean()),
        "mean_aov_inr": float(aov.mean()),
        "mean_margin": float(margins.mean()),
        "mean_elasticity": float(elasticity.mean()),
        "cannibalization_rate": world.params.cannibalization_rate,
        "seasonality_index": world.params.seasonality_index,
        "budget_inr": world.params.promotion_budget_inr,
        "n_customers": float(world.params.n_customers),
        "n_products": float(len(world.products)),
        "n_segments": float(len(world.segments)),
    }

    # Designed effect: the lift the response model implies for each intervention,
    # in conversion percentage points, averaged over the customer base. Computed
    # with the same function the outcome draw uses, so the report cannot describe
    # a different world than the one on disk.
    for intervention in world.interventions:
        affinity = intervention_affinity(world.params, intervention)
        p1 = np.array(
            [
                treated_conversion_probability(
                    c, intervention, c.expected_order_value_inr, affinity
                )
                for c in world.customers
            ]
        )
        delta = p1 - p0
        summary[f"effect_pp__{intervention.intervention_id}"] = float(delta.mean() * 100.0)
        # Within-world spread of the individual effect. If this is near zero the
        # worlds are homogeneous and every heterogeneity claim downstream is void.
        summary[f"effect_sd_pp__{intervention.intervention_id}"] = float(delta.std() * 100.0)

    return summary


def _percentile_row(label: str, values: list[float], unit: str = "") -> str:
    arr = np.array(values, dtype=float)
    p5, p25, p50, p75, p95 = np.percentile(arr, [5, 25, 50, 75, 95])
    return (
        f"  {label:<34}{p5:>10.3f}{p25:>10.3f}{p50:>10.3f}{p75:>10.3f}{p95:>10.3f}"
        f"  {unit}"
    )


def _print_report(summaries: list[dict[str, float]], intervention_ids: list[str]) -> None:
    print()
    print("=" * 96)
    print(f"SANITY REPORT — {len(summaries)} dev worlds (holdout worlds not inspected)")
    print("=" * 96)
    print(f"  {'':<34}{'p5':>10}{'p25':>10}{'p50':>10}{'p75':>10}{'p95':>10}")
    print("-" * 96)

    def column(key: str) -> list[float]:
        return [s[key] for s in summaries]

    print("  Structure")
    print(_percentile_row("customers per world", column("n_customers")))
    print(_percentile_row("products per world", column("n_products")))
    print(_percentile_row("segments per world", column("n_segments")))
    print()
    print("  Demand and basket")
    print(_percentile_row("baseline conversion", column("mean_conversion"), "(fraction)"))
    print(_percentile_row("average order value", column("mean_aov_inr"), "(INR)"))
    print(_percentile_row("contribution margin", column("mean_margin"), "(fraction)"))
    print(_percentile_row("price elasticity", column("mean_elasticity"), ""))
    print(_percentile_row("seasonality index", column("seasonality_index"), ""))
    print(_percentile_row("cannibalization rate", column("cannibalization_rate"), "(fraction)"))
    print(_percentile_row("promotion budget", column("budget_inr"), "(INR)"))
    print()
    print("  Designed treatment effect — mean lift across the customer base")
    for intervention_id in intervention_ids:
        print(
            _percentile_row(
                intervention_id.replace("int_", ""),
                column(f"effect_pp__{intervention_id}"),
                "(conversion pp)",
            )
        )
    print()
    print("  Within-world spread of that effect — heterogeneity across customers")
    for intervention_id in intervention_ids:
        print(
            _percentile_row(
                intervention_id.replace("int_", ""),
                column(f"effect_sd_pp__{intervention_id}"),
                "(conversion pp, sd)",
            )
        )
    print("-" * 96)
    print(
        "  Read this as: does it look like retail? Conversion in single-to-low-double\n"
        "  digit percent, AOV a few hundred to a few thousand rupees, margins 20-40%,\n"
        "  elasticity around -1 to -3.5 (Tellis 1988: -1.76; Bijmolt et al. 2005: -2.62),\n"
        "  and a within-world effect spread comparable to the effect itself. Ranges and\n"
        "  their sources are in docs/simulator.md."
    )
    print("=" * 96)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.world", description=__doc__)
    parser.add_argument(
        "--out", default="worlds", type=Path, help="root directory for generated worlds"
    )
    parser.add_argument(
        "--no-report", action="store_true", help="generate without printing the sanity report"
    )
    args = parser.parse_args()

    root: Path = args.out
    print(f"MarginPilot world generator {GENERATOR_VERSION}")
    print(f"  dev     : {len(DEV_SEEDS)} worlds -> {root / DEV_SPLIT}")
    print(f"  holdout : {len(HOLDOUT_SEEDS)} worlds -> {root / HOLDOUT_SPLIT} (sealed on write)")
    print()

    summaries: list[dict[str, float]] = []
    intervention_ids: list[str] = []

    for count, seed in enumerate(DEV_SEEDS, start=1):
        world, truth = generate(seed, split=DEV_SPLIT)
        write_world(world, truth, root / DEV_SPLIT)
        summaries.append(_world_summary(world))
        if not intervention_ids:
            intervention_ids = [i.intervention_id for i in world.interventions]
        print(f"\r  dev      {count:>3}/{len(DEV_SEEDS)}", end="", flush=True)
        del world, truth
    print()

    for count, seed in enumerate(HOLDOUT_SEEDS, start=1):
        world, truth = generate(seed, split=HOLDOUT_SPLIT)
        write_world(world, truth, root / HOLDOUT_SPLIT)
        # Nothing is summarised, printed or retained. The seal starts here.
        print(f"\r  holdout  {count:>3}/{len(HOLDOUT_SEEDS)}", end="", flush=True)
        del world, truth
    print()
    print(f"\n  holdout worlds written and sealed — not inspected (CLAUDE.md invariant 4)")

    if not args.no_report:
        _print_report(summaries, intervention_ids)


if __name__ == "__main__":
    main()
