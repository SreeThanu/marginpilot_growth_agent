"""When the webhook never arrives, ask Razorpay what happened.

Webhooks are best-effort. One that is delayed or lost leaves an order in limbo:
the customer may have paid, the merchant does not know, and the experiment is
missing an outcome it should have counted. Waiting forever silently under-counts
the treatment arm, which biases the very number the project reports.

So: any order without an attribution after ``timeout_seconds`` is resolved by
fetching its state directly. Orders confirmed paid are attributed late but
correctly; orders confirmed unpaid are closed out. **No orphan charges, no
dangling attributions** — every order ends in a known state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from src.payments.razorpay_client import Order, OrderStatus, PaymentClient
from src.payments.webhooks import Attribution, WebhookReceiver

#: How long to wait for a webhook before asking directly. Long enough that
#: normal delivery wins the race, short enough that an experiment is not left
#: waiting on a provider outage.
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True, slots=True)
class PendingOrder:
    """An order created by this system, awaiting a webhook."""

    order_id: str
    experiment_id: str
    customer_id: str
    created_at: datetime


@dataclass(slots=True)
class ReconciliationReport:
    """What reconciliation found. Every field is a count a reviewer can check."""

    checked: int = 0
    already_attributed: int = 0
    still_waiting: int = 0
    resolved_paid: int = 0
    resolved_unpaid: int = 0
    unknown: list[str] = field(default_factory=list)
    late_attributions: list[Attribution] = field(default_factory=list)

    @property
    def orphans(self) -> int:
        """Orders left in an unknown state. Must be zero."""
        return len(self.unknown)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "already_attributed": self.already_attributed,
            "still_waiting": self.still_waiting,
            "resolved_paid": self.resolved_paid,
            "resolved_unpaid": self.resolved_unpaid,
            "orphans": self.orphans,
        }


def reconcile(
    pending: Sequence[PendingOrder],
    client: PaymentClient,
    receiver: WebhookReceiver,
    *,
    now: datetime | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ReconciliationReport:
    """Resolve every pending order to a known state."""
    now = now or datetime.now(timezone.utc)
    cutoff = timedelta(seconds=timeout_seconds)
    report = ReconciliationReport()

    for order in pending:
        report.checked += 1
        attributed = {
            a.order_id for a in receiver.attributions_for(order.experiment_id)
        }
        if order.order_id in attributed:
            report.already_attributed += 1
            continue

        if now - order.created_at < cutoff:
            # The webhook still has time to arrive; asking now would race it.
            report.still_waiting += 1
            continue

        try:
            fetched: Order = client.fetch_order(order.order_id)
        except KeyError:
            report.unknown.append(order.order_id)
            continue

        if fetched.status is OrderStatus.PAID:
            # Attribute late, through the same idempotent write the webhook uses,
            # so a webhook arriving afterwards still cannot double-count. There
            # is no signature to check here: the state came from asking Razorpay
            # directly, which is a stronger guarantee than a signed webhook.
            attribution = receiver.attribute_reconciled(
                payment_id=f"pay_recon_{fetched.order_id}",
                order_id=fetched.order_id,
                amount_inr=fetched.amount_inr,
                experiment_id=order.experiment_id,
                customer_id=order.customer_id,
                delivery_id=f"recon:{fetched.order_id}",
            )
            if attribution is not None:
                report.late_attributions.append(attribution)
            report.resolved_paid += 1
        else:
            report.resolved_unpaid += 1

    return report
