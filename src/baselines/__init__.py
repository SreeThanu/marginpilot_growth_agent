"""The five comparison strategies.

Responsibility
--------------
Implement each baseline behind the same interface as the agent,
``decide(world_state, budget) -> list[Intervention]``, so the harness can run
all six strategies over identical worlds:

1. Do nothing — natural business performance.
2. Rule-based marketer — 10% off where P(purchase) < 0.4.
3. Conversion optimizer — maximizes expected conversions, ignores contribution.
4. LLM strategist — the LLM picks campaigns from context, with no experiments
   and no economic gate.
5. Engine without LLM — the same statistical machinery and the same policy
   gates driven by a fixed hypothesis set. **This is the ablation, and it is the
   baseline that matters.**

Boundary rules (CLAUDE.md)
--------------------------
* Baseline 4 is the only baseline that may reach an LLM, and it does so through
  ``src.agent``.
* If MarginPilot loses to a baseline — Baseline 5 especially — that result is
  reported, not tuned away.

Built Day 5: baselines 1, 1b, 2, 3 and 5. Baseline 4 (the LLM strategist)
arrived Day 6 with the agent, and delegates its model call to
``src/agent/reasoner.py`` so that only ``src/agent/`` imports an LLM client.

Baseline 1b is a diagnostic rather than a competitor. It runs the same
experiments as Baseline 5 and scales none of them, so its result isolates the
cost of learning — the constraint the Day 4 replay showed to be binding.
"""


from src.baselines.conversion_optimizer import ConversionOptimizer  # noqa: E402
from src.baselines.do_nothing import DoNothing  # noqa: E402
from src.baselines.engine_without_llm import EngineWithoutLLM, LearnOnly  # noqa: E402
from src.baselines.llm_strategist import LLMStrategist  # noqa: E402
from src.baselines.rule_based import RuleBasedMarketer  # noqa: E402

#: Every strategy the harness compares, in report order. Baseline 1b sits with
#: them for convenience but is a diagnostic, not a competitor.
ALL_BASELINES = (
    DoNothing(),
    LearnOnly(),
    RuleBasedMarketer(),
    ConversionOptimizer(),
    EngineWithoutLLM(),
)

__all__ = [
    "ALL_BASELINES",
    "ConversionOptimizer",
    "DoNothing",
    "EngineWithoutLLM",
    "LLMStrategist",
    "LearnOnly",
    "RuleBasedMarketer",
]
