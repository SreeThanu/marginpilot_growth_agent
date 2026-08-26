"""Append-only, and provably so. CLAUDE.md invariant 6."""

from __future__ import annotations

import inspect
import sqlite3

import pytest

from src.audit.log import AuditLog, Stage, render_chain


@pytest.fixture()
def log(tmp_path):
    return AuditLog(tmp_path / "audit.db")


def _entry(log, experiment_id="exp_1", stage=Stage.INTENT, **payload):
    return log.append(
        world_id="world_00001", experiment_id=experiment_id, stage=stage,
        actor="test", payload=payload or {"note": "x"},
    )


def test_the_log_exposes_no_mutation_path() -> None:
    """The absent methods are the enforcement."""
    forbidden = {"update", "delete", "remove", "edit", "amend", "revise", "drop", "truncate", "set"}
    public = [n for n, _ in inspect.getmembers(AuditLog, callable) if not n.startswith("_")]
    for name in public:
        assert not any(word in name.lower() for word in forbidden), (
            f"AuditLog.{name} looks like a mutation path; the log is append-only"
        )


def test_update_is_refused_by_the_database(log) -> None:
    """Not just absent from the API — impossible at the storage layer, so a
    stray sqlite3 session cannot rewrite a decision either."""
    _entry(log)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        log._conn.execute("UPDATE audit_entries SET actor = 'someone else' WHERE id = 1")


def test_delete_is_refused_by_the_database(log) -> None:
    _entry(log)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        log._conn.execute("DELETE FROM audit_entries WHERE id = 1")


def test_entries_chain_by_hash(log) -> None:
    first = _entry(log)
    second = _entry(log, stage=Stage.POLICY_VERDICT)
    assert first.prev_hash == "genesis"
    assert second.prev_hash == first.entry_hash
    assert log.verify()


def test_tampering_breaks_the_chain(log, tmp_path) -> None:
    """Even if the triggers were dropped, edited history does not verify."""
    _entry(log)
    _entry(log, stage=Stage.OUTCOME)
    assert log.verify()

    raw = sqlite3.connect(str(tmp_path / "audit.db"))
    raw.execute("DROP TRIGGER audit_no_update")
    raw.execute("UPDATE audit_entries SET payload = '{\"note\": \"rewritten\"}' WHERE id = 1")
    raw.commit()
    raw.close()

    assert AuditLog(tmp_path / "audit.db").verify() is False


def test_a_rejection_is_logged_as_fully_as_an_approval(log) -> None:
    """A log that records only what happened cannot show what was prevented."""
    _entry(log, stage=Stage.POLICY_VERDICT, approved=False,
           rule="max_discount", observed=0.40, limit=0.25)
    entry = log.chain("exp_1")[0]
    assert entry.payload["approved"] is False
    assert entry.payload["rule"] == "max_discount"
    assert entry.payload["observed"] == 0.40


def test_the_chain_reads_in_order_and_renders(log) -> None:
    for stage in (Stage.INTENT, Stage.POLICY_VERDICT, Stage.RANDOMIZATION,
                  Stage.EXECUTION, Stage.OUTCOME):
        _entry(log, stage=stage)
    chain = log.chain("exp_1")
    assert [e.stage for e in chain] == [
        Stage.INTENT, Stage.POLICY_VERDICT, Stage.RANDOMIZATION,
        Stage.EXECUTION, Stage.OUTCOME,
    ]
    rendered = render_chain(log, "exp_1")
    assert "DECISION CHAIN" in rendered
    assert "chain intact: yes" in rendered


def test_entries_for_other_experiments_do_not_leak_into_a_chain(log) -> None:
    _entry(log, experiment_id="exp_1")
    _entry(log, experiment_id="exp_2")
    assert len(log.chain("exp_1")) == 1
    assert set(log.experiments()) == {"exp_1", "exp_2"}
