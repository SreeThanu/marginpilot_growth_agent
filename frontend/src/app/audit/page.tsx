/**
 * Audit — the immutable record, and whether it still hangs together.
 *
 * The chain is written by `src/audit/log.py` with the same append(), the same
 * stages and the same hash chaining the rest of the project uses. The identity
 * check matters more than it looks: the payload written to the log is the same
 * object the decision screen renders, so this page proves a record of *that*
 * decision rather than a valid chain of unrelated entries.
 */

"use client";

import { useState } from "react";

import { useScenarioId } from "@/components/ScenarioContext";
import { FixtureNotice } from "@/components/TopRail";
import {
  Band,
  Chip,
  ErrorState,
  Eyebrow,
  Loading,
  Rule,
  SectionHead,
  Shell,
} from "@/components/ui";
import { useAudit } from "@/lib/api";
import type { AuditEntry } from "@/types/domain";

const STAGE_TITLE: Record<string, string> = {
  intent: "Intent",
  policy_verdict: "Policy verdict",
  randomization: "Randomization",
  execution: "Execution",
  payment: "Payment",
  outcome: "Outcome",
  skip: "Declined to spend",
};

const STAGE_NOTE: Record<string, string> = {
  intent: "What was proposed, and what the policy made of it.",
  execution: "The pilot, launched and read at its pre-committed horizon.",
  policy_verdict: "The deterministic verdict the merchant was given.",
};

function timestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

