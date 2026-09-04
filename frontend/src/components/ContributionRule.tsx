/**
 * The ledger — this product's one picture, drawn on the decision band.
 *
 * Three metric tiles can state the contribution and the incentive without ever
 * making you feel the subtraction between them. So the arithmetic is drawn:
 * contribution runs right from zero, the incentive is taken back off its tip,
 * and whatever the incentive does not consume is the net. When the incentive is
 * longer than the contribution the remainder lands left of zero, in the deficit
 * field — which is the entire argument of the product, in one line, without a
 * sentence of explanation.
 *
 * Every extent is a proportion of numbers the engine returned. Nothing here
 * computes an economic quantity: it converts three given rupee figures into
 * three widths.
 */

"use client";

import { rupees } from "@/lib/format";

/** Below this share of the axis a label will not fit inside its own bar. */
const INSIDE_LABEL_MIN_WIDTH = 26;

interface Props {
  contributionInr: number;
  incentiveInr: number;
  netInr: number;
  /** Whether the net came from a measurement or from the proposed lift. */
  measured: boolean;
  basisNote: string;
}

/**
 * A contribution or incentive extent.
 *
 * The contribution bar is solid viridian only when a measurement stands behind
 * it. Where the figure rests on a prior or on history it is drawn as an
 * outlined amber extent instead — present, sized correctly, and visibly not
 * yet banked. The width is the same either way; only the confidence reads
 * differently.
 */
function Bar({
  left,
  width,
  top,
  kind,
  measured,
  label,
}: {
  left: number;
  width: number;
  top: number;
  kind: "earn" | "spend";
  measured: boolean;
  label: string;
}) {
  const inside = width >= INSIDE_LABEL_MIN_WIDTH;
  const projected = kind === "earn" && !measured;

  const fill =
    kind === "spend"
      ? "bg-spend-dark/45"
      : measured
        ? "bg-earn-dark/85"
        : "border border-dashed border-open-dark/70 bg-open-dark/15";

  const insideText =
    kind === "earn" && measured
      ? "text-band"
      : projected
        ? "text-open-dark"
        : "text-band-ink/85";

  return (
    <>
      <div
        className={`mp-extent absolute flex h-[34px] items-center justify-end rounded-[2px] px-3 ${fill}`}
        style={{ top, left: `${left}%`, width: `${width}%` }}
      >
        {inside ? (
          <span
            className={`figure text-[0.72rem] font-medium whitespace-nowrap ${insideText}`}
          >
            {label}
          </span>
        ) : null}
      </div>
      {!inside ? (
        <span
          className={`figure absolute text-[0.72rem] font-medium whitespace-nowrap ${
            kind === "earn"
              ? measured
                ? "text-earn-dark"
                : "text-open-dark"
              : "text-band-muted"
          }`}
          style={{ top: top + 9, left: `calc(${left + width}% + 10px)` }}
        >
          {label}
        </span>
      ) : null}
    </>
  );
}

export function ContributionRule({
  contributionInr,
  incentiveInr,
  netInr,
  measured,
  basisNote,
}: Props) {
  const negative = netInr < 0;

  // The axis must hold zero, the contribution's tip and the net's landing
  // point. Padding keeps the end labels off the edge of the frame.
  const low = Math.min(0, netInr, contributionInr);
  const high = Math.max(0, netInr, contributionInr);
  const span = high - low || 1;
  const pad = span * 0.06;
  const min = low - pad;
  const max = high + pad;
  const scale = (value: number) => ((value - min) / (max - min)) * 100;

  const zeroX = scale(0);
  const contributionX = scale(contributionInr);
  const netX = scale(netInr);

  const earnedLeft = Math.min(zeroX, contributionX);
  const earnedWidth = Math.abs(contributionX - zeroX);
  const spentLeft = Math.min(netX, contributionX);
  const spentWidth = Math.abs(contributionX - netX);

  // Viridian is reserved for a net a measurement stands behind. A positive net
  // resting on a prior is potential, and reads amber so it cannot be mistaken
  // for money already banked.
  const netMarker = negative
    ? "bg-risk-dark"
    : measured
      ? "bg-earn-dark"
      : "bg-open-dark";
  const netText = negative
    ? "text-risk-dark"
    : measured
      ? "text-earn-dark"
      : "text-open-dark";

  // The net label rides above its marker, pulled inside the frame at the edges.
  const netStyle =
    netX < 13
      ? { left: 0 }
      : netX > 87
        ? { right: 0 }
        : { left: `${netX}%`, transform: "translateX(-50%)" };

  return (
    <figure className="mt-9">
      <div className="relative h-[168px] w-full select-none">
        {/* The deficit field. Present only when the net lands inside it. */}
        {negative ? (
          <div
            aria-hidden="true"
            className="absolute top-[52px] bottom-[28px] left-0 bg-risk-dark/12"
            style={{ width: `${zeroX}%` }}
          />
        ) : null}

        {/* Zero. The line every figure on this graphic is measured against. */}
        <div
          aria-hidden="true"
          className="absolute top-[48px] bottom-[24px] w-px bg-band-rule-strong"
          style={{ left: `${zeroX}%` }}
        />
        <span
          aria-hidden="true"
          className="figure absolute bottom-0 -translate-x-1/2 text-[0.68rem] text-band-subtle"
          style={{ left: `${zeroX}%` }}
        >
          0
        </span>

        {/* Where the subtraction lands. */}
        <div
          aria-hidden="true"
          className={`mp-extent absolute top-[48px] h-[86px] w-[2px] ${netMarker}`}
          style={{ left: `${netX}%` }}
        />
        <div className="absolute top-0 flex flex-col" style={netStyle}>
          <span className="eyebrow eyebrow-dark">Net contribution</span>
          <span
            className={`figure mt-1.5 text-[1.05rem] font-medium whitespace-nowrap ${netText}`}
          >
            {rupees(netInr)}
          </span>
        </div>

        {/* Contribution earned, then the incentive taken back off its tip. */}
        <Bar
          left={earnedLeft}
          width={earnedWidth}
          top={52}
          kind="earn"
          measured={measured}
          label={`+ ${rupees(contributionInr)} contribution`}
        />
        <Bar
          left={spentLeft}
          width={spentWidth}
          top={94}
          kind="spend"
          measured={measured}
          label={`− ${rupees(incentiveInr)} incentive`}
        />
      </div>

      <figcaption className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-band-rule pt-3.5">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] font-mono text-[0.685rem] font-medium tracking-[0.06em] ${
            measured
              ? "border-earn-dark/40 bg-earn-dark/10 text-earn-dark"
              : "border-open-dark/50 border-dashed bg-open-dark/10 text-open-dark"
          }`}
        >
          <span aria-hidden="true">{measured ? "◆" : "◇"}</span>
          {measured ? "MEASURED" : "PROJECTED — NOT EARNED"}
        </span>
        <span className="t-caption text-band-muted">{basisNote}</span>
      </figcaption>

      <p className="sr-only">
        Contribution {rupees(contributionInr)} less incentive{" "}
        {rupees(incentiveInr)} leaves a net of {rupees(netInr)}.
      </p>
    </figure>
  );
}
