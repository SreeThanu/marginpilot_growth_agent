/**
 * Overview — the decision workspace.
 *
 * The verdict is the first thing on the page, on the dark band, with the
 * arithmetic that settled it in the same view. Merchant metadata comes after
 * the answer rather than before it: a reader who never scrolls should still
 * leave knowing what was decided, what it earns, and that a deterministic layer
 * — not the model — decided it.
 */

"use client";

import Link from "next/link";

import {
  ControlPath,
  DecisionBand,
  GateLadder,
  Reasoning,
} from "@/components/Decision";
import {
  AgentProposal,
  MerchantContext,
  NextAction,
  PriorEvidence,
} from "@/components/Merchant";
import { useScenarioId, withScenario } from "@/components/ScenarioContext";
import { FixtureNotice } from "@/components/TopRail";
import {
  ErrorState,
  Loading,
  Rule,
  SectionHead,
  Shell,
} from "@/components/ui";
import { useScenario } from "@/lib/api";

export default function OverviewPage() {
  const { scenario } = useScenarioId();
  const { data, error, loading, retry } = useScenario(scenario);

  if (error) return <ErrorState message={error.message} onRetry={retry} />;
  if (loading || !data) return <Loading label="Deciding" />;

  const final = data.final;
  const changedItsMind = data.initial.decision !== final.decision;

  return (
    <>
      {/* -- the verdict, continuous with the chrome above it --------------- */}
      <DecisionBand recommendation={final} scenarioKey={data.scenario} />

      <Shell className="pt-5">
        <FixtureNotice label={data.label} />
      </Shell>

      {/* -- the architecture, made literal --------------------------------- */}
      <Shell className="pt-16">
        <SectionHead
          eyebrow="Control path"
          title="The assistant proposes. The policy disposes."
          note="Four stations, in order. Nothing downstream can be reached around, and no station can be entered by the model."
        />
        <div className="mt-9">
          <ControlPath recommendation={final} experiment={data.experiment} />
        </div>

        {changedItsMind ? (
          <div className="mt-10 flex flex-wrap items-center justify-between gap-x-10 gap-y-4 border-l-2 border-earn pl-5">
            <p className="t-small max-w-[62ch] text-ink">
              This merchant did not start here. Before the experiment ran the
              answer was{" "}
              <span className="font-medium text-open">
                run experiment first
              </span>
              . A randomised pilot changed the evidence, and only then did the
              rollout gate reopen the question.
            </p>
            <Link
              href={withScenario("/experiment", scenario)}
              className="t-small shrink-0 font-medium text-ink underline underline-offset-4 hover:no-underline"
            >
              See the progression →
            </Link>
          </div>
        ) : null}
      </Shell>

      {/* -- who this is about ---------------------------------------------- */}
      <Shell className="pt-16">
        <Rule />
        <div className="pt-10">
          <MerchantContext
            title={data.title}
            story={data.story}
            merchant={data.merchant}
            intervention={data.intervention}
          />
        </div>
      </Shell>

      {/* -- why ------------------------------------------------------------ */}
      <Shell className="pt-16">
        <Rule />
        <div className="pt-10">
          <SectionHead
            eyebrow="Reasoning"
            title="Why the policy answered this way"
            note="Written by the policy layer at the moment it decided, and rendered verbatim. Nothing here is a summary produced after the fact."
          />
          <div className="mt-9">
            <Reasoning recommendation={final} />
          </div>
        </div>
      </Shell>

      {/* -- the gates ------------------------------------------------------ */}
      <Shell className="pt-16">
        <Rule />
        <div className="grid gap-x-16 gap-y-10 pt-10 lg:grid-cols-[0.85fr_1.15fr]">
          <SectionHead
            eyebrow="Gates"
            title="Six ordered checks"
            note="The first that fires returns. Spending requires a measurement; declining requires none."
          />
          <GateLadder recommendation={final} />
        </div>
      </Shell>

      {/* -- the model's contribution --------------------------------------- */}
      <Shell className="pt-16">
        <Rule />
        <div className="grid gap-x-16 gap-y-12 pt-10 lg:grid-cols-[1.15fr_0.85fr]">
          <AgentProposal envelope={data.proposal} merchant={data.merchant} />
          <PriorEvidence history={data.history} />
        </div>
      </Shell>

      {/* -- next ----------------------------------------------------------- */}
      <Shell className="pt-16">
        <Rule />
        <div className="pt-10">
          <NextAction
            decision={final.decision}
            scenario={scenario}
            hasExperiment={data.experiment !== null}
            recommendation={final}
          />
        </div>
      </Shell>
    </>
  );
}
