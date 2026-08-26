"""The executed subset: which orders actually go through Razorpay.

Experiment mathematics run across simulated customer populations of 12,000 to
28,000 per world. No sandbox supports that, and pretending otherwise would be
the kind of claim that gets discovered rather than disclosed. So a **defined
subset** of each experiment's treated orders is executed end to end — order
created, payment captured, webhook received, attribution recorded — and the
remainder is simulated.

Both halves are recorded per experiment in the audit trail, so any number in
the results can be traced to whether money actually moved. The scope is stated
plainly in ``docs/razorpay_scope.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from src.audit.log import AuditLog, Stage
from src.payments.razorpay_client import PaymentClient
from src.payments.reconciliation import PendingOrder
from src.payments.webhooks import Attribution, WebhookReceiver, build_webhook_body, sign

#: How many treated orders per experiment execute for real. Small on purpose:
#: enough to demonstrate the loop closes, not enough to pretend the sandbox is
#: carrying the evaluation.
DEFAULT_EXECUTED_SUBSET = 5


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """What happened to one experiment's payments, live and simulated."""

    experiment_id: str
    executed_live: int
    simulated: int
    orders: tuple[str, ...]
    attributions: tuple[Attribution, ...]
    pending: tuple[PendingOrder, ...]
    client_mode: str

    @property
    def total_treated_orders(self) -> int:
        return self.executed_live + self.simulated

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "client_mode": self.client_mode,
            "executed_live": self.executed_live,
            "simulated": self.simulated,
            "total_treated_orders": self.total_treated_orders,
            "order_ids": list(self.orders),
            "payment_ids": [a.payment_id for a in self.attributions],
        }


def execute_subset(
    *,
    experiment_id: str,
    world_id: str,
    customer_ids: Sequence[str],
    order_value_inr: float,
    total_treated_orders: int,
    client: PaymentClient,
    receiver: WebhookReceiver,
    audit: AuditLog | None = None,
    subset_size: int = DEFAULT_EXECUTED_SUBSET,
    webhook_secret: str = "",
) -> ExecutionRecord:
    """Run the first ``subset_size`` treated orders through Razorpay for real.

    The webhook is replayed through the same idempotent receiver a live delivery
    would hit, so the executed path in a demo is the executed path in production
    — not a shortcut around it.
    """
    subset = list(customer_ids[:subset_size])
    orders: list[str] = []
    attributions: list[Attribution] = []
    pending: list[PendingOrder] = []

    for customer_id in subset:
        order = client.create_order(
            amount_inr=order_value_inr,
            receipt=f"{experiment_id}:{customer_id}",
            notes={"experiment_id": experiment_id, "customer_id": customer_id},
        )
        orders.append(order.order_id)
        pending.append(
            PendingOrder(
                order_id=order.order_id,
                experiment_id=experiment_id,
                customer_id=customer_id,
                created_at=datetime.now(timezone.utc),
            )
        )

        body = build_webhook_body(
            payment_id=f"pay_{order.order_id[6:]}",
            order_id=order.order_id,
            amount_inr=order.amount_inr,
            experiment_id=experiment_id,
            customer_id=customer_id,
        )
        signature = sign(body, webhook_secret) if webhook_secret else None
        attribution = receiver.handle(body, signature, delivery_id=f"live:{order.order_id}")
        if attribution is not None:
            attributions.append(attribution)

    record = ExecutionRecord(
        experiment_id=experiment_id,
        executed_live=len(subset),
        simulated=max(total_treated_orders - len(subset), 0),
        orders=tuple(orders),
        attributions=tuple(attributions),
        pending=tuple(pending),
        client_mode=client.mode,
    )

    if audit is not None:
        audit.append(
            world_id=world_id,
            experiment_id=experiment_id,
            stage=Stage.PAYMENT,
            actor="payments",
            payload=record.to_dict(),
        )
    return record
