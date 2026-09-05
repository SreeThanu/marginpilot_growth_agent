"""The merchant request layer: what it may decide, and what it may never reach.

The economics are not re-derived here. Where a figure is asserted it is asserted
against the engine's own output or against a relationship between two of the
engine's outputs — never against a formula reimplemented in the test, which
would only prove the test and the adapter share a mistake.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from api import reprice as reprice_module
from api.reprice import RequestInadmissible, depth_ceiling, reprice
from demo.fixtures import FIXTURES, SCENARIO_A, SCENARIO_C, locked_fingerprint
from src.agent.decision_policy import recommend_from_raw

#: Scenario A's basket, from the fixture. The ceiling in rupees follows from it.
A_AOV = SCENARIO_A.aov_inr
A_CEILING_INR = A_AOV * depth_ceiling()


# --------------------------------------------------------------------------- #
# The new path is the old path
# --------------------------------------------------------------------------- #


def test_repricing_at_the_declared_amount_reproduces_the_fixture_decision() -> None:
    """The identity case. At Rs.120 the request layer must vanish.

    This is the assertion that makes the panel honest: if the re-priced path
    agreed with the fixture path everywhere *except* at the declared amount, the
    control would be demonstrating something other than the shipped decision.
    """
    from api import service

    result = reprice("A", SCENARIO_A.intervention_magnitude)

    assert result["status"] == "EVALUATED"
    assert result["request"]["is_declared_offer"] is True
    assert result["recommendation"] == service.scenario_detail("A")["initial"]


def test_the_request_reports_the_offer_the_engine_actually_priced() -> None:
    result = reprice("A", 60.0)
    request = result["request"]

    # Rs.60 on a Rs.600 basket. Read back off the brief, not computed here.
    assert request["incentive_cost_per_order_inr"] == pytest.approx(60.0)
    assert request["depth_at_observed_aov"] == pytest.approx(0.10)
    assert request["is_declared_offer"] is False
    # The lift is the model's, carried through unchanged from the proposal.
    assert request["expected_lift_absolute"] == SCENARIO_A.proposed_lift_absolute
    assert request["evidence_basis"] == SCENARIO_A.proposed_evidence_basis


# --------------------------------------------------------------------------- #
# Nothing the merchant can type reaches PROMOTE
# --------------------------------------------------------------------------- #


def test_no_admissible_incentive_reaches_promote() -> None:
    """Sweep the whole admissible domain in Rs.1 steps.

    Not a spot check. ``recommend_from_raw`` runs G1-G5 and has no branch that
    constructs PROMOTE; this proves the property holds across every value the
    control can produce rather than asserting the reading of the source.
    """
    seen = set()
    for rupees in range(0, int(A_CEILING_INR) + 1):
        decision = reprice("A", float(rupees))["recommendation"]["decision"]
        seen.add(decision)

    assert "PROMOTE" not in seen
    # And the sweep really did cross the interesting boundary, so a future
    # change that made every value refuse would not pass this quietly.
    assert seen == {"DO_NOT_PROMOTE", "RUN_EXPERIMENT_FIRST"}


def test_the_verdict_flips_exactly_once_as_the_offer_gets_cheaper() -> None:
    """Cheaper is never worse. A non-monotone control would be a bug."""
    decisions = [
        reprice("A", float(r))["recommendation"]["decision"]
        for r in range(0, int(A_CEILING_INR) + 1)
    ]
    flips = sum(1 for a, b in zip(decisions, decisions[1:]) if a != b)
    assert flips == 1
    assert decisions[0] == "RUN_EXPERIMENT_FIRST"
    assert decisions[-1] == "DO_NOT_PROMOTE"


@pytest.mark.parametrize(
    "amount,decision",
    [
        (120.0, "DO_NOT_PROMOTE"),
        (60.0, "DO_NOT_PROMOTE"),
        (40.0, "DO_NOT_PROMOTE"),
        (37.0, "RUN_EXPERIMENT_FIRST"),
        (20.0, "RUN_EXPERIMENT_FIRST"),
    ],
)
def test_representative_offers_decide_as_the_engine_says(
    amount: float, decision: str
) -> None:
    """Regression expectations produced by the engine, not chosen for the demo."""
    assert reprice("A", amount)["recommendation"]["decision"] == decision


def test_a_refused_offer_names_the_gate_that_refused_it() -> None:
    recommendation = reprice("A", 120.0)["recommendation"]
    assert recommendation["binding_constraints"] == ["G2_NEGATIVE_EXPECTED_NET"]
    assert recommendation["gates_passed"] == ["G1"]

    unreachable = reprice("A", 132.0)["recommendation"]
    assert unreachable["binding_constraints"] == ["G2_BREAK_EVEN_UNREACHABLE"]
    assert unreachable["required_break_even_lift_absolute"] is None


def test_a_recommended_experiment_carries_its_cost_and_its_open_question() -> None:
    """The G4 moment: the experiment can cost more than the campaign it clears.

    Asserted as a relationship between two engine outputs, so the test states
    the finding without inventing either number.
    """
    recommendation = reprice("A", 37.0)["recommendation"]

    assert recommendation["decision"] == "RUN_EXPERIMENT_FIRST"
    assert recommendation["experiment_required"] is True
    assert recommendation["experiment_horizon_per_arm"] > 0
    assert recommendation["experiment_cost_inr"] > 0
    assert "G4_VALUE_OF_INFORMATION_UNRESOLVED" in recommendation["unresolved"]
    # Just past the flip the pilot costs more than the campaign it would clear.
    assert (
        recommendation["experiment_cost_inr"]
        > recommendation["expected_net_contribution_inr"]
    )


# --------------------------------------------------------------------------- #
# Admissibility — refused, never clamped
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "amount", [-0.01, -50.0, float("nan"), float("inf"), -float("inf")]
)
def test_a_malformed_incentive_is_refused(amount: float) -> None:
    with pytest.raises(RequestInadmissible):
        reprice("A", amount)


@pytest.mark.parametrize("amount", [150.01, 151.0, 300.0, 100_000.0])
def test_an_incentive_above_the_ceiling_is_refused_by_the_policy_rule(
    amount: float,
) -> None:
    with pytest.raises(RequestInadmissible) as caught:
        reprice("A", amount)

    violation = caught.value.violation
    assert violation is not None, "the refusal must carry the rule that fired"
    assert violation.rule.value == "max_discount"
    assert violation.limit == depth_ceiling()
    assert violation.observed > depth_ceiling()


def test_the_ceiling_is_a_refusal_and_never_a_silent_clamp() -> None:
    """Rs.300 and Rs.100,000 both clamp to depth 0.5 inside the schema.

    If either were priced instead of refused, the panel would show a plausible
    figure for a request nobody could make. Both must refuse, and the refusal
    must distinguish them.
    """
    reasons = []
    for amount in (300.0, 100_000.0):
        with pytest.raises(RequestInadmissible) as caught:
            reprice("A", amount)
        reasons.append(caught.value.reason)

    assert all("above the standing ceiling" in r for r in reasons)
    assert "Rs.300" in reasons[0] and "Rs.100,000" in reasons[1]


def test_the_last_admissible_rupee_is_still_priced() -> None:
    """The boundary is closed on the admissible side, not off by one."""
    result = reprice("A", A_CEILING_INR)
    assert result["status"] == "EVALUATED"
    assert result["request"]["depth_at_observed_aov"] == pytest.approx(depth_ceiling())


def test_the_refusal_is_not_one_of_the_three_decisions() -> None:
    with pytest.raises(RequestInadmissible) as caught:
        reprice("A", 151.0)

    payload = reprice_module.inadmissible_payload("A", 151.0, caught.value)
    assert payload["status"] == "REQUEST_INADMISSIBLE"
    assert payload["recommendation"] is None
    assert payload["refusal"]["refused_by"] == "src/policy/gates.py::check_discount"
    # The gate's own wording is carried, imprecise rounding and all.
    assert payload["refusal"]["engine_message"].startswith("REJECTED")


def test_an_offer_priced_as_a_fraction_is_declined_rather_than_converted() -> None:
    """Scenario B is 12% off. A rupee amount has no meaning against it."""
    with pytest.raises(RequestInadmissible) as caught:
        reprice("B", 50.0)
    assert "not in rupees" in caught.value.reason
    assert caught.value.violation is None


# --------------------------------------------------------------------------- #
# Nothing is mutated, and nothing is recorded
# --------------------------------------------------------------------------- #


def test_repricing_never_mutates_a_fixture() -> None:
    before_c, before_a = SCENARIO_C.fingerprint(), SCENARIO_A.fingerprint()

    for amount in (0.0, 20.0, 37.0, 120.0, 150.0):
        reprice("A", amount)
    for bad in (-1.0, 500.0):
        with pytest.raises(RequestInadmissible):
            reprice("A", bad)

    assert SCENARIO_C.fingerprint() == before_c == locked_fingerprint()
    assert SCENARIO_A.fingerprint() == before_a
    assert SCENARIO_A.intervention_magnitude == 120.0


def test_the_cached_view_is_copied_not_edited() -> None:
    """A dragged control must not leave the previous amount behind."""
    view = reprice_module._view("A")
    original = view.interventions[0].flat_discount_inr

    reprice("A", 20.0)
    reprice("A", 90.0)

    assert reprice_module._view("A").interventions[0].flat_discount_inr == original
    assert reprice_module._view("A") is view


def test_repricing_preserves_the_arity_of_the_intervention_tuple() -> None:
    """The brief the policy reads is the fixture's brief with one number moved."""
    view = reprice_module._view("A")
    brief = reprice_module._repriced_brief(FIXTURES["A"], 55.0)

    assert len(brief.interventions) == len(view.interventions)
    assert [i.intervention_id for i in brief.interventions] == [
        i.intervention_id for i in view.interventions
    ]


