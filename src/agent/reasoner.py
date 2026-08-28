"""Where the LLM lives. The only file in the project that talks to a model.

The agent's decisions are made here; the authority to act on them is not. A
reasoner returns an :class:`~src.agent.hypothesis.Assessment` — run this
question, or decline to spend — and every money-adjacent consequence of that
answer is enforced downstream by the experiment engine and the scaling rule.

Three implementations behind one Protocol:

* :class:`ClaudeReasoner` — Claude Opus 5.
* :class:`GeminiReasoner` — Gemini 3.6 Flash.
* :class:`HeuristicReasoner` — a deterministic stand-in with no model behind it,
  so the loop, the tests and CI run offline. It is **not** a substitute for a
  model in any result: it cannot read the merchant's situation, and any
  evaluation using it measures the pipeline, not the reasoning.

That the provider is swappable is a property worth having and worth showing:
the same prompts, the same parsing and the same downstream authority boundary
serve both. Which model produced a result is recorded with the result, because
"an LLM decided this" is not a claim — "*this* model decided this" is.

Neither model client falls back to the heuristic when credentials are missing.
Both raise. A run labelled with a model's name must actually have come from that
model, or the results table is fiction.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

from dotenv import load_dotenv

#: Resolved from this file rather than the caller's stack or cwd. python-dotenv's
#: default find_dotenv() walks frames, which fails outright under `python -` and
#: silently misses when the process starts anywhere but the repo root.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

from src.agent.hypothesis import (
    AgentHypothesis,
    Assessment,
    ContextCitation,
    Decision,
    Diagnosis,
    SkipDecision,
)
from src.eval.contracts import MerchantView

#: CLAUDE.md pins the Claude model choice to the current flagship.
DEFAULT_MODEL = "claude-opus-5"

#: Gemini model. The project has no Anthropic credentials, and an agent that
#: cannot run cannot be evaluated.
#:
#: 3.6 Flash rather than 2.5 Flash because 2.5 is retired for new keys — it
#: still appears in models.list() but calling it returns 404 "no longer
#: available to new users. Please update your code to use models/gemini-3.6-flash".
#: The substitution follows Google's own deprecation notice. Recorded in
#: docs/simulator.md 4f.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

#: Free-tier request ceiling. Exceeding it returns 429s that would otherwise be
#: mistaken for model behaviour.
GEMINI_FREE_TIER_RPM = 15


class RateLimitExceededError(RuntimeError):
    """Raised when a provider rate limit survives every retry.

    A distinct type on purpose. A 429 is an infrastructure failure, not a
    decision, and must never be recorded as one — an agent that "skipped"
    because the API was busy would be scored as having exercised restraint.
    """


class ReasonerError(RuntimeError):
    """The model replied, but not with something usable."""


@dataclass
class _RateLimiter:
    """Paces requests to stay under a per-minute ceiling.

    Spacing requests evenly is cheaper than discovering the limit by hitting it:
    a 429 costs a retry and a wait either way, and the wait is longer.
    """

    requests_per_minute: int
    _last_call: float = 0.0

    @property
    def min_interval_s(self) -> float:
        return 60.0 / max(self.requests_per_minute, 1)

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        remaining = self.min_interval_s - elapsed
        if self._last_call and remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()

#: Fix A's contribution, isolated so it can be switched off. Cycle 2 measures
#: the two fixes as an ablation rather than as one lump: an improvement whose
#: source is unknown is not a diagnosis, and §4j committed in advance to
#: reporting whether Fix B replaced reasoning or informed it.
_BREAK_EVEN_DOCTRINE = """THE QUESTION IS NOT WHICH OFFER MOVES CUSTOMERS. It is which offer moves them at a \
cost the margin can absorb. Those are different questions and they often have \
different answers. An offer that customers visibly want can still be the worst \
choice available, because wanting it is not the same as it paying for itself.

Work the break-even before you argue for anything. For each intervention:

    break-even incremental share = cost per treated order / contribution per order

