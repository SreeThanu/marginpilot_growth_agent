/**
 * Trust & safety — the refusals, run live.
 *
 * Every row on this page comes back from a call made when the page loaded. The
 * seven adversarial scenarios are executed by `src/eval/adversarial.py`, the
 * malformed replies go through the same `recommend_from_raw` a live model reply
 * would, and the override table is read off the three decisions the other
 * screens are showing. Nothing here is a stored result.
 */

"use client";

import { useReproducibility, useSafety } from "@/lib/api";
import { DECISION_LABEL, percent } from "@/lib/format";
import {
  Chip,
  ErrorState,
  Eyebrow,
  Field,
  Loading,
  Panel,
  SectionHeading,
  toneText,
} from "@/components/ui";
import { FixtureNotice } from "@/components/TopRail";
import { DECISION_TONE } from "@/lib/format";

function Headline({
  value,
  label,
  detail,
  tone,
}: {
  value: string;
  label: string;
  detail: string;
  tone: "earn" | "deficit" | "spend";
}) {
  return (
    <div className="bg-surface px-5 py-5">
      <p className={`figure text-[1.9rem] leading-none ${toneText(tone)}`}>
        {value}
      </p>
      <p className="mt-2.5 text-[0.88rem] font-medium text-ink">{label}</p>
      <p className="mt-1 text-[0.78rem] leading-relaxed text-slate-soft">
        {detail}
      </p>
    </div>
  );
}

