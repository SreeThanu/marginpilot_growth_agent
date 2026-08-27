"""Append-only decision log. No update path, no delete path. Ever.

CLAUDE.md invariant 6. Every money-adjacent action writes one row, and the rows
for an experiment form a chain a reviewer can read end to end:

    agent intent -> policy verdict (with the rule that fired) -> randomization
    seed -> execution -> payment ID -> measured outcome

Immutability is enforced three ways, because a convention is not an enforcement:

1. **No mutating methods.** The class exposes ``append`` and readers. There is
   no ``update``, no ``delete``, no ``amend``; ``tests/audit/`` scans the public
   API to keep it that way.
2. **SQLite triggers.** ``UPDATE`` and ``DELETE`` on the table raise at the
   database level, so a stray ``sqlite3`` session or a future module cannot
   rewrite history even by going around this class.
3. **Hash chaining.** Each row carries the SHA-256 of its own content plus the
   previous row's hash. Deleting or editing a row breaks every hash after it,
   so tampering is detectable even if someone recreates the table without the
   triggers.

A rejected proposal is logged as fully as an approved one. A refusal is
evidence — of the gate working — and a log that only records what happened
cannot show what was prevented.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Sequence

#: Generated artifacts live under data/, which is gitignored. Keeping them out
#: of the repo root means a careless `git add -A` cannot commit a decision log.
DEFAULT_DB_PATH = Path("data/audit.db")


class Stage(str, Enum):
    """The stations a money-adjacent action passes through, in order."""

    INTENT = "intent"                 # what the agent proposed, and why
    POLICY_VERDICT = "policy_verdict" # approved or refused, naming the rule
    RANDOMIZATION = "randomization"   # the assignment rule and its inputs
    EXECUTION = "execution"           # launched, or rolled out
    PAYMENT = "payment"               # Razorpay reference (Day 8)
    OUTCOME = "outcome"               # what was measured at the horizon
    SKIP = "skip"                     # the agent declining to spend, with reasoning


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at   TEXT NOT NULL,
    world_id      TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    stage         TEXT NOT NULL,
    actor         TEXT NOT NULL,
    payload       TEXT NOT NULL,
    prev_hash     TEXT NOT NULL,
    entry_hash    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_experiment ON audit_entries(experiment_id);

-- The append-only guarantee, enforced by the database rather than by habit.
-- A future module, a migration script, or someone at a sqlite3 prompt all hit
-- these; none of them can rewrite a decision after the fact.
CREATE TRIGGER IF NOT EXISTS audit_no_update
BEFORE UPDATE ON audit_entries
BEGIN
    SELECT RAISE(ABORT, 'audit_entries is append-only: UPDATE is not permitted');
END;

CREATE TRIGGER IF NOT EXISTS audit_no_delete
BEFORE DELETE ON audit_entries
BEGIN
    SELECT RAISE(ABORT, 'audit_entries is append-only: DELETE is not permitted');
END;
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One immutable row."""

    id: int
    recorded_at: str
    world_id: str
    experiment_id: str
    stage: Stage
    actor: str
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "recorded_at": self.recorded_at,
            "world_id": self.world_id,
            "experiment_id": self.experiment_id,
            "stage": self.stage.value,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


