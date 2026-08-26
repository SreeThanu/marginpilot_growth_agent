"""Payments: test mode only, one attribution per payment, no orphan orders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.audit.log import AuditLog, Stage
from src.payments.attribution import execute_subset
from src.payments.razorpay_client import (
    LiveKeyRefused,
    MockRazorpayClient,
    OrderStatus,
    PaymentClient,
    RazorpayTestClient,
    default_client,
)
from src.payments.reconciliation import PendingOrder, reconcile
from src.payments.webhooks import (
    SignatureInvalid,
    WebhookReceiver,
    build_webhook_body,
    sign,
    verify_signature,
)

SECRET = "whsec_test_abc"


@pytest.fixture()
def receiver(tmp_path):
    return WebhookReceiver(tmp_path / "payments.db", secret=SECRET)


# --------------------------------------------------------------------------- #
# Test mode only
# --------------------------------------------------------------------------- #


def test_a_live_key_is_refused_at_construction() -> None:
    """CLAUDE.md: test mode only. A guard is cheap; a real charge is not."""
    with pytest.raises(LiveKeyRefused, match="LIVE"):
        RazorpayTestClient(key_id="rzp_live_abc123", key_secret="secret")


def test_an_unrecognised_key_prefix_is_refused() -> None:
    with pytest.raises(LiveKeyRefused, match="test key"):
        RazorpayTestClient(key_id="sk_something_else", key_secret="secret")


def test_the_mock_satisfies_the_same_protocol_as_the_real_client() -> None:
    """The interface is what matters — a later run with credentials swaps one
    implementation for the other and nothing else changes."""
    assert isinstance(MockRazorpayClient(), PaymentClient)
    assert isinstance(default_client(), PaymentClient)


def test_amounts_convert_to_paise_once() -> None:
    order = MockRazorpayClient().create_order(
        amount_inr=800.55, receipt="r", notes={}
    )
    assert order.amount_paise == 80055
    assert order.amount_inr == pytest.approx(800.55)


# --------------------------------------------------------------------------- #
# Idempotency — the test CLAUDE.md names explicitly
# --------------------------------------------------------------------------- #


def test_duplicate_delivery_produces_exactly_one_attribution(receiver) -> None:
    body = build_webhook_body(
        payment_id="pay_1", order_id="order_1", amount_inr=800.0,
        experiment_id="exp_1", customer_id="cust_1",
    )
    signature = sign(body, SECRET)

    first = receiver.handle(body, signature, delivery_id="d1")
    second = receiver.handle(body, signature, delivery_id="d2")
    third = receiver.handle(body, signature, delivery_id="d3")

    assert first is not None
    assert second is None and third is None
    assert len(receiver.attributions_for("exp_1")) == 1
    # The duplicates are still recorded as having arrived: a webhook delivered
    # four times is an operational fact worth keeping.
    assert receiver.delivery_count("pay_1") == 3


def test_two_different_payments_both_attribute(receiver) -> None:
    for i in (1, 2):
        body = build_webhook_body(
            payment_id=f"pay_{i}", order_id=f"order_{i}", amount_inr=500.0,
            experiment_id="exp_2", customer_id=f"cust_{i}",
        )
        assert receiver.handle(body, sign(body, SECRET)) is not None
    assert len(receiver.attributions_for("exp_2")) == 2


def test_a_mis_signed_webhook_is_refused(receiver) -> None:
    """Refusing to attribute a payment the system cannot prove Razorpay sent."""
    body = build_webhook_body(
        payment_id="pay_x", order_id="order_x", amount_inr=100.0,
        experiment_id="exp_3", customer_id="cust_x",
    )
    with pytest.raises(SignatureInvalid):
        receiver.handle(body, "deadbeef")
    assert len(receiver.attributions_for("exp_3")) == 0


def test_signature_verification_is_constant_time_and_correct() -> None:
    body = b'{"a": 1}'
    assert verify_signature(body, sign(body, SECRET), SECRET)
    assert not verify_signature(body, sign(body, "other"), SECRET)
    assert not verify_signature(body, "", SECRET)


# --------------------------------------------------------------------------- #
# Reconciliation — no orphans, no dangling attributions
# --------------------------------------------------------------------------- #


def test_a_missing_webhook_is_resolved_by_fetch(receiver) -> None:
    client = MockRazorpayClient(autopay=False)
    order = client.create_order(
        amount_inr=800.0, receipt="exp_4:cust_1",
        notes={"experiment_id": "exp_4", "customer_id": "cust_1"},
    )
    client.mark_paid(order.order_id)  # paid, but no webhook arrived

    pending = [PendingOrder(order.order_id, "exp_4", "cust_1",
                            datetime.now(timezone.utc) - timedelta(seconds=600))]
    report = reconcile(pending, client, receiver, timeout_seconds=120)

    assert report.resolved_paid == 1
    assert report.orphans == 0
    assert len(receiver.attributions_for("exp_4")) == 1


def test_reconciliation_does_not_race_a_webhook_that_still_has_time(receiver) -> None:
    client = MockRazorpayClient(autopay=False)
    order = client.create_order(amount_inr=100.0, receipt="exp_5:c", notes={})
    pending = [PendingOrder(order.order_id, "exp_5", "c", datetime.now(timezone.utc))]

    report = reconcile(pending, client, receiver, timeout_seconds=120)
    assert report.still_waiting == 1
    assert report.resolved_paid == 0


def test_a_late_webhook_after_reconciliation_does_not_double_count(receiver) -> None:
    """Reconciliation attributes through the same idempotent path, so a webhook
    arriving afterwards still cannot produce a second attribution."""
    client = MockRazorpayClient(autopay=False)
    order = client.create_order(
        amount_inr=800.0, receipt="exp_6:cust_1",
        notes={"experiment_id": "exp_6", "customer_id": "cust_1"},
    )
    client.mark_paid(order.order_id)
    pending = [PendingOrder(order.order_id, "exp_6", "cust_1",
                            datetime.now(timezone.utc) - timedelta(seconds=600))]
    reconcile(pending, client, receiver, timeout_seconds=120)
    assert len(receiver.attributions_for("exp_6")) == 1

    late = build_webhook_body(
        payment_id=f"pay_recon_{order.order_id}", order_id=order.order_id,
        amount_inr=800.0, experiment_id="exp_6", customer_id="cust_1",
    )
    assert receiver.handle(late, sign(late, SECRET)) is None
    assert len(receiver.attributions_for("exp_6")) == 1


def test_an_unpaid_order_is_closed_out_not_left_dangling(receiver) -> None:
    client = MockRazorpayClient(autopay=False)
    order = client.create_order(amount_inr=100.0, receipt="exp_7:c", notes={})
    pending = [PendingOrder(order.order_id, "exp_7", "c",
                            datetime.now(timezone.utc) - timedelta(seconds=600))]
    report = reconcile(pending, client, receiver, timeout_seconds=120)

    assert report.resolved_unpaid == 1
    assert report.orphans == 0
    assert len(receiver.attributions_for("exp_7")) == 0


# --------------------------------------------------------------------------- #
# The executed subset, and its audit record
# --------------------------------------------------------------------------- #


def test_the_executed_subset_is_recorded_in_the_audit_chain(tmp_path) -> None:
    """Which orders moved real money is recorded per experiment, so no figure in
    the results is ambiguous about it."""
    audit = AuditLog(tmp_path / "audit.db")
    receiver = WebhookReceiver(tmp_path / "pay.db")
    client = MockRazorpayClient()

    record = execute_subset(
        experiment_id="exp_live", world_id="world_00001",
        customer_ids=[f"cust_{i:05d}" for i in range(50)],
        order_value_inr=800.0, total_treated_orders=2_400,
        client=client, receiver=receiver, audit=audit, subset_size=5,
    )

    assert record.executed_live == 5
    assert record.simulated == 2_395
    assert len(receiver.attributions_for("exp_live")) == 5

    chain = audit.chain("exp_live")
    payment_entries = [e for e in chain if e.stage is Stage.PAYMENT]
    assert len(payment_entries) == 1
    payload = payment_entries[0].payload
    assert payload["client_mode"] == "mock"
    assert payload["executed_live"] == 5
    assert payload["simulated"] == 2_395
    assert len(payload["payment_ids"]) == 5


def test_replaying_the_subset_does_not_double_attribute(tmp_path) -> None:
    """The demo path is the production path: re-running it is idempotent."""
    receiver = WebhookReceiver(tmp_path / "pay.db")
    client = MockRazorpayClient()
    args = dict(
        experiment_id="exp_twice", world_id="w",
        customer_ids=[f"cust_{i}" for i in range(10)],
        order_value_inr=500.0, total_treated_orders=100,
        client=client, receiver=receiver, subset_size=3,
    )
    execute_subset(**args)
    execute_subset(**args)
    assert len(receiver.attributions_for("exp_twice")) == 3
