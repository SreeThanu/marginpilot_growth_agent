/**
 * The standalone merchant-promotion workflow.
 *
 * Recorded cases do not render this component. A merchant supplies a concrete
 * offer and the facts of their shop; the backend constructs the matching Python
 * Intervention and remains the only place that can decide the result.
 */

"use client";

import { useState, type ReactNode } from "react";

import { useEvaluate, type EvaluationRequest } from "@/lib/api";
import {
  DECISION_LABEL,
  DECISION_TONE,
  economicTone,
  percent,
  rupees,
} from "@/lib/format";
import type {
  EvaluationResult,
  OfferKind,
  Recommendation,
  RequestRefusal,
} from "@/types/domain";
import { Chip, Eyebrow, SubHeading, toneText } from "@/components/ui";

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

function Field({
  id,
  label,
  value,
  onChange,
  prefix,
  suffix,
  step = "1",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  prefix?: string;
  suffix?: string;
  step?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-rule py-2.5">
      <label htmlFor={id} className="t-caption text-ink-subtle">
        {label}
      </label>
      <div className="flex items-baseline gap-1 border-b border-rule-strong pb-0.5 focus-within:border-ink">
        {prefix ? (
          <span className="figure text-[0.82rem] text-ink-subtle">{prefix}</span>
        ) : null}
        <input
          id={id}
          name={id}
          type="number"
          inputMode="decimal"
          step={step}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="figure w-24 bg-transparent text-right text-[0.86rem] text-ink outline-none"
        />
        {suffix ? (
          <span className="figure text-[0.82rem] text-ink-subtle">{suffix}</span>
        ) : null}
      </div>
    </div>
  );
}

function OfferSelector({
  kind,
  magnitude,
  onKind,
  onMagnitude,
}: {
  kind: OfferKind | "";
  magnitude: string;
  onKind: (next: OfferKind | "") => void;
  onMagnitude: (next: string) => void;
}) {
  const label =
    kind === "percentage_discount"
      ? "Discount"
      : kind === "free_shipping"
        ? "Shipping fee waived"
        : "Discount amount";
  const suffix = kind === "percentage_discount" ? "%" : undefined;

  return (
    <>
      <div className="flex items-baseline justify-between gap-6 border-b border-rule py-2.5">
        <label htmlFor="offer_kind" className="t-caption text-ink-subtle">
          Offer
        </label>
        <select
          id="offer_kind"
          name="offer_kind"
          value={kind}
          onChange={(event) => onKind(event.target.value as OfferKind | "")}
          className="t-caption bg-transparent text-right text-ink outline-none"
        >
          <option value="">Choose an offer</option>
          <option value="flat_discount">Flat discount</option>
          <option value="percentage_discount">Percentage discount</option>
          <option value="free_shipping">Free shipping</option>
        </select>
      </div>

      {kind ? (
        <Field
          id="offer_magnitude"
          label={label}
          prefix={suffix ? undefined : "₹"}
          suffix={suffix}
          value={magnitude}
          onChange={onMagnitude}
          step={suffix ? "0.5" : "1"}
        />
      ) : null}
    </>
  );
}

