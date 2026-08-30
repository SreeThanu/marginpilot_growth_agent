"""Measure the evaluation's own noise floor, and compute what it can resolve.

§4l. Cycle 2 compared four arms over 20 worlds and read differences off the
result without asking whether 20 worlds could resolve them. This module asks.

Two things happen here, in order:

1. **Instrument noise**, from replicates of a *single* arm. Deriving it from the
   spread across arms would confound noise with the signal under test; taking it
   from one arm — the control, running the Cycle 1 prompt — makes it manifestly
   noise. The statistic that matters is the standard deviation *across
   replicates of the arm-level count*, not the per-world flip rate: the metric
   being compared is arm-level, so that is the scale its error lives on.

2. **Required replicates K**, for the pre-registered MDE, by the formula stated
   in §4l. Reported whether or not the answer is affordable.

Reads committed JSON and calls no model.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np

#: Pre-registered in §4l, before this file existed. Materiality of 5% of the
#: median dev promotion budget (Rs.369,000 -> Rs.18,450) divided by the pooled
#: cost of one false act (Rs.131,012). Not derived from the observed arm gaps.
MDE_FALSE_ACT_RATE = 18_450.0 / 131_012.0

#: The materiality bar itself, in rupees per merchant. 5% of the median dev
#: promotion budget of Rs.369,000. Realized-net contrasts are held to this
#: directly rather than converted into a count.
MATERIALITY_PER_MERCHANT_INR = 18_450.0

#: Two-sided alpha and target power, fixed in §4l.
Z_ALPHA_TWO_SIDED = 1.959964
Z_POWER = 0.841621


def _optimal_actions(rows: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Run where the best intervention pays, skip otherwise. A world property."""
    return {
        r["world_id"]: ("run" if r["true_net_of_best"] > 0 else "skip")
        for r in rows
        if r["decision"] != "error"
    }


def _metrics(rows: Sequence[dict[str, Any]], optimal: dict[str, str]) -> dict[str, float]:
    false_act = false_skip = ran = shipping = correct = cwhd = 0
    net = 0.0
    for r in rows:
        act = r["decision"]
        if act == "error":
            continue  # excluded from every denominator; never substituted
        if act == "run":
            ran += 1
            net += r["true_net_of_choice"]
            if r["chosen"] == "int_shipping":
                shipping += 1
            if optimal[r["world_id"]] == "skip":
                false_act += 1
            else:
                # A correct action: ran where running was right, on the best
                # intervention. The strict count of §4k.
                if r["chosen"] == r["truth_best"]:
                    correct += 1
            if r["chosen"] == r["truth_best"] and r["history_best"] != r["truth_best"]:
                cwhd += 1
        elif optimal[r["world_id"]] == "run":
            false_skip += 1
    return {
        "false_act": float(false_act),
        "false_skip": float(false_skip),
        "run_count": float(ran),
        "correct_action": float(correct),
        "cwhd": float(cwhd),
        "int_shipping": float(shipping),
        "realized_net_inr": net,
    }