def test_repricing_writes_no_audit_entry() -> None:
    """An evaluation is not an execution. There is nothing to record."""
    from api import service

    before = service.audit_trail("A")
    for amount in (20.0, 60.0, 120.0):
        reprice("A", amount)
    after = service.audit_trail("A")

    assert len(after["entries"]) == len(before["entries"])
    assert after["head_hash"] == before["head_hash"]
    assert after["verified"] is True


# --------------------------------------------------------------------------- #
# The structural boundary
# --------------------------------------------------------------------------- #

#: What the request layer may never reach. ``FixtureExecutor`` generates
#: observations from ``declared_true_lift_absolute``, and ``run_scenario`` drives
#: it. Either import would put a user-facing control upstream of ground truth.
FORBIDDEN_NAMES = frozenset(
    {
        "FixtureExecutor",
        "run_scenario",
        "declared_true_lift_absolute",
        "decide_after_experiment",
        "evaluate",
        "ExperimentRegistry",
    }
)

FORBIDDEN_MODULES = frozenset({"demo.run_scenarios", "src.audit", "src.eval.harness"})


def _imported(path: Path) -> tuple[set[str], set[str]]:
    """Every module and every bound name imported by ``path``, via its AST.

    An AST walk rather than a grep: a textual scan is defeated by the word
    appearing in this module's own docstring, which it does, on purpose.
    """
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    modules: set[str] = set()
    names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            modules.add(base)
            for alias in node.names:
                names.add(alias.asname or alias.name)
                modules.add(f"{base}.{alias.name}")

    return modules, names


