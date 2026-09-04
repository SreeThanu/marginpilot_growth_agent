/**
 * The API contract, typed once.
 *
 * These shapes mirror what `api/service.py` returns, which in turn mirrors what
 * the Python engine produced. Nothing is optional here for convenience: a field
 * the engine can leave empty is typed `| null` so the view is forced to decide
 * what to render when it is absent, rather than defaulting it to a number.
 */

export type Decision =
  | "PROMOTE"
  | "DO_NOT_PROMOTE"
  | "RUN_EXPERIMENT_FIRST"
  | "INSUFFICIENT_EVIDENCE";

export type EvidenceBasis = "NONE" | "PRIOR" | "HISTORY" | "EXPERIMENT";

export interface Merchant {
  merchant_id: string;
  population: number;
  budget_inr: number;
  observed_conversion: number;
  observed_aov_inr: number;
  observed_margin: number;
  contribution_per_order_inr: number;
  experiment_window_days: number;
  context: string[];
}

export interface Intervention {
  intervention_id: string;
  kind: string;
  name: string;
  description: string;
  incentive_cost_per_order_inr: number;
  depth_at_observed_aov: number;
}

export interface CampaignHistory {
  intervention_id: string;
  treated_customers: number;
  orders: number;
  net_per_treated_customer_inr: number;
  standard_error_inr: number;
}

export interface Proposal {
  intervention_id: string;
  cohort_id: string;
  expected_lift_absolute: number;
  evidence_basis: EvidenceBasis;
  hypothesis: string;
  mechanism: string;
  citations: string[];
  requested_decision: Decision | null;
}

export interface ProposalEnvelope {
  accepted: boolean;
  rejected_because: string | null;
  proposal: Proposal | null;
}

export interface Recommendation {
  decision: Decision;
  diagnosis: string;
  rationale: string;
  intervention_id: string | null;
  cohort_id: string | null;
  expected_incremental_contribution_inr: number;
  expected_incentive_cost_inr: number;
  expected_net_contribution_inr: number;
  required_break_even_lift_absolute: number | null;
  evidence_basis: EvidenceBasis;
  experiment_required: boolean;
  experiment_cost_inr: number;
  experiment_horizon_per_arm: number;
  customers_treated: number;
  binding_constraints: string[];
  unresolved: string[];
  citations: string[];
  assumptions: string[];
  model_requested: Decision | null;
  overruled_the_model: boolean;
  gates_passed: string[];
}

export interface Arm {
  name: string;
  n_assigned: number;
  n_converted: number;
  conversion_rate: number;
  contribution_mean_inr: number;
}

export interface Comparison {
  conversion_control: number;
  conversion_treatment: number;
  absolute_difference: number;
  difference_ci_low: number;
  difference_ci_high: number;
  p_value: number;
  net_contribution_inr: number;
  contribution_ci_low: number;
  contribution_ci_high: number;
  contribution_se_inr: number;
  net_per_treated_customer_inr: number;
  probability_net_positive: number;
  scale_eligible: boolean;
}

export interface Experiment {
  experiment_id: string;
  horizon_per_arm: number;
  intervention_id: string;
  arms: Arm[];
  verdict_eligible: boolean;
  pilot_spend_inr: number;
  depth: number;
  comparison: Comparison | null;
}

export interface ScenarioDetail {
  scenario: string;
  title: string;
  story: string;
  label: string;
  merchant: Merchant;
  intervention: Intervention | null;
  history: CampaignHistory | null;
  proposal: ProposalEnvelope;
  initial: Recommendation;
  experiment: Experiment | null;
  final: Recommendation;
}

export interface ScenarioSummary {
  scenario: string;
  title: string;
  story: string;
  decision: Decision;
  expected_net_contribution_inr: number;
  merchant_name: string;
  has_experiment: boolean;
}

export interface ScenarioIndex {
  label: string;
  scenarios: ScenarioSummary[];
}

export interface AuditEntry {
  id: number;
  recorded_at: string;
  world_id: string;
  experiment_id: string;
  stage: string;
  actor: string;
  payload_keys: string[];
  payload: Record<string, unknown>;
  prev_hash: string;
  entry_hash: string;
}

export interface AuditTrail {
  scenario: string;
  experiment_id: string;
  verified: boolean;
  head_hash: string;
  payload_is_the_rendered_object: boolean;
  rendered: string;
  entries: AuditEntry[];
}

export interface AdversarialScenario {
  name: string;
  attempted: string;
  refused: boolean;
  refused_by: string;
  reason: string;
}

export interface MalformedOutcome {
  label: string;
  decision: Decision;
  rationale: string;
  binding_constraints: string[];
  spends_money: boolean;
}

export interface ModelOverride {
  scenario: string;
  title: string;
  model_requested: Decision | null;
  policy_decided: Decision;
  overruled: boolean;
  rationale: string;
}

export interface PolicyLimits {
  max_discount_pct: number;
  min_contribution_margin: number;
  max_customer_exposure_share: number;
  min_experiment_power: number;
  min_budget_headroom_share: number;
}

export interface SafetyReport {
  scenarios: AdversarialScenario[];
  refused: number;
  total: number;
  malformed: MalformedOutcome[];
  model_overrides: ModelOverride[];
  policy_limits: PolicyLimits;
}

export interface Badge {
  label: string;
  value: string;
  detail: string;
}

export interface Reproducibility {
  badges: Badge[];
}
