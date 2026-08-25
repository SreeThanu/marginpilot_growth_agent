"""A launched experiment cannot be edited — enforced by the type, not by habit.

CLAUDE.md invariant 3 (the horizon is fixed at launch) and invariant 7 (the
hypothesis is pre-committed and immutable). Both fail silently and invisibly if
they are only conventions, which is why each has a test that attempts the edit
and requires it to raise.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from src.experiment import registry as registry_module
from src.experiment.registry import (
    ExperimentAlreadyLaunchedError,
    ExperimentNotFoundError,
    ExperimentRegistry,
    ExperimentStatus,
    Hypothesis,
    design_experiment,
)


def _design(experiment_id: str = "exp_001"):
    return design_experiment(
        experiment_id=experiment_id,
        world_id="world_00011",
        intervention_id="int_flat",
        hypothesis_id="hyp_001",
        prediction="A flat Rs.100 off lifts conversion from 12% to 18% among small-basket regulars.",
        reasoning="Small baskets see the deepest relative depth, and the segment is price sensitive.",
        baseline_conversion=0.12,
        expected_effect_absolute=0.06,
        success_condition="CI lower bound on incremental contribution above zero at horizon.",
        failure_condition="CI on incremental contribution contains or lies below zero.",
        budget_inr=50_000.0,
    )


def test_horizon_follows_from_the_power_calculation() -> None:
    design = _design()
    assert design.horizon_per_arm == 553
    assert design.hypothesis.required_sample_per_arm == 553


def test_launched_record_is_frozen() -> None:
    reg = ExperimentRegistry()
    reg.register(_design())
    launched = reg.launch("exp_001")

    with pytest.raises(dataclasses.FrozenInstanceError):
        launched.horizon_per_arm = 10  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        launched.design = _design("other")  # type: ignore[misc]


def test_hypothesis_is_frozen() -> None:
    hypothesis = _design().hypothesis
    with pytest.raises(dataclasses.FrozenInstanceError):
        hypothesis.prediction = "actually I meant something else"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        hypothesis.expected_effect_absolute = 0.01  # type: ignore[misc]


def test_an_incomplete_hypothesis_cannot_be_constructed() -> None:
    """A prediction with no failure condition cannot be wrong, so it cannot be
    scored on Day 9. Rejected at construction rather than at launch."""
    for missing in ("prediction", "reasoning", "success_condition", "failure_condition"):
        fields = {
            "hypothesis_id": "hyp_x",
            "prediction": "p",
            "reasoning": "r",
            "expected_effect_absolute": 0.05,
            "required_sample_per_arm": 100,
            "success_condition": "s",
            "failure_condition": "f",
        }
        fields[missing] = "   "
        with pytest.raises(ValueError, match=missing):
            Hypothesis(**fields)


def test_relaunching_is_refused() -> None:
    """The shape a 'let me just revise the prediction' bug would take."""
    reg = ExperimentRegistry()
    reg.register(_design())
    reg.launch("exp_001")
    with pytest.raises(ExperimentAlreadyLaunchedError, match="immutable"):
        reg.launch("exp_001")


def test_an_edited_hypothesis_no_longer_matches_the_launch_record() -> None:
    """Someone can always build an edited copy. What they cannot do is pass it
    off as the one that was committed to."""
    reg = ExperimentRegistry()
    design = _design()
    reg.register(design)
    reg.launch("exp_001")

    assert reg.verify_hypothesis("exp_001", design.hypothesis)

    revised = dataclasses.replace(
        design.hypothesis, prediction="a much more modest lift, in hindsight"
    )
    assert not reg.verify_hypothesis("exp_001", revised)


def test_registry_exposes_no_mutation_path() -> None:
    """The absent methods are the enforcement. Adding one fails here."""
    forbidden = {"update", "set", "edit", "replace", "delete", "remove", "amend", "revise", "patch"}
    public = [
        name for name, _ in inspect.getmembers(ExperimentRegistry, callable)
        if not name.startswith("_")
    ]
    for name in public:
        assert not any(word in name.lower() for word in forbidden), (
            f"ExperimentRegistry.{name} looks like a mutation path; launched "
            "experiments are immutable (CLAUDE.md invariants 3 and 7)"
        )


def test_status_is_derived_from_an_append_only_event_log() -> None:
    reg = ExperimentRegistry()
    reg.register(_design())
    assert reg.status("exp_001") is ExperimentStatus.DESIGNED

    reg.launch("exp_001")
    assert reg.status("exp_001") is ExperimentStatus.RUNNING

    before = len(reg.events)
    reg.complete("exp_001", detail="horizon reached")
    assert reg.status("exp_001") is ExperimentStatus.COMPLETED
    assert len(reg.events) == before + 1

    # Events only ever accumulate.
    assert [e.kind for e in reg.events] == ["registered", "launched", "completed"]


def test_stopping_requires_a_recorded_reason() -> None:
    reg = ExperimentRegistry()
    reg.register(_design())
    reg.launch("exp_001")
    with pytest.raises(ValueError, match="reason"):
        reg.stop("exp_001", reason="  ")


def test_a_design_whose_horizon_contradicts_its_power_analysis_is_refused() -> None:
    """The horizon must follow from the power calculation, not from the proposal."""
    design = _design()
    tampered = dataclasses.replace(
        design.hypothesis, required_sample_per_arm=10
    )
    with pytest.raises(ValueError, match="power"):
        dataclasses.replace(design, hypothesis=tampered)


def test_unknown_experiments_raise() -> None:
    reg = ExperimentRegistry()
    with pytest.raises(ExperimentNotFoundError):
        reg.get("exp_missing")
    with pytest.raises(ExperimentNotFoundError):
        reg.launch("exp_missing")