def test_the_request_layer_cannot_reach_ground_truth() -> None:
    source = Path(reprice_module.__file__)
    modules, names = _imported(source)

    assert not (names & FORBIDDEN_NAMES), (
        f"api/reprice.py imports {sorted(names & FORBIDDEN_NAMES)}, which would put "
        "a merchant-facing control upstream of the fixture's declared response"
    )
    assert not (modules & FORBIDDEN_MODULES)

    # The AST is the assertion, but the words really are present in the prose,
    # which is what makes a grep-based version of this test useless.
    assert "FixtureExecutor" in source.read_text("utf-8")


def test_the_request_layer_reaches_the_policy_only_through_recommend_from_raw() -> None:
    _, names = _imported(Path(reprice_module.__file__))
    assert "recommend_from_raw" in names
    assert reprice_module.recommend_from_raw is recommend_from_raw


def test_no_response_field_names_a_forbidden_quantity() -> None:
    """Ground truth cannot leave by the new surface, whatever it is called."""
    from src.agent.recommendation import FORBIDDEN_PROPOSAL_TOKENS

    blob = repr(reprice("A", 37.0)).lower()
    for token in FORBIDDEN_PROPOSAL_TOKENS:
        assert token not in blob, f"the reprice payload leaks {token!r}"


def test_the_declared_true_lift_never_appears_in_a_response() -> None:
    """The strongest form: the fixture's own response is a number, not a name."""
    true_lift = SCENARIO_A.declared_true_lift_absolute
    assert true_lift == 0.05  # guard: if the fixture moved, this test is stale

    for amount in (20.0, 37.0, 120.0):
        request = reprice("A", amount)["request"]
        assert request["expected_lift_absolute"] != true_lift
        assert request["expected_lift_absolute"] == SCENARIO_A.proposed_lift_absolute


def test_the_incentive_is_the_only_thing_a_request_can_change() -> None:
    """Everything else on the panel is fixed by the merchant record."""
    fixed = (
        "observed_conversion",
        "observed_aov_inr",
        "observed_margin",
        "budget_inr",
        "population",
        "expected_lift_absolute",
        "evidence_basis",
        "cohort_id",
        "cohort_customers",
    )
    baseline = reprice("A", 120.0)["request"]
    for amount in (0.0, 20.0, 90.0, 150.0):
        request = reprice("A", amount)["request"]
        for field in fixed:
            assert request[field] == baseline[field], f"{field} moved with the incentive"


def test_a_reprice_is_reproducible() -> None:
    assert reprice("A", 33.0) == reprice("A", 33.0)


@pytest.mark.parametrize("amount", [0.0, 20.0, 120.0, 150.0])
def test_every_admissible_response_is_json_serialisable(amount: float) -> None:
    import json

    payload = json.loads(json.dumps(reprice("A", amount)))
    assert math.isfinite(payload["recommendation"]["expected_net_contribution_inr"])
