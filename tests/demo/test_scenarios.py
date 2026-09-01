"""The three demonstration scenarios, end to end.

DEMONSTRATION FIXTURES — NOT RESEARCH EVIDENCE. These tests assert the decision
*path*, never that a particular economic outcome is a fact about merchants.
"""

from __future__ import annotations

import io
import runpy
import sys
from contextlib import redirect_stdout

import pytest

from demo.fixtures import FIXTURE_LABEL, SCENARIO_A, SCENARIO_B, SCENARIO_C
from demo.run_scenarios import run_scenario
from src.agent.recommendation import (
    UNRESOLVED_VALUE_OF_INFORMATION,
    RecommendationDecision,
)


@pytest.fixture(scope="module")
def scenario_c():
    return run_scenario(SCENARIO_C)


def test_scenario_a_refuses_a_promotion_that_cannot_pay() -> None:
    record = run_scenario(SCENARIO_A)
    final = record["final"]
    assert final["decision"] == RecommendationDecision.DO_NOT_PROMOTE.value
    assert final["expected_net_contribution_inr"] < 0
    assert record["experiment"] is None, "a losing campaign should not be tested"


def test_scenario_b_asks_for_an_experiment_instead_of_guessing() -> None:
    record = run_scenario(SCENARIO_B)
    final = record["final"]
    assert final["decision"] == RecommendationDecision.RUN_EXPERIMENT_FIRST.value
    assert final["expected_net_contribution_inr"] > 0
    assert final["experiment_required"] is True
    assert final["experiment_horizon_per_arm"] > 0
    assert UNRESOLVED_VALUE_OF_INFORMATION in final["unresolved"]


def test_scenario_c_starts_by_asking_for_an_experiment(scenario_c) -> None:
    """PROMOTE must never come from the prior."""
    assert scenario_c["initial"]["decision"] == (
        RecommendationDecision.RUN_EXPERIMENT_FIRST.value
    )


def test_scenario_c_runs_a_real_experiment_through_the_real_machinery(scenario_c) -> None:
    exp = scenario_c["experiment"]
    assert exp is not None
    assert exp["verdict_eligible"] is True, "the pilot must reach its horizon"
    assert {arm["name"] for arm in exp["arms"]} == {"control", "treatment"}
    assert all(arm["n_assigned"] == exp["horizon_per_arm"] for arm in exp["arms"])


def test_scenario_c_reaches_promote_only_through_g6(scenario_c) -> None:
    final = scenario_c["final"]
    assert final["decision"] == RecommendationDecision.PROMOTE.value
    assert "G6" in final["gates_passed"], "PROMOTE without the rollout gate"
    assert final["expected_net_contribution_inr"] > 0
    assert final["evidence_basis"] == "EXPERIMENT"
    assert not final["binding_constraints"]


def test_adv11_the_unresolved_gate_is_visible_to_the_merchant() -> None:
    """It must not exist only as an internal field."""
    buffer = io.StringIO()
    argv = sys.argv
    sys.argv = ["run_scenarios", "--scenario", "B"]
    try:
        with redirect_stdout(buffer):
            runpy.run_module("demo.run_scenarios", run_name="__main__")
    finally:
        sys.argv = argv
    rendered = buffer.getvalue()
    assert UNRESOLVED_VALUE_OF_INFORMATION in rendered, (
        "the open value-of-information question was hidden from the merchant"
    )


def test_every_scenario_is_labelled_as_a_demonstration_fixture() -> None:
    for spec in (SCENARIO_A, SCENARIO_B, SCENARIO_C):
        assert run_scenario(spec, run_experiment=False)["label"] == FIXTURE_LABEL


def test_the_demo_imports_no_research_or_ground_truth_module() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    for relative in ("demo/fixtures/__init__.py", "demo/run_scenarios.py",
                     "demo/recommendation_app.py"):
        source = (root / relative).read_text(encoding="utf-8")
        for banned in ("load_ground_truth", "src.eval.oracle", "src.eval.replay",
                       "src.eval.harness", "src.eval.devcorpus", "analysis.posthoc",
                       "worlds_cycle2", "final_eval"):
            assert banned not in source, f"{relative} references {banned}"
