/**
 * Overview — the decision workspace.
 *
 * One question, answered at the top of the screen, with the arithmetic that
 * settled it directly underneath. Everything that supports the answer — the
 * gate ladder, the assistant's proposal, the experiment, the audit chain — sits
 * below it or one click away. A judge who reads only the first screenful should
 * still leave knowing what was decided and what it earns.
 */

"use client";

import { ContributionRule } from "@/components/ContributionRule";
import {
  DecisionHero,
  GateLadder,
  ProposalToPolicy,
  WhyPanel,
} from "@/components/Decision";
import {
  AgentProposal,
  HistoryNote,
  MerchantStrip,
  NextAction,
} from "@/components/Merchant";
import { useScenarioId, withScenario } from "@/components/ScenarioContext";
import { FixtureNotice } from "@/components/TopRail";
import {
  ErrorState,
  Figure,
  Loading,
  Panel,
  SectionHeading,
} from "@/components/ui";
import { useScenario } from "@/lib/api";
import { rupees } from "@/lib/format";
import Link from "next/link";

export default function OverviewPage() {
  const { scenario } = useScenarioId();
  const { data, error, loading, retry } = useScenario(scenario);

  if (error) return <ErrorState message={error.message} onRetry={retry} />;
  if (loading || !data) return <Loading label="Deciding" />;

  const final = data.final;
  const measured = final.evidence_basis === "EXPERIMENT";
  const changedItsMind = data.initial.decision !== final.decision;

  return (
    <div className="space-y-12">
      <FixtureNotice label={data.label} />

      <MerchantStrip
        title={data.title}
        story={data.story}
        merchant={data.merchant}
        intervention={data.intervention}
      />

      {/* ---- The decision, and the arithmetic behind it ------------------- */}
      <Panel className="overflow-hidden">
        <div className="grid gap-10 p-7 lg:grid-cols-[1.15fr_1fr] lg:p-9">
          <DecisionHero recommendation={final} />

          <div className="flex flex-col justify-center gap-7 border-t border-rule pt-8 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-9">
            <div className="grid grid-cols-2 gap-6">
              <Figure
                label="Incremental contribution"
                value={rupees(final.expected_incremental_contribution_inr)}
                tone="earn"
              />
              <Figure
                label="Incentive cost"
                value={rupees(final.expected_incentive_cost_inr)}
                tone="spend"
              />
            </div>
            <div className="border-t border-rule pt-6">
              <Figure
                label="Net contribution"
                value={rupees(final.expected_net_contribution_inr)}
                tone={
                  final.expected_net_contribution_inr < 0 ? "deficit" : "earn"
                }
                emphasis
                footnote={
                  measured
                    ? "Projected from the measured pilot across the rollout the budget can fund."
                    : "Expected at the lift the assistant proposed. Not a measurement."
                }
              />
            </div>
          </div>
        </div>

        <div className="border-t border-rule bg-sunk/40 px-7 pt-6 pb-7 lg:px-9">
          <SectionHeading
            eyebrow="The subtraction"
            title="What the promotion earns, and what the incentive takes back"
          />
          <ContributionRule
            contributionInr={final.expected_incremental_contribution_inr}
            incentiveInr={final.expected_incentive_cost_inr}
            netInr={final.expected_net_contribution_inr}
            basisNote={
              measured
                ? "measured, then projected to the funded rollout"
                : "expected at the proposed lift"
            }
          />
        </div>
      </Panel>

      {/* ---- How the decision got here ----------------------------------- */}
      {changedItsMind ? (
        <Panel className="flex flex-wrap items-center justify-between gap-5 px-5 py-5">
          <p className="max-w-[62ch] text-[0.92rem] leading-relaxed text-ink">
            This merchant did not start here. Before the experiment ran, the
            answer was{" "}
            <span className="font-medium text-open">
              run experiment first
            </span>
            . A randomised pilot changed the evidence, and the rollout gate
            reopened the question.
          </p>
          <Link
            href={withScenario("/experiment", scenario)}
            className="rounded-[2px] border border-rule-strong px-4 py-2 text-[0.85rem] font-medium text-ink transition-colors hover:bg-sunk"
          >
            See the progression →
          </Link>
        </Panel>
      ) : null}

      {/* ---- Why --------------------------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Why"
          title="Why MarginPilot recommends this"
          note="Written by the policy layer at the moment it decided. Nothing on this page is a summary produced after the fact."
        />
        <Panel className="p-7">
          <WhyPanel recommendation={final} />
        </Panel>
      </section>

      {/* ---- The gates --------------------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Policy"
          title="The gates this decision passed through"
          note="Six ordered gates. The first that fires returns, and none of them can be reached around."
        />
        <GateLadder recommendation={final} />
      </section>

      {/* ---- Model to policy --------------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Authority"
          title="AI suggests. MarginPilot decides."
          note="The assistant may propose an intervention, a cohort and a hypothesis, and may request an outcome. The request is recorded, priced by the deterministic layer, and then either upheld or overruled."
        />
        <div className="space-y-5">
          <ProposalToPolicy recommendation={final} />
          <div className="grid gap-5 lg:grid-cols-2">
            <AgentProposal
              envelope={data.proposal}
              merchant={data.merchant}
            />
            <Panel className="p-5">
              <SectionHeading
                eyebrow="Prior evidence"
                title="What was known before"
              />
              {data.history ? (
                <HistoryNote
                  treated={data.history.treated_customers}
                  netPerCustomer={data.history.net_per_treated_customer_inr}
                  standardError={data.history.standard_error_inr}
                />
              ) : (
                <p className="text-[0.86rem] leading-relaxed text-slate-soft italic">
                  No prior campaign is recorded for this offer.
                </p>
              )}
              <p className="mt-4 text-[0.84rem] leading-relaxed text-slate">
                History and priors are enough to justify asking a question. Only
                a measurement on this merchant can authorise spending, which is
                why the evidence basis is carried on every screen.
              </p>
            </Panel>
          </div>
        </div>
      </section>

      <NextAction
        decision={final.decision}
        scenario={scenario}
        hasExperiment={data.experiment !== null}
        recommendation={final}
      />
    </div>
  );
}