That is the fraction of treated orders that must be genuinely NEW — orders that \
would not have happened otherwise — just to cover the discount. An offer needing \
40% of its orders to be incremental is a far harder bet than one needing 8%, \
whatever the customers say they want. Compute this ratio for every option and say \
what it is before you choose. A cheap offer on a healthy margin can pay while an \
attractive offer on a thin one cannot.

Signals about customer RESPONSE — support tickets, stated preferences, segment \
friction — tell you who will react. They do not tell you whether reacting pays. \
Use them to explain a number, never as a substitute for one.

"""

_SYSTEM_HEAD = """You are MarginPilot, an autonomous growth agent for an Indian \
direct-to-consumer merchant.

You optimise INCREMENTAL CONTRIBUTION, not conversion. A discount is paid to every \
buyer who converts, including the ones who would have bought at full price, so a \
campaign can lift conversion sharply and still destroy contribution.

"""

_SYSTEM_TAIL = """EXPERIMENTATION IS SCARCE. On merchants like this one, a single experiment costs \
roughly 2.8x the entire annual profit pool that promotions could generate. You can \
afford about ONE experiment per merchant. Your primary decision is therefore NOT \
"which campaign" but "is any question here worth its cost at all".

DECLINING TO SPEND IS A CORRECT ANSWER, not a fallback. Most promotions on merchants \
like this lose money. If the merchant's situation does not give you a specific, \
grounded reason to expect an intervention to pay, say so and decline. A well-argued \
skip is a better outcome than a poorly-motivated experiment.

Ground every claim in the merchant's actual situation. When you cite something, quote \
the exact line you are reasoning from — support tickets, competitor activity, inventory \
notes, segment descriptions, trading commentary. Do not justify a decision with generic \
retail theory, and do not invent facts that are not in the context you were given.

You never choose who is treated, how long an experiment runs, or when to read it. \
Randomisation, the horizon and the decision rule are fixed by the system.

Reply with a single JSON object and no other text."""

#: The Cycle 2 prompt. Concatenated rather than formatted — the tail contains
#: braces, and a format string here would be a parsing accident waiting to fail
#: silently.
SYSTEM_PROMPT = _SYSTEM_HEAD + _BREAK_EVEN_DOCTRINE + _SYSTEM_TAIL

#: The Cycle 1 prompt, byte-for-byte, as the control arm of the ablation.
SYSTEM_PROMPT_WITHOUT_BREAK_EVEN = _SYSTEM_HEAD + _SYSTEM_TAIL

_RUN_SCHEMA = """{
  "decision": "run" | "skip",

  // when "run":
  "intervention_id": "<one of the intervention_ids offered>",
  "prediction": "<what you predict will happen, specifically enough to be wrong>",
  "reasoning": "<why you believe it, from this merchant's situation>",
  "citations": [{"field": "<where you read it>", "quote": "<exact text>", "inference": "<what it implies>"}],
  "expected_effect_absolute": <predicted absolute lift in conversion, e.g. 0.03>,
  "mde_contribution_per_customer_inr": <smallest per-customer rupee effect worth resolving>,
  "success_condition": "<observation that would confirm the prediction>",
  "failure_condition": "<observation that would refute it>",
  "break_even_analysis": "<the break-even incremental share for EVERY intervention, and which is most affordable>",
  "selection_rationale": "<why this question rather than the others, in terms of that ratio>",

  // when "skip":
  "reasoning": "<why no experiment here is worth its cost>",
  "citations": [{"field": "...", "quote": "...", "inference": "..."}],
  "would_run_if": "<what would have to be true for you to spend>",
  "best_option_considered": "<the strongest option you looked at>",
  "expected_value_reasoning": "<why it still is not worth the cost>"
}"""


@runtime_checkable
class Reasoner(Protocol):
    """What the agent needs from a mind, LLM-backed or not."""

    name: str

    def assess(
        self,
        view: MerchantView,
        *,
        budget_remaining_inr: float,
        experiments_remaining: int,
        history: Sequence[dict[str, Any]],
    ) -> Assessment:
        ...

    def diagnose(
        self,
        view: MerchantView,
        hypothesis: AgentHypothesis,
        outcome: dict[str, Any],
    ) -> Diagnosis:
        ...

    def choose_campaign(self, view: MerchantView) -> dict[str, Any]:
        """Pick a campaign with no experiment and no economic gate.

        Baseline 4's entire method. Present on the Reasoner rather than in
        ``src/baselines/`` because CLAUDE.md permits only ``src/agent/`` to
        import an LLM client — the baseline delegates here so the boundary holds.
        """
        ...


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model reply.

    Tolerant by design: a model that wraps JSON in a fence or adds a sentence is
    not an error worth failing a run over, but silently guessing at malformed
    output would be. Anything unparseable raises.
    """
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON object in model reply: {text[:400]}")
    return json.loads(match.group(0))


