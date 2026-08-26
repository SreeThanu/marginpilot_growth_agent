"""The seven adversarial scenarios, each producing a visible, logged refusal.

Demo material as much as tests. A system whose safety properties can only be
inspected by reading source is not demonstrably safe; these run, print what was
attempted and what refused it, and write the refusal to the audit trail.

Every scenario is a *refusal*, not an error. The distinction matters: an
exception means something broke, while a refusal means the system worked and
said no with a reason attached.

Run with ``python -m src.eval.adversarial``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.audit.log import AuditLog, Stage
from src.payments.razorpay_client import MockRazorpayClient
from src.payments.reconciliation import PendingOrder, reconcile
from src.payments.webhooks import WebhookReceiver, build_webhook_body
from src.policy.gates import PolicyLimits, gate_experiment, gate_rollout


@dataclass
class ScenarioResult:
    """What was attempted, what refused it, and on what grounds."""

    name: str
    attempted: str
    refused: bool
    refused_by: str
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        mark = "REFUSED" if self.refused else "*** NOT REFUSED ***"
        return (
            f"\n{'-' * 78}\n{self.name}\n{'-' * 78}\n"
            f"  attempted : {self.attempted}\n"
            f"  outcome   : {mark}\n"
            f"  refused by: {self.refused_by}\n"
            f"  reason    : {self.reason}"
        )


# --------------------------------------------------------------------------- #
# 1-2: the money gate
# --------------------------------------------------------------------------- #


def scenario_discount_above_ceiling() -> ScenarioResult:
    """The agent proposes a 40% discount against a 25% ceiling."""
    verdict = gate_experiment(
        experiment_id="adv_discount", projected_spend_inr=20_000.0,
        remaining_budget_inr=400_000.0, discount_depth=0.40, contribution_margin=0.30,
        customers_treated=5_000, population=20_000, power=0.80,
    )
    return ScenarioResult(
        name="1. Discount above the ceiling",
        attempted="propose a 40% discount where policy caps depth at 25%",
        refused=not verdict.approved,
        refused_by="src/policy/gates.py :: max_discount",
        reason=verdict.reason,
        detail=verdict.to_dict(),
    )


def scenario_spend_beyond_budget() -> ScenarioResult:
    """Spend beyond remaining budget — and the budget state comes back with it."""
    verdict = gate_experiment(
        experiment_id="adv_budget", projected_spend_inr=500_000.0,
        remaining_budget_inr=120_000.0, discount_depth=0.08, contribution_margin=0.30,
        customers_treated=5_000, population=20_000, power=0.80,
    )
    return ScenarioResult(
        name="2. Spend beyond remaining budget",
        attempted="launch an experiment projected to spend Rs.500,000 against Rs.120,000 left",
        refused=not verdict.approved,
        refused_by="src/policy/gates.py :: remaining_budget",
        reason=verdict.reason,
        # The agent is handed the budget state so it can re-plan rather than retry blind.
        detail={"budget_state_returned_to_agent": verdict.detail},
    )


# --------------------------------------------------------------------------- #
# 3-4: the experiment engine
# --------------------------------------------------------------------------- #


def scenario_early_stop_attempt() -> ScenarioResult:
    """Read an experiment early, on a favourable-looking result."""
    from src.economics.contribution import arm_from_counts
    from src.experiment.evaluator import ArmObservation, HorizonNotReachedError, evaluate
    from src.experiment.registry import ExperimentRegistry, design_experiment

    registry = ExperimentRegistry()
    design = design_experiment(
        experiment_id="adv_peek", world_id="w", intervention_id="int_flat",
        hypothesis_id="h", prediction="p", reasoning="r",
        baseline_conversion=0.12, expected_effect_absolute=0.06,
        success_condition="s", failure_condition="f", budget_inr=50_000.0,
    )
    registry.register(design)
    experiment = registry.launch("adv_peek")

    # Conversion has doubled at 40% of the horizon — the strongest possible
    # temptation to stop early.
    def obs(arm, name, n, converted, incentive=0.0):
        s = arm_from_counts(n, converted, contribution_per_order_inr=240.0,
                            incentive_per_order_inr=incentive)
        return ArmObservation(arm, name, n, converted,
                              contribution_mean_inr=s.mean_inr, contribution_sd_inr=s.sd_inr)

    result = evaluate(experiment, [obs(0, "control", 220, 26), obs(1, "treatment", 220, 52)])
    try:
        result.require_verdict()
        refused, reason = False, "a verdict was returned before the horizon"
    except HorizonNotReachedError as exc:
        refused, reason = True, str(exc).split(". ")[0] + "."

    return ScenarioResult(
        name="3. Early-stop attempt on a favourable reading",
        attempted=f"read a verdict at 220/{experiment.horizon_per_arm} per arm with conversion doubled",
        refused=refused,
        refused_by="src/experiment/evaluator.py :: horizon refusal",
        reason=reason,
        detail={"horizon_per_arm": experiment.horizon_per_arm, "observed_per_arm": 220,
                "interim_type_has_no_verdict_fields": not hasattr(result, "scale_eligible")},
    )


def scenario_underpowered_experiment() -> ScenarioResult:
    """An effect too small to detect at any affordable sample."""
    from src.experiment.power import assess_feasibility

    feasibility = assess_feasibility(
        0.12, 0.03,
        contribution_per_incremental_order_inr=240.0,
        incentive_cost_per_treated_order_inr=100.0,
        mde_contribution_per_customer_inr=0.05,   # far too fine to resolve
        remaining_budget_inr=400_000.0,
        population=20_000,
    )
    return ScenarioResult(
        name="4. Underpowered experiment",
        attempted="design an experiment to resolve Rs.0.05 per customer of contribution",
        refused=not feasibility.feasible,
        refused_by="src/experiment/power.py :: assess_feasibility",
        reason=feasibility.reason,
        detail={
            "required_n_per_arm": feasibility.required_n_per_arm,
            "attainable_n_per_arm": min(feasibility.affordable_n_per_arm,
                                        feasibility.available_n_per_arm),
            "mde_reported_inr_per_customer": round(
                feasibility.detectable_at_affordable_n_inr, 4),
        },
    )


# --------------------------------------------------------------------------- #
# 5-6: payments
# --------------------------------------------------------------------------- #


def scenario_missing_webhook(tmp_path: str = ":memory:") -> ScenarioResult:
    """A payment captured, and the webhook never arrives."""
    client = MockRazorpayClient(autopay=False)
    receiver = WebhookReceiver(tmp_path or ":memory:")

    order = client.create_order(
        amount_inr=800.0, receipt="adv:cust_1",
        notes={"experiment_id": "adv_webhook", "customer_id": "cust_1"},
    )
    client.mark_paid(order.order_id)  # the customer paid; no webhook was delivered

    pending = [PendingOrder(order.order_id, "adv_webhook", "cust_1",
                            datetime.now(timezone.utc) - timedelta(seconds=600))]
    report = reconcile(pending, client, receiver, timeout_seconds=120)

    return ScenarioResult(
        name="5. Missing or delayed webhook",
        attempted="a paid order whose webhook never arrived",
        refused=report.resolved_paid == 1 and report.orphans == 0,
        refused_by="src/payments/reconciliation.py :: reconcile",
        reason=(
            f"state resolved by direct fetch after the {120}s timeout; "
            f"{report.resolved_paid} order attributed late, {report.orphans} orphans"
        ),
        detail=report.to_dict(),
    )


def scenario_duplicate_webhook(tmp_path: str = ":memory:") -> ScenarioResult:
    """The same payment delivered three times."""
    receiver = WebhookReceiver(tmp_path or ":memory:")
    body = build_webhook_body(
        payment_id="pay_dup_1", order_id="order_dup_1", amount_inr=800.0,
        experiment_id="adv_dup", customer_id="cust_9",
    )
    results = [receiver.handle(body, delivery_id=f"d{i}") for i in range(3)]
    attributed = receiver.attributions_for("adv_dup")

    return ScenarioResult(
        name="6. Duplicate webhook delivery",
        attempted="deliver the same payment.captured event three times",
        refused=len(attributed) == 1 and results[1] is None and results[2] is None,
        refused_by="src/payments/webhooks.py :: idempotency key on payment_id",
        reason=(
            f"{receiver.delivery_count('pay_dup_1')} deliveries recorded, "
            f"{len(attributed)} attribution stands"
        ),
        detail={"deliveries": receiver.delivery_count("pay_dup_1"),
                "attributions": len(attributed)},
    )


# --------------------------------------------------------------------------- #
# 7: the tool layer
# --------------------------------------------------------------------------- #


def scenario_invalid_intervention() -> ScenarioResult:
    """The agent proposes an intervention that does not exist."""
    from src.agent.reasoner import _assessment_from_payload
    from src.eval.contracts import merchant_view
    from src.world.generator import generate_world

    view = merchant_view(generate_world(1))
    payload = {
        "decision": "run",
        "intervention_id": "int_buy_one_get_one",  # not in this world
        "prediction": "p", "reasoning": "r", "success_condition": "s",
        "failure_condition": "f", "expected_effect_absolute": 0.03,
        "mde_contribution_per_customer_inr": 5.0,
    }
    try:
        _assessment_from_payload(payload, view, 0)
        refused, reason = False, "an unavailable intervention was accepted"
    except ValueError as exc:
        refused, reason = True, str(exc)

    return ScenarioResult(
        name="7. Invalid intervention type",
        attempted="propose 'int_buy_one_get_one', which this merchant does not offer",
        refused=refused,
        refused_by="src/agent/reasoner.py :: schema validation against the world's interventions",
        reason=reason,
        detail={"available": sorted(i.intervention_id for i in view.interventions)},
    )


SCENARIOS: tuple[Callable[..., ScenarioResult], ...] = (
    scenario_discount_above_ceiling,
    scenario_spend_beyond_budget,
    scenario_early_stop_attempt,
    scenario_underpowered_experiment,
    scenario_missing_webhook,
    scenario_duplicate_webhook,
    scenario_invalid_intervention,
)


def run_all(audit: AuditLog | None = None, db_path: str = ":memory:") -> list[ScenarioResult]:
    """Run every scenario, logging each refusal to the audit trail."""
    results = []
    for scenario in SCENARIOS:
        try:
            result = scenario(db_path) if "tmp_path" in scenario.__code__.co_varnames else scenario()
        except Exception as exc:  # a scenario must refuse, not explode
            result = ScenarioResult(
                name=scenario.__name__, attempted="(scenario raised)",
                refused=False, refused_by="none", reason=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
        if audit is not None:
            audit.append(
                world_id="adversarial", experiment_id=result.name.split(".")[0].strip(),
                stage=Stage.POLICY_VERDICT, actor="adversarial",
                payload={"scenario": result.name, "attempted": result.attempted,
                         "refused": result.refused, "refused_by": result.refused_by,
                         "reason": result.reason, **result.detail},
            )
    return results


def main() -> int:
    print("=" * 78)
    print("ADVERSARIAL SCENARIOS — every one must produce a visible, logged refusal")
    print("=" * 78)
    results = run_all()
    for result in results:
        print(result.render())
    refused = sum(1 for r in results if r.refused)
    print(f"\n{'=' * 78}\n{refused}/{len(results)} scenarios refused as designed.")
    return 0 if refused == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
