"""Infrastructure failures must not reach the loop looking like decisions.

The reasoner's contract is that a rate limit, a 5xx or a dropped connection is
retried, while a refusal or an unparseable body is raised. Cycle 3 found the
gap: ``httpx.RemoteProtocolError`` was not in the retried set, and one dropped
connection ended a three-replicate measurement run that had already completed
tens of world-runs.

These tests drive a fake client, so they neither need credentials nor make a
network call.
"""

from __future__ import annotations

import httpx
import pytest

from src.agent.reasoner import (
    _TRANSPORT_ERRORS,
    GeminiReasoner,
    RateLimitExceededError,
    ReasonerError,
)


class _Models:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeResponse:
    usage_metadata = None
    candidates = ()

    def __init__(self, text):
        self.text = text


class _FakeClient:
    def __init__(self, script):
        self.models = _Models(script)


def _reasoner(script) -> GeminiReasoner:
    # requests_per_minute high so the limiter does not slow the test down.
    return GeminiReasoner(_client=_FakeClient(script), requests_per_minute=100_000)


@pytest.mark.parametrize("error", _TRANSPORT_ERRORS)
def test_transport_errors_are_retried_not_raised(error) -> None:
    """A dropped connection is retried, and the eventual answer is returned."""
    r = _reasoner([error("boom"), _FakeResponse('{"decision": "skip"}')])
    assert r._ask("prompt") == {"decision": "skip"}
    assert r._client.models.calls == 2


def test_a_persistent_transport_failure_still_raises() -> None:
    """Retry is bounded. A network that never comes back is reported, not hidden."""
    r = _reasoner([httpx.RemoteProtocolError("boom")] * 20)
    with pytest.raises(RateLimitExceededError):
        r._ask("prompt")


def test_exhaustion_is_catchable_by_the_measurement_harness() -> None:
    """src/eval/devrun.py must be able to catch what exhaustion actually raises.

    Retry exhaustion raises RateLimitExceededError, which is not a subclass of
    ReasonerError. A harness catching only ReasonerError would still lose a
    multi-hour replication to one dropped connection -- the exact failure this
    module exists to prevent.
    """
    import inspect

    from src.eval import devrun

    source = inspect.getsource(devrun._run_once)
    assert "RateLimitExceededError" in source and "ReasonerError" in source


def test_an_empty_reply_is_not_treated_as_a_decision() -> None:
    """An empty body carries no decision, so it must not become one."""
    r = _reasoner([_FakeResponse("")])
    with pytest.raises(ReasonerError):
        r._ask("prompt")
