"""Re-report a dev ablation on a fixed denominator. Reads committed JSON only.

Produces the corrected table in ``docs/simulator.md`` §4k. Cycle 2 first reported
selection accuracy as "chose the best intervention, among the worlds this arm
ran" — a denominator the fixes themselves move, so the arms were not comparable.
Here the denominator is all 20 worlds and the optimal action is a property of the
world, so a fix that changes how often the agent acts cannot change its own scale.

Runs nothing and calls no model: the inputs are ``results/cycle2_dev_*.json``,
already committed. Re-deriving a reported number must not require re-running the
thing that produced it.
"""
import json
from pathlib import Path

ARMS = ["neither", "break_even_only", "history_only", "both"]
LABEL = {"neither": "neither (Cycle 1 prompt)", "break_even_only": "Fix A only (break-even)",
         "history_only": "Fix B only (history)", "both": "both fixes"}

data = {a: json.loads(Path(f"results/cycle2_dev_{a}.json").read_text()) for a in ARMS}

# Optimal action per world, from ground truth: run iff the best available
# intervention has positive population net. Generous to running -- it ignores
# the pilot's own cost of learning, so false-skip is over-counted and false-act
# under-counted relative to a full accounting.
opt = {}
for r in data["neither"]["rows"]:
    if r["decision"] == "error":
        continue
    opt[r["world_id"]] = ("run" if r["true_net_of_best"] > 0 else "skip", r["truth_best"])

# The optimal action is a property of the world, not the arm. Verify.
for a in ARMS:
    for r in data[a]["rows"]:
        if r["decision"] == "error" or r["world_id"] not in opt:
            continue
        assert opt[r["world_id"]][0] == ("run" if r["true_net_of_best"] > 0 else "skip")
        assert opt[r["world_id"]][1] == r["truth_best"]

n_opt_run = sum(1 for v in opt.values() if v[0] == "run")
print(f"worlds: {len(opt)}   optimal=run: {n_opt_run}   optimal=skip: {len(opt)-n_opt_run}\n")

hdr = (f"{'arm':<26}{'ran':>4}{'correct':>9}{'false-act':>11}{'false-skip':>12}"
       f"{'corr-skip':>11}{'cwhd':>6}{'ship':>6}{'net (INR)':>14}")
print(hdr); print("-" * len(hdr))
for a in ARMS:
    d = data[a]
    fa = fs = cs = correct = decision_correct = 0
    for r in d["rows"]:
        o, best = opt[r["world_id"]]
        act = r["decision"]
        if act == "run" and o == "skip": fa += 1
        elif act == "skip" and o == "run": fs += 1
        elif act == "skip" and o == "skip": cs += 1
        if act == o: decision_correct += 1
        # A correct action: ran when running was right, on the right intervention.
        if act == "run" and o == "run" and r["chosen"] == best: correct += 1
    s = d["summary"]
    print(f"{LABEL[a]:<26}{s['ran']:>4}{f'{correct}/20':>9}{f'{fa}/20':>11}{f'{fs}/20':>12}"
          f"{f'{cs}/20':>11}{s['correct_where_history_disagreed']:>6}"
          f"{s['mix'].get('int_shipping',0):>6}{s['net_of_choices_inr']:>14,.0f}")
print("-" * len(hdr))
print("\ndecision-level agreement with the optimal action (run/skip only, ignoring which intervention):")
for a in ARMS:
    dc = sum(1 for r in data[a]["rows"] if r["decision"] == opt[r["world_id"]][0])
    print(f"  {LABEL[a]:<26}{dc}/20")
print("\nold 'accuracy' numerator/denominator, for comparison:")
for a in ARMS:
    print(f"  {LABEL[a]:<26}{data[a]['summary']['selection_accuracy']:>8}"
          f"   <- denominator is the arm's own run count, which the fixes move")

# A ceiling that is a property of the worlds, not of the arm's choices, so it is
# comparable across arms -- unlike net_if_always_best_inr, which summed only over
# the worlds each arm happened to run.
ceiling = sum(max(r["true_net_of_best"], 0.0) for r in data["neither"]["rows"])
print(f"\nfixed ceiling over all 20 worlds (take the best intervention where it pays, else skip):"
      f" Rs.{ceiling:,.0f}")
print("regret against that ceiling:")
for a in ARMS:
    net = data[a]["summary"]["net_of_choices_inr"]
    print(f"  {LABEL[a]:<26} net Rs.{net:>12,.0f}   regret Rs.{ceiling-net:>12,.0f}")

print("\nwhere the loss comes from -- net contributed by each action class:")
hdr2 = f"{'arm':<26}{'false-act net':>16}{'correct-act net':>18}"
print(hdr2); print("-"*len(hdr2))
for a in ARMS:
    fa_net = ca_net = 0.0
    for r in data[a]["rows"]:
        if r["decision"] != "run":
            continue
        o, best = opt[r["world_id"]]
        if o == "skip":
            fa_net += r["true_net_of_choice"]
        else:
            ca_net += r["true_net_of_choice"]
    print(f"{LABEL[a]:<26}{fa_net:>16,.0f}{ca_net:>18,.0f}")