def _citations(raw: Any) -> tuple[ContextCitation, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        ContextCitation(
            field=str(c.get("field", "")),
            quote=str(c.get("quote", "")),
            inference=str(c.get("inference", "")),
        )
        for c in raw
        if isinstance(c, dict)
    )


def _assessment_from_payload(
    payload: dict[str, Any], view: MerchantView, cycle: int
) -> Assessment:
    """Build a typed Assessment, refusing anything the world cannot honour."""
    if str(payload.get("decision", "")).lower() == "skip":
        return Assessment(
            decision=Decision.SKIP,
            skip=SkipDecision(
                reasoning=str(payload.get("reasoning", "")).strip(),
                citations=_citations(payload.get("citations")),
                would_run_if=str(payload.get("would_run_if", "")).strip(),
                best_option_considered=str(payload.get("best_option_considered", "")),
                expected_value_reasoning=str(payload.get("expected_value_reasoning", "")),
            ),
        )

    intervention_id = str(payload.get("intervention_id", ""))
    available = {i.intervention_id for i in view.interventions}
    if intervention_id not in available:
        raise ValueError(
            f"proposed intervention {intervention_id!r} does not exist; "
            f"available: {sorted(available)}"
        )

    return Assessment(
        decision=Decision.RUN,
        hypothesis=AgentHypothesis(
            hypothesis_id=f"hyp_{view.world_id}_c{cycle}",
            intervention_id=intervention_id,
            prediction=str(payload.get("prediction", "")).strip(),
            reasoning=str(payload.get("reasoning", "")).strip(),
            citations=_citations(payload.get("citations")),
            expected_effect_absolute=float(payload.get("expected_effect_absolute", 0.03)),
            mde_contribution_per_customer_inr=float(
                payload.get("mde_contribution_per_customer_inr", 0.0)
            ),
            success_condition=str(payload.get("success_condition", "")).strip(),
            failure_condition=str(payload.get("failure_condition", "")).strip(),
            selection_rationale=" ".join(
                s for s in (
                    str(payload.get("break_even_analysis", "")).strip(),
                    str(payload.get("selection_rationale", "")).strip(),
                ) if s
            ),
        ),
    )


