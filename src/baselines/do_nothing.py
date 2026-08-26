"""Baseline 1 — do nothing.

Zero experiments, zero spend, zero realized contribution. The honest floor, and
the number MarginPilot has to beat before any other comparison means anything.

It is easy to overlook how strong this baseline is. Experimentation costs money
before it earns any, and a corpus where most promotions lose money rewards
inaction. If MarginPilot cannot beat zero, the fact that it beats a
conversion-optimiser is irrelevant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.eval.contracts import MerchantView, Proposal, ScalingRule


@dataclass(frozen=True, slots=True)
class DoNothing:
    name: str = "1_do_nothing"
    scaling_rule: ScalingRule = ScalingRule.NEVER
    max_experiments: int = 0

    def decide(self, view: MerchantView, budget_inr: float) -> Sequence[Proposal]:
        return []