function Assessment({ result }: { result: EvaluationResult | null }) {
  const assessment = result?.assessment;
  return (
    <div>
      <div className="flex items-baseline gap-3">
        <Eyebrow>MarginPilot assessment</Eyebrow>
        <Chip tone="spend" glyph="🔒" title="not a merchant input">
          read-only
        </Chip>
      </div>
      <div className="mt-3.5">
        <RequestLine
          label="Expected lift"
          value={
            assessment && assessment.expected_lift_absolute !== null ? (
              `${percent(assessment.expected_lift_absolute, 2)} absolute`
            ) : (
              <span className="t-small text-ink-subtle italic">Not available</span>
            )
          }
        />
        <RequestLine
          label="Evidence"
          value={
            assessment ? assessment.evidence_basis.toLowerCase() : "Not available"
          }
        />
      </div>

      {/*
        The hypothesis is shown as the reasoner's own words, attributed to the
        reasoner that produced them. A quote a reader can attribute is the
        difference between an assessment and a number that simply appeared.
      */}
      {assessment?.status === "AVAILABLE" ? (
        <div className="mt-3.5">
          {assessment.hypothesis ? (
            <p className="t-caption max-w-[52ch] text-ink-subtle">
              &ldquo;{assessment.hypothesis}&rdquo;
            </p>
          ) : null}
          {assessment.mechanism ? (
            <p className="t-caption mt-2 max-w-[52ch] text-ink-subtle">
              {assessment.mechanism}
            </p>
          ) : null}
          <p className="t-caption mt-3 max-w-[52ch] text-ink-subtle">
            Stated by <span className="figure">{assessment.source}</span> from
            this promotion&rsquo;s own brief
            {assessment.citations.length ? (
              <>
                {" "}
                (<span className="figure">
                  {assessment.citations.join(", ")}
                </span>)
              </>
            ) : null}
            . The policy below recomputed every rupee and may overrule it.
          </p>
        </div>
      ) : assessment?.reason ? (
        <div className="mt-4 border-l-2 border-open pl-3">
          <p className="t-small max-w-[52ch] text-ink">{assessment.reason}</p>
          <p className="t-caption mt-2 max-w-[52ch] text-ink-subtle">
            No recorded-case hypothesis is borrowed for a different merchant or
            promotion, and no fixed number is substituted for one.
          </p>
        </div>
      ) : (
        <p className="t-caption mt-4 max-w-[52ch] text-ink-subtle">
          Expected lift, evidence, and the growth hypothesis are supplied by
          MarginPilot. They cannot be entered here.
        </p>
      )}
    </div>
  );
}

function Refusal({ refusal }: { refusal: RequestRefusal }) {
  return (
    <div className="border border-dashed border-risk/50 bg-risk-wash/40 px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Chip tone="risk" glyph="×">
          EVALUATION_INADMISSIBLE
        </Chip>
        <span className="t-caption text-ink-subtle">
          The request was not priced
        </span>
      </div>
      <p className="t-small mt-3 max-w-[62ch] text-ink">{refusal.reason}</p>
      {refusal.observed !== null && refusal.limit !== null ? (
        <p className="figure mt-2.5 text-[0.74rem] text-ink-muted">
          {percent(refusal.observed, 2)} requested · {percent(refusal.limit, 2)} ceiling
        </p>
      ) : null}
      <p className="t-caption mt-3 max-w-[62ch] text-ink-subtle">
        Refused by <span className="figure">{refusal.refused_by}</span>. The
        evaluator does not convert the offer into another type or substitute a
        plausible number.
      </p>
    </div>
  );
}

function OfferEconomics({ result }: { result: EvaluationResult }) {
  const { offer } = result;
  return (
    <div>
      <Eyebrow>Offer economics</Eyebrow>
      <div className="mt-3.5">
        <RequestLine label="Offer" value={offer.name} />
        <RequestLine
          label="Incentive per order"
          value={rupees(offer.incentive_cost_per_order_inr)}
        />
        <RequestLine
          label="Depth at stated AOV"
          value={percent(offer.depth_at_observed_aov, 2)}
        />
        <RequestLine
          label="Contribution per order"
          value={rupees(offer.contribution_per_order_inr)}
        />
      </div>
    </div>
  );
}

/**
 * The verdict, and the arithmetic that produced it.
 *
 * The net figure is the product's whole argument — the incentive is paid on
 * every treated order, not only the incremental ones — so it is stated as a
 * figure rather than left inside the rationale sentence. `diagnosis` carries
 * the break-even reasoning in the engine's own words and is shown for the same
 * reason: a decision a merchant cannot check is a decision they cannot trust.
 *
 * Every value is read from the recommendation. Nothing is computed here.
 */
