/**
 * Who the decision is about, what was proposed, and what to do next.
 *
 * The context strip carries only what is needed to follow the arithmetic on the
 * rest of the page: how many customers, what an order is worth, what margin it
 * carries, and what the offer costs. Everything else about the merchant lives
 * behind a disclosure.
 */

"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { count, percent, rupees, rupeesExact } from "@/lib/format";
import type {
  Decision,
  Intervention,
  Merchant,
  ProposalEnvelope,
  Recommendation,
} from "@/types/domain";
import { withScenario, type ScenarioId } from "./ScenarioContext";
import { Chip, Eyebrow, Panel } from "./ui";

/* -------------------------------------------------------------------------- */
/* Context strip                                                               */
/* -------------------------------------------------------------------------- */

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[7.5rem] border-l border-rule pl-4 first:border-l-0 first:pl-0">
      <p className="eyebrow">{label}</p>
      <p className="figure mt-1.5 text-[0.95rem] text-ink">{value}</p>
    </div>
  );
}

export function MerchantStrip({
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
    <Panel className="px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div className="max-w-[34ch]">
          <Eyebrow>Merchant</Eyebrow>
          <h2 className="mt-1.5 text-[1.15rem] font-medium tracking-[-0.015em] text-ink">
            {title}
          </h2>
          <p className="figure mt-1 text-[0.72rem] text-slate-soft">
            {merchant.merchant_id}
          </p>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-4">
          <Stat label="Customers" value={count(merchant.population)} />
          <Stat label="Avg order" value={rupees(merchant.observed_aov_inr)} />
          <Stat label="Margin" value={percent(merchant.observed_margin, 0)} />
          <Stat
            label="Contribution / order"
            value={rupees(merchant.contribution_per_order_inr)}
          />
          <Stat label="Conversion" value={percent(merchant.observed_conversion)} />
          <Stat label="Budget" value={rupees(merchant.budget_inr)} />
        </div>
      </div>

      <p className="mt-4 max-w-[76ch] border-t border-rule pt-4 text-[0.88rem] leading-relaxed text-slate">
        {story}
      </p>

      {intervention ? (
        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule pt-4">
          <Eyebrow>Offer</Eyebrow>
          <span className="text-[0.9rem] font-medium text-ink">
            {intervention.name}
          </span>
          <Chip tone="spend">
            {rupees(intervention.incentive_cost_per_order_inr)} per order
          </Chip>
          <Chip tone="spend">
            {percent(intervention.depth_at_observed_aov, 1)} depth
          </Chip>
          <span className="w-full max-w-[70ch] text-[0.84rem] leading-relaxed text-slate">
            {intervention.description}
          </span>
        </div>
      ) : null}

      {merchant.context.length ? (
        <details className="group mt-4 border-t border-rule pt-3">
          <summary className="cursor-pointer list-none text-[0.8rem] text-slate transition-colors hover:text-ink">
            <span className="mr-2 inline-block text-slate-soft transition-transform group-open:rotate-90">
              ▸
            </span>
            What the assistant was allowed to read
          </summary>
          <ul className="mt-3 space-y-1.5">
            {merchant.context.map((line) => (
              <li
                key={line}
                className="figure text-[0.78rem] leading-relaxed text-slate"
              >
                {line}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* The agent's proposal                                                        */
/* -------------------------------------------------------------------------- */

/**
 * What the assistant said, in its own terms.
 *
 * Shown as a proposal rather than a conversation: the useful thing about the
 * model's contribution is the hypothesis and the mechanism it names, not the
 * chat it arrived in. A reply that failed validation is shown as a refusal with
 * the validator's own reason, never as a partial proposal.
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
      <Panel className="p-5">
        <Eyebrow className="!text-deficit">AI proposal refused</Eyebrow>
        <p className="mt-2 max-w-[62ch] text-[0.92rem] leading-relaxed text-ink">
          {envelope.rejected_because ?? "The reply could not be used."}
        </p>
        <p className="mt-2 text-[0.82rem] text-slate">
          Nothing was proposed to the policy layer, and nothing was spent.
        </p>
      </Panel>
    );
  }

  const p = envelope.proposal;

  return (
    <Panel className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <Eyebrow>AI proposal</Eyebrow>
        <Chip tone="open" glyph="◇">
          Evidence: {p.evidence_basis.toLowerCase()}
        </Chip>
      </div>

      <dl className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
        <div>
          <dt className="text-[0.78rem] text-slate-soft">Intervention</dt>
          <dd className="figure mt-1 text-[0.88rem] text-ink">
            {p.intervention_id}
          </dd>
        </div>
        <div>
          <dt className="text-[0.78rem] text-slate-soft">Cohort</dt>
          <dd className="figure mt-1 text-[0.88rem] text-ink">
            {p.cohort_id === "ALL"
              ? `Whole base — ${count(merchant.population)} customers`
              : p.cohort_id}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-[0.78rem] text-slate-soft">Hypothesis</dt>
          <dd className="mt-1 max-w-[64ch] text-[0.92rem] leading-relaxed text-ink">
            {p.hypothesis}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-[0.78rem] text-slate-soft">Mechanism</dt>
          <dd className="mt-1 max-w-[64ch] text-[0.92rem] leading-relaxed text-slate">
            {p.mechanism}
          </dd>
        </div>
        <div>
          <dt className="text-[0.78rem] text-slate-soft">Expected lift</dt>
          <dd className="figure mt-1 text-[0.88rem] text-ink">
            {percent(p.expected_lift_absolute, 2)} absolute
          </dd>
        </div>
        <div>
          <dt className="text-[0.78rem] text-slate-soft">Read from</dt>
          <dd className="mt-1 flex flex-wrap gap-1.5">
            {p.citations.map((c) => (
              <span
                key={c}
                className="figure rounded-[2px] bg-sunk px-1.5 py-0.5 text-[0.72rem] text-slate"
              >
                {c}
              </span>
            ))}
          </dd>
        </div>
      </dl>
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* History                                                                     */
/* -------------------------------------------------------------------------- */

export function HistoryNote({
  treated,
  netPerCustomer,
  standardError,
}: {
  treated: number;
  netPerCustomer: number;
  standardError: number;
}) {
  return (
    <p className="text-[0.86rem] leading-relaxed text-slate">
      The only prior evidence is one campaign on {count(treated)} customers:{" "}
      <span className="figure text-ink">{rupeesExact(netPerCustomer)}</span> net
      per treated customer, standard error{" "}
      <span className="figure text-ink">{rupeesExact(standardError)}</span>.
    </p>
  );
}

/* -------------------------------------------------------------------------- */
/* Next action                                                                 */
/* -------------------------------------------------------------------------- */

function ActionLink({
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
      className={`inline-flex items-center gap-2 rounded-[2px] px-4 py-2 text-[0.85rem] font-medium transition-colors ${
        primary
          ? "bg-ink text-surface hover:bg-ink/85"
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
 * Each action navigates to evidence that already exists. None of them launches
 * a campaign, moves money, or re-runs a decision — this product's actuator is
 * the Python engine, and a button here that claimed otherwise would be a lie
 * about where authority sits.
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
    <Panel className="flex flex-wrap items-center justify-between gap-5 px-5 py-5">
      <div>
        <Eyebrow>Next action</Eyebrow>
        <p className="mt-2 max-w-[52ch] text-[0.95rem] leading-relaxed text-ink">
          {copy[decision]}
        </p>
      </div>
      <div className="flex flex-wrap gap-2.5">
        {decision === "PROMOTE" && hasExperiment ? (
          <ActionLink href={withScenario("/experiment", scenario)} primary>
            View experiment evidence
          </ActionLink>
        ) : null}
        {decision === "RUN_EXPERIMENT_FIRST" ? (
          <ActionLink href={withScenario("/experiment", scenario)} primary>
            View experiment plan
          </ActionLink>
        ) : null}
        <ActionLink href={withScenario("/audit", scenario)}>
          View decision record
        </ActionLink>
      </div>
    </Panel>
  );
}
