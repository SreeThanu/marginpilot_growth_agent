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


def test_repricing_preserves_the_shape_of_the_brief() -> None:
    """The stated brief is the fixture's brief with numbers moved, not a variant.

    Both are built by ``build_view`` from a ``FixtureSpec``, so the intervention
    tuple, the cohort split and every other structural feature come from one
    constructor. A brief the policy reads must not differ in shape from the one
    the fixture path produces, or the two are not comparable.
    """
    from src.agent.brief import build_brief

    fixture = build_brief(reprice_module._view("A"))
    stated = reprice_module._stated_brief(
        FIXTURES["A"],
        reprice_module.MerchantConditions(incentive_inr=55.0),
    )

    assert [i.intervention_id for i in stated.interventions] == [
        i.intervention_id for i in fixture.interventions
    ]
    assert [c.cohort_id for c in stated.cohorts] == [
        c.cohort_id for c in fixture.cohorts
    ]
    assert len(stated.cohort_economics) == len(fixture.cohort_economics)
    assert len(stated.history) == len(fixture.history)


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


# --------------------------------------------------------------------------- #
# Merchant-stated business conditions
# --------------------------------------------------------------------------- #

#: The five conditions beyond the incentive, with a value that differs from
#: Scenario A's own figure, and the brief field each must land on.
STATED_CONDITIONS = {
    "population": (10_000, "population"),
    "aov_inr": (1_200.0, "observed_aov_inr"),
    "margin": (0.45, "observed_margin"),
    "observed_conversion": (0.05, "observed_conversion"),
    "budget_inr": (250_000.0, "budget_inr"),
}


@pytest.mark.parametrize("field,value_and_target", sorted(STATED_CONDITIONS.items()))
def test_a_stated_condition_reaches_the_brief(field, value_and_target) -> None:
    """Each condition must arrive at the merchant record the policy reads."""
    value, brief_field = value_and_target
    request = reprice("A", 120.0, **{field: value})["request"]

    assert request[brief_field] == pytest.approx(value)
    assert field in request["stated"]
    assert request["is_declared_request"] is False


def test_omitting_every_condition_is_the_declared_request() -> None:
    """The default panel state must still be the shipped Scenario A request."""
    from api import service

    result = reprice("A", SCENARIO_A.intervention_magnitude)

    assert result["request"]["is_declared_request"] is True
    assert result["recommendation"] == service.scenario_detail("A")["initial"]


def test_stating_a_condition_at_its_declared_value_changes_nothing() -> None:
    """Restating the record's own figure is not a change to it."""
    explicit = reprice(
        "A",
        SCENARIO_A.intervention_magnitude,
        population=SCENARIO_A.population,
        aov_inr=SCENARIO_A.aov_inr,
        margin=SCENARIO_A.margin,
        observed_conversion=SCENARIO_A.observed_conversion,
        budget_inr=SCENARIO_A.budget_inr,
    )
    assert explicit["request"]["is_declared_request"] is True
    assert explicit["recommendation"] == reprice("A", 120.0)["recommendation"]


def test_aov_moves_contribution_per_order() -> None:
    """Contribution per order is AOV times margin, computed by the engine."""
    at600 = reprice("A", 120.0, aov_inr=600.0)["request"]
    at1200 = reprice("A", 120.0, aov_inr=1_200.0)["request"]

    assert at600["contribution_per_order_inr"] == pytest.approx(132.0)
    assert at1200["contribution_per_order_inr"] == pytest.approx(264.0)
    # A richer basket earns more per order against the same flat incentive, so
    # the lift needed to break even falls. Asserted as a direction, not a value.
    a = reprice("A", 120.0, aov_inr=600.0)["recommendation"]
    b = reprice("A", 120.0, aov_inr=1_200.0)["recommendation"]
    assert (
        b["required_break_even_lift_absolute"]
        < a["required_break_even_lift_absolute"]
    )


def test_margin_moves_contribution_per_order() -> None:
    thin = reprice("A", 120.0, margin=0.22)["request"]
    fat = reprice("A", 120.0, margin=0.45)["request"]

    assert thin["contribution_per_order_inr"] == pytest.approx(132.0)
    assert fat["contribution_per_order_inr"] == pytest.approx(270.0)
    assert fat["incentive_cost_per_order_inr"] == thin["incentive_cost_per_order_inr"]


