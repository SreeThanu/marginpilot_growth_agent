/**
 * Experiment — what was tested, what came back, and what it bought.
 *
 * Three states, and the screen says plainly which it is in: no experiment
 * warranted, an experiment planned but unrun, or an experiment read at its
 * horizon. Only the third shows a measurement, and it is the only route on this
 * product to a rollout — so only the third earns the dark band.
 */

"use client";

import {
  ContributionChart,
  ConversionChart,
  EffectInterval,
} from "@/components/ExperimentCharts";
import { ActionLink } from "@/components/Merchant";
import { useScenarioId, withScenario } from "@/components/ScenarioContext";
import { FixtureNotice } from "@/components/TopRail";
import {
  Band,
  Chip,
  DataRow,
  EmptyState,
  ErrorState,
  Eyebrow,
  Loading,
  ProcessRail,
  Rule,
  SectionHead,
  Shell,
  SubHeading,
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
  type RailState,
} from "@/lib/format";
import type { ScenarioDetail } from "@/types/domain";

/* -------------------------------------------------------------------------- */
/* The progression                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The five stations a validated promotion passes through.
 *
 * Numbered because the content genuinely is a sequence: the rollout gate cannot
 * be reached before the horizon, and the horizon cannot be reached before the
 * pilot launches. It speaks the same state vocabulary as the Overview control
 * path, so a reader who learned the colours there reads these without effort.
 */
