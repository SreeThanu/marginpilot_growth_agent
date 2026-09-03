/**
 * The application chrome: identity, where you are, and which merchant.
 *
 * The merchant switch sits in the chrome rather than on the page because it
 * changes what every screen is about. It shows each merchant's standing
 * decision under its name, so switching is a considered move between three
 * known situations, not a blind radio button.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useScenarioIndex } from "@/lib/api";
import { DECISION_LABEL, DECISION_TONE } from "@/lib/format";
import { useScenarioId, withScenario, type ScenarioId } from "./ScenarioContext";
import { toneText } from "./ui";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/experiment", label: "Experiment" },
  { href: "/trust", label: "Trust & safety" },
  { href: "/audit", label: "Audit" },
] as const;

function ScenarioSwitch() {
  const { scenario, setScenario } = useScenarioId();
  const { data, error } = useScenarioIndex();

  const summaries = data?.scenarios ?? [];

  return (
    <div
      role="radiogroup"
      aria-label="Merchant"
      className="flex w-full items-stretch overflow-hidden rounded-[3px] border border-rule-strong bg-surface sm:w-auto"
    >
      {(["A", "B", "C"] as ScenarioId[]).map((id) => {
        const summary = summaries.find((s) => s.scenario === id);
        const active = scenario === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setScenario(id)}
            className={`group relative min-w-0 flex-1 border-r border-rule px-3.5 py-2 text-left transition-colors last:border-r-0 sm:min-w-[9.5rem] sm:flex-none ${
              active ? "bg-ink" : "bg-surface hover:bg-sunk"
            }`}
          >
            <span
              className={`eyebrow block ${
                active ? "!text-surface/60" : ""
              }`}
            >
              Merchant {id}
            </span>
            <span
              className={`mt-1 block truncate text-[0.78rem] font-medium ${
                active
                  ? "text-surface"
                  : summary
                    ? toneText(DECISION_TONE[summary.decision])
                    : "text-slate-soft"
              }`}
            >
              {summary
                ? DECISION_LABEL[summary.decision]
                : error
                  ? "Unavailable"
                  : "…"}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function TopRail() {
  const pathname = usePathname();
  const { scenario } = useScenarioId();

  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-ground/92 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-x-8 gap-y-4 px-6 py-4 lg:px-8">
        <Link
          href={withScenario("/", scenario)}
          className="flex items-baseline gap-2.5 rounded-[2px]"
        >
          <span className="text-[1.05rem] font-semibold tracking-[-0.02em] text-ink">
            MarginPilot
          </span>
          <span className="hidden text-[0.78rem] text-slate sm:inline">
            AI growth decisions, grounded in merchant economics
          </span>
        </Link>

        <nav aria-label="Sections" className="flex items-center gap-1">
          {NAV.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={withScenario(item.href, scenario)}
                aria-current={active ? "page" : undefined}
                className={`rounded-[2px] px-2.5 py-1.5 text-[0.83rem] transition-colors ${
                  active
                    ? "text-ink font-medium"
                    : "text-slate hover:text-ink"
                }`}
              >
                {item.label}
                <span
                  aria-hidden="true"
                  className={`mt-1 block h-px transition-colors ${
                    active ? "bg-ink" : "bg-transparent"
                  }`}
                />
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto w-full sm:w-auto">
          <ScenarioSwitch />
        </div>
      </div>
    </header>
  );
}

/**
 * The integrity notice. Small, permanent, and never larger than the decision
 * it qualifies — but present on every screen, because a screenshot of any one
 * of them could otherwise be mistaken for a research result.
 */
export function FixtureNotice({ label }: { label?: string }) {
  return (
    <p className="flex items-center gap-2.5 border-l-2 border-open py-1 pl-3 text-[0.74rem] leading-snug text-slate">
      <span className="eyebrow !text-open">
        {label ?? "Demonstration fixture — not research evidence"}
      </span>
      <span className="hidden md:inline">
        These merchants are hand-declared for the demo. No number on this page is
        a research result.
      </span>
    </p>
  );
}
