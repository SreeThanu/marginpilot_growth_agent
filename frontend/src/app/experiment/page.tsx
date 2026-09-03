/**
 * Experiment — what was tested, what came back, and what it bought.
 *
 * Three states, and the screen says plainly which one it is in: no experiment
 * recommended, an experiment planned but not run, or an experiment read at its
 * horizon. The third is the only one that shows a measurement, and it is the
 * only route on this product to a rollout.
 */

"use client";

import Link from "next/link";

import {
  ContributionChart,
  ConversionChart,
  EffectInterval,
} from "@/components/ExperimentCharts";
import { useScenarioId, withScenario } from "@/components/ScenarioContext";
import { FixtureNotice } from "@/components/TopRail";
import {
  Chip,
  EmptyState,
  ErrorState,
  Eyebrow,
  Field,
  Loading,
  Panel,
  SectionHeading,
  Unavailable,
} from "@/components/ui";
import { useScenario } from "@/lib/api";
import {
  DECISION_LABEL,
  count,
  pValue,
  percent,
  rupees,
  rupeesExact,
} from "@/lib/format";
import type { ScenarioDetail } from "@/types/domain";

/* -------------------------------------------------------------------------- */
/* The progression                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The five stations a validated promotion passes through, in order.
 *
 * Numbered because the content genuinely is a sequence: the rollout gate cannot
 * be reached before the horizon, and the horizon cannot be reached before the
 * pilot launches.
 */