@dataclass
class ClaudeReasoner:
    """The real agent. Calls Claude and parses a structured decision.

    Adaptive thinking is on: the run/skip judgement is the whole point of the
    system and is worth the tokens. Requires ``ANTHROPIC_API_KEY`` — with no
    credential the constructor raises rather than silently degrading to a
    heuristic, because a run that quietly stopped using the LLM would produce
    results labelled as MarginPilot that are not.
    """

    name: str = "marginpilot"
    model: str = DEFAULT_MODEL
    effort: str = "high"
    max_tokens: int = 16000
    _client: Any = None

    def __post_init__(self) -> None:
        if self._client is not None:
            return
        load_dotenv(_ENV_PATH)
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise RuntimeError(
                "ClaudeReasoner needs Anthropic credentials (ANTHROPIC_API_KEY or an "
                "`ant auth login` profile). Refusing to fall back to a heuristic: a run "
                "labelled MarginPilot must actually be the LLM."
            )
        import anthropic

        self._client = anthropic.Anthropic()

    def _ask(self, prompt: str) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.system_prompt,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"model declined: {response.stop_details}")
        text = "".join(b.text for b in response.content if b.type == "text")
        return _extract_json(text)

    #: Cycle 2 ablation switches. Both fixes on by default; the ablation turns
    #: them off one at a time so an improvement can be attributed rather than
    #: just observed.
    break_even: bool = True
    merchant_history: bool = True

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT if self.break_even else SYSTEM_PROMPT_WITHOUT_BREAK_EVEN

    def assess(
        self,
        view: MerchantView,
        *,
        budget_remaining_inr: float,
        experiments_remaining: int,
        history: Sequence[dict[str, Any]],
    ) -> Assessment:
        prompt = build_assessment_prompt(
            view,
            budget_remaining_inr=budget_remaining_inr,
            experiments_remaining=experiments_remaining,
            history=history,
            show_break_even=self.break_even,
            show_merchant_history=self.merchant_history,
        )
        return _assessment_from_payload(self._ask(prompt), view, len(history))

    def choose_campaign(self, view: MerchantView) -> dict[str, Any]:
        payload = self._ask(build_campaign_prompt(view))
        available = {i.intervention_id for i in view.interventions}
        chosen = str(payload.get("intervention_id", ""))
        if chosen not in available:
            raise ValueError(f"chose unavailable intervention {chosen!r}")
        return {"intervention_id": chosen, "rationale": str(payload.get("rationale", ""))}

    def diagnose(
        self, view: MerchantView, hypothesis: AgentHypothesis, outcome: dict[str, Any]
    ) -> Diagnosis:
        payload = self._ask(build_diagnosis_prompt(view, hypothesis, outcome))
        return Diagnosis(
            what_was_predicted=str(payload.get("what_was_predicted", hypothesis.prediction)),
            what_happened=str(payload.get("what_happened", "")),
            why_it_differed=str(payload.get("why_it_differed", "")),
            what_this_rules_out=str(payload.get("what_this_rules_out", "")),
        )



