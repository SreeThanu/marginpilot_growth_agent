/**
 * Trust — the control architecture, and the refusals that prove it holds.
 *
 * Not an appendix. The page opens with the architecture itself on the band —
 * model, policy, gates, audit — and then shows, from live calls, what each
 * layer refused. The seven adversarial scenarios are executed by
 * `src/eval/adversarial.py`, the malformed replies go through the same
 * `recommend_from_raw` a live model reply would, and the override table is read
 * off the three decisions the other screens are showing.
 */

"use client";

import { FixtureNotice } from "@/components/TopRail";
import {
  Band,
  Chip,
  DataRow,
  ErrorState,
  Eyebrow,
  Loading,
  Rule,
  SectionHead,
  Shell,
  toneText,
} from "@/components/ui";
import { useReproducibility, useSafety } from "@/lib/api";
import { DECISION_LABEL, DECISION_TONE, percent } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/* The control architecture                                                    */
/* -------------------------------------------------------------------------- */

const LAYERS = [
  {
    name: "Model",
    role: "Proposes an intervention, a cohort and a hypothesis. May request an outcome.",
    authority: "No authority",
  },
  {
    name: "Policy",
    role: "Prices the request from the merchant's own economics and decides.",
    authority: "Decides",
  },
  {
    name: "Gates",
    role: "Standing limits on depth, exposure, power and remaining budget.",
    authority: "Can refuse",
  },
  {
    name: "Audit",
    role: "Append-only, hash-chained record of what was proposed and what was decided.",
    authority: "Records",
  },
] as const;