def _hash(prev_hash: str, recorded_at: str, world_id: str, experiment_id: str,
          stage: str, actor: str, payload: str) -> str:
    blob = "|".join([prev_hash, recorded_at, world_id, experiment_id, stage, actor, payload])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class AuditLog:
    """Append and read. That is the entire surface.

    SQLite because CLAUDE.md forbids server processes, and because a single file
    that a reviewer can open with any sqlite3 client is a better audit artefact
    than a bespoke format.
    """

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- writing ------------------------------------------------------------

    def append(
        self,
        *,
        world_id: str,
        experiment_id: str,
        stage: Stage,
        actor: str,
        payload: dict[str, Any],
    ) -> AuditEntry:
        """Add one row. The only way anything enters the log."""
        recorded_at = _utc_now()
        serialized = json.dumps(payload, sort_keys=True, default=str)
        prev = self.head_hash()
        entry_hash = _hash(
            prev, recorded_at, world_id, experiment_id, stage.value, actor, serialized
        )
        cursor = self._conn.execute(
            "INSERT INTO audit_entries "
            "(recorded_at, world_id, experiment_id, stage, actor, payload, prev_hash, entry_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (recorded_at, world_id, experiment_id, stage.value, actor, serialized, prev, entry_hash),
        )
        self._conn.commit()
        return AuditEntry(
            id=int(cursor.lastrowid),
            recorded_at=recorded_at,
            world_id=world_id,
            experiment_id=experiment_id,
            stage=stage,
            actor=actor,
            payload=payload,
            prev_hash=prev,
            entry_hash=entry_hash,
        )

    # -- reading ------------------------------------------------------------

    def head_hash(self) -> str:
        row = self._conn.execute(
            "SELECT entry_hash FROM audit_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["entry_hash"] if row else "genesis"

    def chain(self, experiment_id: str) -> tuple[AuditEntry, ...]:
        """Every entry for one experiment, in the order it was written."""
        rows = self._conn.execute(
            "SELECT * FROM audit_entries WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()
        return tuple(self._row(r) for r in rows)

    def __iter__(self) -> Iterator[AuditEntry]:
        for row in self._conn.execute("SELECT * FROM audit_entries ORDER BY id"):
            yield self._row(row)

    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) c FROM audit_entries").fetchone()["c"])

    def experiments(self) -> tuple[str, ...]:
        rows = self._conn.execute(
            "SELECT DISTINCT experiment_id FROM audit_entries ORDER BY experiment_id"
        ).fetchall()
        return tuple(r["experiment_id"] for r in rows)

    def verify(self) -> bool:
        """Recompute the chain. False if any row was altered or removed.

        The last line of defence: even if the triggers were dropped and the
        table rewritten, the hashes will not line up.
        """
        prev = "genesis"
        for row in self._conn.execute("SELECT * FROM audit_entries ORDER BY id"):
            expected = _hash(
                prev, row["recorded_at"], row["world_id"], row["experiment_id"],
                row["stage"], row["actor"], row["payload"],
            )
            if expected != row["entry_hash"] or row["prev_hash"] != prev:
                return False
            prev = row["entry_hash"]
        return True

    def _row(self, row: sqlite3.Row) -> AuditEntry:
        return AuditEntry(
            id=row["id"],
            recorded_at=row["recorded_at"],
            world_id=row["world_id"],
            experiment_id=row["experiment_id"],
            stage=Stage(row["stage"]),
            actor=row["actor"],
            payload=json.loads(row["payload"]),
            prev_hash=row["prev_hash"],
            entry_hash=row["entry_hash"],
        )

    def close(self) -> None:
        self._conn.close()


def render_chain(log: AuditLog, experiment_id: str) -> str:
    """The decision chain, formatted for a human. What `make audit` prints."""
    entries = log.chain(experiment_id)
    if not entries:
        return f"No audit entries for {experiment_id!r}."

    lines = [
        "=" * 78,
        f"DECISION CHAIN — {experiment_id}",
        f"world: {entries[0].world_id}   entries: {len(entries)}   "
        f"chain intact: {'yes' if log.verify() else 'NO — TAMPERED'}",
        "=" * 78,
    ]
    for entry in entries:
        lines.append(f"\n[{entry.id}] {entry.stage.value.upper()}  ({entry.actor})  {entry.recorded_at}")
        for key, value in entry.payload.items():
            text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
            if len(text) > 240:
                text = text[:237] + "..."
            lines.append(f"      {key}: {text}")
        lines.append(f"      hash: {entry.entry_hash[:16]}  <- prev: {entry.prev_hash[:16]}")
    lines.append("\n" + "=" * 78)
    return "\n".join(lines)
