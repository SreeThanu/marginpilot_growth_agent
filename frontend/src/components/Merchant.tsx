/**
 * Who the decision is about, what was proposed, and what to do next.
 *
 * The context is a rule, not a card. It carries only what a reader needs to
 * follow the arithmetic above it — how many customers, what an order earns,
 * what the offer costs — and everything else about the merchant sits behind a
 * disclosure. Merchant metadata is the least important thing on this page and
 * is sized accordingly.
 */

"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { count, percent, rupees, rupeesExact } from "@/lib/format";
import type {
  CampaignHistory,
  Decision,
  Intervention,
  Merchant,
  ProposalEnvelope,
  Recommendation,
} from "@/types/domain";
import { withScenario, type ScenarioId } from "./ScenarioContext";
import { Chip, Eyebrow, SubHeading } from "./ui";

/* -------------------------------------------------------------------------- */
/* Context                                                                     */
/* -------------------------------------------------------------------------- */

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="figure mt-1.5 text-[0.95rem] text-ink">{value}</p>
    </div>
  );
}

export function MerchantContext({
  title,
  story,
  merchant,
  intervention,
}: {
  title: string;
  story: string;
  merchant: Merchant;
  intervention: Intervention | null;
}) {
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-10 gap-y-3">
        <div>
          <Eyebrow>Merchant under evaluation</Eyebrow>
          <h2 className="t-title mt-2 text-ink">{title}</h2>
        </div>
        <p className="figure t-caption text-ink-subtle">
          {merchant.merchant_id}
        </p>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-x-8 gap-y-6 border-t border-rule pt-6 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Customers" value={count(merchant.population)} />
        <Stat label="Avg order" value={rupees(merchant.observed_aov_inr)} />
        <Stat label="Margin" value={percent(merchant.observed_margin, 0)} />
        <Stat
          label="Contribution / order"
          value={rupees(merchant.contribution_per_order_inr)}
        />
        <Stat
          label="Conversion"
          value={percent(merchant.observed_conversion)}
        />
        <Stat label="Budget" value={rupees(merchant.budget_inr)} />
      </div>

      {intervention ? (
        <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule pt-5">
          <Eyebrow>Offer</Eyebrow>
          <span className="t-small font-medium text-ink">
            {intervention.name}
          </span>
          <Chip tone="spend">
            {rupees(intervention.incentive_cost_per_order_inr)} per order
          </Chip>
          <Chip tone="spend">
            {percent(intervention.depth_at_observed_aov, 1)} depth
          </Chip>
        </div>
      ) : null}

      <details className="group mt-5">
        <summary className="t-caption cursor-pointer list-none text-ink-muted transition-colors hover:text-ink">
          <span className="mr-2 inline-block text-ink-subtle transition-transform group-open:rotate-90">
            ▸
          </span>
          Merchant story, offer detail, and what the assistant was allowed to
          read
        </summary>
        <div className="mt-4 grid gap-x-14 gap-y-6 border-t border-rule pt-5 lg:grid-cols-2">
          <div className="space-y-4">
            <p className="t-small max-w-[58ch] text-ink-muted">{story}</p>
            {intervention ? (
              <p className="t-small max-w-[58ch] text-ink-muted">
                {intervention.description}
              </p>
            ) : null}
          </div>
          <ul className="space-y-1.5">
            {merchant.context.map((line) => (
              <li key={line} className="figure t-caption text-ink-muted">
                {line}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The assistant's proposal                                                    */
/* -------------------------------------------------------------------------- */

/**
 * What the assistant said, in its own terms.
 *
 * A proposal, not a conversation: the useful thing about the model's
 * contribution is the hypothesis and the mechanism it names. A reply that
 * failed validation is shown as a refusal carrying the validator's own reason,
 * never as a partial proposal.
 */
export function AgentProposal({
  envelope,
  merchant,
}: {
  envelope: ProposalEnvelope;
  merchant: Merchant;
}) {
  if (!envelope.accepted || !envelope.proposal) {
    return (
      <div className="border-l-2 border-risk pl-5">
        <Eyebrow className="!text-risk">AI proposal refused</Eyebrow>
        <p className="t-small mt-2.5 max-w-[58ch] text-ink">
          {envelope.rejected_because ?? "The reply could not be used."}
        </p>
        <p className="t-caption mt-2 text-ink-muted">
          Nothing reached the policy layer, and nothing was spent.
        </p>
      </div>
    );
  }

  const p = envelope.proposal;

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <SubHeading>What the assistant proposed</SubHeading>
        <Chip tone="open" glyph="◇">
          Evidence: {p.evidence_basis.toLowerCase()}
        </Chip>
      </div>

      <p className="t-lead mt-4 max-w-[52ch] text-ink">{p.hypothesis}</p>
      <p className="t-small mt-3 max-w-[52ch] text-ink-muted">{p.mechanism}</p>

      <dl className="mt-7 grid grid-cols-2 gap-x-8 gap-y-5">
        <div>
          <dt className="eyebrow">Intervention</dt>
          <dd className="figure mt-1.5 text-[0.85rem] text-ink">
            {p.intervention_id}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Cohort</dt>
          <dd className="figure mt-1.5 text-[0.85rem] text-ink">
            {p.cohort_id === "ALL"
              ? `Whole base · ${count(merchant.population)}`
              : p.cohort_id}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Expected lift</dt>
          <dd className="figure mt-1.5 text-[0.85rem] text-ink">
            {percent(p.expected_lift_absolute, 2)} absolute
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Read from</dt>
          <dd className="figure mt-1.5 text-[0.85rem] text-ink">
            {p.citations.join(", ")}
          </dd>
        </div>
      </dl>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Prior evidence                                                              */
/* -------------------------------------------------------------------------- */

export function PriorEvidence({
  history,
}: {
  history: CampaignHistory | null;
}) {
  return (
    <div>
      <SubHeading>What was known before</SubHeading>
      {history ? (
        <p className="t-small mt-4 max-w-[46ch] text-ink">
          One past campaign on{" "}
          <span className="figure">{count(history.treated_customers)}</span>{" "}
          customers:{" "}
          <span className="figure">
            {rupeesExact(history.net_per_treated_customer_inr)}
          </span>{" "}
          net per treated customer, standard error{" "}
          <span className="figure">
            {rupeesExact(history.standard_error_inr)}
          </span>
          .
        </p>
      ) : (
        <p className="t-small mt-4 text-ink-subtle italic">
          No prior campaign is recorded for this offer.
        </p>
      )}
      <p className="t-caption mt-4 max-w-[46ch] text-ink-muted">
        History and priors are enough to justify asking a question. Only a
        measurement on this merchant can authorise spending — which is why an
        evidence basis is carried on every screen.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Next action                                                                 */
/* -------------------------------------------------------------------------- */

export function ActionLink({
  href,
  children,
  primary = false,
}: {
  href: string;
  children: ReactNode;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-2 rounded-[3px] px-4 py-2 text-[0.85rem] font-medium transition-colors ${
        primary
          ? "bg-ink text-surface hover:opacity-85"
          : "border border-rule-strong text-ink hover:bg-sunk"
      }`}
    >
      {children}
      <span aria-hidden="true">→</span>
    </Link>
  );
}

/**
 * What the merchant does next.
 *
 * Each action navigates to evidence that already exists. None launches a
 * campaign, moves money, or re-runs a decision — the actuator is the Python
 * engine, and a button here that implied otherwise would misstate where
 * authority sits.
 */
export function NextAction({
  decision,
  scenario,
  hasExperiment,
  recommendation,
}: {
  decision: Decision;
  scenario: ScenarioId;
  hasExperiment: boolean;
  recommendation: Recommendation;
}) {
  const copy: Record<Decision, string> = {
    PROMOTE: "Fund the rollout the measurement supports.",
    DO_NOT_PROMOTE:
      "No experiment recommended. Hold the promotion and keep the budget.",
    RUN_EXPERIMENT_FIRST: `Run a controlled test of ${count(
      recommendation.experiment_horizon_per_arm,
    )} customers per arm before spending.`,
    INSUFFICIENT_EVIDENCE: "Nothing can be decided from this proposal.",
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-10 gap-y-5">
      <div>
        <Eyebrow>Next action</Eyebrow>
        <p className="t-lead mt-2.5 max-w-[50ch] text-ink">{copy[decision]}</p>
      </div>
      <div className="flex flex-wrap gap-2.5">
        {decision === "PROMOTE" && hasExperiment ? (
          <ActionLink href={withScenario("/experiment", scenario)} primary>
            View the evidence
          </ActionLink>
        ) : null}
        {decision === "RUN_EXPERIMENT_FIRST" ? (
          <ActionLink href={withScenario("/experiment", scenario)} primary>
            View the experiment plan
          </ActionLink>
        ) : null}
        <ActionLink href={withScenario("/audit", scenario)}>
          View the decision record
        </ActionLink>
      </div>
    </div>
  );
}
