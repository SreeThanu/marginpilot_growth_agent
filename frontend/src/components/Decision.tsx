/**
 * The verdict, the control path that produced it, and the reasoning behind it.
 *
 * The band is where the system speaks: decision, the arithmetic that settles
 * it, and — inline, in the same glance — what the assistant had asked for. The
 * override is not a section further down the page; on a merchant where policy
 * overrules the model, that fact is legible in the first screen.
 */

"use client";

import type { ReactNode } from "react";

import {
  DECISION_LABEL,
  DECISION_SUBTITLE,
  DECISION_TONE,
  GATE_NAMES,
  GATE_ORDER,
  codeText,
  count,
  economicTone,
  percent,
  rupees,
  type RailState,
} from "@/lib/format";
import type { Experiment, Recommendation } from "@/types/domain";
import { ContributionRule } from "./ContributionRule";
import {
  Band,
  Chip,
  DataRow,
  Eyebrow,
  ProcessRail,
  Rule,
  Shell,
  SubHeading,
  toneText,
} from "./ui";

/* -------------------------------------------------------------------------- */
/* The decision band                                                           */
/* -------------------------------------------------------------------------- */

/**
 * The verdict line: what the assistant asked for, and what the policy returned.
 *
 * Kept to one row so it can sit inside the hero. Where the two disagree the row
 * says so plainly; where they agree it says the policy decided independently,
 * because agreement is not evidence that the model is reliable and this row
 * must never imply that it is.
 */
function VerdictLine({
  recommendation,
  onBand = true,
}: {
  recommendation: Recommendation;
  onBand?: boolean;
}) {
  const requested = recommendation.model_requested;
  const overruled = recommendation.overruled_the_model;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="eyebrow eyebrow-dark">AI proposal</span>
      <span className="t-small text-band-muted">
        {requested ? DECISION_LABEL[requested] : "No decision requested"}
      </span>
      <span aria-hidden="true" className="text-band-subtle">
        →
      </span>
      <span className="eyebrow eyebrow-dark">Policy</span>
      <span
        className={`t-small font-medium ${toneText(
          DECISION_TONE[recommendation.decision],
          onBand,
        )}`}
      >
        {DECISION_LABEL[recommendation.decision]}
      </span>
      <Chip
        tone={overruled ? "risk" : "spend"}
        glyph={overruled ? "■" : "="}
        onBand={onBand}
      >
        {overruled ? "Model overruled" : "Decided independently"}
      </Chip>
    </div>
  );
}

/**
 * The premise, on its own band.
 *
 * Lifted out of the decision band so it reaches the first paint. It has no data
 * dependency, and leaving it inside the data-gated render meant the one
 * sentence the whole product turns on was missing from the server HTML and
 * appeared only after the engine answered.
 */
export function PremiseBand() {
  return (
    <Band>
      <Shell className="pt-12 pb-10">
        {/*
          The measure is set in rem, not ch: `ch` resolves against this
          wrapper's body font rather than the statement's display size, which
          collapsed the sentence to seven lines and pushed the verdict off the
          first screen.
        */}
        <div className="max-w-[44rem]">
          <Eyebrow onBand>The premise</Eyebrow>
          <p className="t-statement mt-4 text-band-ink">
            A promotion can lift conversions and still make the merchant poorer.
          </p>
          <p className="t-small mt-5 max-w-[58ch] text-band-muted">
            MarginPilot decides whether the economics justify the spend. Below
            is that judgement applied to one merchant.
          </p>
        </div>
        <Rule onBand className="mt-10" />
      </Shell>
    </Band>
  );
}

