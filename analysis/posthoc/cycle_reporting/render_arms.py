"""Render the Cycle 2 2x2 ablation as one table."""
import json, sys
from pathlib import Path

ARMS = ["neither", "break_even_only", "history_only", "both"]
LABEL = {
    "neither": "neither (Cycle 1 prompt)",
    "break_even_only": "Fix A only (break-even)",
    "history_only": "Fix B only (history)",
    "both": "both fixes",
}
rows = []
for arm in ARMS:
    p = Path(f"results/cycle2_dev_{arm}.json")
    if not p.exists():
        continue
    d = json.loads(p.read_text())
    s = d["summary"]
    ran = s["ran"]
    mix = s["mix"]
    rows.append((arm, s, ran, mix, d["rows"]))

hdr = f"{'arm':<26}{'ran':>5}{'skip':>6}{'correct':>9}{'hist-match':>12}{'beyond-hist':>13}{'shipping':>10}{'bundle':>8}"
print(hdr); print("-" * len(hdr))
for arm, s, ran, mix, _ in rows:
    print(f"{LABEL[arm]:<26}{ran:>5}{s['skipped']:>6}{s['selection_accuracy']:>9}"
          f"{s['history_match_rate']:>12}{s['correct_where_history_disagreed']:>13}"
          f"{mix.get('int_shipping',0):>10}{mix.get('int_bundle',0):>8}")
print("-" * len(hdr))
print(f"{'':<26}{'':>5}{'':>6}{'':>9}{'':>12}{'':>13}")
print("\nRealized true net contribution of the choices made (INR):")
for arm, s, ran, mix, _ in rows:
    print(f"  {LABEL[arm]:<26}{s['net_of_choices_inr']:>14,.0f}"
          f"   (always-best ceiling on the same worlds: {s['net_if_always_best_inr']:,.0f})")
