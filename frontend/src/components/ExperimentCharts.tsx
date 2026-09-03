/**
 * Two comparisons and an interval. Nothing decorative.
 *
 * Charts here exist because the shape of the answer is easier to read than the
 * digits: two arms side by side, and a measured effect held against the lift
 * the campaign had to clear. There is no time series, because the experiment
 * has no time series — it is read once, at its pre-committed horizon.
 */

"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import { percent, rupeesExact } from "@/lib/format";
import type { Arm, Comparison } from "@/types/domain";
import { Eyebrow } from "./ui";

const EARN = "#1b6b4e";
const SPEND = "#626d76";
const RULE = "#e0e2dd";
const SLATE = "#59636c";

function armColour(name: string): string {
  return name === "treatment" ? EARN : SPEND;
}

function ArmChart({
  arms,
  valueOf,
  formatValue,
  domainPad = 1.25,
}: {
  arms: Arm[];
  valueOf: (arm: Arm) => number;
  formatValue: (value: number) => string;
  domainPad?: number;
}) {
  const rows = arms.map((arm) => ({
    name: arm.name,
    value: valueOf(arm),
    label: formatValue(valueOf(arm)),
  }));
  const top = Math.max(...rows.map((r) => r.value)) * domainPad;

  return (
    <div className="h-[172px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          margin={{ top: 22, right: 8, bottom: 4, left: 8 }}
          barCategoryGap="34%"
        >
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={{ stroke: RULE }}
            tick={{
              fill: SLATE,
              fontSize: 11,
              fontFamily: "var(--font-plex-mono)",
            }}
          />
          <YAxis hide domain={[0, top]} />
          <Bar dataKey="value" radius={[2, 2, 0, 0]} isAnimationActive={false}>
            {rows.map((row) => (
              <Cell key={row.name} fill={armColour(row.name)} />
            ))}
            <LabelList
              dataKey="label"
              position="top"
              offset={8}
              style={{
                fill: "#101519",
                fontSize: 12,
                fontFamily: "var(--font-plex-mono)",
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ConversionChart({ arms }: { arms: Arm[] }) {
  return (
    <div>
      <Eyebrow>Conversion by arm</Eyebrow>
      <ArmChart
        arms={arms}
        valueOf={(a) => a.conversion_rate}
        formatValue={(v) => percent(v, 2)}
      />
    </div>
  );
}

export function ContributionChart({ arms }: { arms: Arm[] }) {
  return (
    <div>
      <Eyebrow>Contribution per customer</Eyebrow>
      <ArmChart
        arms={arms}
        valueOf={(a) => a.contribution_mean_inr}
        formatValue={(v) => rupeesExact(v)}
      />
    </div>
  );
}

/**
 * The measured effect, its interval, and the lift the campaign had to clear.
 *
 * This is the chart that answers the question a merchant actually asked. A
 * point estimate above break-even is not enough; the interval has to sit above
 * it too, and drawing both on one axis is the only way to see that at a glance.
 */
export function EffectInterval({
  comparison,
  breakEven,
}: {
  comparison: Comparison;
  breakEven: number | null;
}) {
  const points = [
    0,
    comparison.difference_ci_low,
    comparison.difference_ci_high,
    breakEven ?? 0,
  ];
  const low = Math.min(...points);
  const high = Math.max(...points);
  const span = high - low || 1;
  const pad = span * 0.14;
  const min = low - pad;
  const max = high + pad;
  const at = (v: number) => ((v - min) / (max - min)) * 100;

  const clears =
    breakEven !== null && comparison.difference_ci_low > breakEven;

  return (
    <div>
      <Eyebrow>Measured lift against break-even</Eyebrow>

      <div className="relative mt-6 h-[86px] w-full">
        {/* The interval. */}
        <div
          className="absolute top-[30px] h-[10px] rounded-full bg-earn/25"
          style={{
            left: `${at(comparison.difference_ci_low)}%`,
            width: `${
              at(comparison.difference_ci_high) -
              at(comparison.difference_ci_low)
            }%`,
          }}
        />
        {[comparison.difference_ci_low, comparison.difference_ci_high].map(
          (edge) => (
            <div
              key={edge}
              aria-hidden="true"
              className="absolute top-[26px] h-[18px] w-px bg-earn/60"
              style={{ left: `${at(edge)}%` }}
            />
          ),
        )}

        {/* The point estimate. */}
        <div
          aria-hidden="true"
          className="absolute top-[22px] h-[26px] w-[3px] bg-earn"
          style={{ left: `${at(comparison.absolute_difference)}%` }}
        />
        <span
          className="figure absolute top-0 -translate-x-1/2 text-[0.78rem] font-medium whitespace-nowrap text-earn"
          style={{ left: `${at(comparison.absolute_difference)}%` }}
        >
          {percent(comparison.absolute_difference, 2)}
        </span>

        {/* Break-even. */}
        {breakEven !== null ? (
          <>
            <div
              aria-hidden="true"
              className="absolute top-[16px] h-[38px] border-l border-dashed border-open"
              style={{ left: `${at(breakEven)}%` }}
            />
            <span
              className="figure absolute top-[58px] -translate-x-1/2 text-[0.72rem] whitespace-nowrap text-open"
              style={{ left: `${at(breakEven)}%` }}
            >
              break-even {percent(breakEven, 2)}
            </span>
          </>
        ) : null}
      </div>

      <p className="mt-2 border-t border-rule pt-3 text-[0.84rem] leading-relaxed text-slate">
        {breakEven === null ? (
          "No break-even lift exists for this offer, so there is nothing to hold the interval against."
        ) : clears ? (
          <>
            The whole 95% interval —{" "}
            <span className="figure text-ink">
              {percent(comparison.difference_ci_low, 2)}
            </span>{" "}
            to{" "}
            <span className="figure text-ink">
              {percent(comparison.difference_ci_high, 2)}
            </span>{" "}
            — sits above the {percent(breakEven, 2)} the campaign had to clear.
          </>
        ) : (
          <>
            The interval —{" "}
            <span className="figure text-ink">
              {percent(comparison.difference_ci_low, 2)}
            </span>{" "}
            to{" "}
            <span className="figure text-ink">
              {percent(comparison.difference_ci_high, 2)}
            </span>{" "}
            — does not sit entirely above the {percent(breakEven, 2)} break-even
            lift.
          </>
        )}
      </p>
    </div>
  );
}
