"""Was the profitable choice inferable at decision time, or only from the oracle?

Dev worlds only. Reads ground truth to SCORE the answer, never to inform it.
"""
import json, sys
sys.path.insert(0, ".")
from src.eval.devcorpus import open_dev
from src.eval.contracts import merchant_view
from src.eval.harness import _true_population_net
from src.world import vocabulary as vocab

SHIP = vocab.SIGNAL_SHIPPING_THRESHOLD

rows = json.load(open("results/cycle3_noise_neither_rep1.json"))["rows"]
runopt = {r["world_id"] for r in rows if r["true_net_of_best"] > 0}

print(f"{'world':<13}{'truth_best':<14}{'cheapest seen':<14}{'cheap==best':<12}"
      f"{'ship signal':<12}{'clearance sig':<14}{'signal points to':<16}")
print("-" * 100)
out = []
for world, truth in open_dev("worlds_cycle2", limit=20):
    if world.world_id not in runopt:
        del world, truth; continue
    view = merchant_view(world)
    nets = {i.intervention_id: _true_population_net(world, truth, i) for i in world.interventions}
    best = max(nets, key=nets.get)
    costs = {i.intervention_id: i.incentive_cost_inr(view.observed_aov_inr) for i in world.interventions}
    cheapest = min(costs, key=costs.get)

    ship_sig = any(SHIP in t for t in view.semantic.customer_service_themes)
    clear_sig = any(vocab.SIGNAL_CLEARS_WHEN_DISCOUNTED in n
                    for n in view.semantic.inventory_notes)
    pointed = []
    if ship_sig: pointed.append("int_shipping")
    if clear_sig: pointed.append("int_flat")
    ptxt = "+".join(pointed) if pointed else "(none)"
    out.append(dict(world=world.world_id, best=best, cheapest=cheapest,
                    match=best == cheapest, ship=ship_sig, clear=clear_sig,
                    pointed=pointed, nets=nets, costs=costs))
    print(f"{world.world_id:<13}{best:<14}{cheapest:<14}{str(best==cheapest):<12}"
          f"{str(ship_sig):<12}{str(clear_sig):<14}{ptxt:<16}")
    del world, truth

print()
n = len(out)
print(f"run-optimal worlds examined: {n}")
print(f"  truth_best == cheapest-by-cost (margin-inferable): "
      f"{sum(r['match'] for r in out)}/{n}")
print(f"  a response signal was present at all            : "
      f"{sum(1 for r in out if r['pointed'])}/{n}")
print(f"  signal present AND pointed at truth_best        : "
      f"{sum(1 for r in out if r['best'] in r['pointed'])}/{n}")
print(f"  signal present AND pointed AWAY from truth_best : "
      f"{sum(1 for r in out if r['pointed'] and r['best'] not in r['pointed'])}/{n}")
print(f"  truth_best is pct or bundle (NO signal exists)  : "
      f"{sum(1 for r in out if r['best'] in ('int_pct','int_bundle'))}/{n}")
json.dump(out, open("analysis/posthoc/probes/outputs/pred.json","w"), indent=1)
