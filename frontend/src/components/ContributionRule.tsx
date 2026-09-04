/**
 * The ledger — this product's one picture, drawn on the decision band.
 *
 * A diverging chart on a single zero-anchored axis, because the arithmetic is
 * the argument. Contribution runs right from zero. The incentive is then drawn
 * back from the contribution's tip in the opposing direction, and wherever it
 * comes to rest is the net — read directly off the axis rather than off a
 * caption. When the incentive is longer than the contribution it crosses zero,
 * and the overhang on the far side *is* the loss.
 *
 * Every extent is a proportion of three numbers the engine returned:
 * contribution, incentive, net. Nothing here computes an economic quantity — it
 * converts given rupee figures into pixel positions, and the only values shown
 * as text are those same three fields.
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
 * One extent on the axis.
 *
 * `fill` and `text` are decided by the caller, because what a bar means differs
 * per row: contribution is earned or projected, the incentive is a cost, and
 * the resolved net is a gain or a loss.
 */
function Extent({
  left,
  width,
  top,
  height = 34,
  fill,
  labelInside,
  labelOutside,
  label,
}: {
  left: number;
  width: number;
  top: number;
  height?: number;
  fill: string;
  labelInside: string;
  labelOutside: string;
  label: string;
}) {
  const inside = width >= INSIDE_LABEL_MIN_WIDTH;
  return (
    <>
      <div
        className={`mp-extent absolute flex items-center justify-end rounded-[2px] px-3 ${fill}`}
        style={{ top, left: `${left}%`, width: `${width}%`, height }}
      >
        {inside ? (
          <span
            className={`figure text-[0.72rem] font-medium whitespace-nowrap ${labelInside}`}
          >
            {label}
          </span>
        ) : null}
      </div>
      {!inside ? (
        <span
          className={`figure absolute text-[0.72rem] font-medium whitespace-nowrap ${labelOutside}`}
          style={{
            top: top + height / 2 - 8,
            left: `calc(${left + width}% + 10px)`,
          }}
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

  // Row 1: contribution, right from zero.
  const earnedLeft = Math.min(zeroX, contributionX);
  const earnedWidth = Math.abs(contributionX - zeroX);

  // Row 2: the incentive, taken back from the contribution's tip. Where it ends
  // is the net. The portion still covered by contribution reads as cost; any
  // portion beyond zero is the overhang, and that overhang is the loss.
  const coveredLeft = Math.min(Math.max(netX, zeroX), contributionX);
  const coveredWidth = Math.abs(contributionX - Math.max(netX, zeroX));
  const overhangLeft = Math.min(netX, zeroX);
  const overhangWidth = negative ? Math.abs(zeroX - netX) : 0;

  // Row 3: the resolved position — what the subtraction actually left.
  const netLeft = Math.min(zeroX, netX);
  const netWidth = Math.abs(netX - zeroX);

  // Viridian is reserved for a net a measurement stands behind. A positive net
  // resting on a prior is potential, and reads amber so it cannot be mistaken
  // for money already banked. A negative net is value destroyed: brick.
  const resultFill = negative
    ? "bg-risk-dark/85"
    : measured
      ? "bg-earn-dark/85"
      : "bg-open-dark/25";
  /*
   * Marked important because this class also lands on `.eyebrow`, whose own
   * `color` otherwise wins the cascade and painted the row label grey. The
   * negative branch already carried the flag, so only these two were affected —
   * the loss row rendered brick while the gain rows did not render viridian or
   * amber at all. This restores the colour the code always intended.
   */
  const resultText = negative
    ? "!text-risk-dark"
    : measured
      ? "!text-earn-dark"
      : "!text-open-dark";

  return (
    <figure className="mt-9">
      <div className="relative h-[214px] w-full select-none">
        {/* The deficit field, behind everything left of zero. */}
        {negative ? (
          <div
            aria-hidden="true"
            className="absolute top-[26px] bottom-[30px] left-0 bg-risk-dark/10"
            style={{ width: `${zeroX}%` }}
          />
        ) : null}

        {/* Zero. The line every extent on this graphic is measured from. */}
        <div
          aria-hidden="true"
          className="absolute top-[22px] bottom-[26px] w-px bg-band-rule-strong"
          style={{ left: `${zeroX}%` }}
        />
        <span
          aria-hidden="true"
          className="figure absolute bottom-[6px] -translate-x-1/2 text-[0.68rem] text-band-subtle"
          style={{ left: `${zeroX}%` }}
        >
          0
        </span>

        {/* Row 1 — what the promotion earns. */}
        <span className="eyebrow eyebrow-dark absolute top-0">
          Contribution earned
        </span>
        <Extent
          left={earnedLeft}
          width={earnedWidth}
          top={26}
          fill={
            measured
              ? "bg-earn-dark/85"
              : "border border-dashed border-open-dark/70 bg-open-dark/15"
          }
          labelInside={measured ? "text-band" : "text-open-dark"}
          labelOutside={measured ? "text-earn-dark" : "text-open-dark"}
          label={`+ ${rupees(contributionInr)}`}
        />

        {/* Row 2 — what the incentive takes back, drawn against it. */}
        <span
          className="eyebrow eyebrow-dark absolute"
          style={{ top: 74 }}
        >
          Incentive paid
        </span>
        <Extent
          left={coveredLeft}
          width={coveredWidth}
          top={100}
          fill="bg-spend-dark/45"
          labelInside="text-band-ink/85"
          labelOutside="text-band-muted"
          label={`− ${rupees(incentiveInr)}`}
        />
        {/* The overhang past zero. This is the loss, and it is brick. */}
        {overhangWidth > 0 ? (
          <div
            className="mp-extent absolute h-[34px] rounded-[2px] bg-risk-dark/80"
            style={{
              top: 100,
              left: `${overhangLeft}%`,
              width: `${overhangWidth}%`,
            }}
          />
        ) : null}

        {/* Row 3 — where the subtraction came to rest. */}
        <span
          className={`eyebrow absolute ${resultText}`}
          style={{ top: 148 }}
        >
          {negative ? "Value destroyed" : measured ? "Net earned" : "Net, if it holds"}
        </span>
        <Extent
          left={netLeft}
          width={netWidth}
          top={168}
          height={22}
          fill={resultFill}
          labelInside={negative || measured ? "text-band" : "text-open-dark"}
          labelOutside={resultText}
          label={rupees(netInr)}
        />
      </div>

      <figcaption className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-band-rule pt-3.5">
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