export default function TrustPage() {
  const safety = useSafety();
  const repro = useReproducibility();

  if (safety.error)
    return <ErrorState message={safety.error.message} onRetry={safety.retry} />;
  if (safety.loading || !safety.data)
    return <Loading label="Running the refusal scenarios" />;

  const s = safety.data;
  const allRefused = s.refused === s.total;
  const malformedHeld = s.malformed.every((m) => !m.spends_money);
  const overrides = s.model_overrides.filter((m) => m.overruled);

  return (
    <div className="space-y-12">
      <FixtureNotice />

      <section>
        <SectionHeading
          eyebrow="Trust"
          title="What MarginPilot refuses to do"
          note="These checks ran when this page loaded. Each one attempts something the system must not permit, and each returns a refusal naming the module that produced it."
        />

        <div className="grid gap-px overflow-hidden rounded-[3px] border border-rule bg-rule sm:grid-cols-3">
          <Headline
            value={`${s.refused} / ${s.total}`}
            label="Adversarial scenarios refused"
            detail="Run live from src/eval/adversarial.py"
            tone={allRefused ? "earn" : "deficit"}
          />
          <Headline
            value={`${s.malformed.filter((m) => !m.spends_money).length} / ${
              s.malformed.length
            }`}
            label="Malformed replies held"
            detail="Broken model output fails closed instead of defaulting"
            tone={malformedHeld ? "earn" : "deficit"}
          />
          <Headline
            value={`${overrides.length} / ${s.model_overrides.length}`}
            label="Model requests overruled"
            detail="The assistant asked to promote in every scenario; the policy decided each one on its own"
            tone="spend"
          />
        </div>
      </section>

      {/* ---- Live refusals ------------------------------------------------ */}
      <section>
        <SectionHeading
          eyebrow="Refusals"
          title="Attempted, and stopped"
          note="A refusal is not an error. Each of these is the system working and saying no with a reason attached."
        />
        <div className="grid gap-px overflow-hidden rounded-[3px] border border-rule bg-rule lg:grid-cols-2">
          {s.scenarios.map((scenario) => (
            <article key={scenario.name} className="bg-surface p-5">
              <div className="flex items-start justify-between gap-4">
                <h3 className="text-[0.95rem] font-medium text-ink">
                  {scenario.name}
                </h3>
                <Chip
                  tone={scenario.refused ? "earn" : "deficit"}
                  glyph={scenario.refused ? "✓" : "■"}
                >
                  {scenario.refused ? "Refused" : "Not refused"}
                </Chip>
              </div>
              <p className="mt-2.5 max-w-[56ch] text-[0.85rem] leading-relaxed text-slate">
                {scenario.attempted}
              </p>
              <p className="figure mt-3 text-[0.74rem] text-slate-soft">
                {scenario.refused_by}
              </p>
              <p className="mt-2 max-w-[56ch] border-t border-rule pt-2.5 text-[0.82rem] leading-relaxed text-ink">
                {scenario.reason}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* ---- Fail closed -------------------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Fail closed"
          title="When the assistant's reply is unusable"
          note="Each of these is fed to the same entry point a live model reply goes through. A refusal is the safe outcome and is never softened into a default proposal."
        />
        <Panel className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-rule-strong">
                {["Reply", "Outcome", "Constraint", "Spends money"].map(
                  (head) => (
                    <th key={head} className="eyebrow px-5 py-3 font-medium">
                      {head}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {s.malformed.map((row) => (
                <tr key={row.label} className="border-b border-rule last:border-b-0">
                  <td className="px-5 py-3 text-[0.86rem] text-ink">
                    {row.label}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`text-[0.86rem] font-medium ${toneText(
                        DECISION_TONE[row.decision],
                      )}`}
                    >
                      {DECISION_LABEL[row.decision]}
                    </span>
                  </td>
                  <td className="figure px-5 py-3 text-[0.78rem] text-slate">
                    {row.binding_constraints.join(", ") || "—"}
                  </td>
                  <td className="px-5 py-3">
                    <Chip
                      tone={row.spends_money ? "deficit" : "earn"}
                      glyph={row.spends_money ? "■" : "✓"}
                    >
                      {row.spends_money ? "Yes" : "No"}
                    </Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </section>

      {/* ---- Where authority sits ----------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Authority"
          title="What the model asked for, and what the policy returned"
          note="Agreement in one scenario is not evidence that the model is reliable. It is evidence that the policy decided independently and happened to reach the same answer."
        />
        <div className="grid gap-px overflow-hidden rounded-[3px] border border-rule bg-rule md:grid-cols-3">
          {s.model_overrides.map((row) => (
            <article key={row.scenario} className="bg-surface p-5">
              <Eyebrow>Merchant {row.scenario}</Eyebrow>
              <p className="mt-2 text-[0.88rem] font-medium text-ink">
                {row.title}
              </p>
              <div className="mt-4 space-y-1.5">
                <p className="text-[0.82rem] text-slate">
                  Model asked:{" "}
                  <span className="text-ink">
                    {row.model_requested
                      ? DECISION_LABEL[row.model_requested]
                      : "nothing"}
                  </span>
                </p>
                <p className="text-[0.82rem] text-slate">
                  Policy returned:{" "}
                  <span
                    className={`font-medium ${toneText(
                      DECISION_TONE[row.policy_decided],
                    )}`}
                  >
                    {DECISION_LABEL[row.policy_decided]}
                  </span>
                </p>
              </div>
              <div className="mt-4">
                <Chip
                  tone={row.overruled ? "deficit" : "spend"}
                  glyph={row.overruled ? "■" : "="}
                >
                  {row.overruled ? "Overruled" : "Agreed"}
                </Chip>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ---- Standing limits ---------------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Policy"
          title="The standing limits every action is checked against"
          note="Numbers a merchant would recognise and could argue with. A policy nobody can read is a policy nobody agreed to."
        />
        <Panel className="px-5 py-2">
          <Field
            label="Deepest permitted discount"
            value={percent(s.policy_limits.max_discount_pct, 0)}
          />
          <Field
            label="Minimum contribution margin"
            value={percent(s.policy_limits.min_contribution_margin, 0)}
          />
          <Field
            label="Maximum share of the base in one campaign"
            value={percent(s.policy_limits.max_customer_exposure_share, 0)}
          />
          <Field
            label="Minimum experiment power"
            value={percent(s.policy_limits.min_experiment_power, 0)}
          />
          <Field
            label="Budget that must survive one action"
            value={percent(s.policy_limits.min_budget_headroom_share, 0)}
          />
        </Panel>
      </section>

      {/* ---- Reproducibility ---------------------------------------------- */}
      <section>
        <SectionHeading
          eyebrow="Reproducibility"
          title="What this repository pins itself to"
          note="Read from source at load time, so a drifted corpus or an edited fixture is visible here rather than silent."
        />
        {repro.error ? (
          <ErrorState message={repro.error.message} onRetry={repro.retry} />
        ) : repro.loading || !repro.data ? (
          <Loading label="Reading the pins" />
        ) : (
          <div className="grid gap-px overflow-hidden rounded-[3px] border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-3">
            {repro.data.badges.map((badge) => (
              <article key={badge.label} className="bg-surface p-5">
                <Eyebrow>{badge.label}</Eyebrow>
                <p className="figure mt-2 text-[0.92rem] text-ink">
                  {badge.value}
                </p>
                <p className="mt-2 text-[0.78rem] leading-relaxed text-slate-soft">
                  {badge.detail}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