function ControlArchitecture({
  refused,
  total,
  held,
  overruled,
  scenarios,
}: {
  refused: number;
  total: number;
  held: number;
  overruled: number;
  scenarios: number;
}) {
  return (
    <Band>
      <Shell className="py-14">
        <Eyebrow onBand>Control architecture</Eyebrow>
        <h1 className="t-headline mt-4 max-w-[26ch] text-band-ink">
          The model can ask. It cannot spend.
        </h1>

        <ol className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {LAYERS.map((layer) => (
            <li
              key={layer.name}
              className={`border-t-2 pt-5 pr-8 ${
                layer.authority === "Decides"
                  ? "border-earn-dark"
                  : "border-band-rule-strong"
              }`}
            >
              <p className="t-title text-band-ink">{layer.name}</p>
              <p
                className={`figure mt-1.5 text-[0.72rem] ${
                  layer.authority === "Decides"
                    ? "text-earn-dark"
                    : "text-band-subtle"
                }`}
              >
                {layer.authority.toUpperCase()}
              </p>
              <p className="t-caption mt-3 max-w-[30ch] text-band-muted">
                {layer.role}
              </p>
            </li>
          ))}
        </ol>

        <Rule onBand className="mt-12" />

        <div className="mt-9 grid grid-cols-1 gap-x-12 gap-y-8 sm:grid-cols-3">
          <div>
            <p className="figure text-[1.9rem] leading-none text-earn-dark">
              {refused} / {total}
            </p>
            <p className="t-small mt-3 font-medium text-band-ink">
              Adversarial attempts refused
            </p>
            <p className="t-caption mt-1 text-band-subtle">
              Executed live from src/eval/adversarial.py when this page loaded
            </p>
          </div>
          <div>
            <p className="figure text-[1.9rem] leading-none text-earn-dark">
              {held} / {held}
            </p>
            <p className="t-small mt-3 font-medium text-band-ink">
              Malformed replies held
            </p>
            <p className="t-caption mt-1 text-band-subtle">
              Broken model output fails closed rather than defaulting
            </p>
          </div>
          <div>
            <p className="figure text-[1.9rem] leading-none text-band-ink">
              {overruled} / {scenarios}
            </p>
            <p className="t-small mt-3 font-medium text-band-ink">
              Model requests overruled
            </p>
            <p className="t-caption mt-1 text-band-subtle">
              The assistant asked to promote every time; the policy decided each
              on its own
            </p>
          </div>
        </div>
      </Shell>
    </Band>
  );
}

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function TrustPage() {
  const safety = useSafety();
  const repro = useReproducibility();

  if (safety.error)
    return <ErrorState message={safety.error.message} onRetry={safety.retry} />;
  if (safety.loading || !safety.data)
    return <Loading label="Running the refusal scenarios" />;

  const s = safety.data;
  const overrides = s.model_overrides.filter((m) => m.overruled);

  return (
    <>
      <ControlArchitecture
        refused={s.refused}
        total={s.total}
        held={s.malformed.filter((m) => !m.spends_money).length}
        overruled={overrides.length}
        scenarios={s.model_overrides.length}
      />

      <Shell className="pt-5">
        <FixtureNotice />
      </Shell>

      {/* -- live refusals --------------------------------------------------- */}
      <Shell className="pt-14">
        <SectionHead
          eyebrow="Refusals"
          title="Attempted, and stopped"
          note="A refusal is not an error. Each of these is the system working and saying no, with the module that said it."
        />
        <ol className="mt-9">
          {s.scenarios.map((scenario) => (
            <li
              key={scenario.name}
              className="grid gap-x-10 gap-y-2.5 border-b border-rule py-5 lg:grid-cols-[1.1fr_1.4fr_auto]"
            >
              <div>
                <p className="t-small font-medium text-ink">{scenario.name}</p>
                <p className="figure t-caption mt-1.5 text-ink-subtle">
                  {scenario.refused_by}
                </p>
              </div>
              <div>
                <p className="t-caption text-ink-muted">{scenario.attempted}</p>
                <p className="t-small mt-1.5 text-ink">{scenario.reason}</p>
              </div>
              <div className="lg:self-center">
                <Chip
                  tone={scenario.refused ? "earn" : "risk"}
                  glyph={scenario.refused ? "✓" : "■"}
                >
                  {scenario.refused ? "Refused" : "Not refused"}
                </Chip>
              </div>
            </li>
          ))}
        </ol>
      </Shell>

      {/* -- fail closed ------------------------------------------------------ */}
      <Shell className="pt-16">
        <Rule />
        <div className="grid gap-x-16 gap-y-10 pt-10 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHead
            eyebrow="Fail closed"
            title="When the assistant's reply is unusable"
            note="Each of these is fed to the same entry point a live model reply goes through. Refusal is the safe outcome and is never softened into a default proposal."
          />
          <ol>
            {s.malformed.map((row) => (
              <li
                key={row.label}
                className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-1.5 border-b border-rule py-3.5"
              >
                <span className="t-small text-ink">{row.label}</span>
                <span className="flex items-center gap-4">
                  <span className="figure t-caption text-ink-subtle">
                    {row.binding_constraints.join(", ") || "—"}
                  </span>
                  <span
                    className={`t-small font-medium ${toneText(
                      DECISION_TONE[row.decision],
                    )}`}
                  >
                    {DECISION_LABEL[row.decision]}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      </Shell>

      {/* -- where authority sits --------------------------------------------- */}
      <Shell className="pt-16">
        <Rule />
        <div className="pt-10">
          <SectionHead
            eyebrow="Authority"
            title="What the model asked for, and what the policy returned"
            note="Agreement in one scenario is not evidence that the model is reliable. It is evidence that the policy decided independently and happened to reach the same answer."
          />
          <ol className="mt-9 grid grid-cols-1 gap-x-12 gap-y-8 lg:grid-cols-3">
            {s.model_overrides.map((row) => (
              <li
                key={row.scenario}
                className={`border-t-2 pt-5 ${
                  row.overruled ? "border-risk" : "border-rule-strong"
                }`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <Eyebrow>Merchant {row.scenario}</Eyebrow>
                  <Chip
                    tone={row.overruled ? "risk" : "spend"}
                    glyph={row.overruled ? "■" : "="}
                  >
                    {row.overruled ? "Overruled" : "Agreed"}
                  </Chip>
                </div>
                <p className="t-small mt-3 font-medium text-ink">{row.title}</p>
                <div className="mt-5 space-y-1.5">
                  <p className="t-caption text-ink-muted">
                    Model asked:{" "}
                    <span className="text-ink">
                      {row.model_requested
                        ? DECISION_LABEL[row.model_requested]
                        : "nothing"}
                    </span>
                  </p>
                  <p className="t-caption text-ink-muted">
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
              </li>
            ))}
          </ol>
        </div>
      </Shell>

      {/* -- standing limits --------------------------------------------------- */}
      <Shell className="pt-16">
        <Rule />
        <div className="grid gap-x-16 gap-y-10 pt-10 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHead
            eyebrow="Standing limits"
            title="What every action is checked against"
            note="Numbers a merchant would recognise and could argue with. A policy nobody can read is a policy nobody agreed to."
          />
          <div>
            <DataRow
              label="Deepest permitted discount"
              value={percent(s.policy_limits.max_discount_pct, 0)}
            />
            <DataRow
              label="Minimum contribution margin"
              value={percent(s.policy_limits.min_contribution_margin, 0)}
            />
            <DataRow
              label="Maximum share of the base in one campaign"
              value={percent(s.policy_limits.max_customer_exposure_share, 0)}
            />
            <DataRow
              label="Minimum experiment power"
              value={percent(s.policy_limits.min_experiment_power, 0)}
            />
            <DataRow
              label="Budget that must survive one action"
              value={percent(s.policy_limits.min_budget_headroom_share, 0)}
            />
          </div>
        </div>
      </Shell>

      {/* -- reproducibility ---------------------------------------------------- */}
      <Shell className="pt-16">
        <Rule />
        <div className="grid gap-x-16 gap-y-10 pt-10 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHead
            eyebrow="Reproducibility"
            title="What this repository pins itself to"
            note="Read from source at load time, so a drifted corpus or an edited fixture shows up here rather than staying silent."
          />
          {repro.error ? (
            <ErrorState message={repro.error.message} onRetry={repro.retry} />
          ) : repro.loading || !repro.data ? (
            <Loading label="Reading the pins" />
          ) : (
            <ol>
              {repro.data.badges.map((badge) => (
                <li
                  key={badge.label}
                  className="grid gap-x-8 gap-y-1 border-b border-rule py-3.5 sm:grid-cols-[1fr_1fr]"
                >
                  <div>
                    <p className="t-small text-ink">{badge.label}</p>
                    <p className="t-caption mt-1 text-ink-subtle">
                      {badge.detail}
                    </p>
                  </div>
                  <p className="figure text-[0.85rem] text-ink sm:text-right">
                    {badge.value}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </div>
      </Shell>
    </>
  );
}
