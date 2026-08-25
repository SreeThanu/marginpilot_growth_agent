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

Not implemented yet — Day 7.
"""
