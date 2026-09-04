"""Write the recommendation the demo is showing into the project's audit log.

A demo-side wrapper and nothing more. ``src/audit/log.py`` is used exactly as it
already exists — same ``append()``, same ``Stage`` values, same hash chain, no
extra fields, no parallel implementation — and ``src/agent/decision_policy.py``
is untouched, so the audited decision path is byte-identical to the one the
boundary audit signed off.

**The record must be the decision on screen.** A chain of unrelated-but-valid
entries would render a green tick while proving nothing about the recommendation
beside it. So the payloads passed to ``append()`` are the *same dict objects* the
view renders, and :attr:`AuditTrail.payload_is_the_rendered_object` carries the
identity check through to the UI, where it is displayed rather than asserted in
a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.audit.log import AuditEntry, AuditLog, Stage, render_chain


@dataclass(frozen=True, slots=True)
class AuditTrail:
    """What the log recorded for one recommendation, and its own verdict on it."""

    experiment_id: str
    entries: tuple[AuditEntry, ...]
    verified: bool
    rendered: str
    #: True when the audited payload is the very dict the view is rendering —
    #: identity, not equality.
    payload_is_the_rendered_object: bool

    @property
    def head_hash(self) -> str:
        return self.entries[-1].entry_hash if self.entries else ""


def audit_recommendation(record: dict[str, Any]) -> AuditTrail:
    """Append one scenario's decision to a fresh in-memory chain.

    ``record`` is what :func:`demo.run_scenarios.run_scenario` returned. Its
    ``initial`` and ``final`` dicts are the objects the view displays, and they
    are what gets written — passed by reference, not rebuilt.

    In-memory because a demo should not accumulate state between runs, and
    because ``src/eval/adversarial.py`` already uses ``":memory:"`` for the same
    reason. The append-only guarantee is enforced by SQLite triggers inside the
    schema, so it holds here exactly as it holds on disk.
    """
    initial = record["initial"]
    final = record["final"]
    world_id = f"demo_scenario_{record['scenario']}"
    experiment = record.get("experiment")
    experiment_id = (
        experiment["experiment_id"] if experiment else f"{world_id}_recommendation"
    )

    log = AuditLog(":memory:")
    entries: list[AuditEntry] = [
        log.append(
            world_id=world_id,
            experiment_id=experiment_id,
            stage=Stage.INTENT,
            actor="demo.run_scenarios :: proposal assessed",
            payload=initial,
        )
    ]

    if experiment is not None:
        entries.append(
            log.append(
                world_id=world_id,
                experiment_id=experiment_id,
                stage=Stage.EXECUTION,
                actor="src.experiment.registry :: pilot launched and read at horizon",
                payload=experiment,
            )
        )

    entries.append(
        log.append(
            world_id=world_id,
            experiment_id=experiment_id,
            stage=Stage.POLICY_VERDICT,
            actor="src.agent.decision_policy :: deterministic gates",
            payload=final,
        )
    )

    return AuditTrail(
        experiment_id=experiment_id,
        entries=tuple(entries),
        verified=log.verify(),
        rendered=render_chain(log, experiment_id),
        payload_is_the_rendered_object=entries[-1].payload is final,
    )


#: Deliberately malformed proposals for the graceful-failure control.
#:
#: These are *inputs*, not logic: each is fed to the existing
#: ``recommend_from_raw``, which owns every rule about what a valid proposal is.
#: Nothing here validates anything.
MALFORMED_PROPOSALS: dict[str, dict[str, Any]] = {
    "Empty reply": {},
    "Missing required fields": {"intervention_id": "demo_free_shipping"},
    "No citations": {
        "intervention_id": "demo_free_shipping",
        "cohort_id": "ALL",
        "expected_lift_absolute": 0.03,
        "evidence_basis": "HISTORY",
        "hypothesis": "Waiving the fee will lift conversion.",
        "mechanism": "Support tickets mention the delivery fee.",
        "citations": [],
    },
    "Ground truth injected": {
        "intervention_id": "demo_free_shipping",
        "cohort_id": "ALL",
        "expected_lift_absolute": 0.03,
        "evidence_basis": "EXPERIMENT",
        "hypothesis": "y1 minus y0 is positive for this cohort.",
        "mechanism": "The ground_truth shows a lift.",
        "citations": ["ground_truth"],
    },
    "Hidden segment identity": {
        "intervention_id": "demo_free_shipping",
        "cohort_id": "segment_name:Deal seekers",
        "expected_lift_absolute": 0.03,
        "evidence_basis": "HISTORY",
        "hypothesis": "Target the deal-seeking archetype.",
        "mechanism": "That segment responds to discounts.",
        "citations": ["segments"],
    },
    "Impossible lift (250%)": {
        "intervention_id": "demo_free_shipping",
        "cohort_id": "ALL",
        "expected_lift_absolute": 2.5,
        "evidence_basis": "PRIOR",
        "hypothesis": "This will triple conversion.",
        "mechanism": "Free shipping is very popular.",
        "citations": ["interventions"],
    },
}
