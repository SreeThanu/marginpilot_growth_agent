"""Webhook receipt and attribution. Duplicate delivery must not double-count.

Razorpay retries webhooks. A payment captured once can arrive three times, and
a system that attributes each delivery reports three incremental orders where
one happened — inflating exactly the number MarginPilot exists to measure
honestly.

Two defences, and the second is the one that matters:

1. **Signature verification.** HMAC-SHA256 over the raw body with the webhook
   secret, compared in constant time. An unsigned or mis-signed event is
   rejected before it can touch attribution.
2. **Idempotency key.** Attribution is keyed on the payment id, stored, and
   checked before recording. A repeat delivery is recognised and discarded,
   whatever the event id or delivery count says.

The store is SQLite, like the audit log, because CLAUDE.md forbids server
processes and a file a reviewer can open is a better artefact than a cache.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path("payments.db")


class SignatureInvalid(ValueError):
    """Raised when a webhook body does not match its signature."""


@dataclass(frozen=True, slots=True)
class Attribution:
    """One payment, attributed to one customer in one experiment. Recorded once."""

    payment_id: str
    order_id: str
    experiment_id: str
    customer_id: str
    amount_inr: float
    status: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "order_id": self.order_id,
            "experiment_id": self.experiment_id,
            "customer_id": self.customer_id,
            "amount_inr": self.amount_inr,
            "status": self.status,
            "recorded_at": self.recorded_at,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS attributions (
    payment_id    TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    customer_id   TEXT NOT NULL,
    amount_paise  INTEGER NOT NULL,
    status        TEXT NOT NULL,
    recorded_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attr_experiment ON attributions(experiment_id);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id TEXT PRIMARY KEY,
    payment_id  TEXT NOT NULL,
    received_at TEXT NOT NULL,
    duplicate   INTEGER NOT NULL
);
"""


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Constant-time HMAC check. Razorpay signs with SHA-256."""
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


class WebhookReceiver:
    """Records attributions exactly once per payment."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH, *, secret: str = "") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def handle(
        self, raw_body: bytes, signature: str | None = None, *, delivery_id: str | None = None
    ) -> Attribution | None:
        """Process one delivery.

        Returns the attribution when this payment is seen for the first time,
        and ``None`` when the delivery is a duplicate. The duplicate is still
        recorded as having been received — knowing a webhook arrived four times
        is operationally useful, and silently dropping it would hide a provider
        problem.
        """
        if self.secret:
            if not verify_signature(raw_body, signature or "", self.secret):
                raise SignatureInvalid(
                    "webhook signature does not match the request body; refusing to "
                    "attribute a payment this system cannot prove Razorpay sent"
                )

        event = json.loads(raw_body.decode("utf-8"))
        payment = (
            event.get("payload", {}).get("payment", {}).get("entity", {})
        )
        return self._record(payment, delivery_id=delivery_id)

    def attribute_reconciled(
        self,
        *,
        payment_id: str,
        order_id: str,
        amount_inr: float,
        experiment_id: str,
        customer_id: str,
        delivery_id: str | None = None,
    ) -> Attribution | None:
        """Attribute an order resolved by direct fetch rather than by webhook.

        A separate, deliberately greppable entry point. Reconciliation has no
        signature to verify — it asked Razorpay directly, which is a stronger
        guarantee than a signed webhook, not a weaker one — but it must still go
        through the same idempotency check, so a webhook arriving afterwards
        cannot produce a second attribution.

        Bypassing signature verification is exactly the kind of thing that
        should be visible at the call site rather than hidden behind a flag on
        the normal path.
        """
        return self._record(
            {
                "id": payment_id,
                "order_id": order_id,
                "amount": int(round(amount_inr * 100)),
                "status": "captured",
                "notes": {"experiment_id": experiment_id, "customer_id": customer_id},
            },
            delivery_id=delivery_id,
        )

    def _record(
        self, payment: dict[str, Any], *, delivery_id: str | None
    ) -> Attribution | None:
        """The single idempotent write path. Both entry points funnel here."""
        payment_id = payment.get("id")
        if not payment_id:
            raise ValueError("payment payload carries no payment id")

        notes = payment.get("notes") or {}
        existing = self._conn.execute(
            "SELECT payment_id FROM attributions WHERE payment_id = ?", (payment_id,)
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO deliveries (delivery_id, payment_id, received_at, duplicate) "
            "VALUES (?, ?, ?, ?)",
            (delivery_id or f"{payment_id}:{now}", payment_id, now, 1 if existing else 0),
        )

        if existing:
            self._conn.commit()
            return None  # already attributed; exactly one attribution stands

        attribution = Attribution(
            payment_id=payment_id,
            order_id=payment.get("order_id", ""),
            experiment_id=str(notes.get("experiment_id", "")),
            customer_id=str(notes.get("customer_id", "")),
            amount_inr=int(payment.get("amount", 0)) / 100.0,
            status=payment.get("status", "captured"),
            recorded_at=now,
        )
        self._conn.execute(
            "INSERT INTO attributions "
            "(payment_id, order_id, experiment_id, customer_id, amount_paise, status, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (attribution.payment_id, attribution.order_id, attribution.experiment_id,
             attribution.customer_id, int(payment.get("amount", 0)), attribution.status,
             attribution.recorded_at),
        )
        self._conn.commit()
        return attribution

    def attributions_for(self, experiment_id: str) -> tuple[Attribution, ...]:
        rows = self._conn.execute(
            "SELECT * FROM attributions WHERE experiment_id = ? ORDER BY recorded_at",
            (experiment_id,),
        ).fetchall()
        return tuple(
            Attribution(
                payment_id=r["payment_id"], order_id=r["order_id"],
                experiment_id=r["experiment_id"], customer_id=r["customer_id"],
                amount_inr=r["amount_paise"] / 100.0, status=r["status"],
                recorded_at=r["recorded_at"],
            )
            for r in rows
        )

    def delivery_count(self, payment_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) c FROM deliveries WHERE payment_id = ?", (payment_id,)
        ).fetchone()
        return int(row["c"])

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) c FROM attributions").fetchone()["c"])

    def close(self) -> None:
        self._conn.close()


def build_webhook_body(
    *, payment_id: str, order_id: str, amount_inr: float, experiment_id: str,
    customer_id: str, status: str = "captured",
) -> bytes:
    """Construct a Razorpay-shaped `payment.captured` body.

    Used by the tests and the adversarial demo. Kept beside the parser so the
    two cannot drift into disagreeing about the payload shape.
    """
    return json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": int(round(amount_inr * 100)),
                        "status": status,
                        "notes": {"experiment_id": experiment_id, "customer_id": customer_id},
                    }
                }
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def sign(raw_body: bytes, secret: str) -> str:
    """Sign a body the way Razorpay would. Test helper."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