def test_eligible_customers_scale_the_campaign_not_its_unit_economics() -> None:
    """Population scales totals. Per-order figures and break-even do not move."""
    big = reprice("A", 120.0, population=30_000)
    small = reprice("A", 120.0, population=10_000)

    assert small["request"]["cohort_customers"] == 10_000
    assert (
        small["recommendation"]["required_break_even_lift_absolute"]
        == big["recommendation"]["required_break_even_lift_absolute"]
    )
    assert small["recommendation"]["expected_net_contribution_inr"] == pytest.approx(
        big["recommendation"]["expected_net_contribution_inr"] / 3.0
    )


def test_budget_is_a_deterministic_constraint_not_an_economic_input() -> None:
    """Budget cannot change what a promotion earns, only whether it may be tested."""
    rich = reprice("A", 30.0, budget_inr=400_000.0)["recommendation"]
    poor = reprice("A", 30.0, budget_inr=10_000.0)["recommendation"]

    assert rich["expected_net_contribution_inr"] == poor["expected_net_contribution_inr"]
    assert rich["decision"] == "RUN_EXPERIMENT_FIRST"
    assert poor["decision"] == "DO_NOT_PROMOTE"
    assert "G4_EXPERIMENT_UNAFFORDABLE" in poor["binding_constraints"]


def test_baseline_conversion_moves_break_even_through_the_engine() -> None:
    """Break-even is p0*I/(C-I); halving p0 halves it. The engine computes it."""
    high = reprice("A", 120.0, observed_conversion=0.10)["recommendation"]
    low = reprice("A", 120.0, observed_conversion=0.05)["recommendation"]

    assert low["required_break_even_lift_absolute"] == pytest.approx(
        high["required_break_even_lift_absolute"] / 2.0
    )


def test_stated_conditions_reach_the_policy_gates() -> None:
    """Each gate must be reachable from a business condition, not just from G2."""
    exposure = reprice("A", 30.0, population=8_000)["recommendation"]
    assert "max_customer_exposure" in exposure["binding_constraints"]

    floor = reprice("A", 5.0, margin=0.14)["recommendation"]
    assert "min_contribution_margin" in floor["binding_constraints"]

    unaffordable = reprice("A", 30.0, budget_inr=10_000.0)["recommendation"]
    assert "G4_EXPERIMENT_UNAFFORDABLE" in unaffordable["binding_constraints"]


# --------------------------------------------------------------------------- #
# What the merchant may not state
# --------------------------------------------------------------------------- #


def test_expected_lift_is_not_a_parameter() -> None:
    """There is no route through this surface that sets the demand hypothesis."""
    import inspect

    accepted = set(inspect.signature(reprice).parameters)
    for forbidden in (
        "expected_lift_absolute", "expected_lift", "lift",
        "evidence_basis", "evidence", "declared_true_lift_absolute",
    ):
        assert forbidden not in accepted

    with pytest.raises(TypeError):
        reprice("A", 120.0, expected_lift_absolute=0.5)  # type: ignore[call-arg]


def test_the_hypothesis_is_invariant_under_every_stated_condition() -> None:
    """Business conditions move economics. They must never move the hypothesis."""
    baseline = reprice("A", 120.0)["request"]

    for field, (value, _) in STATED_CONDITIONS.items():
        request = reprice("A", 37.0, **{field: value})["request"]
        assert request["expected_lift_absolute"] == baseline["expected_lift_absolute"]
        assert request["evidence_basis"] == baseline["evidence_basis"]
        assert request["hypothesis"] == baseline["hypothesis"]


def test_merchant_conditions_carries_no_outcome_field() -> None:
    """The input object itself must not have somewhere to put an outcome."""
    from dataclasses import fields as dataclass_fields

    names = {f.name for f in dataclass_fields(reprice_module.MerchantConditions)}
    assert names == {
        "incentive_inr", "population", "aov_inr", "margin",
        "observed_conversion", "budget_inr",
    }


# --------------------------------------------------------------------------- #
# Admissibility of the stated conditions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs",
    [
        {"population": 0},
        {"population": -5},
        {"population": 1.5},
        {"population": reprice_module.MAX_POPULATION + 1},
        {"aov_inr": 0.0},
        {"aov_inr": -600.0},
        {"aov_inr": float("inf")},
        {"aov_inr": float("nan")},
        {"margin": 1.5},
        {"margin": -0.2},
        {"margin": float("nan")},
        {"observed_conversion": 0.0},
        {"observed_conversion": 1.5},
        {"observed_conversion": -0.1},
        {"observed_conversion": float("nan")},
        {"budget_inr": -1.0},
        {"budget_inr": float("nan")},
    ],
)
def test_an_impossible_condition_is_refused(kwargs) -> None:
    with pytest.raises(RequestInadmissible):
        reprice("A", 120.0, **kwargs)


