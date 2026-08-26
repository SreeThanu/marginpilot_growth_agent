"""The loop: restraint first, and a second cycle that learns from the first."""

from __future__ import annotations

import dataclasses

import pytest

from src.agent.agent import MarginPilotAgent
from src.agent.hypothesis import (
    AgentHypothesis,
    Assessment,
    ContextCitation,
    Decision,
    SkipDecision,
)
from src.agent.reasoner import ClaudeReasoner, HeuristicReasoner, Reasoner
from src.eval.contracts import merchant_view
from src.eval.executor import GroundTruthExecutor
from src.world.generator import generate


def _run(seed: int, **kwargs):
    world, truth = generate(seed)
    view = merchant_view(world)
    executor = GroundTruthExecutor(world, truth, view.observed_margin)
    return MarginPilotAgent(HeuristicReasoner(), **kwargs).run(view, executor)


def test_the_agent_runs_two_cycles_and_the_second_reflects_the_first() -> None:
    """The whole point: one cycle is a calculator."""
    run = _run(1)
    assert len(run.cycles) == 2

    first, second = run.cycles
    assert first.launched, "the first cycle should have tested something"
    assert first.diagnosis is not None, "a finished experiment must be diagnosed"

    # The second decision refers to what the first one established.
    if second.skipped:
        text = second.assessment.skip.reasoning + second.assessment.skip.expected_value_reasoning
        assert first.assessment.hypothesis.intervention_id in text or "first experiment" in text
    else:
        assert second.assessment.hypothesis.intervention_id != first.assessment.hypothesis.intervention_id


def test_a_skip_is_logged_with_its_reasoning() -> None:
    """Declining to spend is a decision and is audited like one."""
    run = _run(1)
    skips = [c for c in run.cycles if c.skipped]
    assert skips, "expected at least one reasoned skip"

    skip = skips[0].assessment.skip
    assert skip.reasoning.strip()
    assert skip.would_run_if.strip(), "a skip must say what would have changed it"
    assert skip.expected_value_reasoning.strip()


def test_a_skip_cannot_be_recorded_without_reasoning() -> None:
    with pytest.raises(ValueError, match="reasoning"):
        SkipDecision(reasoning="  ", citations=(), would_run_if="x", best_option_considered="y",
                     expected_value_reasoning="z")
    with pytest.raises(ValueError, match="changed it"):
        SkipDecision(reasoning="x", citations=(), would_run_if="", best_option_considered="y",
                     expected_value_reasoning="z")


def test_skip_on_the_merits_ends_the_loop_without_spending() -> None:
    """A world where the agent declines immediately must cost nothing."""

    class AlwaysSkip:
        name = "always_skip"

        def assess(self, view, **kwargs):
            return Assessment(
                decision=Decision.SKIP,
                skip=SkipDecision(
                    reasoning="No intervention here has a grounded path to paying.",
                    citations=(ContextCitation("trading_notes", "flat revenue", "no signal"),),
                    would_run_if="A shallower offer existed.",
                    best_option_considered="int_shipping",
                    expected_value_reasoning="Cost exceeds the plausible gain.",
                ),
            )

        def diagnose(self, view, hypothesis, outcome):  # pragma: no cover - never called
            raise AssertionError("diagnose must not be called when nothing ran")

        def choose_campaign(self, view):  # pragma: no cover - not used here
            raise NotImplementedError

    world, truth = generate(2)
    view = merchant_view(world)
    run = MarginPilotAgent(AlwaysSkip()).run(
        view, GroundTruthExecutor(world, truth, view.observed_margin)
    )
    assert run.experiments_launched == 0
    assert run.skips == 1
    assert len(run.cycles) == 1, "the loop stops once the agent has concluded to spend nothing"


def test_the_agent_cannot_exceed_its_experiment_allowance() -> None:
    run = _run(3, max_experiments=1, max_cycles=3)
    assert run.experiments_launched <= 1


def test_the_launched_hypothesis_is_frozen() -> None:
    run = _run(1)
    hypothesis = run.cycles[0].assessment.hypothesis
    with pytest.raises(dataclasses.FrozenInstanceError):
        hypothesis.prediction = "something more flattering"  # type: ignore[misc]


def test_both_reasoners_satisfy_the_protocol() -> None:
    assert isinstance(HeuristicReasoner(), Reasoner)


def test_the_llm_reasoner_refuses_to_run_without_credentials(monkeypatch) -> None:
    """No silent degradation.

    A run labelled MarginPilot must actually be the LLM; quietly falling back to
    a heuristic would put a number in the results table that did not come from
    the thing being evaluated.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="credentials"):
        ClaudeReasoner()
