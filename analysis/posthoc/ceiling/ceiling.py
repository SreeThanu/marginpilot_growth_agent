"""Economic ceiling of learning-by-experiment. Analysis probe, not the product agent.

The learner pays for every experiment using Cycle 1 / Baseline 5 accounting:
horizon from design_experiment_on_contribution with Baseline 5's fixed MDE rule
(2% of contribution per order) and assumed lift (0.03); cost = incentive spend on
the treatment arm's converters, exactly as src/eval/harness.py charges it.

Idealisation (the ceiling): after testing a set of interventions the learner is
assumed to identify the best AMONG THOSE TESTED with certainty -- perfect
updating, correct stopping, no estimation error. It is never told which to test
or what an untested intervention would do. Ground truth scores outcomes only.

Experiments use disjoint customer blocks. Rollout uses whatever population and
budget remain, under Cycle 1's exposure cap and budget gate.
"""
import itertools, json, sys
sys.path.insert(0, ".")
import numpy as np
from src.baselines.engine_without_llm import EngineWithoutLLM
from src.eval.contracts import merchant_view
from src.eval.devcorpus import open_dev
from src.experiment.randomize import assign
from src.experiment.registry import design_experiment_on_contribution
from src.policy.gates import PolicyLimits

E, L = EngineWithoutLLM(), PolicyLimits()
N_WORLDS = 20

def net_over(ids, truth, iv, treated):
    """Realized incremental net and incentive spend over a customer block."""
    net = spend = 0.0
    for cid in ids:
        pair = truth.outcomes[cid][iv.intervention_id]
        if not treated:
            continue
        net += pair.y1.contribution_inr - pair.y0.contribution_inr
        if pair.y1.converted:
            c = iv.incentive_cost_inr(pair.y1.order_value_inr)
            spend += c; net -= c
    return net, spend

rows = []
for world, truth in open_dev("worlds_cycle2", limit=N_WORLDS):
    view = merchant_view(world)
    cpo = view.observed_aov_inr * view.observed_margin
    ivs = list(world.interventions)
    horizons = {}
    for iv in ivs:
        d = design_experiment_on_contribution(
            experiment_id=f"ceil_{world.world_id}_{iv.intervention_id}", world_id=world.world_id,
            intervention_id=iv.intervention_id, hypothesis_id="h", prediction="p", reasoning="r",
            baseline_conversion=view.observed_conversion,
            expected_effect_absolute=E.assumed_lift_absolute,
            contribution_per_incremental_order_inr=cpo,
            incentive_cost_per_treated_order_inr=iv.incentive_cost_inr(view.observed_aov_inr),
            mde_contribution_per_customer_inr=cpo * E.mde_fraction_of_order_contribution,
            success_condition="s", failure_condition="f", budget_inr=view.budget_inr)
        horizons[iv.intervention_id] = d.horizon_per_arm

    cust = [c.customer_id for c in world.customers]
    best_k = None
    for k in range(0, len(ivs) + 1):                       # how many to test
        for subset in itertools.combinations(ivs, k):
            cursor, pilot_net, pilot_spend, tested = 0, 0.0, 0.0, {}
            feasible = True
            for iv in subset:
                H = horizons[iv.intervention_id]
                block = cust[cursor:cursor + 2 * H]
                if len(block) < 2 * H:
                    feasible = False; break
                cursor += 2 * H
                arms = [[], []]
                for cid in block:
                    a = assign(cid, f"ceil_{world.world_id}_{iv.intervention_id}", 2)
                    arms[a].append(cid)
                n, s = net_over(arms[1], truth, iv, True)
                pilot_net += n; pilot_spend += s
                # Perfect updating: the true full-population value of this arm.
                tested[iv.intervention_id] = sum(
                    truth.outcomes[c][iv.intervention_id].y1.contribution_inr
                    - truth.outcomes[c][iv.intervention_id].y0.contribution_inr
                    - (iv.incentive_cost_inr(truth.outcomes[c][iv.intervention_id].y1.order_value_inr)
                       if truth.outcomes[c][iv.intervention_id].y1.converted else 0.0)
                    for c in cust[cursor:])
            if not feasible:
                continue
            treated_share = cursor / len(cust)
            if treated_share > L.max_customer_exposure_share or pilot_spend > view.budget_inr:
                continue
            # Exploit: roll out the best tested intervention, or nothing if all lose.
            roll_net = 0.0
            if tested:
                pick = max(tested, key=tested.get)
                if tested[pick] > 0:
                    iv = view.intervention(pick)
                    roll_net, roll_spend = net_over(cust[cursor:], truth,
                                                    next(i for i in ivs if i.intervention_id == pick), True)
                    if pilot_spend + roll_spend > view.budget_inr:
                        roll_net = 0.0
            total = pilot_net + roll_net
            cand = dict(k=k, total=total, pilot_net=pilot_net, pilot_spend=pilot_spend,
                        roll_net=roll_net, tested=[i.intervention_id for i in subset])
            if best_k is None or cand["total"] > best_k["total"]:
                best_k = cand
    best_k["world"] = world.world_id
    rows.append(best_k)
    print(f"{world.world_id}  k={best_k['k']}  learn_cost=Rs.{best_k['pilot_spend']:>10,.0f}  "
          f"pilot_net=Rs.{best_k['pilot_net']:>10,.0f}  rollout=Rs.{best_k['roll_net']:>12,.0f}  "
          f"TOTAL=Rs.{best_k['total']:>12,.0f}", flush=True)
    del world, truth

json.dump(rows, open("analysis/posthoc/ceiling/outputs/ceiling.json","w"), indent=1)
print()
print(f"worlds                         : {len(rows)}")
print(f"cumulative experimentation cost: Rs.{sum(r['pilot_spend'] for r in rows):,.0f}")
print(f"cumulative pilot net           : Rs.{sum(r['pilot_net'] for r in rows):,.0f}")
print(f"cumulative rollout (exploit)   : Rs.{sum(r['roll_net'] for r in rows):,.0f}")
print(f"CUMULATIVE NET                 : Rs.{sum(r['total'] for r in rows):,.0f}")
print(f"worlds where it chose to test  : {sum(1 for r in rows if r['k']>0)}/{len(rows)}")