@dataclass
class GeminiReasoner:
    """The same agent, on Gemini 2.5 Flash.

    Identical prompts, identical parsing, identical downstream authority
    boundary — only the provider differs. Free-tier request pacing and 429
    backoff live here because a rate limit is an infrastructure event that must
    never reach the loop looking like a decision.
    """

    name: str = "marginpilot_gemini"
    model: str = DEFAULT_GEMINI_MODEL
    requests_per_minute: int = GEMINI_FREE_TIER_RPM
    max_retries: int = 5
    max_output_tokens: int = 8192
    #: Zero temperature so a re-run of the same merchant gives the same
    #: decision. The diagnostics compare paired runs, and a sampling difference
    #: would be indistinguishable from a reasoning difference.
    temperature: float = 0.0
    _client: Any = None
    _limiter: _RateLimiter = field(default_factory=lambda: _RateLimiter(GEMINI_FREE_TIER_RPM))
    #: Cumulative token usage across every call this reasoner has made. Recorded
    #: because the run has a real cost and a result whose price is unknown is a
    #: result nobody can decide whether to repeat.
    usage: dict[str, int] = field(
        default_factory=lambda: {"calls": 0, "prompt": 0, "output": 0, "thinking": 0}
    )

    def __post_init__(self) -> None:
        self._limiter = _RateLimiter(self.requests_per_minute)
        if self._client is not None:
            return
        load_dotenv(_ENV_PATH)
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GeminiReasoner needs GEMINI_API_KEY (in .env or the environment). "
                "Refusing to fall back to a heuristic: a run labelled as a model's "
                "reasoning must actually be that model's."
            )
        from google import genai

        self._client = genai.Client(api_key=api_key)

    def _ask(self, prompt: str) -> dict[str, Any]:
        """One request, paced and retried. Raises rather than guessing."""
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            # The prompts already specify a JSON object; asking the API to
            # enforce the MIME type removes the most common parse failure.
            response_mime_type="application/json",
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._limiter.wait()
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
            except errors.ClientError as exc:  # 4xx, including 429
                if getattr(exc, "code", None) != 429:
                    raise
                last_error = exc
            except errors.ServerError as exc:  # 5xx — transient
                last_error = exc
            else:
                meta = getattr(response, "usage_metadata", None)
                if meta is not None:
                    self.usage["calls"] += 1
                    self.usage["prompt"] += meta.prompt_token_count or 0
                    self.usage["output"] += meta.candidates_token_count or 0
                    self.usage["thinking"] += meta.thoughts_token_count or 0
                text = (response.text or "").strip()
                if not text:
                    # An empty body is usually a safety block or a truncated
                    # response; either way there is no decision to record.
                    raise ReasonerError(
                        f"empty reply from {self.model} "
                        f"(finish_reason={getattr(response.candidates[0], 'finish_reason', None) if response.candidates else None})"
                    )
                return _extract_json(text)

            # Exponential backoff with jitter. Free-tier limits are per-minute,
            # so the sleep is measured in seconds, not milliseconds.
            delay = min(2**attempt * self._limiter.min_interval_s, 60.0)
            time.sleep(delay + random.uniform(0, 1.0))

        raise RateLimitExceededError(
            f"{self.model} rate limit survived {self.max_retries} retries: {last_error}. "
            "This is an infrastructure failure, not a decision, and is not recorded as one."
        )

    #: Cycle 2 ablation switches. Both fixes on by default; the ablation turns
    #: them off one at a time so an improvement can be attributed rather than
    #: just observed.
    break_even: bool = True
    merchant_history: bool = True

    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT if self.break_even else SYSTEM_PROMPT_WITHOUT_BREAK_EVEN

    def assess(
        self,
        view: MerchantView,
        *,
        budget_remaining_inr: float,
        experiments_remaining: int,
        history: Sequence[dict[str, Any]],
    ) -> Assessment:
        prompt = build_assessment_prompt(
            view,
            budget_remaining_inr=budget_remaining_inr,
            experiments_remaining=experiments_remaining,
            history=history,
            show_break_even=self.break_even,
            show_merchant_history=self.merchant_history,
        )
        return _assessment_from_payload(self._ask(prompt), view, len(history))

    def choose_campaign(self, view: MerchantView) -> dict[str, Any]:
        payload = self._ask(build_campaign_prompt(view))
        available = {i.intervention_id for i in view.interventions}
        chosen = str(payload.get("intervention_id", ""))
        if chosen not in available:
            raise ReasonerError(f"chose unavailable intervention {chosen!r}")
        return {"intervention_id": chosen, "rationale": str(payload.get("rationale", ""))}

    def diagnose(
        self, view: MerchantView, hypothesis: AgentHypothesis, outcome: dict[str, Any]
    ) -> Diagnosis:
        payload = self._ask(build_diagnosis_prompt(view, hypothesis, outcome))
        return Diagnosis(
            what_was_predicted=str(payload.get("what_was_predicted", hypothesis.prediction)),
            what_happened=str(payload.get("what_happened", "")),
            why_it_differed=str(payload.get("why_it_differed", "")),
            what_this_rules_out=str(payload.get("what_this_rules_out", "")),
        )