export function DecisionBand({
  recommendation,
  scenarioKey,
}: {
  recommendation: Recommendation;
  scenarioKey: string;
}) {
  const tone = DECISION_TONE[recommendation.decision];
  const measured = recommendation.evidence_basis === "EXPERIMENT";
  const netTone = economicTone(
    recommendation.evidence_basis,
    recommendation.expected_net_contribution_inr,
  );

  return (
    <Band>
      <Shell className="pb-16">
        <div className="grid gap-x-16 gap-y-12 lg:grid-cols-[1.05fr_0.95fr]">
          {/* -- the verdict, as the consequence ---------------------------- */}
          <div key={scenarioKey}>
            <Eyebrow onBand>
              Merchant {scenarioKey} · the policy&rsquo;s answer
            </Eyebrow>
            {/*
              Rendered statically. The clip-reveal used to paint a partially
              masked headline ("Prom…") on every scenario switch, and the
              staggered fades left the metrics column blank for a beat.
            */}
            <h1 className={`t-verdict mt-4 ${toneText(tone, true)}`}>
              {DECISION_LABEL[recommendation.decision]}
            </h1>
            <p className="t-lead mt-4 max-w-[40ch] text-band-ink">
              {DECISION_SUBTITLE[recommendation.decision]}
            </p>

            <div className="mt-8">
              <VerdictLine recommendation={recommendation} />
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              <Chip
                tone={measured ? "earn" : "open"}
                glyph={measured ? "◆" : "◇"}
                onBand
              >
                Evidence: {recommendation.evidence_basis.toLowerCase()}
              </Chip>
              {recommendation.gates_passed.length ? (
                <Chip tone="spend" glyph="✓" onBand>
                  Gates {recommendation.gates_passed.join(" ")}
                </Chip>
              ) : null}
              {recommendation.binding_constraints.map((code) => (
                <Chip
                  key={code}
                  tone="risk"
                  glyph="■"
                  onBand
                  title={codeText(code)}
                >
                  {code}
                </Chip>
              ))}
              {recommendation.unresolved.map((code) => (
                <Chip
                  key={code}
                  tone="open"
                  glyph="?"
                  onBand
                  title={codeText(code)}
                >
                  {code}
                </Chip>
              ))}
            </div>
          </div>

          {/* -- the arithmetic --------------------------------------------- */}
          <div className="self-start">
            <div className="grid grid-cols-2 gap-x-8 gap-y-6">
              <div>
                <Eyebrow onBand>Incremental contribution</Eyebrow>
                <p
                  className={`figure mt-2.5 text-[1.28rem] leading-none ${
                    measured ? "text-earn-dark" : "text-open-dark"
                  }`}
                >
                  {rupees(
                    recommendation.expected_incremental_contribution_inr,
                  )}
                </p>
              </div>
              <div>
                <Eyebrow onBand>Incentive cost</Eyebrow>
                <p className="figure mt-2.5 text-[1.28rem] leading-none text-spend-dark">
                  {rupees(recommendation.expected_incentive_cost_inr)}
                </p>
              </div>
            </div>

            <Rule onBand className="my-7" />

            {/*
              "Potential" reads wrong over a loss, so the label follows the
              tone: banked, potential, or expected-and-negative.
            */}
            <Eyebrow onBand>
              {netTone === "earn"
                ? "Net contribution"
                : netTone === "open"
                  ? "Potential net contribution"
                  : "Expected net contribution"}
            </Eyebrow>
            <p
              className={`figure mt-3 text-[2.6rem] leading-none font-medium ${toneText(
                netTone,
                true,
              )}`}
            >
              {rupees(recommendation.expected_net_contribution_inr)}
            </p>
            <p className="t-caption mt-3 max-w-[38ch] text-band-subtle">
              {measured
                ? "Projected from the measured pilot across the rollout the budget can fund."
                : "Expected at the lift the assistant proposed. Not a measurement."}
            </p>

          </div>
        </div>

        {/*
          Why a promising merchant still does not get a rollout.
          Rendered only where the engine itself asked for an experiment, so it
          appears for the merchant waiting on evidence and stays out of the way
          for the two that are not. Every figure is a field the engine
          returned; nothing here is derived.
        */}
        {recommendation.experiment_required ? (
          <>
            <Rule onBand className="mt-12" />
            <div className="mt-9 grid gap-x-16 gap-y-8 lg:grid-cols-[1.05fr_0.95fr]">
              <div>
                <Eyebrow onBand>What would unlock a rollout</Eyebrow>
                <div className="mt-4">
                  <DataRow
                    onBand
                    label="Lift this offer must clear to break even"
                    value={
                      recommendation.required_break_even_lift_absolute === null
                        ? "—"
                        : percent(
                            recommendation.required_break_even_lift_absolute,
                            2,
                          )
                    }
                  />
                  <DataRow
                    onBand
                    label="Controlled test the policy asks for"
                    value={`${count(
                      recommendation.experiment_horizon_per_arm,
                    )} per arm`}
                  />
                  <DataRow
                    onBand
                    label="Cost of running it"
                    value={rupees(recommendation.experiment_cost_inr)}
                  />
                  <DataRow
                    onBand
                    label="Confidence rests on"
                    value={recommendation.evidence_basis.toLowerCase()}
                  />
                  <DataRow
                    onBand
                    label="Measured result"
                    value={
                      <span className="text-band-subtle italic">
                        Not yet measured
                      </span>
                    }
                  />
                </div>
              </div>

              <div className="self-center">
                {recommendation.unresolved.map((code) => (
                  <div
                    key={code}
                    className="border-l-2 border-open-dark pl-5"
                  >
                    <p className="figure text-[0.74rem] text-open-dark">
                      {code}
                    </p>
                    <p className="t-small mt-2 max-w-[46ch] text-band-muted">
                      {codeText(code)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : null}

        {/* -- the ledger --------------------------------------------------- */}
        <Rule onBand className="mt-14" />
        <div key={`${scenarioKey}-ledger`}>
          {/* level 2: this is the first heading after the page's h1. */}
          <SubHeading onBand level={2} className="mt-7">
            What the promotion earns, and what the incentive takes back
          </SubHeading>
          <ContributionRule
            contributionInr={
              recommendation.expected_incremental_contribution_inr
            }
            incentiveInr={recommendation.expected_incentive_cost_inr}
            netInr={recommendation.expected_net_contribution_inr}
            measured={measured}
            basisNote={
              measured
                ? "measured at the pre-committed horizon, then projected to the funded rollout"
                : "expected at the lift the assistant proposed"
            }
          />
        </div>
      </Shell>
    </Band>
  );
}

/* -------------------------------------------------------------------------- */
/* The control path                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Proposal → policy → experiment → rollout, drawn as the sequence it is.
 *
 * This is the product's architecture made literal, and it is why the
 * thirty-second version of the pitch needs no narration. Each stage reads its
 * state off fields the engine already returned — nothing is decided here — and
 * it speaks the same state vocabulary the Experiment progression uses, so the
 * colours are learned once and read everywhere.
 */
export function ControlPath({
  recommendation,
  experiment,
}: {
  recommendation: Recommendation;
  experiment: Experiment | null;
}) {
  const requested = recommendation.model_requested;
  const rolloutPassed = recommendation.gates_passed.includes("G6");
  const refused = recommendation.decision === "DO_NOT_PROMOTE";

  const stages: {
    label: string;
    value: string;
    note: string;
    state: RailState;
  }[] = [
    {
      label: "Proposal",
      value: requested ? DECISION_LABEL[requested] : "None requested",
      note: "The assistant may ask. The request carries no authority.",
      state: "complete",
    },
    {
      label: "Policy",
      value: DECISION_LABEL[recommendation.decision],
      note: recommendation.overruled_the_model
        ? "Deterministic gates overruled the request."
        : "Deterministic gates priced the request independently.",
      state: refused ? "blocked" : "complete",
    },
    {
      label: "Experiment",
      value: experiment
        ? `${count(experiment.horizon_per_arm)} per arm`
        : recommendation.experiment_required
          ? `${count(recommendation.experiment_horizon_per_arm)} per arm, not run`
          : "Not warranted",
      note: experiment
        ? "Read once at the pre-committed horizon."
        : recommendation.experiment_required
          ? "Rollout stays closed until this is measured."
          : "The arithmetic settles it before a test is worth running.",
      state: experiment
        ? "complete"
        : recommendation.experiment_required
          ? "current"
          : "not-reached",
    },
    {
      label: "Rollout",
      value: rolloutPassed ? "G6 passed" : refused ? "Held" : "Not reached",
      note: rolloutPassed
        ? "Re-priced against the rollout the budget can actually fund."
        : "No spend is authorised without a measured result clearing G6.",
      state: rolloutPassed ? "complete" : refused ? "blocked" : "not-reached",
    },
  ];

  return <ProcessRail stages={stages} />;
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

const GATE_MARK: Record<
  GateState,
  { glyph: string; text: string; word: string }
> = {
  passed: { glyph: "✓", text: "text-earn", word: "Passed" },
  binding: { glyph: "■", text: "text-risk", word: "Stopped here" },
  open: { glyph: "?", text: "text-open", word: "Open question" },
  "not-recorded": {
    glyph: "·",
    text: "text-ink-subtle",
    word: "Not recorded on this path",
  },
};

/**
 * Six ordered gates as a rule-separated list rather than six boxes.
 *
 * The two entry points run different subsets — G1 to G5 before an experiment,
 * G1 to G3 and G6 after one — so a gate that is neither passed nor binding
 * reads as "not recorded on this path" rather than as a failure.
 */
export function GateLadder({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  return (
    <div>
      <ol>
        {GATE_ORDER.map((gate) => {
          const state = gateState(gate, recommendation);
          const mark = GATE_MARK[state];
          return (
            <li
              key={gate}
              className="flex items-baseline gap-5 border-b border-rule py-3.5 last:border-b-0"
            >
              <span className="figure w-7 shrink-0 text-[0.78rem] text-ink-subtle">
                {gate}
              </span>
              <span className="t-small min-w-0 flex-1 text-ink">
                {GATE_NAMES[gate]}
              </span>
              <span
                className={`t-caption shrink-0 text-right ${mark.text}`}
              >
                <span aria-hidden="true" className="mr-2">
                  {mark.glyph}
                </span>
                {mark.word}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="t-caption mt-4 max-w-[70ch] text-ink-subtle">
        The pre-experiment path runs G1 to G5 and cannot return Promote. G6 is
        reached only with a measured result, and is the sole route to a rollout.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Reasoning                                                                   */
/* -------------------------------------------------------------------------- */

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Eyebrow>{label}</Eyebrow>
      <div className="t-small mt-2.5 max-w-[54ch] text-ink">{children}</div>
    </div>
  );
}

export function Reasoning({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  const breakEven = recommendation.required_break_even_lift_absolute;

  return (
    <div className="grid gap-x-16 gap-y-10 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-8">
        <Detail label="Diagnosis">{recommendation.diagnosis}</Detail>
        <Detail label="Rationale">
          {/* Engine-authored, rendered verbatim. Not a summary written after. */}
          {recommendation.rationale}
        </Detail>

        {recommendation.assumptions.length ? (
          <Detail label="Assumptions">
            <ul className="space-y-1.5">
              {recommendation.assumptions.map((a) => (
                <li key={a} className="text-ink-muted">
                  {a}
                </li>
              ))}
            </ul>
          </Detail>
        ) : null}
      </div>

      <div>
        <DataRow
          label="Break-even lift this offer must clear"
          value={
            breakEven === null ? (
              <span className="t-small text-ink-subtle italic">
                Unreachable at any lift
              </span>
            ) : (
              percent(breakEven, 2)
            )
          }
        />
        <DataRow
          label="Customers covered"
          value={count(recommendation.customers_treated)}
        />
        <DataRow
          label="Experiment cost"
          value={
            recommendation.experiment_required ? (
              rupees(recommendation.experiment_cost_inr)
            ) : (
              <span className="t-small text-ink-subtle italic">
                No experiment recommended
              </span>
            )
          }
        />
        <DataRow
          label="Evidence basis"
          value={recommendation.evidence_basis.toLowerCase()}
        />
        <DataRow
          label="Brief fields read"
          value={recommendation.citations.join(", ") || "—"}
        />

        {recommendation.binding_constraints.length ||
        recommendation.unresolved.length ? (
          <div className="mt-8 space-y-5">
            {recommendation.binding_constraints.map((code) => (
              <div key={code} className="border-l-2 border-risk pl-4">
                <p className="figure text-[0.74rem] text-risk">{code}</p>
                <p className="t-small mt-1.5 max-w-[46ch] text-ink-muted">
                  {codeText(code)}
                </p>
              </div>
            ))}
            {recommendation.unresolved.map((code) => (
              <div key={code} className="border-l-2 border-open pl-4">
                <p className="figure text-[0.74rem] text-open">{code}</p>
                <p className="t-small mt-1.5 max-w-[46ch] text-ink-muted">
                  {codeText(code)}
                </p>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
