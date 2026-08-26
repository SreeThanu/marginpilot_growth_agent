"""Append-only decision log.

Responsibility
--------------
Record, for every money-adjacent action, the full chain: agent intent -> policy
verdict (including the rule that fired and the violating value) -> randomization
seed -> execution -> payment ID -> measured outcome. ``make audit
EXPERIMENT=<id>`` prints the chain for any experiment.

Boundary rules (CLAUDE.md)
--------------------------
* **Append-only. No update path, no delete path. Ever.**
* Rejections are logged as fully as approvals — a refused proposal is evidence,
  not noise.
* A failed experiment's records are never deleted or rewritten.
* Storage is SQLite (no server processes).

Built Day 7. Append-only enforced three ways: no mutating methods on the class,
SQLite triggers that abort UPDATE and DELETE at the storage layer, and a
SHA-256 hash chain so that tampering is detectable even if the triggers were
dropped and the table rewritten.

``make audit EXPERIMENT=<id>`` prints one experiment's decision chain.
"""