function Progression({ data }: { data: ScenarioDetail }) {
  const exp = data.experiment;
  const rolloutPassed = data.final.gates_passed.includes("G6");
  const refused = data.final.decision === "DO_NOT_PROMOTE";

  const stations: {
    index: string;
    label: string;
    value: string;
    note: string;
    state: RailState;
  }[] = [
    {
      index: "01",
      label: "Assessment",
      value: DECISION_LABEL[data.initial.decision],
      note: "Decided from the brief alone. This path cannot return Promote.",
      state: "complete",
    },
    {
      index: "02",
      label: "Experiment",
      value: exp ? `${count(exp.horizon_per_arm)} per arm` : "Not launched",
      note: exp
        ? "Assignment in production is a blake2b hash of customer and experiment id, with no route for the assistant. This fixture draws arm outcomes in aggregate from its committed seed."
        : "No pilot has been launched for this merchant.",
      state: exp
        ? "complete"
        : data.final.experiment_required
          ? "current"
          : "not-reached",
    },
    {
      index: "03",
      label: "Horizon",
      value: exp
        ? exp.verdict_eligible
          ? "Horizon reached"
          : "Before the horizon"
        : "Not read",
      note: "The horizon is fixed at design time. There is no early-stop path.",
      state: exp?.verdict_eligible ? "complete" : "not-reached",
    },
    {
      index: "04",
      label: "Rollout",
      value: rolloutPassed ? "G6 passed" : refused ? "Held" : "Not reached",
      note: "The measured effect is re-priced against the rollout the budget can actually fund.",
      state: rolloutPassed
        ? "complete"
        : refused
          ? "blocked"
          : "not-reached",
    },
    {
      index: "05",
      label: "Decision",
      value: DECISION_LABEL[data.final.decision],
      note: data.final.diagnosis,
      state: refused ? "blocked" : "complete",
    },
  ];

  return <ProcessRail stages={stations} />;
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
    <>
      <Shell className="pt-10">
        <FixtureNotice label={data.label} />
      </Shell>

      <Shell className="pt-10">
        <SectionHead
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
              ? "One control arm and one treatment arm, sized before launch and read exactly once, at the pre-committed horizon."
              : data.final.experiment_required
                ? "Sized by the same power calculation that would run it, and priced against the merchant's budget."
                : "The arithmetic settles this offer before an experiment is worth contemplating."
          }
        />
        <div className="mt-10">
          <Progression data={data} />
        </div>
      </Shell>

      {/* -- nothing worth testing ------------------------------------------ */}
      {!exp && !data.final.experiment_required ? (
        <Shell className="pt-14">
          <EmptyState
            title="Nothing here is worth testing"
            body={data.final.rationale}
            action={
              <ActionLink href={withScenario("/", scenario)}>
                Back to the decision
              </ActionLink>
            }
          />
        </Shell>
      ) : null}

      {/* -- planned, not yet run -------------------------------------------- */}
      {!exp && data.final.experiment_required ? (
        <Shell className="pt-14">
          <Rule />
          <div className="grid gap-x-16 gap-y-12 pt-10 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <SubHeading>The experiment this merchant should run</SubHeading>
              <p className="t-lead mt-4 max-w-[54ch] text-ink">
                {data.final.rationale}
              </p>
              <div className="mt-8">
                <DataRow
                  label="Customers per arm"
                  value={count(data.final.experiment_horizon_per_arm)}
                />
                <DataRow label="Arms" value="2 — control and treatment" />
                <DataRow
                  label="Pilot cost"
                  value={rupees(data.final.experiment_cost_inr)}
                />
                <DataRow
                  label="Break-even lift the offer must clear"
                  value={
                    data.final.required_break_even_lift_absolute === null ? (
                      <Unavailable reason="Unreachable at any lift" />
                    ) : (
                      percent(
                        data.final.required_break_even_lift_absolute,
                        2,
                      )
                    )
                  }
                />
                <DataRow
                  label="Measured result"
                  value={<Unavailable reason="Not yet measured" />}
                />
              </div>
            </div>

            <div className="border-l-2 border-open pl-6">
              <Eyebrow className="!text-open">Open question</Eyebrow>
              <p className="t-lead mt-4 max-w-[44ch] text-ink">
                Whether this experiment costs less than the information it buys
                is unresolved in this project.
              </p>
              <p className="t-small mt-4 max-w-[44ch] text-ink-muted">
                No threshold for it has been committed, so none is applied. The
                gate checks affordability only, and carries{" "}
                <span className="figure text-open">
                  G4_VALUE_OF_INFORMATION_UNRESOLVED
                </span>{" "}
                through to the merchant rather than quietly taking a side.
              </p>
            </div>
          </div>
        </Shell>
      ) : null}

      {/* -- measured: the evidence earns the band --------------------------- */}
      {exp ? (
        <>
          <Band className="mt-14">
            <Shell className="py-14">
              <div className="flex flex-wrap items-baseline justify-between gap-x-10 gap-y-4">
                <div>
                  <Eyebrow onBand>Evidence</Eyebrow>
                  <p className="figure mt-2 text-[0.95rem] text-band-ink">
                    {exp.experiment_id}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Chip
                    tone={exp.verdict_eligible ? "earn" : "open"}
                    glyph={exp.verdict_eligible ? "✓" : "◇"}
                    onBand
                  >
                    {exp.verdict_eligible
                      ? "Horizon reached"
                      : "Before the horizon"}
                  </Chip>
                  <Chip tone="spend" onBand>
                    {count(exp.horizon_per_arm)} per arm
                  </Chip>
                  <Chip tone="spend" onBand>
                    Pilot spend {rupees(exp.pilot_spend_inr)}
                  </Chip>
                  <Chip tone="spend" onBand>
                    {percent(exp.depth, 1)} depth
                  </Chip>
                </div>
              </div>

              <div className="mt-12">
                {comparison ? (
                  <EffectInterval
                    comparison={comparison}
                    breakEven={data.initial.required_break_even_lift_absolute}
                  />
                ) : (
                  <>
                    <Eyebrow onBand>
                      Measured lift against the break-even requirement
                    </Eyebrow>
                    <p className="mt-3">
                      <Unavailable
                        onBand
                        reason="The evaluator returned no comparison"
                      />
                    </p>
                  </>
                )}
              </div>

              <Rule onBand className="mt-14" />

              <div className="mt-10 grid gap-x-16 gap-y-10 lg:grid-cols-2">
                <ConversionChart arms={exp.arms} />
                <ContributionChart arms={exp.arms} />
              </div>
            </Shell>
          </Band>

          {/* -- the numbers behind the picture ----------------------------- */}
          <Shell className="pt-14">
            <div className="grid gap-x-16 gap-y-12 lg:grid-cols-[1fr_1fr]">
              <div>
                <SectionHead
                  eyebrow="Readout"
                  title="What the evaluator returned"
                  note="Produced by src/experiment/evaluator.py and rendered without recomputation."
                />
                <div className="mt-8">
                  {comparison ? (
                    <>
                      <DataRow
                        label="Absolute lift"
                        value={percent(comparison.absolute_difference, 2)}
                      />
                      <DataRow
                        label="95% interval"
                        value={`${percent(
                          comparison.difference_ci_low,
                          2,
                        )} … ${percent(comparison.difference_ci_high, 2)}`}
                      />
                      <DataRow
                        label="p-value"
                        value={pValue(comparison.p_value)}
                      />
                      <DataRow
                        label="Net contribution, pilot"
                        value={rupees(comparison.net_contribution_inr)}
                      />
                      <DataRow
                        label="Net per treated customer"
                        value={rupeesExact(
                          comparison.net_per_treated_customer_inr,
                        )}
                      />
                      <DataRow
                        label="P(net > 0)"
                        value={percent(
                          comparison.probability_net_positive,
                          2,
                        )}
                      />
                    </>
                  ) : (
                    <Unavailable />
                  )}
                </div>
              </div>

              <div>
                <SectionHead
                  eyebrow="Arms"
                  title="Control against treatment"
                  note="Both arms the same size, both read at the same moment."
                />
                <div className="mt-8 overflow-x-auto">
                  <table className="w-full min-w-[420px] border-collapse text-left">
                    <thead>
                      <tr className="border-b border-rule-strong">
                        {["Arm", "Assigned", "Converted", "Rate"].map(
                          (head, i) => (
                            <th
                              key={head}
                              className={`eyebrow pb-3 font-medium ${
                                i === 0 ? "" : "text-right"
                              }`}
                            >
                              {head}
                            </th>
                          ),
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {exp.arms.map((arm) => (
                        <tr key={arm.name} className="border-b border-rule">
                          <td className="t-small py-3 text-ink">{arm.name}</td>
                          <td className="figure py-3 text-right text-[0.85rem] text-ink">
                            {count(arm.n_assigned)}
                          </td>
                          <td className="figure py-3 text-right text-[0.85rem] text-ink">
                            {count(arm.n_converted)}
                          </td>
                          <td className="figure py-3 text-right text-[0.85rem] text-ink">
                            {percent(arm.conversion_rate, 2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </Shell>

          {/* -- what the evidence bought ------------------------------------ */}
          <Shell className="pt-16">
            <Rule />
            <div className="grid gap-x-16 gap-y-10 pt-10 lg:grid-cols-[0.9fr_1.1fr]">
              <SectionHead
                eyebrow="Controlled release"
                title="What the rollout gate authorised"
                note="The measured effect is re-priced against the population the remaining budget can actually fund — not the population that was tested."
              />
              <div>
                <p className="t-small max-w-[62ch] text-ink">
                  {data.final.rationale}
                </p>
                <div className="mt-7">
                  <DataRow
                    label="Customers funded"
                    value={count(data.final.customers_treated)}
                  />
                  <DataRow
                    label="Incremental contribution"
                    value={rupees(
                      data.final.expected_incremental_contribution_inr,
                    )}
                  />
                  <DataRow
                    label="Incentive cost"
                    value={rupees(data.final.expected_incentive_cost_inr)}
                  />
                  <DataRow
                    label="Net contribution"
                    value={rupees(data.final.expected_net_contribution_inr)}
                  />
                </div>
                <div className="mt-6 flex flex-wrap gap-2">
                  {data.final.gates_passed.map((gate) => (
                    <Chip key={gate} tone="earn" glyph="✓">
                      {gate}
                    </Chip>
                  ))}
                  {data.final.binding_constraints.map((code) => (
                    <Chip key={code} tone="risk" glyph="■">
                      {code}
                    </Chip>
                  ))}
                </div>
              </div>
            </div>
          </Shell>
        </>
      ) : null}
    </>
  );
}