def build_assessment_prompt(
    view: MerchantView,
    *,
    budget_remaining_inr: float,
    experiments_remaining: int,
    history: Sequence[dict[str, Any]],
    show_break_even: bool = True,
    show_merchant_history: bool = True,
) -> str:
    """The merchant's situation, as the agent sees it.

    ``show_break_even`` and ``show_merchant_history`` switch off Fix A's
    arithmetic table and Fix B's campaign history respectively. Both default to
    on; the Cycle 2 ablation turns them off one at a time to find out which of
    the two fixes, if either, is doing the work.

    Semantic context is presented before the numbers, deliberately: the
    question is whether this merchant's *situation* justifies the spend, and
    leading with metrics invites pattern-matching on them.
    """
    semantic = view.semantic
    lines = [
        f"MERCHANT: {semantic.merchant_name} ({semantic.vertical})",
        semantic.merchant_description,
        "",
        "TRADING NOTES:",
        *(f"  - {n}" for n in semantic.trading_notes),
        "",
        "CUSTOMER SERVICE THEMES:",
        *(f"  - {n}" for n in semantic.customer_service_themes),
        "",
        "COMPETITOR ACTIVITY:",
        *(f"  - {n}" for n in semantic.competitor_events),
        "",
        "SEASONAL CONTEXT:",
        *(f"  - {n}" for n in semantic.seasonal_events),
        "",
        "INVENTORY NOTES:",
        *(f"  - {n}" for n in semantic.inventory_notes),
        "",
        "SEGMENTS:",
        *(
            f"  - {s.name} ({s.share:.0%}): {s.notes}"
            for s in view.segments
        ),
        "",
        "AVAILABLE INTERVENTIONS:",
        *(
            f"  - {i.intervention_id} ({i.name}): {i.description}"
            for i in view.interventions
        ),
    ]
    if show_break_even:
        lines += [
            "",
            "BREAK-EVEN ARITHMETIC — the share of treated orders that must be genuinely",
            "incremental just to cover the discount. Lower is an easier bet:",
        ]
        lines += [
            f"  - {i.intervention_id:<14} costs Rs."
            f"{i.incentive_cost_inr(view.observed_aov_inr):>7,.0f} per treated order "
            f"against Rs.{view.observed_aov_inr * view.observed_margin:,.0f} contribution "
            f"-> needs {i.incentive_cost_inr(view.observed_aov_inr) / max(view.observed_aov_inr * view.observed_margin, 1e-9):.0%} "
            "of treated orders to be incremental"
            for i in view.interventions
        ]
    lines += [
        "",
        "NUMBERS:",
        f"  customers: {view.population:,}",
        f"  observed conversion: {view.observed_conversion:.1%}",
        f"  average order value: Rs.{view.observed_aov_inr:,.0f}",
        f"  contribution margin: {view.observed_margin:.1%}",
        f"  contribution per order: Rs.{view.observed_aov_inr * view.observed_margin:,.0f}",
        f"  promotion budget remaining: Rs.{budget_remaining_inr:,.0f}",
        f"  experiments you may still run: {experiments_remaining}",
    ]

    if view.history and show_merchant_history:
        lines += [
            "",
            "PAST CAMPAIGNS ON THIS MERCHANT — incremental net contribution per treated",
            "customer, measured against a control group held back at the time. Small",
            "samples, so read the standard error alongside the estimate: an effect",
            "smaller than its own error is not evidence of anything.",
        ]
        for entry in view.history:
            lines.append(
                f"  - {entry.intervention_id:<14} Rs.{entry.net_per_treated_customer_inr:>7.2f} "
                f"per treated customer  (+/- {entry.standard_error_inr:.2f}, "
                f"n={entry.sample_size}, {entry.orders} orders)"
            )

    if history:
        lines += ["", "WHAT YOU ALREADY LEARNED HERE:"]
        for entry in history:
            lines.append(f"  - {json.dumps(entry, default=str)}")
        lines += [
            "",
            "Your revised decision must reflect what that result ruled out. If nothing "
            "further is worth testing, skip and say why.",
        ]

    lines += [
        "",
        "Decide: is any experiment here worth its cost? Reply with JSON of this shape:",
        _RUN_SCHEMA,
    ]
    return "\n".join(lines)


def build_campaign_prompt(view: MerchantView) -> str:
    """Baseline 4's prompt: choose a campaign, with no experiment available.

    Same merchant context as the agent gets, and deliberately no mention of
    experiments, contribution gates or restraint — the baseline exists to show
    what the same model does when nothing checks it.
    """
    semantic = view.semantic
    return "\n".join(
        [
            f"MERCHANT: {semantic.merchant_name} ({semantic.vertical})",
            semantic.merchant_description,
            "",
            "TRADING NOTES:",
            *(f"  - {n}" for n in semantic.trading_notes),
            "CUSTOMER SERVICE THEMES:",
            *(f"  - {n}" for n in semantic.customer_service_themes),
            "COMPETITOR ACTIVITY:",
            *(f"  - {n}" for n in semantic.competitor_events),
            "SEGMENTS:",
            *(f"  - {s.name} ({s.share:.0%}): {s.notes}" for s in view.segments),
            "",
            "CAMPAIGNS AVAILABLE:",
            *(f"  - {i.intervention_id} ({i.name}): {i.description}" for i in view.interventions),
            "",
            "Choose the campaign to run for this merchant. Reply with JSON:",
            '{"intervention_id": "...", "rationale": "..."}',
        ]
    )


