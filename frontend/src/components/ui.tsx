/**
 * The vocabulary every screen is built from.
 *
 * Deliberately short, and deliberately not card-shaped. Most groupings in this
 * product are lists of facts, and a list of facts reads better on hairlines
 * than inside forty bordered boxes. A panel exists only where a genuinely
 * separate concept needs a surface of its own.
 *
 * Every primitive that can appear on the dark band takes an `onBand` flag
 * rather than guessing, because the two colour ladders are not interchangeable.
 */

"use client";

import type { ReactNode } from "react";

import { RAIL_MARK, type RailState, type Tone } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/* Structure                                                                   */
/* -------------------------------------------------------------------------- */

/** The content measure. Everything aligns to this column. */
export function Shell({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mx-auto w-full max-w-[1240px] px-8 ${className}`}>
      {children}
    </div>
  );
}

/**
 * The dark band — the one place the system states a verdict.
 *
 * Full-bleed by design. It is the page's spine, not a card on the page, and
 * that is the whole reason the layout does not read as a dashboard.
 */
export function Band({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`on-band bg-band text-band-ink ${className}`}>
      {children}
    </section>
  );
}

export function Eyebrow({
  children,
  onBand = false,
  className = "",
}: {
  children: ReactNode;
  onBand?: boolean;
  className?: string;
}) {
  return (
    <p className={`eyebrow ${onBand ? "eyebrow-dark" : ""} ${className}`}>
      {children}
    </p>
  );
}

export function SectionHead({
  eyebrow,
  title,
  note,
  onBand = false,
  className = "",
}: {
  eyebrow: string;
  title: string;
  note?: string;
  onBand?: boolean;
  className?: string;
}) {
  return (
    <div className={`max-w-[68ch] ${className}`}>
      <Eyebrow onBand={onBand}>{eyebrow}</Eyebrow>
      <h2
        className={`t-headline mt-3 ${onBand ? "text-band-ink" : "text-ink"}`}
      >
        {title}
      </h2>
      {note ? (
        <p
          className={`t-small mt-2.5 ${
            onBand ? "text-band-muted" : "text-ink-muted"
          }`}
        >
          {note}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A section heading below the page's own headline.
 *
 * The rung the scale was missing: a conceptual, sentence-length label that is
 * not metadata and is not a display statement. Mono eyebrows keep the short
 * work — identifiers, gates, hashes, timestamps, compact context.
 */
export function SubHeading({
  children,
  onBand = false,
  className = "",
  level = 3,
}: {
  children: ReactNode;
  onBand?: boolean;
  className?: string;
  /**
   * The outline level, not the size — `.t-section` styles both identically, so
   * this changes what a screen reader hears and nothing a sighted reader sees.
   * The decision band passes 2 because its ledger heading is the first heading
   * after the page's h1, and jumping h1 → h3 breaks the document outline.
   */
  level?: 2 | 3;
}) {
  const Tag = level === 2 ? "h2" : "h3";
  return (
    <Tag
      className={`t-section ${
        onBand ? "text-band-ink" : "text-ink"
      } ${className}`}
    >
      {children}
    </Tag>
  );
}

/**
 * One process rail, spoken in one state vocabulary.
 *
 * Overview draws the four-station control path with it; Experiment draws the
 * five-station progression. A reader who learns the colours once on the first
 * screen reads them without effort on the second — which is the entire reason
 * this is a shared component rather than two similar lists.
 */
export function ProcessRail({
  stages,
}: {
  stages: {
    label: string;
    value: string;
    note: string;
    state: RailState;
    index?: string;
  }[];
}) {
  return (
    <ol
      className={`grid grid-cols-1 sm:grid-cols-2 ${
        stages.length === 5 ? "lg:grid-cols-5" : "lg:grid-cols-4"
      }`}
    >
      {stages.map((stage) => {
        const mark = RAIL_MARK[stage.state];
        return (
          <li key={stage.label} className={`border-t-2 pt-5 pr-8 ${mark.rail}`}>
            <div className="flex items-baseline gap-2">
              {stage.index ? (
                <span className="figure text-[0.72rem] text-ink-subtle">
                  {stage.index}
                </span>
              ) : null}
              <Eyebrow>{stage.label}</Eyebrow>
              <span
                className={`ml-auto text-[0.8rem] ${mark.text}`}
                aria-hidden="true"
              >
                {mark.glyph}
              </span>
            </div>
            <p className="t-section mt-2.5 text-ink">{stage.value}</p>
            <p className={`t-caption mt-1 ${mark.text}`}>{mark.word}</p>
            <p className="t-caption mt-2.5 max-w-[32ch] text-ink-muted">
              {stage.note}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

/** A hairline. Named so the intent is visible at the call site. */
export function Rule({
  onBand = false,
  className = "",
}: {
  onBand?: boolean;
  className?: string;
}) {
  return (
    <hr
      className={`border-0 border-t ${
        onBand ? "border-band-rule" : "border-rule"
      } ${className}`}
    />
  );
}

/** A bordered surface. Used only where a concept needs its own ground. */
export function Panel({
  children,
  className = "",
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return (
    <Tag className={`rounded-[3px] border border-rule bg-surface ${className}`}>
      {children}
    </Tag>
  );
}

/* -------------------------------------------------------------------------- */
/* Tone                                                                        */
/* -------------------------------------------------------------------------- */

const TEXT: Record<Tone, string> = {
  earn: "text-earn",
  risk: "text-risk",
  open: "text-open",
  spend: "text-spend",
};

const TEXT_ON_BAND: Record<Tone, string> = {
  earn: "text-earn-dark",
  risk: "text-risk-dark",
  open: "text-open-dark",
  spend: "text-spend-dark",
};

export function toneText(tone: Tone, onBand = false): string {
  return onBand ? TEXT_ON_BAND[tone] : TEXT[tone];
}

const CHIP: Record<Tone, string> = {
  earn: "border-earn/25 bg-earn-wash text-earn",
  risk: "border-risk/25 bg-risk-wash text-risk",
  open: "border-open/25 bg-open-wash text-open",
  spend: "border-rule-strong bg-spend-wash text-spend",
};

const CHIP_ON_BAND: Record<Tone, string> = {
  earn: "border-earn-dark/30 bg-earn-dark/10 text-earn-dark",
  risk: "border-risk-dark/30 bg-risk-dark/10 text-risk-dark",
  open: "border-open-dark/30 bg-open-dark/10 text-open-dark",
  spend: "border-band-rule-strong bg-band-2 text-band-muted",
};

/**
 * A status pill. The glyph is not decoration: colour alone must never be the
 * only thing separating "passed" from "did not".
 */
export function Chip({
  children,
  tone = "spend",
  glyph,
  title,
  onBand = false,
}: {
  children: ReactNode;
  tone?: Tone;
  glyph?: string;
  title?: string;
  onBand?: boolean;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] font-mono text-[0.685rem] font-medium tracking-[0.04em] whitespace-nowrap ${
        onBand ? CHIP_ON_BAND[tone] : CHIP[tone]
      }`}
    >
      {glyph ? <span aria-hidden="true">{glyph}</span> : null}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Figures and rows                                                            */
/* -------------------------------------------------------------------------- */

export function Figure({
  label,
  value,
  tone,
  size = "md",
  note,
  onBand = false,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  size?: "md" | "lg";
  note?: string;
  onBand?: boolean;
}) {
  const colour = tone
    ? toneText(tone, onBand)
    : onBand
      ? "text-band-ink"
      : "text-ink";
  return (
    <div>
      <Eyebrow onBand={onBand}>{label}</Eyebrow>
      <p
        className={`figure mt-2.5 leading-none ${
          size === "lg"
            ? "text-[2.35rem] font-medium"
            : "text-[1.28rem]"
        } ${colour}`}
      >
        {value}
      </p>
      {note ? (
        <p
          className={`t-caption mt-2.5 max-w-[34ch] ${
            onBand ? "text-band-subtle" : "text-ink-subtle"
          }`}
        >
          {note}
        </p>
      ) : null}
    </div>
  );
}

/** A label/value pair on a hairline. The default grouping in this product. */
export function DataRow({
  label,
  value,
  onBand = false,
}: {
  label: string;
  value: ReactNode;
  onBand?: boolean;
}) {
  return (
    <div
      className={`flex items-baseline justify-between gap-8 border-b py-3 last:border-b-0 ${
        onBand ? "border-band-rule" : "border-rule"
      }`}
    >
      <span
        className={`t-small ${onBand ? "text-band-muted" : "text-ink-muted"}`}
      >
        {label}
      </span>
      <span
        className={`figure text-right text-[0.86rem] ${
          onBand ? "text-band-ink" : "text-ink"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Absence and failure                                                         */
/* -------------------------------------------------------------------------- */

/**
 * The single way this product says it has no number. A phrase, never a dash
 * and never a zero — a zero is a measurement.
 */
export function Unavailable({
  reason = "Not available",
  onBand = false,
}: {
  reason?: string;
  onBand?: boolean;
}) {
  return (
    <span
      className={`text-[0.82rem] italic ${
        onBand ? "text-band-subtle" : "text-ink-subtle"
      }`}
    >
      {reason}
    </span>
  );
}

export function Loading({ label = "Reading the engine" }: { label?: string }) {
  return (
    <Shell className="py-28">
      <div role="status" aria-live="polite" className="flex items-center gap-3">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-subtle" />
        <span className="eyebrow">{label}…</span>
      </div>
    </Shell>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Shell className="py-20">
      <div className="max-w-[62ch] border-l-2 border-risk pl-6">
        <Eyebrow className="!text-risk">Engine unavailable</Eyebrow>
        <p className="t-lead mt-3 text-ink">{message}</p>
        <p className="t-small mt-3 text-ink-muted">
          No figure is shown in place of the missing one. Start the engine with{" "}
          <code className="figure rounded-[2px] bg-sunk px-1.5 py-0.5 text-[0.8rem]">
            python -m api
          </code>{" "}
          from the repository root, then try again.
        </p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-6 rounded-[3px] bg-ink px-4 py-2 text-[0.85rem] font-medium text-surface transition-opacity hover:opacity-85"
          >
            Try again
          </button>
        ) : null}
      </div>
    </Shell>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="max-w-[62ch] border-l-2 border-rule-strong pl-6">
      <h3 className="t-title text-ink">{title}</h3>
      <p className="t-small mt-2.5 text-ink-muted">{body}</p>
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