def sd_interval(sd: float, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Confidence interval for a standard deviation estimated from n replicates.

    Chi-square, and reported because it is easy to forget that an SD from a
    handful of replicates is itself a noisy estimate. Required K scales with the
    square of the SD, so the interval on K is wider still — which is exactly the
    kind of uncertainty this cycle exists to stop glossing over.
    """
    from scipy import stats

    if n < 2 or sd <= 0:
        return (sd, sd)
    df = n - 1
    lo = sd * math.sqrt(df / stats.chi2.ppf(1 - (1 - conf) / 2, df))
    hi = sd * math.sqrt(df / stats.chi2.ppf((1 - conf) / 2, df))
    return (lo, hi)


def structural_sd_bound(n_eligible: int) -> float:
    """The largest SD a count over ``n_eligible`` worlds can have, for any arm.

    ``false_act`` counts, out of the worlds whose optimal action is *skip*, how
    many the arm ran. Within one replicate the worlds are separate calls with no
    shared state, so the count is a sum of independent Bernoulli indicators and
    its variance is ``sum p_w(1-p_w) <= n/4``, maximised when every per-world run
    probability sits at one half.

    This matters because it is **distribution-free and arm-independent**: it
    bounds a treatment arm's variance without that arm having been replicated,
    which the control arm's *measured* variance cannot do. It is also tighter
    than the chi-square upper bound on the control's SD, which can exceed a value
    the statistic is structurally incapable of reaching.
    """
    return math.sqrt(n_eligible * 0.25)


def required_replicates(sd_count: float, mde_count: float) -> float:
    """K per arm for a two-sided paired contrast at the pre-registered alpha/power.

    Both arms measured as a mean over K replicates on the same worlds, so the
    world-to-world component cancels and Var(difference) = 2*sd^2/K.
    """
    if mde_count <= 0:
        return math.inf
    return 2.0 * (sd_count**2) * ((Z_ALPHA_TWO_SIDED + Z_POWER) ** 2) / (mde_count**2)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.power", description=__doc__)
    parser.add_argument("--stem", default="results/cycle3_noise_neither",
                        help="replicate files are <stem>_rep<N>.json")
    parser.add_argument(
        "--seconds-per-world", type=float, default=38.3,
        help="measured wall clock per world-run. Taken from the replication that "
             "produced these files (mean of 767s per 20-world pass), not from a "
             "calls-per-minute guess: the rate limiter, model latency and retries "
             "all land in this number and a token-based estimate understates it.",
    )
    args = parser.parse_args()

    paths = sorted(Path().glob(f"{args.stem}_rep*.json"),
                   key=lambda p: int(p.stem.split("rep")[-1]))
    if len(paths) < 2:
        print(f"need at least 2 replicates matching {args.stem}_rep*.json; found {len(paths)}")
        return 1

    reps = [json.loads(p.read_text()) for p in paths]
    optimal = _optimal_actions(reps[0]["rows"])
    n_worlds = len(reps[0]["rows"])
    per_rep = [_metrics(r["rows"], optimal) for r in reps]

    print("=" * 78)
    print(f"INSTRUMENT NOISE — {len(reps)} replicates of one arm, {n_worlds} worlds, "
          "identical code and prompts")
    print("=" * 78)

    # Per-world decision stability. A world that flips is one the instrument
    # cannot place; a world that never flips contributes no noise at all.
    flips = {}
    for wid in optimal:
        runs = sum(1 for r in reps if next(x for x in r["rows"] if x["world_id"] == wid)["decision"] == "run")
        flips[wid] = runs / len(reps)
    unstable = [w for w, p in flips.items() if 0 < p < 1]
    print(f"\nper-world run-probability across replicates:")
    for wid in sorted(flips):
        bar = "#" * round(flips[wid] * 10)
        tag = "  <- unstable" if 0 < flips[wid] < 1 else ""
        print(f"  {wid}  P(run)={flips[wid]:.2f} {bar:<10}{tag}")
    print(f"\nworlds whose decision is not stable: {len(unstable)}/{n_worlds} "
          f"({len(unstable)/n_worlds:.0%})")
    expected_flip = float(np.mean([2 * p * (1 - p) for p in flips.values()]))
    print(f"expected per-world disagreement between two runs: {expected_flip:.1%}")

    # Each metric gets the MDE its own units imply, from the same pre-registered
    # materiality bar. Counts inherit the 14.1%-of-worlds threshold; realized net
    # inherits Rs.18,450 per merchant across the world set.
    mde_count = MDE_FALSE_ACT_RATE * n_worlds
    mde = {
        "false_act": mde_count,
        "false_skip": mde_count,
        "run_count": mde_count,
        "correct_action": mde_count,
        "cwhd": mde_count,
        "int_shipping": mde_count,
        "realized_net_inr": MATERIALITY_PER_MERCHANT_INR * n_worlds,
    }
    print(f"\n{'metric':<20}{'mean':>10}{'sd':>10}{'min':>10}{'max':>10}{'MDE':>10}{'K needed':>10}")
    print("-" * 80)
    results = {}
    for key in ("false_act", "false_skip", "run_count", "correct_action", "cwhd",
                "int_shipping", "realized_net_inr"):
        vals = np.array([m[key] for m in per_rep], dtype=float)
        sd = float(vals.std(ddof=1))
        k = required_replicates(sd, mde[key])
        results[key] = {"mean": float(vals.mean()), "sd": sd, "required_k": k,
                        "min": float(vals.min()), "max": float(vals.max())}
        fmt = ",.0f" if key == "realized_net_inr" else ".2f"
        kt = "1" if k <= 1 else str(math.ceil(k))
        _, sd_hi = sd_interval(sd, len(per_rep))
        k_hi = required_replicates(sd_hi, mde[key])
        results[key]["required_k_conservative"] = k_hi
        kt_hi = "1" if k_hi <= 1 else str(math.ceil(k_hi))
        print(f"{key:<20}{vals.mean():>10{fmt}}{sd:>10{fmt}}"
              f"{vals.min():>10{fmt}}{vals.max():>10{fmt}}{mde[key]:>10{fmt}}"
              f"{kt:>10}{kt_hi:>14}")

    sd = results["false_act"]["sd"]
    k = results["false_act"]["required_k"]
    k_int = max(1, math.ceil(k)) if math.isfinite(k) else None
    # The design must satisfy every metric it reports, not just the primary one.
    k_all = max(
        (max(1, math.ceil(v["required_k"])) for v in results.values() if math.isfinite(v["required_k"])),
        default=1,
    )

    print("\n" + "=" * 78)
    print("REQUIRED DESIGN")
    print("=" * 78)
    print(f"  pre-registered MDE      : {MDE_FALSE_ACT_RATE:.1%} of worlds "
          f"= {mde_count:.2f} of {n_worlds}")
    print(f"  measured SD (false-act) : {sd:.3f} worlds per replicate")
    print(f"  formula                 : K >= 2*sd^2*(z_a+z_b)^2 / MDE^2")
    print(f"                          = 2*{sd:.3f}^2*{(Z_ALPHA_TWO_SIDED+Z_POWER):.4f}^2"
          f" / {mde_count:.3f}^2")
    if k_int is None:
        print("  required K              : unbounded (zero MDE)")
        return 0
    print(f"  required K per arm      : {k_int}   (primary metric: false-act)")
    k_all_cons = max(
        (max(1, math.ceil(v["required_k_conservative"])) for v in results.values()
         if math.isfinite(v["required_k_conservative"])),
        default=1,
    )
    sd_lo, sd_hi = sd_interval(sd, len(per_rep))
    print(f"  SD 95% CI ({len(per_rep)} reps): [{sd_lo:.3f}, {sd_hi:.3f}] "
          f"-- K scales with SD^2, so this interval matters more than it looks")
    print(f"  required K for ALL metrics: {k_all}   "
          f"(driven by {max(results, key=lambda m: results[m]['required_k'])})")
    print(f"  conservative K (SD upper): {k_all_cons}")
    total = k_all * 4 * n_worlds
    hours = total * args.seconds_per_world / 3600.0
    print(f"  total world-runs (4 arms) : {total:,}")
    print(f"  measured throughput       : {args.seconds_per_world:.1f}s per world-run")
    print(f"  est. wall clock, full 2x2 : {hours:.1f} hours")

    # What is already on disk counts against the requirement.
    have = {"neither": len(paths)}
    print("\n  already measured:")
    for arm in ("neither", "break_even_only", "history_only", "both"):
        n = have.get(arm, 0) + (1 if Path(f"results/cycle2_dev_{arm}.json").exists() else 0)
        print(f"    {arm:<18}{n} replicate(s)")
    remaining = sum(
        max(0, k_all - (have.get(a, 0) + (1 if Path(f"results/cycle2_dev_{a}.json").exists() else 0)))
        for a in ("neither", "break_even_only", "history_only", "both")
    )
    print(f"  replicate-passes still needed: {remaining}  "
          f"({remaining * n_worlds:,} world-runs, "
          f"{remaining * n_worlds * args.seconds_per_world / 3600.0:.1f} hours)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
