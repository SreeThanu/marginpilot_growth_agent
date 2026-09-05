/**
 * The system chrome — identity, thesis, section, and the state comparator.
 *
 * It is dark for the same reason the decision band is dark: this strip belongs
 * to the machine. On Overview it runs straight into the verdict below it with
 * no seam, so the top of the page reads as one continuous instrument.
 *
 * The case rail is not a chooser, and the wording is what stops it reading as
 * one. A merchant does not know whether their promotion is a refusal, a test or
 * a rollout — that is the answer MarginPilot returns, so a strip inviting them
 * to pick between the three had the product running backwards.
 *
 * What it actually holds is three decisions the policy has already made, kept
 * side by side because seeing all three at once is what makes the argument that
 * one deterministic policy produces all of them. Secondary by construction: the
 * primary act on Overview is stating a promotion and asking for it to be
 * priced, and this strip stays quieter than the form that does it.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useScenarioIndex } from "@/lib/api";
import { DECISION_LABEL, DECISION_TONE, rupees } from "@/lib/format";
import {
  SCENARIO_IDS,
  useScenarioId,
  withScenario,
} from "./ScenarioContext";
import { toneText } from "./ui";

const NAV = [
  { href: "/", label: "Recorded Cases" },
  { href: "/evaluate", label: "Evaluate a promotion" },
  { href: "/experiment", label: "Experiment" },
  { href: "/trust", label: "Trust" },
  { href: "/audit", label: "Audit" },
] as const;

function Comparator() {
  const { scenario, setScenario } = useScenarioId();
  const { data, error } = useScenarioIndex();
  const summaries = data?.scenarios ?? [];

  return (
    /*
     * A navigation region, not a radiogroup. The old role announced these as a
     * choice to be made before proceeding, which is precisely the reading the
     * product cannot afford: the decision is the output, never the input.
     */
    <nav
      aria-label="Recorded cases"
      className="grid grid-cols-1 sm:grid-cols-[minmax(0,0.9fr)_repeat(3,minmax(0,1fr))]"
    >
      <div className="self-center py-2.5 sm:py-0">
        <p className="eyebrow eyebrow-dark">Recorded cases</p>
        <p className="t-caption mt-0.5 text-band-subtle">
          already decided — for comparison
        </p>
      </div>

      {SCENARIO_IDS.map((id) => {
        const summary = summaries.find((s) => s.scenario === id);
        const active = scenario === id;
        return (
          <button
            key={id}
            type="button"
            aria-current={active ? "true" : undefined}
            onClick={() => setScenario(id)}
            className={`group relative border-l border-band-rule px-4 py-2.5 text-left transition-colors ${
              active ? "bg-band-1" : "hover:bg-band-1"
            }`}
          >
            <span
              aria-hidden="true"
              className={`absolute inset-x-0 top-0 h-px transition-colors ${
                active ? "bg-earn-dark" : "bg-transparent"
              }`}
            />
            <span className="flex items-baseline gap-2">
              <span
                className={`figure text-[0.7rem] ${
                  active ? "text-earn-dark" : "text-band-subtle"
                }`}
              >
                {id}
              </span>
              <span
                className={`t-caption truncate ${
                  active ? "text-band-ink" : "text-band-muted"
                }`}
              >
                {summary
                  ? DECISION_LABEL[summary.decision]
                  : error
                    ? "Unavailable"
                    : "…"}
              </span>
              {/*
                The active case is marked in words as well as in colour, so the
                strip still reads correctly in greyscale and to a screen reader.
              */}
              {active ? (
                <span className="t-caption text-band-subtle">· viewing</span>
              ) : null}
            </span>
            <span
              className={`figure mt-0.5 block text-[0.8rem] ${
                summary
                  ? toneText(DECISION_TONE[summary.decision], true)
                  : "text-band-subtle"
              }`}
            >
              {summary ? rupees(summary.expected_net_contribution_inr) : "—"}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

export function TopRail() {
  const pathname = usePathname();
  const { scenario } = useScenarioId();
  const evaluating = pathname === "/evaluate";

  return (
    /*
     * Sticky, because the nav was previously unreachable from anywhere but the
     * top of the page: the header is `static`, so at scrollY 1500 its bottom sat
     * 1356px above the viewport. Routing was never broken — the control simply
     * was not on screen. The chrome is kept short (the thesis moved to the
     * landing, where it now opens the page) so pinning it costs little height.
     */
    <header className="on-band sticky top-0 z-50 bg-band text-band-ink">
      <div className="mx-auto max-w-[1240px] px-8">
        <div className="flex flex-wrap items-center gap-x-10 gap-y-4 py-3.5">
          <Link
            href={evaluating ? "/" : withScenario("/", scenario)}
            className="flex items-center gap-2.5 rounded-[2px]"
          >
            <span
              aria-hidden="true"
              className="h-[7px] w-[7px] rounded-full bg-earn-dark"
            />
            <span className="t-title text-band-ink">MarginPilot</span>
          </Link>

          <nav aria-label="Sections" className="ml-auto flex items-center gap-1">
            {NAV.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href === "/evaluate" ? item.href : withScenario(item.href, scenario)}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-[2px] px-3 py-1.5 text-[0.85rem] transition-colors ${
                    active
                      ? "bg-band-2 font-medium text-band-ink"
                      : "text-band-muted hover:text-band-ink"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>

      {!evaluating ? (
        <div className="border-t border-band-rule">
          <div className="mx-auto max-w-[1240px] px-8">
            <Comparator />
          </div>
        </div>
      ) : null}
    </header>
  );
}

/**
 * The integrity notice. Small, permanent, never larger than the decision it
 * qualifies — but present on every screen, because a screenshot of any one of
 * them could otherwise be mistaken for a research result.
 */
export function FixtureNotice({
  label,
  onBand = false,
}: {
  label?: string;
  onBand?: boolean;
}) {
  return (
    <p
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 border-l-2 py-1 pl-3 ${
        onBand ? "border-open-dark" : "border-open"
      }`}
    >
      <span className={`eyebrow ${onBand ? "!text-open-dark" : "!text-open"}`}>
        {label ?? "Demonstration fixture — not research evidence"}
      </span>
      <span
        className={`t-caption ${onBand ? "text-band-subtle" : "text-ink-subtle"}`}
      >
        Hand-declared merchants. No number here is a research result.
      </span>
    </p>
  );
}
