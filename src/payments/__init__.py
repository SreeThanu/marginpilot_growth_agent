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

Not implemented yet — Day 8.
"""
