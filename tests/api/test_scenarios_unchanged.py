"""The pinned A/B/C record must survive the merchant request layer untouched.

``tests/api/golden/scenario_*.json`` was captured from ``api.service`` on the
branch point, **before** the first edit of this feature. That ordering is the
whole value of the file: a snapshot taken afterwards would agree with whatever
the code now does and prove nothing.

Every figure in the submission video is read off these three payloads, so the
assertion is equality of the whole object rather than of a chosen field. A
regression that moved a number this test did not think to name would otherwise
pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api import service

GOLDEN = Path(__file__).resolve().parent / "golden"

#: The headline figures, restated here in the form a reviewer would check them.
#: Redundant with the golden files by design — if a payload and this table ever
#: disagree, one of the two was edited to fit the other.
HEADLINES = {
    "A": ("DO_NOT_PROMOTE", -345_600.0, 158_400.0, 504_000.0, 1.0),
    "B": ("RUN_EXPERIMENT_FIRST", 97_200.0, 648_000.0, 550_800.0, 0.06),
    "C": ("PROMOTE", 151_003.84, 250_417.12, 99_413.28, None),
}


@pytest.mark.parametrize("scenario_id", ["A", "B", "C"])
def test_the_scenario_payload_matches_the_pre_edit_snapshot(scenario_id: str) -> None:
    expected = json.loads((GOLDEN / f"scenario_{scenario_id}.json").read_text("utf-8"))
    assert service.scenario_detail(scenario_id) == expected


@pytest.mark.parametrize("scenario_id", ["A", "B", "C"])
def test_the_headline_figures_are_what_the_video_shows(scenario_id: str) -> None:
    decision, net, incremental, cost, break_even = HEADLINES[scenario_id]
    final = service.scenario_detail(scenario_id)["final"]

    assert final["decision"] == decision
    assert final["expected_net_contribution_inr"] == pytest.approx(net)
    assert final["expected_incremental_contribution_inr"] == pytest.approx(incremental)
    assert final["expected_incentive_cost_inr"] == pytest.approx(cost)
    if break_even is None:
        assert final["required_break_even_lift_absolute"] is None
    else:
        assert final["required_break_even_lift_absolute"] == pytest.approx(break_even)


def test_scenario_b_sizes_its_experiment_as_recorded() -> None:
    final = service.scenario_detail("B")["final"]
    assert final["experiment_horizon_per_arm"] == 2_604
    assert final["experiment_cost_inr"] == pytest.approx(47_809.44)
    assert "G4_VALUE_OF_INFORMATION_UNRESOLVED" in final["unresolved"]


def test_scenario_c_still_earns_its_rollout_through_a_measurement() -> None:
    detail = service.scenario_detail("C")
    final, comparison = detail["final"], detail["experiment"]["comparison"]

    assert final["decision"] == "PROMOTE"
    assert final["customers_treated"] == 14_313
    assert "G6" in final["gates_passed"]
    assert comparison["absolute_difference"] == pytest.approx(0.032400, abs=5e-6)
    assert comparison["difference_ci_low"] == pytest.approx(0.017175, abs=5e-6)
    assert comparison["difference_ci_high"] == pytest.approx(0.047624, abs=5e-6)
    assert comparison["probability_net_positive"] == pytest.approx(0.99633, abs=5e-6)
