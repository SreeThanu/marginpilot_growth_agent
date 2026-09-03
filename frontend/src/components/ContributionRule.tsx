/**
 * The contribution rule — this product's one picture.
 *
 * Three metric cards can tell you that contribution is ₹250,417 and the
 * incentive is ₹99,413 without ever making you feel the subtraction. So the
 * arithmetic is drawn instead of listed: contribution runs right from zero, the
 * incentive is taken back off its tip, and whatever the incentive does not
 * consume is the net. When the incentive is longer than the contribution the
 * remainder lands left of zero, in the deficit field, which is the whole of
 * Scenario A's argument in one line.
 *
 * Every extent is a proportion of numbers the engine returned. Nothing here
 * computes an economic quantity: it converts three given rupee figures into
 * three widths.
 */

"use client";

import { rupees } from "@/lib/format";
import { Eyebrow } from "./ui";

/** Below this share of the axis a label will not fit inside its own bar. */
const INSIDE_LABEL_MIN_WIDTH = 24;

interface Props {
  contributionInr: number;
  incentiveInr: number;
  netInr: number;
  /** Shown under the net marker, e.g. "expected" or "projected from the pilot". */
  basisNote: string;
}

function Bar({
  left,
  width,
  top,
  tone,
  label,
}: {
  left: number;
  width: number;
  top: number;
  tone: "earn" | "spend";
  label: string;
}) {
  const inside = width >= INSIDE_LABEL_MIN_WIDTH;
  return (
    <>
      <div
        className={`mp-extent absolute flex h-[30px] items-center justify-end rounded-[2px] px-2.5 ${
          tone === "earn" ? "bg-earn" : "bg-spend"
        }`}
        style={{ top, left: `${left}%`, width: `${width}%` }}
      >
        {inside ? (
          <span className="figure text-[0.72rem] font-medium whitespace-nowrap text-white/95">
            {label}
          </span>
        ) : null}
      </div>
      {!inside ? (
        <span
          className={`figure absolute text-[0.72rem] font-medium whitespace-nowrap ${
            tone === "earn" ? "text-earn" : "text-spend"
          }`}
          style={{ top: top + 8, left: `calc(${left + width}% + 8px)` }}
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
  basisNote,
}: Props) {
  const negative = netInr < 0;

  // The axis has to hold zero, the contribution's tip and the net's landing
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

  // The net label rides above its marker, pulled back inside the frame at the
  // edges so it never clips.
  const netAnchor =
    netX < 14 ? "left-0" : netX > 86 ? "right-0" : "-translate-x-1/2";
  const netStyle =
    netX < 14
      ? { left: 0 }
      : netX > 86
        ? { right: 0 }
        : { left: `${netX}%` };

  return (
    <figure className="mt-4">
      <div className="relative h-[154px] w-full select-none">
        {/* The deficit field. Present only when the net lands inside it. */}
        {negative ? (
          <div
            aria-hidden="true"
            className="absolute top-[44px] bottom-[26px] left-0 bg-deficit-soft"
            style={{ width: `${zeroX}%` }}
          />
        ) : null}

        {/* Zero. The line every figure on this graphic is measured against. */}
        <div
          aria-hidden="true"
          className="absolute top-[42px] bottom-[22px] w-px bg-rule-strong"
          style={{ left: `${zeroX}%` }}
        />
        <span
          aria-hidden="true"
          className="figure absolute bottom-[4px] -translate-x-1/2 text-[0.68rem] text-slate-soft"
          style={{ left: `${zeroX}%` }}
        >
          0
        </span>

        {/* Where the subtraction lands. */}
        <div
          aria-hidden="true"
          className={`mp-extent absolute top-[42px] h-[78px] w-[2px] ${
            negative ? "bg-deficit" : "bg-earn"
          }`}
          style={{ left: `${netX}%` }}
        />
        <div
          className={`absolute top-0 flex flex-col ${
            netX > 86 ? "items-end" : netX < 14 ? "items-start" : "items-center"
          } ${netAnchor}`}
          style={netStyle}
        >
          <span className="eyebrow">Net</span>
          <span
            className={`figure mt-1 text-[0.9rem] font-medium whitespace-nowrap ${
              negative ? "text-deficit" : "text-earn"
            }`}
          >
            {rupees(netInr)}
          </span>
        </div>

        {/* Contribution earned, then the incentive taken back off its tip. */}
        <Bar
          left={earnedLeft}
          width={earnedWidth}
          top={46}
          tone="earn"
          label={`+ ${rupees(contributionInr)} contribution`}
        />
        <Bar
          left={spentLeft}
          width={spentWidth}
          top={84}
          tone="spend"
          label={`− ${rupees(incentiveInr)} incentive`}
        />
      </div>

      <figcaption className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-rule pt-3">
        <Eyebrow>Net contribution</Eyebrow>
        <span
          className={`figure text-[1.15rem] font-medium ${
            negative ? "text-deficit" : "text-earn"
          }`}
        >
          {rupees(netInr)}
        </span>
        <span className="text-[0.8rem] text-slate">{basisNote}</span>
      </figcaption>

      <p className="sr-only">
        Contribution {rupees(contributionInr)} less incentive{" "}
        {rupees(incentiveInr)} leaves a net of {rupees(netInr)}.
      </p>
    </figure>
  );
}
