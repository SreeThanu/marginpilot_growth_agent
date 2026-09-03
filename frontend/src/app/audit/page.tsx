/**
 * Audit — the decision record, and whether it still hangs together.
 *
 * The chain is written by `src/audit/log.py` with the same append(), the same
 * stages and the same hash chaining the rest of the project uses. The identity
 * check matters more than it looks: the payload written to the log is the same
 * object the Overview screen renders, so this page proves a record of *that*
 * decision rather than a valid chain of unrelated entries.
 */

"use client";

import { useState } from "react";

import { useScenarioId } from "@/components/ScenarioContext";
import { FixtureNotice } from "@/components/TopRail";
import {
  Chip,
  ErrorState,
  Eyebrow,
  Loading,
  Panel,
  SectionHeading,
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

function timestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

function Entry({ entry, last }: { entry: AuditEntry; last: boolean }) {
  const [open, setOpen] = useState(false);

  return (
    <li className="relative pl-8">
      {/* The chain, drawn. Each entry carries the hash of the one before it. */}
      {!last ? (
        <span
          aria-hidden="true"
          className="absolute top-5 bottom-0 left-[7px] w-px bg-rule-strong"
        />
      ) : null}
      <span
        aria-hidden="true"
        className="absolute top-3.5 left-0 h-[15px] w-[15px] rounded-full border-2 border-ink bg-surface"
      />

      <Panel className="p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <Eyebrow>Entry {entry.id}</Eyebrow>
            <h3 className="mt-1.5 text-[1rem] font-medium text-ink">
              {STAGE_TITLE[entry.stage] ?? entry.stage}
            </h3>
          </div>
          <p className="figure text-[0.74rem] text-slate-soft">
            {timestamp(entry.recorded_at)}
          </p>
        </div>

        <p className="figure mt-2.5 text-[0.78rem] leading-relaxed text-slate">
          {entry.actor}
        </p>

        <div className="mt-4 grid gap-2 border-t border-rule pt-3 sm:grid-cols-2">
          <div>
            <p className="eyebrow">This entry</p>
            <p className="figure mt-1 text-[0.74rem] break-all text-ink">
              {entry.entry_hash}
            </p>
          </div>
          <div>
            <p className="eyebrow">Links back to</p>
            <p className="figure mt-1 text-[0.74rem] break-all text-slate">
              {entry.prev_hash}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-rule pt-3">
          <span className="eyebrow">Recorded</span>
          {entry.payload_keys.slice(0, 8).map((key) => (
            <span
              key={key}
              className="figure rounded-[2px] bg-sunk px-1.5 py-0.5 text-[0.7rem] text-slate"
            >
              {key}
            </span>
          ))}
          {entry.payload_keys.length > 8 ? (
            <span className="text-[0.72rem] text-slate-soft">
              +{entry.payload_keys.length - 8} more
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="ml-auto rounded-[2px] border border-rule-strong px-2.5 py-1 text-[0.76rem] text-ink transition-colors hover:bg-sunk"
          >
            {open ? "Hide payload" : "Show payload"}
          </button>
        </div>

        {open ? (
          <pre className="figure mt-3 max-h-[320px] overflow-auto rounded-[2px] bg-sunk p-3.5 text-[0.72rem] leading-relaxed text-ink">
            {JSON.stringify(entry.payload, null, 2)}
          </pre>
        ) : null}
      </Panel>
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
    <div className="space-y-10">
      <FixtureNotice />

      <SectionHeading
        eyebrow={`Merchant ${data.scenario} · ${data.experiment_id}`}
        title="The decision record"
        note="Append-only, hash-chained, and enforced by the database rather than by convention. There is no update path and no delete path."
      />

      <Panel className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            <Eyebrow>Verification</Eyebrow>
            <p
              className={`mt-2 text-[1.6rem] leading-none font-medium ${
                data.verified ? "text-earn" : "text-deficit"
              }`}
            >
              {data.verified ? "Chain intact" : "Verification failed"}
            </p>
            <p className="mt-2.5 max-w-[52ch] text-[0.85rem] leading-relaxed text-slate">
              {data.verified
                ? "Every entry's hash covers its own content and the hash before it. Editing or removing a record breaks every hash after it."
                : "At least one entry's hash no longer matches its content. This record cannot be trusted."}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Chip tone={data.verified ? "earn" : "deficit"} glyph={data.verified ? "✓" : "■"}>
              {data.entries.length} entries
            </Chip>
            <Chip
              tone={data.payload_is_the_rendered_object ? "earn" : "deficit"}
              glyph={data.payload_is_the_rendered_object ? "✓" : "■"}
              title="The audited payload is the same object the decision screen renders — identity, not equality."
            >
              Records the decision on screen
            </Chip>
          </div>
        </div>

        <div className="mt-5 border-t border-rule pt-4">
          <Eyebrow>Head hash</Eyebrow>
          <p className="figure mt-1.5 text-[0.78rem] break-all text-ink">
            {data.head_hash || "—"}
          </p>
        </div>
      </Panel>

      <ol className="space-y-4">
        {data.entries.map((entry, index) => (
          <Entry
            key={entry.id}
            entry={entry}
            last={index === data.entries.length - 1}
          />
        ))}
      </ol>

      <section>
        <button
          type="button"
          onClick={() => setRawOpen((v) => !v)}
          className="rounded-[2px] border border-rule-strong px-4 py-2 text-[0.85rem] font-medium text-ink transition-colors hover:bg-sunk"
        >
          {rawOpen ? "Hide" : "Show"} the chain as `make audit` prints it
        </button>
        {rawOpen ? (
          <pre className="figure mt-4 max-h-[520px] overflow-auto rounded-[3px] border border-rule bg-surface p-5 text-[0.72rem] leading-relaxed text-ink">
            {data.rendered}
          </pre>
        ) : null}
      </section>
    </div>
  );
}
