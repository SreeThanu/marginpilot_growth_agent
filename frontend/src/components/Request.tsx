/**
 * The merchant's request — the input the rest of the page is an answer to.
 *
 * The product loop is `request → evaluation → verdict`, and until now only the
 * last of those was on screen, which made the page read as a viewer for three
 * precomputed cases. This panel is the first term. It is deliberately quiet:
 * small type, hairlines, no surface of its own competing with the dark band. An
 * input should not out-shout the answer.
 *
 * Interactive on Scenario A only, and that is a correctness constraint rather
 * than a scoping one. Re-pricing calls `recommend_from_raw`, the *pre*-experiment
 * path, which tops out at RUN_EXPERIMENT_FIRST. On Scenario C — whose rollout
 * was earned by a measured experiment — an interactive control would render
 * "run experiment first" directly above a page that says "promote". So B and C
 * show the request that was actually made, read-only, from the scenario payload
 * already on screen; only A re-prices.
 *
 * No arithmetic in this file. Every rupee, percentage, sample size and verdict
 * is a value the Python engine returned; this module chooses words and colours
 * for them and nothing else.
 */

"use client";

import { useState, type ReactNode } from "react";

import { useReprice } from "@/lib/api";
import {
  DECISION_LABEL,
  DECISION_TONE,
  count,
  percent,
  rupees,
} from "@/lib/format";
import type {
  Intervention,
  Merchant,
  MerchantRequest,
  ProposalEnvelope,
  Recommendation,
  RepriceRefused,
  RequestRefusal,
} from "@/types/domain";
import { Chip, Eyebrow, SubHeading, toneText } from "@/components/ui";

/** The declared offer for the interactive merchant, in rupees. */
const DECLARED_INCENTIVE_A = 120;

/* -------------------------------------------------------------------------- */
/* Small parts                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * One line of the request.
 *
 * Tighter than `DataRow` on purpose. This is a form the merchant filled in, not
 * a table of results, and the two should not carry the same weight.
 */
function RequestLine({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-rule py-2 last:border-b-0">
      <span className="t-caption text-ink-subtle">{label}</span>
      <div className="text-right">
        <span className="figure text-[0.8rem] text-ink-muted">{value}</span>
        {note ? (
          <span className="t-caption ml-2 text-ink-subtle">{note}</span>
        ) : null}
      </div>
    </div>
  );
}

/**
 * The engine's answer to *this* request, stated compactly.
 *
 * A restatement of the verdict, not a second verdict: the dark band below is
 * still where the decision lives. What this adds is the pairing the band does
 * not show — the net beside what it would cost to find out whether the net is
 * real.
 */
