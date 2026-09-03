/**
 * The small vocabulary every screen is built from.
 *
 * Kept deliberately short. A product that ships forty one-off card variants
 * stops looking designed, so there is one panel, one chip, one figure and one
 * way of saying "this value is not available".
 */

"use client";

import type { ReactNode } from "react";

import type { Tone } from "@/lib/format";

/* -------------------------------------------------------------------------- */
/* Surfaces                                                                    */
/* -------------------------------------------------------------------------- */

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
    <Tag
      className={`rounded-[3px] border border-rule bg-surface shadow-[0_1px_2px_rgba(16,21,25,0.04)] ${className}`}
    >
      {children}
    </Tag>
  );
}

export function Eyebrow({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <p className={`eyebrow ${className}`}>{children}</p>;
}

export function SectionHeading({
  eyebrow,
  title,
  note,
}: {
  eyebrow: string;
  title: string;
  note?: string;
}) {
  return (
    <div className="mb-5">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 className="mt-2 text-[1.35rem] font-medium tracking-[-0.015em] text-ink">
        {title}
      </h2>
      {note ? (
        <p className="mt-1.5 max-w-[62ch] text-[0.9rem] leading-relaxed text-slate">
          {note}
        </p>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Tone                                                                        */
/* -------------------------------------------------------------------------- */

const TONE_TEXT: Record<Tone, string> = {
  earn: "text-earn",
  deficit: "text-deficit",
  open: "text-open",
  spend: "text-spend",
};

const TONE_CHIP: Record<Tone, string> = {
  earn: "bg-earn-soft text-earn border-earn/20",
  deficit: "bg-deficit-soft text-deficit border-deficit/20",
  open: "bg-open-soft text-open border-open/20",
  spend: "bg-spend-soft text-spend border-rule-strong",
};

export function toneText(tone: Tone): string {
  return TONE_TEXT[tone];
}

/**
 * A status pill. The glyph is not decoration: colour alone must never be the
 * only thing separating "passed" from "did not".
 */
export function Chip({
  children,
  tone = "spend",
  glyph,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  glyph?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] font-mono text-[0.7rem] font-medium tracking-[0.03em] ${TONE_CHIP[tone]}`}
    >
      {glyph ? <span aria-hidden="true">{glyph}</span> : null}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Figures                                                                     */
/* -------------------------------------------------------------------------- */

export function Figure({
  label,
  value,
  tone,
  emphasis = false,
  footnote,
}: {
  label: string;
  value: string;
  tone?: Tone;
  emphasis?: boolean;
  footnote?: string;
}) {
  return (
    <div>
      <Eyebrow>{label}</Eyebrow>
      <p
        className={`figure mt-2 ${
          emphasis
            ? "text-[2.1rem] leading-none font-medium"
            : "text-[1.35rem] leading-none"
        } ${tone ? TONE_TEXT[tone] : "text-ink"}`}
      >
        {value}
      </p>
      {footnote ? (
        <p className="mt-2 text-[0.78rem] leading-snug text-slate-soft">
          {footnote}
        </p>
      ) : null}
    </div>
  );
}

/** A label/value pair for dense reference blocks. */
export function Field({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-rule py-2.5 last:border-b-0">
      <span className="text-[0.82rem] text-slate">{label}</span>
      <span
        className={`text-right text-[0.85rem] text-ink ${mono ? "figure" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Absence                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * The single way this product says it does not have a number. It is a phrase,
 * never a dash and never a zero, because a zero is a measurement.
 */
export function Unavailable({
  reason = "Not available",
}: {
  reason?: string;
}) {
  return (
    <span className="figure text-[0.85rem] text-slate-soft italic">
      {reason}
    </span>
  );
}

export function Loading({ label = "Reading the engine" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 py-16 text-slate"
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-soft" />
      <span className="eyebrow">{label}…</span>
    </div>
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
    <Panel className="p-6">
      <Eyebrow className="!text-deficit">Unavailable</Eyebrow>
      <p className="mt-2 max-w-[60ch] text-[0.95rem] leading-relaxed text-ink">
        {message}
      </p>
      <p className="mt-3 max-w-[60ch] text-[0.85rem] leading-relaxed text-slate">
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
          className="mt-5 rounded-[2px] border border-ink px-3.5 py-1.5 text-[0.82rem] font-medium text-ink transition-colors hover:bg-ink hover:text-surface"
        >
          Try again
        </button>
      ) : null}
    </Panel>
  );
}

/** A short empty state that explains why a screen has nothing to show. */
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
    <Panel className="p-8">
      <h3 className="text-[1.05rem] font-medium text-ink">{title}</h3>
      <p className="mt-2 max-w-[58ch] text-[0.9rem] leading-relaxed text-slate">
        {body}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </Panel>
  );
}