def test_a_refused_condition_is_never_clamped_into_range() -> None:
    """The refusal must not be followed by an answer to a different question."""
    with pytest.raises(RequestInadmissible) as caught:
        reprice("A", 120.0, population=reprice_module.MAX_POPULATION * 10)

    # And the cap is disclosed as a limit of the tool, not of the policy.
    assert "not of the policy" in caught.value.reason
    assert caught.value.violation is None


def test_the_engine_states_its_own_bounds() -> None:
    """Margin range is checked in src/economics, and its wording is reported."""
    with pytest.raises(RequestInadmissible) as caught:
        reprice("A", 120.0, margin=1.5)
    assert "contribution_margin must be in [0, 1]" in caught.value.reason


def test_the_boundary_values_are_admissible() -> None:
    """Closed on the admissible side: 1 customer, 100% conversion, zero budget."""
    assert reprice("A", 120.0, population=1)["status"] == "EVALUATED"
    assert reprice("A", 120.0, observed_conversion=1.0)["status"] == "EVALUATED"
    assert reprice("A", 120.0, budget_inr=0.0)["status"] == "EVALUATED"
    assert (
        reprice("A", 120.0, population=reprice_module.MAX_POPULATION)["status"]
        == "EVALUATED"
    )


# --------------------------------------------------------------------------- #
# The PROMOTE boundary, across the whole stated space
# --------------------------------------------------------------------------- #


def test_no_combination_of_stated_conditions_reaches_promote() -> None:
    """A grid over every merchant-controlled input. PROMOTE must stay unreachable.

    The single-variable sweep proves the incentive cannot buy a rollout. This
    proves the other five cannot either, alone or together — spending still
    requires a measured result at a pre-committed horizon, which this path has
    no route to.
    """
    import itertools

    grid = {
        "incentive_inr": [0.0, 30.0, 120.0],
        "aov_inr": [200.0, 600.0, 2_000.0],
        "margin": [0.16, 0.45, 0.95],
        "observed_conversion": [0.01, 0.10, 0.90],
        "population": [1_000, 30_000],
        "budget_inr": [0.0, 400_000.0],
    }
    keys = list(grid)
    seen, evaluated = set(), 0

    for combo in itertools.product(*(grid[k] for k in keys)):
        kwargs = dict(zip(keys, combo))
        incentive = kwargs.pop("incentive_inr")
        try:
            result = reprice("A", incentive, **kwargs)
        except RequestInadmissible:
            continue
        seen.add(result["recommendation"]["decision"])
        evaluated += 1

    assert evaluated > 100, "the grid must actually reach the engine"
    assert "PROMOTE" not in seen
    assert seen <= {"DO_NOT_PROMOTE", "RUN_EXPERIMENT_FIRST", "INSUFFICIENT_EVIDENCE"}


def test_stating_conditions_never_mutates_a_fixture() -> None:
    before_a, before_c = SCENARIO_A.fingerprint(), SCENARIO_C.fingerprint()

    reprice("A", 20.0, population=90_000, aov_inr=1_500.0, margin=0.6,
            observed_conversion=0.25, budget_inr=1_000_000.0)

    assert SCENARIO_A.fingerprint() == before_a
    assert SCENARIO_C.fingerprint() == before_c == locked_fingerprint()
    assert SCENARIO_A.population == 30_000
    assert SCENARIO_A.aov_inr == 600.0
    assert SCENARIO_A.margin == 0.22
    assert reprice_module._view("A").population == 30_000


def test_stating_conditions_writes_no_audit_entry() -> None:
    from api import service

    before = service.audit_trail("A")
    reprice("A", 30.0, population=12_000, aov_inr=900.0, margin=0.4,
            observed_conversion=0.2, budget_inr=99_000.0)
    after = service.audit_trail("A")

    assert len(after["entries"]) == len(before["entries"])
    assert after["head_hash"] == before["head_hash"]
    assert after["verified"] is True
