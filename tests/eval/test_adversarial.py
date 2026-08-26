"""Every adversarial scenario must refuse. These are demo material and tests."""

from __future__ import annotations

import pytest

from src.audit.log import AuditLog
from src.eval.adversarial import SCENARIOS, ScenarioResult, run_all


def test_there_are_seven_scenarios_matching_the_readme_table() -> None:
    assert len(SCENARIOS) == 7


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.__name__)
def test_each_scenario_refuses(scenario) -> None:
    result = (
        scenario(":memory:") if "tmp_path" in scenario.__code__.co_varnames else scenario()
    )
    assert isinstance(result, ScenarioResult)
    assert result.refused, f"{result.name} did not refuse: {result.reason}"
    assert result.refused_by != "none"
    assert result.reason.strip(), "a refusal must carry a reason"


def test_every_refusal_names_the_component_that_refused_it() -> None:
    for result in run_all():
        assert "src/" in result.refused_by, (
            f"{result.name} does not say which module refused it; a refusal a "
            "reviewer cannot locate is not auditable"
        )


def test_refusals_are_written_to_the_audit_trail(tmp_path) -> None:
    audit = AuditLog(tmp_path / "audit.db")
    results = run_all(audit=audit, db_path=":memory:")

    assert len(audit) == len(results)
    assert audit.verify()
    for entry in audit:
        assert entry.payload["refused"] is True
        assert entry.payload["reason"]
