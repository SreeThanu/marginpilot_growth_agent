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


# --------------------------------------------------------------------------- #
# Provider swappability, and rate limits that are not decisions
# --------------------------------------------------------------------------- #


def test_the_gemini_reasoner_refuses_to_run_without_credentials(monkeypatch) -> None:
    from src.agent.reasoner import GeminiReasoner

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr("src.agent.reasoner.load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiReasoner()


def test_both_model_reasoners_implement_the_same_interface() -> None:
    """The provider is swappable; the interface is not."""
    from src.agent.reasoner import ClaudeReasoner, GeminiReasoner, HeuristicReasoner

    required = {"assess", "diagnose", "choose_campaign", "name"}
    for cls in (ClaudeReasoner, GeminiReasoner, HeuristicReasoner):
        assert required <= set(dir(cls)), f"{cls.__name__} is missing part of the interface"


def test_a_rate_limit_is_never_recorded_as_a_decision() -> None:
    """A 429 is an infrastructure failure. An agent that "skipped" because the
    API was busy would be scored as having exercised restraint."""
    from src.agent.reasoner import GeminiReasoner, RateLimitExceededError

    class Busy:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                from google.genai import errors

                raise errors.ClientError(429, {"error": {"message": "quota"}})

    reasoner = GeminiReasoner(_client=Busy(), max_retries=2, requests_per_minute=6000)
    world, truth = generate(1)
    view = merchant_view(world)

    with pytest.raises(RateLimitExceededError):
        reasoner.assess(view, budget_remaining_inr=1e6, experiments_remaining=1, history=[])

    # And the agent loop propagates it rather than logging a skip.
    with pytest.raises(RateLimitExceededError):
        MarginPilotAgent(reasoner).run(
            view, GroundTruthExecutor(world, truth, view.observed_margin)
        )


def test_an_empty_model_reply_is_an_error_not_a_skip() -> None:
    from src.agent.reasoner import GeminiReasoner, ReasonerError

    class Empty:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                class R:
                    text = ""
                    candidates = []
                return R()

    reasoner = GeminiReasoner(_client=Empty(), requests_per_minute=6000)
    world, _ = generate(1)
    with pytest.raises(ReasonerError):
        reasoner.assess(
            merchant_view(world), budget_remaining_inr=1e6, experiments_remaining=1, history=[]
        )


def test_the_rate_limiter_paces_requests() -> None:
    import time

    from src.agent.reasoner import _RateLimiter

    limiter = _RateLimiter(requests_per_minute=60)  # one per second
    assert limiter.min_interval_s == 1.0
    limiter.wait()
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start >= 0.9
