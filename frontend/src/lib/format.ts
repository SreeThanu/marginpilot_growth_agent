/**
 * Presentation only.
 *
 * Every function here takes a number the engine produced and returns a string.
 * None of them adds, subtracts, scales, projects or compares. If a display
 * needs a quantity that is not already in the API response, the right fix is an
 * engine change, not a helper in this file.
 */

import type { Decision } from "@/types/domain";

const RUPEES = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

const RUPEES_EXACT = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const COUNT = new Intl.NumberFormat("en-US");

/** Grouped rupees. The sign travels with the number, never with the colour alone. */
export function rupees(value: number): string {
  const sign = value < 0 ? "−" : "";
  return `${sign}₹${RUPEES.format(Math.abs(Math.round(value)))}`;
}

/** `₹10.55` — used where the figure is per-customer and rounding would erase it. */
export function rupeesExact(value: number): string {
  const sign = value < 0 ? "−" : "";
  return `${sign}₹${RUPEES_EXACT.format(Math.abs(value))}`;
}

export function count(value: number): string {
  return COUNT.format(value);
}

export function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** For p-values, which cross into scientific notation on a good result. */
export function pValue(value: number): string {
  if (value < 0.0001) return "< 0.0001";
  return value.toFixed(4);
}

export const DECISION_LABEL: Record<Decision, string> = {
  PROMOTE: "Promote",
  DO_NOT_PROMOTE: "Do not promote",
  RUN_EXPERIMENT_FIRST: "Run experiment first",
  INSUFFICIENT_EVIDENCE: "Insufficient evidence",
};

/**
 * One sentence per decision, describing what the state means rather than
 * restating the verb. These are labels for the four states the engine can
 * return; they assert nothing the engine did not.
 */
export const DECISION_SUBTITLE: Record<Decision, string> = {
  PROMOTE: "Validated through a measured experiment.",
  DO_NOT_PROMOTE: "The promotion destroys expected contribution.",
  RUN_EXPERIMENT_FIRST: "Promising economics, but insufficient evidence.",
  INSUFFICIENT_EVIDENCE: "The proposal could not be used.",
};

export type Tone = "earn" | "deficit" | "open" | "spend";

export const DECISION_TONE: Record<Decision, Tone> = {
  PROMOTE: "earn",
  DO_NOT_PROMOTE: "deficit",
  RUN_EXPERIMENT_FIRST: "open",
  INSUFFICIENT_EVIDENCE: "spend",
};

/** Human names for the gate identifiers the policy layer emits. */
export const GATE_NAMES: Record<string, string> = {
  G1: "Valid input",
  G2: "Break-even economics",
  G3: "Evidence quality",
  G4: "Learning economics",
  G5: "Exposure and budget",
  G6: "Rollout approval",
};

export const GATE_ORDER = ["G1", "G2", "G3", "G4", "G5", "G6"] as const;

/**
 * Readable text for the constraint and unresolved codes the engine returns.
 * A code with no entry here is shown verbatim — inventing a friendly name for
 * a constraint nobody recognises would hide which rule actually fired.
 */
export const CODE_TEXT: Record<string, string> = {
  G1_INVALID_INPUT: "The proposal referenced something this merchant does not have.",
  G2_BREAK_EVEN_UNREACHABLE:
    "No conversion lift makes this campaign profitable — the incentive costs more than an order earns.",
  G2_NEGATIVE_EXPECTED_NET:
    "At the proposed lift, the incentive costs more than the extra orders earn.",
  G3_EVIDENCE_INSUFFICIENT:
    "The measurement did not clear the pre-registered scaling rule.",
  G4_EXPERIMENT_UNAFFORDABLE:
    "The experiment needed to answer this cannot be run within budget or population.",
  G6_ROLLOUT_NET_NOT_POSITIVE:
    "The measured effect does not survive the rollout the merchant can fund.",
  PROPOSAL_REJECTED: "The assistant's reply failed validation and was refused.",
  G4_VALUE_OF_INFORMATION_UNRESOLVED:
    "Whether the experiment costs less than the information it buys is an open question in this project. No threshold for it has been committed, so none is applied.",
  remaining_budget: "Remaining budget",
  max_discount: "Maximum discount depth",
  min_contribution_margin: "Minimum contribution margin",
  max_customer_exposure: "Maximum customer exposure",
  min_experiment_power: "Minimum experiment power",
};

export function codeText(code: string): string {
  return CODE_TEXT[code] ?? code;
}