function PolicyOutcome({ recommendation }: { recommendation: Recommendation }) {
  const tone = DECISION_TONE[recommendation.decision];
  const priced = recommendation.intervention_id !== null;
  return (
    <div className="border-l-2 border-rule-strong pl-4">
      <Eyebrow>Deterministic policy</Eyebrow>
      <p className={`t-small mt-2 font-medium ${toneText(tone)}`}>
        {DECISION_LABEL[recommendation.decision]}
      </p>
      <p className="t-caption mt-2 max-w-[56ch] text-ink-subtle">
        {recommendation.rationale}
      </p>

      {/*
        Only when the policy actually priced the campaign. A rejected proposal
        never reaches the economics, and zeroes shown as a projection would read
        as a break-even campaign rather than as no campaign at all.
      */}
      {priced ? (
        <>
          <div className="mt-4">
            <RequestLine
              label="Incremental contribution"
              value={rupees(
                recommendation.expected_incremental_contribution_inr,
              )}
            />
            <RequestLine
              label="Incentive cost"
              value={rupees(recommendation.expected_incentive_cost_inr)}
            />
            <RequestLine
              label="Net contribution"
              value={
                <span
                  className={toneText(
                    economicTone(
                      recommendation.evidence_basis,
                      recommendation.expected_net_contribution_inr,
                    ),
                  )}
                >
                  {rupees(recommendation.expected_net_contribution_inr)}
                </span>
              }
            />
            <RequestLine
              label="Break-even lift"
              value={
                recommendation.required_break_even_lift_absolute === null
                  ? "—"
                  : `${percent(
                      recommendation.required_break_even_lift_absolute,
                      2,
                    )} absolute`
              }
            />
          </div>
          {recommendation.diagnosis ? (
            <p className="t-caption mt-3 max-w-[56ch] text-ink-subtle">
              {recommendation.diagnosis}
            </p>
          ) : null}
        </>
      ) : null}

      {recommendation.binding_constraints.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {recommendation.binding_constraints.map((code) => (
            <Chip key={code} tone="risk" glyph="■">
              {code}
            </Chip>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type Draft = {
  offer_kind: OfferKind | "";
  offer_magnitude: string;
  population: string;
  aov_inr: string;
  margin: string;
  observed_conversion: string;
  budget_inr: string;
};

const EMPTY_DRAFT: Draft = {
  offer_kind: "",
  offer_magnitude: "",
  population: "",
  aov_inr: "",
  margin: "",
  observed_conversion: "",
  budget_inr: "",
};

function requestFromDraft(draft: Draft): EvaluationRequest | null {
  if (!draft.offer_kind || Object.values(draft).some((value) => value === "")) {
    return null;
  }
  const magnitude = Number(draft.offer_magnitude);
  const request: EvaluationRequest = {
    offer_kind: draft.offer_kind,
    flat_discount_inr:
      draft.offer_kind === "flat_discount" ? magnitude : null,
    discount_pct:
      draft.offer_kind === "percentage_discount" ? magnitude / 100 : null,
    shipping_fee_waived_inr:
      draft.offer_kind === "free_shipping" ? magnitude : null,
    bundle_added_value_inr: null,
    cohort_id: "ALL",
    population: Number(draft.population),
    aov_inr: Number(draft.aov_inr),
    margin: Number(draft.margin) / 100,
    observed_conversion: Number(draft.observed_conversion) / 100,
    budget_inr: Number(draft.budget_inr),
  };
  return Object.values(request).some(
    (value) => typeof value === "number" && Number.isNaN(value),
  )
    ? null
    : request;
}

export function MerchantRequestPanel() {
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [submitted, setSubmitted] = useState<EvaluationRequest | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const { data, error, loading } = useEvaluate(submitted);

  const setField = (field: keyof Draft) => (next: string) =>
    setDraft((current) => ({ ...current, [field]: next }));
  const refusal = (error?.detail as { refusal?: RequestRefusal } | undefined)
    ?.refusal;

  const submit = () => {
    const request = requestFromDraft(draft);
    if (!request) {
      setFormError("Choose an offer and complete every merchant input.");
      return;
    }
    setFormError(null);
    setSubmitted(request);
  };

  return (
    <section aria-labelledby="merchant-request" className="max-w-[62rem]">
      <Eyebrow>Merchant request</Eyebrow>
      <SubHeading className="mt-2.5">
        <span id="merchant-request">The promotion you want to evaluate</span>
      </SubHeading>
      <p className="t-small mt-2.5 max-w-[66ch] text-ink-muted">
        The merchant supplies the offer and business conditions. MarginPilot
        supplies an assessment when it has defensible evidence. The deterministic
        policy decides.
      </p>

      <form
        className="mt-7 grid gap-x-14 gap-y-9 lg:grid-cols-[0.95fr_1.05fr]"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div>
          <div className="flex items-baseline gap-3">
            <Eyebrow>Merchant inputs</Eyebrow>
            <span className="t-caption text-ink-subtle">
              conditions of your own shop
            </span>
          </div>
          <div className="mt-3.5">
            <OfferSelector
              kind={draft.offer_kind}
              magnitude={draft.offer_magnitude}
              onKind={(next) => {
                setDraft((current) => ({
                  ...current,
                  offer_kind: next,
                  offer_magnitude: "",
                }));
              }}
              onMagnitude={setField("offer_magnitude")}
            />
            <div className="flex items-baseline justify-between gap-6 border-b border-rule py-2.5">
              <label htmlFor="cohort_id" className="t-caption text-ink-subtle">
                Target cohort
              </label>
              <select
                id="cohort_id"
                name="cohort_id"
                value="ALL"
                disabled
                className="t-caption bg-transparent text-right text-ink"
              >
                <option value="ALL">All eligible customers</option>
              </select>
            </div>
            <Field
              id="population"
              label="Eligible customers"
              value={draft.population}
              onChange={setField("population")}
              step="1000"
            />
            <Field
              id="aov_inr"
              label="Average order value"
              prefix="₹"
              value={draft.aov_inr}
              onChange={setField("aov_inr")}
              step="50"
            />
            <Field
              id="margin"
              label="Contribution margin"
              suffix="%"
              value={draft.margin}
              onChange={setField("margin")}
              step="0.5"
            />
            <Field
              id="observed_conversion"
              label="Baseline conversion"
              suffix="%"
              value={draft.observed_conversion}
              onChange={setField("observed_conversion")}
              step="0.5"
            />
            <Field
              id="budget_inr"
              label="Budget"
              prefix="₹"
              value={draft.budget_inr}
              onChange={setField("budget_inr")}
              step="10000"
            />
          </div>
          <p className="t-caption mt-4 max-w-[56ch] text-ink-subtle">
            Bundles are not offered here because the existing pre-experiment
            policy brief does not account for bundle-added order value. The API
            refuses them rather than inventing that economics.
          </p>
          <button
            type="submit"
            disabled={loading}
            className="t-small mt-6 border border-ink bg-ink px-4 py-2 font-medium text-canvas transition-opacity hover:opacity-85 disabled:opacity-45"
          >
            {loading ? "Evaluating…" : "Evaluate promotion"}
          </button>
          {formError ? (
            <p className="t-caption mt-3 text-risk">{formError}</p>
          ) : null}
        </div>

        <div className="space-y-8">
          <Assessment result={data} />
          {refusal ? <Refusal refusal={refusal} /> : null}
          {error && !refusal ? (
            <p className="t-small max-w-[52ch] text-risk">{error.message}</p>
          ) : null}
          {data ? <OfferEconomics result={data} /> : null}
          {data ? <PolicyOutcome recommendation={data.recommendation} /> : null}
        </div>
      </form>
    </section>
  );
}