function Entry({
  entry,
  index,
  last,
}: {
  entry: AuditEntry;
  index: number;
  last: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <li className="relative grid gap-x-10 gap-y-4 pl-10 lg:grid-cols-[1fr_1.2fr]">
      {/* The chain, drawn: each entry carries the hash of the one before it. */}
      {!last ? (
        <span
          aria-hidden="true"
          className="absolute top-4 bottom-0 left-[5px] w-px bg-rule-strong"
        />
      ) : null}
      <span
        aria-hidden="true"
        className="absolute top-[7px] left-0 h-[11px] w-[11px] rounded-full border-2 border-ink bg-canvas"
      />

      <div className="pb-10">
        <div className="flex items-baseline gap-3">
          <span className="figure text-[0.72rem] text-ink-subtle">
            {String(index + 1).padStart(2, "0")}
          </span>
          <h3 className="t-title text-ink">
            {STAGE_TITLE[entry.stage] ?? entry.stage}
          </h3>
        </div>
        <p className="t-caption mt-2 max-w-[42ch] text-ink-muted">
          {STAGE_NOTE[entry.stage] ?? ""}
        </p>
        <p className="figure t-caption mt-3 text-ink-subtle">{entry.actor}</p>
        <p className="figure t-caption mt-1 text-ink-subtle">
          {timestamp(entry.recorded_at)}
        </p>
      </div>

      <div className="pb-10">
        <Eyebrow>Hash</Eyebrow>
        <p className="figure mt-2 text-[0.74rem] break-all text-ink">
          {entry.entry_hash}
        </p>
        <p className="eyebrow mt-4">Links back to</p>
        <p className="figure mt-2 text-[0.74rem] break-all text-ink-muted">
          {entry.prev_hash}
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          {entry.payload_keys.slice(0, 6).map((key) => (
            <span
              key={key}
              className="figure rounded-[2px] bg-sunk px-1.5 py-0.5 text-[0.68rem] text-ink-muted"
            >
              {key}
            </span>
          ))}
          {entry.payload_keys.length > 6 ? (
            <span className="t-caption text-ink-subtle">
              +{entry.payload_keys.length - 6} more
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="t-caption ml-auto rounded-[2px] border border-rule-strong px-2.5 py-1 text-ink transition-colors hover:bg-sunk"
          >
            {open ? "Hide payload" : "Show payload"}
          </button>
        </div>

        {open ? (
          <pre className="figure mt-4 max-h-[320px] overflow-auto rounded-[3px] border border-rule bg-surface p-4 text-[0.7rem] leading-relaxed text-ink">
            {JSON.stringify(entry.payload, null, 2)}
          </pre>
        ) : null}
      </div>
    </li>
  );
}

export default function AuditPage() {
  const { scenario } = useScenarioId();
  const { data, error, loading, retry } = useAudit(scenario);
  const [rawOpen, setRawOpen] = useState(false);

  if (error) return <ErrorState message={error.message} onRetry={retry} />;
  if (loading || !data) return <Loading label="Verifying the chain" />;

  return (
    <>
      <Band>
        <Shell className="py-14">
          <div className="grid gap-x-16 gap-y-10 lg:grid-cols-[1fr_1fr]">
            <div>
              <Eyebrow onBand>Immutable record</Eyebrow>
              <h1
                className={`t-headline mt-4 max-w-[22ch] ${
                  data.verified ? "text-earn-dark" : "text-risk-dark"
                }`}
              >
                {data.verified
                  ? "Chain intact"
                  : "Verification failed"}
              </h1>
              <p className="t-small mt-5 max-w-[50ch] text-band-muted">
                {data.verified
                  ? "Every entry's hash covers its own content and the hash before it. Editing or removing a record breaks every hash after it, so tampering is detectable even by someone who recreates the table."
                  : "At least one entry's hash no longer matches its content. This record cannot be trusted."}
              </p>
              <div className="mt-7 flex flex-wrap gap-2">
                <Chip
                  tone={data.verified ? "earn" : "risk"}
                  glyph={data.verified ? "✓" : "■"}
                  onBand
                >
                  {data.entries.length} entries
                </Chip>
                <Chip
                  tone={data.payload_is_the_rendered_object ? "earn" : "risk"}
                  glyph={data.payload_is_the_rendered_object ? "✓" : "■"}
                  onBand
                  title="The audited payload is the same object the decision screen renders — identity, not equality."
                >
                  Records the decision on screen
                </Chip>
                <Chip tone="spend" glyph="✕" onBand>
                  No update path, no delete path
                </Chip>
              </div>
            </div>

            <div className="self-center">
              <Eyebrow onBand>Experiment</Eyebrow>
              <p className="figure mt-2 text-[0.9rem] text-band-ink">
                {data.experiment_id}
              </p>
              <p className="eyebrow eyebrow-dark mt-7">Head hash</p>
              <p className="figure mt-2 text-[0.78rem] break-all text-band-ink">
                {data.head_hash || "—"}
              </p>
              <p className="t-caption mt-5 max-w-[46ch] text-band-subtle">
                Append-only is enforced by SQLite triggers, not by convention —
                an UPDATE or DELETE on the table aborts at the database level.
              </p>
            </div>
          </div>
        </Shell>
      </Band>

      <Shell className="pt-5">
        <FixtureNotice />
      </Shell>

      <Shell className="pt-14">
        <SectionHead
          eyebrow={`Merchant ${data.scenario}`}
          title="The decision chain, in order"
          note="Every consequential recommendation leaves a record. A refusal is logged as fully as an approval — a log that only records what happened cannot show what was prevented."
        />
        <ol className="mt-10">
          {data.entries.map((entry, index) => (
            <Entry
              key={entry.id}
              entry={entry}
              index={index}
              last={index === data.entries.length - 1}
            />
          ))}
        </ol>
      </Shell>

      <Shell className="pt-4">
        <Rule />
        <div className="pt-8">
          <button
            type="button"
            onClick={() => setRawOpen((v) => !v)}
            className="t-small rounded-[3px] border border-rule-strong px-4 py-2 font-medium text-ink transition-colors hover:bg-sunk"
          >
            {rawOpen ? "Hide" : "Show"} the chain as{" "}
            <span className="figure">make audit</span> prints it
          </button>
          {rawOpen ? (
            <pre className="figure mt-6 max-h-[520px] overflow-auto rounded-[3px] border border-rule bg-surface p-5 text-[0.7rem] leading-relaxed text-ink">
              {data.rendered}
            </pre>
          ) : null}
        </div>
      </Shell>
    </>
  );
}
