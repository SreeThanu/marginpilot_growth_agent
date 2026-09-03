/**
 * The decision, the ladder it came down, and the model's part in it.
 *
 * The order on screen is the order a merchant asks the questions in: what was
 * decided, what it earns, which rule settled it, and only then what the
 * assistant had suggested. The model's proposal is deliberately *below* the
 * decision — it is an input to the answer, not the answer.
 */

"use client";

import {
  DECISION_LABEL,
  DECISION_SUBTITLE,
  DECISION_TONE,
  GATE_NAMES,
  GATE_ORDER,
  codeText,
  percent,
  rupees,
} from "@/lib/format";
import type { Recommendation } from "@/types/domain";
import { Chip, Eyebrow, Panel, toneText } from "./ui";

/* -------------------------------------------------------------------------- */
/* Hero                                                                        */
/* -------------------------------------------------------------------------- */

export function DecisionHero({
  recommendation,
  question = "Should this merchant promote?",
}: {
  recommendation: Recommendation;
  question?: string;
}) {
  const tone = DECISION_TONE[recommendation.decision];

  return (
    <div className="mp-rise">
      <Eyebrow>Growth decision</Eyebrow>
      <p className="mt-3 text-[1.05rem] text-slate">{question}</p>
      <h1
        key={recommendation.decision}
        className={`mp-wipe mt-2 text-[clamp(2.4rem,6vw,3.9rem)] leading-[0.98] font-semibold tracking-[-0.035em] ${toneText(
          tone,
        )}`}
      >
        {DECISION_LABEL[recommendation.decision]}
      </h1>
      <p className="mt-4 max-w-[52ch] text-[1.02rem] leading-relaxed text-ink">
        {DECISION_SUBTITLE[recommendation.decision]}
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        <Chip
          tone={recommendation.evidence_basis === "EXPERIMENT" ? "earn" : "open"}
          glyph={recommendation.evidence_basis === "EXPERIMENT" ? "◆" : "◇"}
        >
          Evidence: {recommendation.evidence_basis.toLowerCase()}
        </Chip>
        {recommendation.gates_passed.length ? (
          <Chip tone="spend" glyph="✓">
            Gates {recommendation.gates_passed.join(" ")}
          </Chip>
        ) : null}
        {recommendation.binding_constraints.map((code) => (
          <Chip key={code} tone="deficit" glyph="■" title={codeText(code)}>
            {code}
          </Chip>
        ))}
        {recommendation.unresolved.map((code) => (
          <Chip key={code} tone="open" glyph="?" title={codeText(code)}>
            {code}
          </Chip>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The gate ladder                                                             */
/* -------------------------------------------------------------------------- */

type GateState = "passed" | "binding" | "open" | "not-recorded";

function gateState(gate: string, recommendation: Recommendation): GateState {
  if (recommendation.binding_constraints.some((c) => c.startsWith(`${gate}_`)))
    return "binding";
  if (recommendation.unresolved.some((c) => c.startsWith(`${gate}_`)))
    return "open";
  if (recommendation.gates_passed.includes(gate)) return "passed";
  return "not-recorded";
}

const GATE_MARK: Record<GateState, { glyph: string; text: string; word: string }> =
  {
    passed: { glyph: "✓", text: "text-earn", word: "Passed" },
    binding: { glyph: "■", text: "text-deficit", word: "Stopped here" },
    open: { glyph: "?", text: "text-open", word: "Open question" },
    "not-recorded": { glyph: "·", text: "text-slate-soft", word: "Not recorded" },
  };

/**
 * Six ordered gates, drawn as the sequence they actually are.
 *
 * The two entry points run different subsets — G1 to G5 before an experiment,
 * G1 to G3 and G6 after one — so a gate that is neither passed nor binding is
 * shown as "not recorded" rather than as a failure.
 */
export function GateLadder({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  return (
    <div>
      <ol className="grid grid-cols-2 gap-px overflow-hidden rounded-[3px] border border-rule bg-rule sm:grid-cols-3 lg:grid-cols-6">
        {GATE_ORDER.map((gate) => {
          const state = gateState(gate, recommendation);
          const mark = GATE_MARK[state];
          return (
            <li key={gate} className="bg-surface px-3.5 py-3">
              <div className="flex items-baseline justify-between gap-2">
                <span className="eyebrow">{gate}</span>
                <span className={`text-[0.9rem] ${mark.text}`} aria-hidden="true">
                  {mark.glyph}
                </span>
              </div>
              <p className="mt-1.5 text-[0.8rem] leading-tight font-medium text-ink">
                {GATE_NAMES[gate]}
              </p>
              <p className={`mt-1 text-[0.72rem] ${mark.text}`}>{mark.word}</p>
            </li>
          );
        })}
      </ol>
      <p className="mt-2.5 text-[0.76rem] leading-relaxed text-slate-soft">
        The pre-experiment path runs G1 to G5 and cannot return Promote. G6 is
        reached only with a measured result, and is the sole route to a rollout.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Model to policy                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The claim the product is built on, shown rather than asserted: the assistant
 * asked for something, and a deterministic layer answered. Where they agree it
 * says so plainly — agreement is not evidence that the model is reliable, and
 * this panel never suggests it is.
 */
export function ProposalToPolicy({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  const requested = recommendation.model_requested;
  const overruled = recommendation.overruled_the_model;

  return (
    <Panel className="overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr]">
        <div className="p-5">
          <Eyebrow>AI proposal</Eyebrow>
          <p className="mt-2.5 text-[1.05rem] font-medium text-slate">
            {requested ? DECISION_LABEL[requested] : "No decision requested"}
          </p>
          <p className="mt-1.5 text-[0.8rem] text-slate-soft">
            Advisory. Recorded so it can be overruled.
          </p>
        </div>

        <div
          aria-hidden="true"
          className="flex items-center justify-center border-y border-rule px-5 py-3 text-slate-soft md:border-x md:border-y-0"
        >
          <span className="hidden md:inline">→</span>
          <span className="md:hidden">↓</span>
        </div>

        <div className="p-5">
          <Eyebrow>MarginPilot policy</Eyebrow>
          <p
            className={`mt-2.5 text-[1.05rem] font-medium ${toneText(
              DECISION_TONE[recommendation.decision],
            )}`}
          >
            {DECISION_LABEL[recommendation.decision]}
            {!overruled && requested ? (
              <span className="ml-2 text-[0.85rem] font-normal text-slate">
                agrees
              </span>
            ) : null}
          </p>
          <p className="mt-1.5 text-[0.8rem] text-slate-soft">
            {overruled
              ? "Policy overruled the model."
              : "Decided independently; the outcome matched the request."}
          </p>
        </div>
      </div>

      {overruled ? (
        <p className="border-t border-rule bg-sunk px-5 py-3.5 text-[0.85rem] leading-relaxed text-ink">
          {recommendation.rationale}
        </p>
      ) : null}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* Why                                                                         */
/* -------------------------------------------------------------------------- */

export function WhyPanel({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  const breakEven = recommendation.required_break_even_lift_absolute;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <Eyebrow>Diagnosis</Eyebrow>
          <p className="mt-2 max-w-[58ch] text-[0.95rem] leading-relaxed text-ink">
            {recommendation.diagnosis}
          </p>
        </div>
        <div>
          <Eyebrow>Rationale</Eyebrow>
          <p className="mt-2 max-w-[58ch] text-[0.95rem] leading-relaxed text-ink">
            {recommendation.rationale}
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[3px] border border-rule bg-rule lg:grid-cols-4">
        <div className="bg-surface px-4 py-3">
          <dt className="eyebrow">Break-even lift</dt>
          <dd className="figure mt-1.5 text-[0.95rem] text-ink">
            {breakEven === null ? (
              <span className="text-[0.85rem] text-slate-soft italic">
                Unreachable at any lift
              </span>
            ) : (
              percent(breakEven, 2)
            )}
          </dd>
        </div>
        <div className="bg-surface px-4 py-3">
          <dt className="eyebrow">Customers covered</dt>
          <dd className="figure mt-1.5 text-[0.95rem] text-ink">
            {recommendation.customers_treated.toLocaleString("en-US")}
          </dd>
        </div>
        <div className="bg-surface px-4 py-3">
          <dt className="eyebrow">Experiment cost</dt>
          <dd className="figure mt-1.5 text-[0.95rem] text-ink">
            {recommendation.experiment_required ? (
              rupees(recommendation.experiment_cost_inr)
            ) : (
              <span className="text-[0.85rem] text-slate-soft italic">
                No experiment recommended
              </span>
            )}
          </dd>
        </div>
        <div className="bg-surface px-4 py-3">
          <dt className="eyebrow">Read from</dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">
            {recommendation.citations.length ? (
              recommendation.citations.map((c) => (
                <span
                  key={c}
                  className="figure rounded-[2px] bg-sunk px-1.5 py-0.5 text-[0.72rem] text-slate"
                >
                  {c}
                </span>
              ))
            ) : (
              <span className="text-[0.85rem] text-slate-soft italic">
                Not available
              </span>
            )}
          </dd>
        </div>
      </dl>

      {recommendation.binding_constraints.length ||
      recommendation.unresolved.length ||
      recommendation.assumptions.length ? (
        <details className="group rounded-[3px] border border-rule bg-surface">
          <summary className="cursor-pointer list-none px-4 py-3 text-[0.85rem] font-medium text-ink transition-colors hover:bg-sunk">
            <span className="mr-2 inline-block text-slate-soft transition-transform group-open:rotate-90">
              ▸
            </span>
            Constraints, open questions and assumptions
          </summary>
          <div className="space-y-5 border-t border-rule px-4 py-4">
            {recommendation.binding_constraints.length ? (
              <div>
                <Eyebrow className="!text-deficit">Binding constraint</Eyebrow>
                <ul className="mt-2 space-y-2">
                  {recommendation.binding_constraints.map((code) => (
                    <li key={code} className="text-[0.87rem] leading-relaxed">
                      <span className="figure text-deficit">{code}</span>{" "}
                      <span className="text-slate">— {codeText(code)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {recommendation.unresolved.length ? (
              <div>
                <Eyebrow className="!text-open">Unresolved</Eyebrow>
                <ul className="mt-2 space-y-2">
                  {recommendation.unresolved.map((code) => (
                    <li key={code} className="text-[0.87rem] leading-relaxed">
                      <span className="figure text-open">{code}</span>{" "}
                      <span className="text-slate">— {codeText(code)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {recommendation.assumptions.length ? (
              <div>
                <Eyebrow>Assumptions</Eyebrow>
                <ul className="mt-2 space-y-1.5">
                  {recommendation.assumptions.map((a) => (
                    <li
                      key={a}
                      className="text-[0.87rem] leading-relaxed text-slate"
                    >
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}
