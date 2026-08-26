"""Razorpay test-mode client — the financial actuator.

Responsibility
--------------
Order creation and payment link generation in Razorpay **test mode**, a webhook
receiver with an idempotency key so duplicate delivery produces exactly one
attribution, and a reconciliation path that resolves order state by Razorpay
fetch when a webhook is missing or delayed.

Boundary rules (CLAUDE.md)
--------------------------
* **Test mode only.** Live keys must never be touched or referenced.
* Credentials come from ``.env`` (see ``.env.example``) and are never committed.
* Payments execute only downstream of a policy verdict — this module is an
  actuator, not a decision-maker.
* Which orders execute live in test mode and which are simulated is recorded per
  experiment in the audit trail and stated in ``docs/razorpay_scope.md``.

Built Day 8, and deliberately small — this is the actuator, not the project.

``razorpay_client`` offers two implementations of one Protocol: the real SDK
(test mode only, live keys refused at construction) and a mock with the
identical interface. ``webhooks`` verifies signatures and keys attribution on
the payment id so duplicate delivery produces exactly one attribution.
``reconciliation`` resolves any order whose webhook never arrived, leaving no
orphans. ``attribution`` executes a defined subset through the API and records
in the audit trail which orders moved real money and which were simulated.

**No Razorpay test credentials were available in this build, so everything ran
against the mock.** See ``docs/razorpay_scope.md``.
"""