def build_diagnosis_prompt(
    view: MerchantView, hypothesis: AgentHypothesis, outcome: dict[str, Any]
) -> str:
    return "\n".join(
        [
            f"Your hypothesis for {view.semantic.merchant_name} was:",
            f"  prediction: {hypothesis.prediction}",
            f"  reasoning: {hypothesis.reasoning}",
            f"  success condition: {hypothesis.success_condition}",
            f"  failure condition: {hypothesis.failure_condition}",
            "",
            "The experiment ran to its pre-committed horizon and returned:",
            json.dumps(outcome, indent=2, default=str),
            "",
            "You may not revise the hypothesis — it is fixed. Diagnose what happened.",
            "Reply with JSON:",
            '{"what_was_predicted": "...", "what_happened": "...", '
            '"why_it_differed": "...", "what_this_rules_out": "..."}',
        ]
    )


@dataclass
class HeuristicReasoner:
    """A deterministic stand-in. **No model behind it.**

    Exists so the agent loop, its tests and CI run without credentials. It
    applies a fixed rule — test the intervention whose incentive is cheapest
    relative to contribution per order, unless the cost of the experiment
    exceeds a share of the profit the merchant could plausibly gain — and writes
    its reasoning out in the same shape the LLM would.

    Any evaluation run with this reasoner measures the pipeline, not the
    reasoning. Results produced with it are labelled accordingly and must never
    be reported as MarginPilot's.
    """

    name: str = "marginpilot_heuristic"
    #: Skip when the projected experiment cost exceeds this share of the
    #: contribution the whole customer base could produce in a window.
    skip_cost_share: float = 0.25

    def assess(
        self,
        view: MerchantView,
        *,
        budget_remaining_inr: float,
        experiments_remaining: int,
        history: Sequence[dict[str, Any]],
    ) -> Assessment:
        contribution_per_order = view.observed_aov_inr * view.observed_margin
        pool = view.population * view.observed_conversion * contribution_per_order

        # Cheapest incentive relative to the contribution an order produces.
        ranked = sorted(
            view.interventions,
            key=lambda i: i.incentive_cost_inr(view.observed_aov_inr) / max(contribution_per_order, 1e-9),
        )
        best = ranked[0]
        cost_ratio = best.incentive_cost_inr(view.observed_aov_inr) / max(contribution_per_order, 1e-9)
        projected_cost = view.population * view.observed_conversion * best.incentive_cost_inr(
            view.observed_aov_inr
        )

        # Reason from what the last result established BEFORE falling back to the
        # mechanical constraint. A second cycle that can only say "no allowance
        # left" has not learned anything; the revision has to stand on the
        # evidence, and the allowance is the harness's business, not the
        # agent's reasoning.
        if history:
            prior = history[-1]
            if not prior.get("scaled", False):
                return Assessment(
                    decision=Decision.SKIP,
                    skip=SkipDecision(
                        reasoning=(
                            f"The first experiment on {prior.get('intervention_id')} did not "
                            "clear the scaling bar, and the remaining interventions are more "
                            "expensive per treated order. A second experiment would cost as "
                            "much as the first and test a weaker candidate."
                        ),
                        citations=(
                            ContextCitation(
                                field="prior_result",
                                quote=str(prior.get("decision_reason", "")),
                                inference="Response here is weaker than the design assumed.",
                            ),
                        ),
                        would_run_if=(
                            "A cheaper intervention were available, or the first result had "
                            "come closer to the bar."
                        ),
                        best_option_considered=ranked[1].intervention_id if len(ranked) > 1 else "none",
                        expected_value_reasoning=(
                            "Cost of a second experiment exceeds the contribution the "
                            "remaining candidates could plausibly add."
                        ),
                    ),
                )

        if experiments_remaining <= 0 or budget_remaining_inr <= 0:
            return Assessment(
                decision=Decision.SKIP,
                skip=SkipDecision(
                    reasoning=(
                        "No experiment allowance or budget remains for this merchant."
                    ),
                    citations=(),
                    would_run_if="Budget or allowance were restored.",
                    best_option_considered=best.intervention_id,
                    expected_value_reasoning="Nothing further can be funded.",
                ),
            )

        if projected_cost > pool * self.skip_cost_share:
            return Assessment(
                decision=Decision.SKIP,
                skip=SkipDecision(
                    reasoning=(
                        f"The cheapest available offer ({best.name}) costs "
                        f"Rs.{best.incentive_cost_inr(view.observed_aov_inr):,.0f} per treated "
                        f"order against Rs.{contribution_per_order:,.0f} of contribution — "
                        f"{cost_ratio:.0%} of the margin on every order it touches."
                    ),
                    citations=(
                        ContextCitation(
                            field="interventions",
                            quote=best.description,
                            inference="Incentive consumes most of the order's contribution.",
                        ),
                    ),
                    would_run_if="A shallower offer were available on this catalogue.",
                    best_option_considered=best.intervention_id,
                    expected_value_reasoning=(
                        f"Projected experiment cost Rs.{projected_cost:,.0f} against a total "
                        f"contribution pool of Rs.{pool:,.0f}."
                    ),
                ),
            )

        return Assessment(
            decision=Decision.RUN,
            hypothesis=AgentHypothesis(
                hypothesis_id=f"hyp_{view.world_id}_c{len(history)}",
                intervention_id=best.intervention_id,
                prediction=(
                    f"{best.name} raises conversion by about 3 points and clears the "
                    "contribution bar."
                ),
                reasoning=(
                    f"{best.name} has the lowest incentive cost relative to the "
                    f"Rs.{contribution_per_order:,.0f} contribution an order produces "
                    f"({cost_ratio:.0%} of it), so it needs the fewest incremental orders to pay."
                ),
                citations=(
                    ContextCitation(
                        field="interventions",
                        quote=best.description,
                        inference="Cheapest incentive per unit of contribution.",
                    ),
                ),
                expected_effect_absolute=0.03,
                mde_contribution_per_customer_inr=contribution_per_order * 0.02,
                success_condition="P(net > 0) >= 0.80 with a tolerable downside.",
                failure_condition="P(net > 0) < 0.80, or the downside breaches tolerance.",
                selection_rationale=(
                    "Ranked all four by incentive cost per unit of contribution; this is "
                    "the cheapest, so it is the only one with a realistic path to paying."
                ),
            ),
        )

    def choose_campaign(self, view: MerchantView) -> dict[str, Any]:
        """Baseline 4's heuristic twin: pick the deepest offer and run it.

        No experiment, no gate — the point of the baseline is that it acts on a
        judgement it never checks.
        """
        deepest = max(
            view.interventions, key=lambda i: i.effective_depth(view.observed_aov_inr)
        )
        return {
            "intervention_id": deepest.intervention_id,
            "rationale": (
                f"{deepest.name} is the strongest offer available and should move the "
                "most customers. No experiment run."
            ),
        }

    def diagnose(
        self, view: MerchantView, hypothesis: AgentHypothesis, outcome: dict[str, Any]
    ) -> Diagnosis:
        return Diagnosis(
            what_was_predicted=hypothesis.prediction,
            what_happened=(
                f"Observed conversion lift {outcome.get('conversion_lift', 0):.3%}, net "
                f"contribution Rs.{outcome.get('net_contribution_inr', 0):,.0f} with "
                f"P(net>0)={outcome.get('probability_net_positive', 0):.2f}."
            ),
            why_it_differed=(
                "The incentive was paid on every treated order while only a fraction were "
                "incremental, so the conversion lift did not carry the contribution."
                if outcome.get("conversion_lift", 0) > 0
                else "The intervention did not move conversion enough to matter."
            ),
            what_this_rules_out=(
                f"{hypothesis.intervention_id} at this depth on this customer base. "
                "Remaining candidates are more expensive per treated order, so they need a "
                "larger response to clear the same bar."
            ),
        )