function Outcome({ recommendation }: { recommendation: Recommendation }) {
  const tone = DECISION_TONE[recommendation.decision];
  const net = recommendation.expected_net_contribution_inr;

  return (
    <div className="border-l-2 border-rule-strong pl-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
        <span className={`t-small font-medium ${toneText(tone)}`}>
          {DECISION_LABEL[recommendation.decision]}
        </span>
        {recommendation.binding_constraints.map((code) => (
          <span key={code} className="figure text-[0.7rem] text-risk">
            {code}
          </span>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-x-10 gap-y-3">
        <div>
          <Eyebrow>Expected net</Eyebrow>
          <p
            className={`figure mt-1.5 text-[1.05rem] ${
              net < 0 ? "text-risk" : "text-open"
            }`}
          >
            {rupees(net)}
          </p>
        </div>

        <div>
          <Eyebrow>Break-even lift</Eyebrow>
          <p className="figure mt-1.5 text-[1.05rem] text-ink">
            {recommendation.required_break_even_lift_absolute === null ? (
              <span className="t-small text-ink-subtle italic">
                No lift reaches it
              </span>
            ) : (
              percent(recommendation.required_break_even_lift_absolute, 2)
            )}
          </p>
        </div>

        {/*
          The G4 moment. Whenever an experiment is recommended its cost sits
          beside the net it would authorise — at Rs.37 that is a Rs.15,488 test
          to resolve a Rs.3,000 campaign. Hiding it would make the panel read
          cleaner and would be the single most dishonest thing on the page.
        */}
        {recommendation.experiment_required ? (
          <div>
            <Eyebrow>Experiment to resolve it</Eyebrow>
            <p className="figure mt-1.5 text-[1.05rem] text-open">
              {rupees(recommendation.experiment_cost_inr)}
            </p>
            <p className="t-caption mt-1 text-ink-subtle">
              {count(recommendation.experiment_horizon_per_arm)} per arm
            </p>
          </div>
        ) : null}
      </div>

      {recommendation.unresolved.length ? (
        <div className="mt-4 border-l-2 border-open pl-3">
          {recommendation.unresolved.map((code) => (
            <p key={code} className="figure text-[0.7rem] text-open">
              {code}
            </p>
          ))}
          <p className="t-caption mt-1 max-w-[58ch] text-ink-subtle">
            Whether a test costs less than the answer it buys is unresolved in
            this project. The figures above are reported side by side rather
            than netted against each other, because no threshold for that
            comparison has been established.
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * A request the policy declined to price at all.
 *
 * Visually distinct from a verdict, and labelled as a different kind of event.
 * `REQUEST_INADMISSIBLE` is not `DO_NOT_PROMOTE`: the first means the merchant
 * asked something outside a standing limit, the second means the policy priced
 * the offer and answered no. A shared treatment would blur the one distinction
 * this panel exists to make legible.
 */
function Refusal({ refusal }: { refusal: RequestRefusal }) {
  return (
    <div className="border border-dashed border-risk/50 bg-risk-wash/40 px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Chip tone="risk" glyph="×">
          REQUEST_INADMISSIBLE
        </Chip>
        <span className="t-caption text-ink-subtle">
          Not a decision — the request was never priced
        </span>
      </div>

      <p className="t-small mt-3 max-w-[62ch] text-ink">{refusal.reason}</p>

      {refusal.observed !== null && refusal.limit !== null ? (
        <p className="figure mt-2.5 text-[0.74rem] text-ink-muted">
          {percent(refusal.observed, 2)} requested · {percent(refusal.limit, 2)}{" "}
          ceiling
        </p>
      ) : null}

      <p className="t-caption mt-3 max-w-[62ch] text-ink-subtle">
        Refused by <span className="figure">{refusal.refused_by}</span> — the
        same rule, and the same refusal, that the adversarial suite&rsquo;s
        discount-ceiling case produces. The policy declines to price the offer;
        it does not clamp it into range and answer anyway.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The control                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * The incentive field and the action that submits it.
 *
 * The draft is held locally and only becomes a request on submit, so the engine
 * is asked a question when the merchant asks one rather than on every keystroke.
 * The action requests an *evaluation*; there is no control anywhere on this
 * surface that approves a spend, and the endpoint behind it is a GET.
 *
 * The field is not bounded to the policy ceiling. Clamping in the browser would
 * hide the refusal, and the refusal is the point — the engine is the thing that
 * says no, and it should be seen saying it.
 */
function IncentiveControl({
  draft,
  onDraft,
  onSubmit,
  pending,
}: {
  draft: string;
  onDraft: (value: string) => void;
  onSubmit: () => void;
  pending: boolean;
}) {
  return (
    <form
      className="flex flex-wrap items-end gap-x-6 gap-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div>
        <label htmlFor="incentive" className="eyebrow block">
          Incentive
        </label>
        <div className="mt-2 flex items-center gap-2 border-b border-rule-strong pb-1 focus-within:border-ink">
          <span className="figure text-[1.05rem] text-ink-subtle">₹</span>
          <input
            id="incentive"
            name="incentive"
            type="number"
            inputMode="decimal"
            step="1"
            min="0"
            value={draft}
            onChange={(event) => onDraft(event.target.value)}
            className="figure w-24 bg-transparent text-[1.05rem] text-ink outline-none"
          />
        </div>
        <p className="t-caption mt-2 text-ink-subtle">
          The merchant&rsquo;s only input on this panel.
        </p>
      </div>

      <button
        type="submit"
        disabled={pending}
        className="t-small border border-ink bg-ink px-4 py-2 font-medium text-canvas transition-opacity hover:opacity-85 disabled:opacity-45"
      >
        {pending ? "Evaluating…" : "Evaluate promotion"}
      </button>
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* The panel                                                                   */
/* -------------------------------------------------------------------------- */

function Frame({ children }: { children: ReactNode }) {
  return (
    <section aria-labelledby="merchant-request" className="max-w-[62rem]">
      <Eyebrow>Merchant request</Eyebrow>
      <SubHeading className="mt-2.5">
        <span id="merchant-request">What the merchant is asking for</span>
      </SubHeading>
      {children}
    </section>
  );
}

/**
 * The fixed-lift framing, stated where the lift is stated.
 *
 * Without this the panel invites a fair objection: a Rs.20 offer would not move
 * as many customers as a Rs.120 one, so holding the lift constant across the
 * range is not a demand model. It is not meant to be. Varying only the price of
 * the incentive asks what the assistant's hypothesis would have to cost to be
 * worth buying — a break-even sensitivity, which is exactly the quantity the
 * merchant cannot work out unaided.
 */
function FixedLiftNote() {
  return (
    <p className="t-caption mt-2.5 max-w-[64ch] text-ink-subtle">
      The assistant&rsquo;s lift hypothesis is held fixed while the incentive
      varies. This does not claim a cheaper offer would convert as well — it
      asks what that hypothesis would have to cost to be worth buying.
    </p>
  );
}

/** The request lines, identical for the interactive and read-only merchants. */
function RequestFacts({
  offer,
  cohortLabel,
  cohortCustomers,
  merchant,
  expectedLift,
  evidenceBasis,
}: {
  offer: string;
  cohortLabel: string;
  cohortCustomers: number;
  merchant: Merchant;
  expectedLift: number | null;
  evidenceBasis: string | null;
}) {
  return (
    <div className="mt-5">
      <RequestLine label="Offer" value={offer} />
      <RequestLine
        label="Target"
        value={cohortLabel}
        note={`${count(cohortCustomers)} customers`}
      />
      <RequestLine
        label="AOV / margin"
        value={`${rupees(merchant.observed_aov_inr)} · ${percent(
          merchant.observed_margin,
        )}`}
      />
      <RequestLine
        label="Baseline conversion"
        value={percent(merchant.observed_conversion)}
      />
      <RequestLine label="Budget" value={rupees(merchant.budget_inr)} />
      <RequestLine
        label="Expected lift"
        value={
          expectedLift === null ? (
            <span className="t-small text-ink-subtle italic">
              Not stated
            </span>
          ) : (
            `${percent(expectedLift, 2)} pts`
          )
        }
      />
      <RequestLine
        label="Evidence"
        value={
          evidenceBasis === null ? (
            <span className="t-small text-ink-subtle italic">None</span>
          ) : (
            evidenceBasis.toLowerCase()
          )
        }
      />
    </div>
  );
}

/**
 * Scenario A. The request is editable and the engine re-prices it live.
 */
function InteractiveRequest({
  scenario,
  merchant,
}: {
  scenario: string;
  merchant: Merchant;
}) {
  const [draft, setDraft] = useState(String(DECLARED_INCENTIVE_A));
  const [submitted, setSubmitted] = useState<number>(DECLARED_INCENTIVE_A);

  const { data, error, loading } = useReprice(scenario, submitted);

  /**
   * The last request the engine actually accepted.
   *
   * A refused request answers 422 and carries no `request` object, so reading
   * the facts straight off `data` blanks the whole left column the moment the
   * ceiling is breached — the offer becomes "—" and the lift "Not stated",
   * neither of which is true. The lift and the cohort did not change; the
   * incentive was rejected. Holding the last accepted request keeps the panel
   * describing the promotion under discussion while the refusal explains why
   * this particular price for it was not priced.
   */
  const [lastAccepted, setLastAccepted] = useState<MerchantRequest | null>(null);
  if (data && data.request !== lastAccepted) setLastAccepted(data.request);

  const facts = data ? data.request : lastAccepted;

  const submit = () => {
    const parsed = Number(draft);
    // An unparseable field is not sent. Everything the engine *can* judge —
    // negative, non-finite, above the ceiling — is sent and refused there.
    if (draft.trim() !== "" && Number.isFinite(parsed)) setSubmitted(parsed);
  };

  const refusal = (error?.detail as RepriceRefused | undefined)?.refusal ?? null;

  return (
    <Frame>
      <p className="t-small mt-2.5 max-w-[64ch] text-ink-muted">
        The assistant proposed this promotion. Change what the incentive costs
        and the engine re-prices the same offer through the same gates.
      </p>

      <div className="mt-7 grid gap-x-14 gap-y-8 lg:grid-cols-[0.95fr_1.05fr]">
        <div>
          <RequestFacts
            offer={facts ? facts.offer_name : "—"}
            cohortLabel={facts ? facts.cohort_id : "—"}
            cohortCustomers={facts ? facts.cohort_customers : 0}
            merchant={merchant}
            expectedLift={facts ? facts.expected_lift_absolute : null}
            evidenceBasis={facts ? facts.evidence_basis : null}
          />
          <FixedLiftNote />
        </div>

        <div className="space-y-7">
          <IncentiveControl
            draft={draft}
            onDraft={setDraft}
            onSubmit={submit}
            pending={loading}
          />

          {refusal ? <Refusal refusal={refusal} /> : null}

          {error && !refusal ? (
            <p className="t-small max-w-[52ch] text-risk">{error.message}</p>
          ) : null}

          {data && !error ? (
            <Outcome recommendation={data.recommendation} />
          ) : null}

          {/*
            Off the declared offer, this panel and the band below are answering
            two different questions, and on camera that reads as a contradiction
            unless it is named. The band is this merchant's shipped decision at
            the offer that was actually proposed; the panel is a counterfactual
            at another price.
          */}
          {data && !data.request.is_declared_offer ? (
            <p className="t-caption max-w-[58ch] text-ink-subtle">
              Above is this offer re-priced at{" "}
              <span className="figure">
                {rupees(data.request.incentive_inr)}
              </span>
              . The verdict below is the merchant&rsquo;s decision at the{" "}
              <span className="figure">
                {rupees(data.request.declared_incentive_inr)}
              </span>{" "}
              the assistant actually proposed, and does not move with this
              control.
            </p>
          ) : null}
        </div>
      </div>
    </Frame>
  );
}

/**
 * Scenarios B and C. The request that was actually made, with no control.
 *
 * Rendered entirely from the scenario payload the page already holds — this
 * variant makes no request of its own, so there is nothing here that could
 * re-price a merchant whose verdict came from a measurement.
 */
function ReadOnlyRequest({
  merchant,
  intervention,
  proposal,
}: {
  merchant: Merchant;
  intervention: Intervention | null;
  proposal: ProposalEnvelope;
}) {
  const accepted = proposal.accepted ? proposal.proposal : null;

  return (
    <Frame>
      <p className="t-small mt-2.5 max-w-[64ch] text-ink-muted">
        The promotion this merchant asked about, as the decision path received
        it.
      </p>

      <div className="mt-5 max-w-[36rem]">
        <RequestFacts
          offer={intervention ? intervention.name : "—"}
          cohortLabel={accepted ? accepted.cohort_id : "—"}
          cohortCustomers={merchant.population}
          merchant={merchant}
          expectedLift={accepted ? accepted.expected_lift_absolute : null}
          evidenceBasis={accepted ? accepted.evidence_basis : null}
        />
        <p className="t-caption mt-2.5 max-w-[64ch] text-ink-subtle">
          Shown as asked. The incentive is adjustable on the thin-margin
          merchant, where the offer is refused before any test is run; here the
          verdict below rests on a measurement, which re-pricing an offer cannot
          produce.
        </p>
      </div>
    </Frame>
  );
}

/**
 * The merchant request panel.
 *
 * `scenario` selects the variant. A is the interactive one; everything else
 * renders the request read-only.
 */
export function MerchantRequestPanel({
  scenario,
  merchant,
  intervention,
  proposal,
}: {
  scenario: string;
  merchant: Merchant;
  intervention: Intervention | null;
  proposal: ProposalEnvelope;
}) {
  if (scenario === "A") {
    return <InteractiveRequest scenario={scenario} merchant={merchant} />;
  }
  return (
    <ReadOnlyRequest
      merchant={merchant}
      intervention={intervention}
      proposal={proposal}
    />
  );
}
