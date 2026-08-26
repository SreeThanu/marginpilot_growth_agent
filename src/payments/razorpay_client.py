"""Razorpay test mode. The financial actuator, not the project.

Deliberately small. This module creates orders and payment links and reads back
order state; it does not model payments, retries, refunds or settlements. The
interesting part of MarginPilot is the decision architecture, and a payments
layer that grew past "close the loop" would be padding.

Two implementations behind one Protocol:

* :class:`RazorpayTestClient` — the real SDK, **test mode only**.
* :class:`MockRazorpayClient` — identical interface, no network. Used when no
  test credentials are present, and in every test.

The interface is what matters. A defined subset of orders executes end to end
through Razorpay so the financial loop demonstrably closes; the rest of the
experiment arithmetic runs over simulated populations at a scale no sandbox
could support. Which is which is recorded per experiment in the audit trail and
stated in ``docs/razorpay_scope.md``.

**Live keys are refused at construction.** CLAUDE.md: test mode only, never
touch live keys. A guard is cheap; discovering that a student project charged a
real card is not.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

#: Razorpay test keys start with this. Anything else is refused.
TEST_KEY_PREFIX = "rzp_test_"
LIVE_KEY_PREFIX = "rzp_live_"


class OrderStatus(str, Enum):
    CREATED = "created"
    ATTEMPTED = "attempted"
    PAID = "paid"
    FAILED = "failed"


class LiveKeyRefused(RuntimeError):
    """Raised if a live Razorpay key is supplied. Never caught anywhere."""


@dataclass(frozen=True, slots=True)
class Order:
    """One Razorpay order, in the fields this project actually uses."""

    order_id: str
    amount_paise: int
    currency: str
    status: OrderStatus
    receipt: str
    notes: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    @property
    def amount_inr(self) -> float:
        return self.amount_paise / 100.0

    @property
    def experiment_id(self) -> str:
        """Experiments are tagged in notes so attribution survives the round trip."""
        return str(self.notes.get("experiment_id", ""))

    @property
    def customer_id(self) -> str:
        return str(self.notes.get("customer_id", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "amount_paise": self.amount_paise,
            "amount_inr": self.amount_inr,
            "currency": self.currency,
            "status": self.status.value,
            "receipt": self.receipt,
            "notes": dict(self.notes),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class PaymentLink:
    link_id: str
    short_url: str
    amount_paise: int
    status: str
    order_id: str = ""


@runtime_checkable
class PaymentClient(Protocol):
    """What the rest of the project needs from a payment provider."""

    mode: str

    def create_order(
        self, *, amount_inr: float, receipt: str, notes: dict[str, Any]
    ) -> Order:
        ...

    def create_payment_link(
        self, *, amount_inr: float, description: str, notes: dict[str, Any]
    ) -> PaymentLink:
        ...

    def fetch_order(self, order_id: str) -> Order:
        ...


def _to_paise(amount_inr: float) -> int:
    """Razorpay works in paise. Rounding here, once, avoids drift downstream."""
    if amount_inr < 0:
        raise ValueError(f"amount cannot be negative, got {amount_inr}")
    return int(round(amount_inr * 100))


class RazorpayTestClient:
    """The real SDK, pinned to test mode.

    Requires ``RAZORPAY_TEST_KEY_ID`` and ``RAZORPAY_TEST_KEY_SECRET``. Raises
    on a live key rather than proceeding.
    """

    mode = "razorpay_test"

    def __init__(self, key_id: str | None = None, key_secret: str | None = None) -> None:
        load_dotenv(_ENV_PATH)
        key_id = key_id or os.environ.get("RAZORPAY_TEST_KEY_ID", "")
        key_secret = key_secret or os.environ.get("RAZORPAY_TEST_KEY_SECRET", "")

        if not key_id or not key_secret:
            raise RuntimeError(
                "RazorpayTestClient needs RAZORPAY_TEST_KEY_ID and "
                "RAZORPAY_TEST_KEY_SECRET. Use MockRazorpayClient when no test "
                "credentials are available — it has the identical interface."
            )
        if key_id.startswith(LIVE_KEY_PREFIX):
            raise LiveKeyRefused(
                f"{key_id[:12]}... is a LIVE Razorpay key. This project is test mode "
                "only (CLAUDE.md). Refusing to construct a client that could move "
                "real money."
            )
        if not key_id.startswith(TEST_KEY_PREFIX):
            raise LiveKeyRefused(
                f"{key_id[:12]}... is not a recognised Razorpay test key "
                f"(expected the {TEST_KEY_PREFIX!r} prefix). Refusing rather than "
                "guessing what environment this points at."
            )

        import razorpay

        self._client = razorpay.Client(auth=(key_id, key_secret))

    def create_order(self, *, amount_inr: float, receipt: str, notes: dict[str, Any]) -> Order:
        raw = self._client.order.create(
            {
                "amount": _to_paise(amount_inr),
                "currency": "INR",
                "receipt": receipt,
                "notes": notes,
            }
        )
        return _order_from_raw(raw)

    def create_payment_link(
        self, *, amount_inr: float, description: str, notes: dict[str, Any]
    ) -> PaymentLink:
        raw = self._client.payment_link.create(
            {
                "amount": _to_paise(amount_inr),
                "currency": "INR",
                "description": description,
                "notes": notes,
            }
        )
        return PaymentLink(
            link_id=raw["id"],
            short_url=raw.get("short_url", ""),
            amount_paise=raw["amount"],
            status=raw.get("status", "created"),
            order_id=raw.get("order_id", ""),
        )

    def fetch_order(self, order_id: str) -> Order:
        return _order_from_raw(self._client.order.fetch(order_id))


def _order_from_raw(raw: dict[str, Any]) -> Order:
    return Order(
        order_id=raw["id"],
        amount_paise=int(raw["amount"]),
        currency=raw.get("currency", "INR"),
        status=OrderStatus(raw.get("status", "created")),
        receipt=raw.get("receipt", ""),
        notes=dict(raw.get("notes") or {}),
        created_at=str(raw.get("created_at", "")),
    )


class MockRazorpayClient:
    """Identical interface, no network. Deterministic ids.

    Used when no test credentials are present. Order ids are derived from the
    receipt by hash rather than a counter, so the same order requested twice
    yields the same id — which is what makes the idempotency tests meaningful
    rather than an artefact of call ordering.
    """

    mode = "mock"

    def __init__(self, *, autopay: bool = True) -> None:
        #: Whether a created order is treated as paid. False simulates the
        #: customer never completing checkout, which reconciliation must handle.
        self.autopay = autopay
        self._orders: dict[str, Order] = {}

    def create_order(self, *, amount_inr: float, receipt: str, notes: dict[str, Any]) -> Order:
        digest = hashlib.blake2b(receipt.encode("utf-8"), digest_size=7).hexdigest()
        order = Order(
            order_id=f"order_{digest}",
            amount_paise=_to_paise(amount_inr),
            currency="INR",
            status=OrderStatus.PAID if self.autopay else OrderStatus.CREATED,
            receipt=receipt,
            notes=dict(notes),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._orders[order.order_id] = order
        return order

    def create_payment_link(
        self, *, amount_inr: float, description: str, notes: dict[str, Any]
    ) -> PaymentLink:
        digest = hashlib.blake2b(description.encode("utf-8"), digest_size=7).hexdigest()
        return PaymentLink(
            link_id=f"plink_{digest}",
            short_url=f"https://rzp.test/{digest}",
            amount_paise=_to_paise(amount_inr),
            status="created",
        )

    def fetch_order(self, order_id: str) -> Order:
        try:
            return self._orders[order_id]
        except KeyError as exc:
            raise KeyError(f"unknown order {order_id!r}") from exc

    def mark_paid(self, order_id: str) -> Order:
        """Test hook: settle an order that was created but not paid."""
        order = self._orders[order_id]
        settled = Order(
            order_id=order.order_id, amount_paise=order.amount_paise,
            currency=order.currency, status=OrderStatus.PAID, receipt=order.receipt,
            notes=order.notes, created_at=order.created_at,
        )
        self._orders[order_id] = settled
        return settled


def default_client() -> PaymentClient:
    """The real client when test credentials exist, the mock otherwise.

    Chooses once, loudly, rather than failing halfway through a run. Which one
    was used is recorded in the audit trail, so no result is ever ambiguous
    about whether money actually moved.
    """
    load_dotenv(_ENV_PATH)
    if os.environ.get("RAZORPAY_TEST_KEY_ID") and os.environ.get("RAZORPAY_TEST_KEY_SECRET"):
        return RazorpayTestClient()
    return MockRazorpayClient()