function Progression({ data }: { data: ScenarioDetail }) {
  const exp = data.experiment;
  const stations = [
    {
      title: "Initial assessment",
      value: DECISION_LABEL[data.initial.decision],
      detail: "Decided from the brief alone. This path cannot return Promote.",
      done: true,
    },
    {
      title: "Randomised experiment",
      value: exp ? `${count(exp.horizon_per_arm)} per arm` : "Not launched",
      detail: exp
        ? "Production assignment is a blake2b hash of customer and experiment id, with no route for the assistant. This demonstration fixture draws arm outcomes in aggregate from its committed seed."
        : "No pilot has been launched for this merchant.",
      done: exp !== null,
    },
    {
      title: "Read at the horizon",
      value: exp
        ? exp.verdict_eligible
          ? "Horizon reached"
          : "Before the horizon"
        : "Not read",
      detail:
        "The horizon is fixed at design time. There is no early-stop path.",
      done: exp?.verdict_eligible ?? false,
    },
    {
      title: "Rollout gate",
      value: data.final.gates_passed.includes("G6")
        ? "G6 passed"
        : "Not reached",
      detail:
        "The measured effect is re-priced against the rollout the budget can actually fund.",
      done: data.final.gates_passed.includes("G6"),
    },
    {
      title: "Decision",
      value: DECISION_LABEL[data.final.decision],
      detail: data.final.diagnosis,
      done: true,
    },
  ];

  return (
    <ol className="grid gap-px overflow-hidden rounded-[3px] border border-rule bg-rule md:grid-cols-5">
      {stations.map((station, index) => (
        <li key={station.title} className="bg-surface p-4">
          <div className="flex items-baseline gap-2">
            <span className="eyebrow">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span
              aria-hidden="true"
              className={`text-[0.8rem] ${
                station.done ? "text-earn" : "text-slate-soft"
              }`}
            >
              {station.done ? "✓" : "·"}
            </span>
          </div>
          <p className="mt-2 text-[0.82rem] font-medium text-ink">
            {station.title}
          </p>
          <p className="figure mt-1 text-[0.82rem] text-slate">
            {station.value}
          </p>
          <p className="mt-2 text-[0.74rem] leading-relaxed text-slate-soft">
            {station.detail}
          </p>
        </li>
      ))}
    </ol>
  );
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function ExperimentPage() {
  const { scenario } = useScenarioId();
  const { data, error, loading, retry } = useScenario(scenario);

  if (error) return <ErrorState message={error.message} onRetry={retry} />;
  if (loading || !data) return <Loading label="Reading the experiment" />;

  const exp = data.experiment;
  const comparison = exp?.comparison ?? null;

  return (
    <div className="space-y-10">
      <FixtureNotice label={data.label} />

      <div>
        <SectionHeading
          eyebrow={`Merchant ${data.scenario} · ${data.merchant.merchant_id}`}
          title={
            exp
              ? "The pilot that decided this"
              : data.final.experiment_required
                ? "The pilot this merchant should run"
                : "No experiment recommended"
          }
          note={
            exp
              ? "One control arm and one treatment arm, sized before launch and read once at the pre-committed horizon."
              : data.final.experiment_required
                ? "Sized by the same power calculation that would run it, and priced against the merchant's budget."
                : "The arithmetic settles this offer before an experiment is worth contemplating."
          }
        />
        <Progression data={data} />
      </div>

      {/* ---- No experiment, and none warranted --------------------------- */}
      {!exp && !data.final.experiment_required ? (
        <EmptyState
          title="Nothing here is worth testing"
          body={data.final.rationale}
          action={
            <Link
              href={withScenario("/", scenario)}
              className="rounded-[2px] border border-rule-strong px-4 py-2 text-[0.85rem] font-medium text-ink transition-colors hover:bg-sunk"
            >
              Back to the decision →
            </Link>
          }
        />
      ) : null}

      {/* ---- Planned, not yet run ---------------------------------------- */}
      {!exp && data.final.experiment_required ? (
        <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
          <Panel className="p-6">
            <Eyebrow>Experiment plan</Eyebrow>
            <p className="mt-3 max-w-[60ch] text-[0.95rem] leading-relaxed text-ink">
              {data.final.rationale}
            </p>
            <div className="mt-6">
              <Field
                label="Customers per arm"
                value={count(data.final.experiment_horizon_per_arm)}
              />
              <Field
                label="Arms"
                value="2 — control and treatment"
              />
              <Field
                label="Pilot cost"
                value={rupees(data.final.experiment_cost_inr)}
              />
              <Field
                label="Break-even lift the offer must clear"
                value={
                  data.final.required_break_even_lift_absolute === null ? (
                    <Unavailable reason="Unreachable at any lift" />
                  ) : (
                    percent(data.final.required_break_even_lift_absolute, 2)
                  )
                }
              />
              <Field
                label="Measured result"
                value={<Unavailable reason="Not yet measured" />}
              />
            </div>
          </Panel>

          <Panel className="p-6">
            <Eyebrow className="!text-open">Open question</Eyebrow>
            <p className="mt-3 max-w-[46ch] text-[0.92rem] leading-relaxed text-ink">
              Whether this experiment costs less than the information it buys is
              unresolved in this project.
            </p>
            <p className="mt-3 max-w-[46ch] text-[0.86rem] leading-relaxed text-slate">
              No threshold for it has been committed, so none is applied. The
              gate checks affordability only, and carries{" "}
              <span className="figure text-open">
                G4_VALUE_OF_INFORMATION_UNRESOLVED
              </span>{" "}
              through to the merchant rather than quietly taking a side.
            </p>
            {data.final.unresolved.length === 0 ? (
              <p className="mt-4 text-[0.84rem] text-slate-soft italic">
                This recommendation carries no unresolved flag.
              </p>
            ) : null}
          </Panel>
        </div>
      ) : null}

      {/* ---- Run and read ------------------------------------------------ */}
      {exp ? (
        <>
          <Panel className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <Eyebrow>Experiment</Eyebrow>
                <p className="figure mt-1.5 text-[0.95rem] text-ink">
                  {exp.experiment_id}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Chip
                  tone={exp.verdict_eligible ? "earn" : "open"}
                  glyph={exp.verdict_eligible ? "✓" : "◇"}
                >
                  {exp.verdict_eligible
                    ? "Horizon reached"
                    : "Before the horizon"}
                </Chip>
                <Chip tone="spend">
                  {count(exp.horizon_per_arm)} per arm
                </Chip>
                <Chip tone="spend">
                  Pilot spend {rupees(exp.pilot_spend_inr)}
                </Chip>
                <Chip tone="spend">
                  {percent(exp.depth, 1)} depth
                </Chip>
              </div>
            </div>

            <div className="mt-7 grid gap-8 lg:grid-cols-2">
              <ConversionChart arms={exp.arms} />
              <ContributionChart arms={exp.arms} />
            </div>

            <div className="mt-8 overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-rule-strong">
                    {[
                      "Arm",
                      "Assigned",
                      "Converted",
                      "Conversion",
                      "Contribution / customer",
                    ].map((head) => (
                      <th
                        key={head}
                        className="eyebrow pb-2.5 font-medium first:text-left last:text-right [&:not(:first-child)]:text-right"
                      >
                        {head}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {exp.arms.map((arm) => (
                    <tr key={arm.name} className="border-b border-rule">
                      <td className="py-2.5 text-[0.88rem] text-ink">
                        {arm.name}
                      </td>
                      <td className="figure py-2.5 text-right text-[0.88rem] text-ink">
                        {count(arm.n_assigned)}
                      </td>
                      <td className="figure py-2.5 text-right text-[0.88rem] text-ink">
                        {count(arm.n_converted)}
                      </td>
                      <td className="figure py-2.5 text-right text-[0.88rem] text-ink">
                        {percent(arm.conversion_rate, 2)}
                      </td>
                      <td className="figure py-2.5 text-right text-[0.88rem] text-ink">
                        {rupeesExact(arm.contribution_mean_inr)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
            <Panel className="flex flex-col justify-center p-6">
              {comparison ? (
                <EffectInterval
                  comparison={comparison}
                  breakEven={data.initial.required_break_even_lift_absolute}
                />
              ) : (
                <>
                  <Eyebrow>Measured lift against break-even</Eyebrow>
                  <p className="mt-3">
                    <Unavailable reason="The evaluator returned no comparison" />
                  </p>
                </>
              )}
            </Panel>

            <Panel className="p-6">
              <Eyebrow>What the evaluator returned</Eyebrow>
              {comparison ? (
                <div className="mt-3">
                  <Field
                    label="Absolute lift"
                    value={percent(comparison.absolute_difference, 2)}
                  />
                  <Field
                    label="95% interval"
                    value={`${percent(comparison.difference_ci_low, 2)} … ${percent(
                      comparison.difference_ci_high,
                      2,
                    )}`}
                  />
                  <Field label="p-value" value={pValue(comparison.p_value)} />
                  <Field
                    label="Net contribution, pilot"
                    value={rupees(comparison.net_contribution_inr)}
                  />
                  <Field
                    label="Net per treated customer"
                    value={rupeesExact(
                      comparison.net_per_treated_customer_inr,
                    )}
                  />
                  <Field
                    label="P(net > 0)"
                    value={percent(comparison.probability_net_positive, 2)}
                  />
                </div>
              ) : (
                <p className="mt-3">
                  <Unavailable reason="Not available" />
                </p>
              )}
            </Panel>
          </div>

          <Panel className="p-6">
            <Eyebrow>Rollout decision</Eyebrow>
            <p className="mt-3 max-w-[74ch] text-[0.95rem] leading-relaxed text-ink">
              {data.final.rationale}
            </p>
            <div className="mt-5 grid gap-x-10 gap-y-1 sm:grid-cols-2">
              <Field
                label="Customers funded"
                value={count(data.final.customers_treated)}
              />
              <Field
                label="Incremental contribution"
                value={rupees(
                  data.final.expected_incremental_contribution_inr,
                )}
              />
              <Field
                label="Incentive cost"
                value={rupees(data.final.expected_incentive_cost_inr)}
              />
              <Field
                label="Net contribution"
                value={rupees(data.final.expected_net_contribution_inr)}
              />
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {data.final.gates_passed.map((gate) => (
                <Chip key={gate} tone="earn" glyph="✓">
                  {gate}
                </Chip>
              ))}
              {data.final.binding_constraints.map((code) => (
                <Chip key={code} tone="deficit" glyph="■">
                  {code}
                </Chip>
              ))}
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}
