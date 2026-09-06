/**
 * Findings Pack v2 contract.
 *
 * Pack v2 carries evidence semantics with each family so a consumer cannot
 * relabel a rate, interval, or rank as another kind of result.
 */

export type PackV2ReleaseStatus =
  | "available"
  | "approximate"
  | "withheld"
  | "superseded";
export type PackV2EraStability =
  | "stable"
  | "sensitive"
  | "insufficient"
  | "not_evaluated";
export type PackV2Tier = "actionable" | "diagnostic" | "a-lite";
export type PackV2RankBand = "S" | "A" | "B" | "C";
export type PackV2MetricKind =
  | "win_rate"
  | "odds_ratio"
  | "odds_ratio_per_standard_deviation"
  | "correlation"
  | "percentage_points"
  | "count"
  | "auc"
  | "status"
  | "possession_rate"
  | "before_time_rate"
  | "contested_first_rate"
  | "no_objective_rate"
  | "matched_effect";
export type PackV2ObjectiveMetricKind =
  | "possession_rate"
  | "before_time_rate"
  | "contested_first_rate"
  | "no_objective_rate"
  | "matched_effect";
export type PackV2ObservationWindowKind =
  | "pooled"
  | "full_match"
  | "at_checkpoint"
  | "before_time"
  | "interval";

export interface PackV2PatchRange {
  min: string;
  max: string;
}

export interface PackV2ObservationWindow {
  kind: PackV2ObservationWindowKind;
  start_seconds?: number;
  end_seconds?: number;
  include_start: boolean;
  include_end: boolean;
  rule: string;
}

export interface PackV2EvidenceMetadata {
  patch_range: PackV2PatchRange;
  population_scope: string;
  era_stability: PackV2EraStability;
  caveats: string[];
  source_document: string;
  source_section: string;
  source_ref: string;
  provenance_key: string;
}

export interface PackV2Provenance {
  source_document: string;
  source_section: string;
  source_ref: string;
  feature_store_manifest_sha256: string;
  generator_revision: `sha256:${string}`;
  feature_contract_version: string;
}

export interface PackV2Dataset extends PackV2EvidenceMetadata {
  raw_unique_matches: number;
  eligible_matches: number;
  participant_performances: number;
  tracked_players: number;
  patch_buckets: number;
  median_game_minutes: number;
  surrender_rate: number;
  patches: string[];
  eligibility: string;
}

export interface PackV2FeatureContracts {
  population: string;
  personal_history: string | null;
  models: Record<string, string> | null;
}

export interface PackV2Finding extends PackV2EvidenceMetadata {
  key: string;
  tier: PackV2Tier;
  release_status: PackV2ReleaseStatus;
  title: string;
  statement: string;
  metric_kind: Exclude<PackV2MetricKind, PackV2ObjectiveMetricKind>;
  unit: string;
  sample: number;
  value?: unknown;
  release_reason?: string | null;
}

export interface PackV2Habit extends PackV2EvidenceMetadata {
  key: string;
  label: string;
  metric_kind:
    | "odds_ratio_per_standard_deviation"
    | "percentage_points"
    | "win_rate";
  unit: string;
  effect: number;
  feature: string;
  eligibility: string;
  tier: PackV2Tier;
  release_status: PackV2ReleaseStatus;
  sample: number;
  release_reason?: string;
}

export type PackV2Objective = PackV2EvidenceMetadata & {
  objective: "dragon" | "herald" | "baron";
  metric_kind: PackV2ObjectiveMetricKind;
  window: PackV2ObservationWindow;
  rate: number;
  sample: number;
  tier: PackV2Tier;
  release_status: PackV2ReleaseStatus;
  release_reason?: string;
};

export interface PackV2ComebackBand extends PackV2EvidenceMetadata {
  feature: "team_gold_diff_15m";
  feature_contract_version: string;
  checkpoint_seconds: 900;
  unit: "gold";
  lower_bound: number;
  upper_bound: number | null;
  include_lower: boolean;
  include_upper: false;
  rate: number | null;
  sample: number;
  eligibility: string;
  tier: PackV2Tier;
  release_status: PackV2ReleaseStatus;
  release_reason?: string | null;
}

export interface PackV2BanContext extends PackV2EvidenceMetadata {
  key: string;
  champion: string | null;
  metric_kind: "ban_rate_win_rate_correlation" | "ban_rate" | "win_rate";
  value: number;
  sample: number;
  tier: "diagnostic";
  release_status: PackV2ReleaseStatus;
  release_reason?: string;
}

export interface PackV2TierEntry extends PackV2EvidenceMetadata {
  champion: string;
  role: "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY";
  games: number;
  observed_win_rate: number;
  role_pick_rate: number;
  rank_band: PackV2RankBand;
  minimum_games: 500;
  tier: "diagnostic";
  release_status: PackV2ReleaseStatus;
  release_reason?: string;
}

export interface PackV2Interval {
  lower: number;
  upper: number;
  include_lower: boolean;
  include_upper: boolean;
}

export interface PackV2Matchup extends PackV2EvidenceMetadata {
  champion: string;
  opponent: string;
  role: "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY";
  games: number;
  estimate: number;
  interval: PackV2Interval;
  tier: "diagnostic";
  release_status: PackV2ReleaseStatus;
  release_reason?: string;
}

export interface PackV2Checkpoint extends PackV2EvidenceMetadata {
  feature: string;
  window: PackV2ObservationWindow;
  value: number;
  unit: string;
  sample: number;
  tier: PackV2Tier;
  release_status: PackV2ReleaseStatus;
  release_reason?: string;
}

export interface PackV2RouteArchetype extends PackV2EvidenceMetadata {
  key: string;
  label: string;
  sample: number;
  observed_outcome: number;
  side_context: string | null;
  champion_context: string | null;
  coordinate_validation: "validated" | "approximate" | "unavailable";
  tier: "a-lite" | "diagnostic";
  release_status: "approximate";
  release_reason?: string;
}

export interface PackV2BuildEvidence extends PackV2EvidenceMetadata {
  release_status: "withheld";
  release_reason: string;
  rows: object[] | null;
}

export interface PackV2ModelInterval {
  min: number;
  max: number;
}

export interface PackV2ModelFeature {
  name: string;
  dtype: "float32";
  unit: string;
  source: string;
  adjustable: boolean;
  bounds: PackV2ModelInterval;
}

export interface PackV2PreprocessingStep {
  name: string;
  feature: string;
  operation: string;
  parameters: number[] | null;
}

export interface PackV2SmokeTest {
  features: number[];
  expected: number;
  tolerance: number;
}

export interface PackV2ModelValidation {
  grouped_holdout: Record<string, number>;
  temporal_holdout: Record<string, number>;
  calibration: Record<string, number>;
  parity: Record<string, string | number | boolean>;
  gates: Record<string, boolean> | null;
}

export interface PackV2ModelCard {
  model_id: string;
  model_version: string;
  input_names: string[];
  output_names: string[];
  features: PackV2ModelFeature[];
  feature_order: string[];
  preprocessing: PackV2PreprocessingStep[];
  bounds: Record<string, PackV2ModelInterval>;
  patch_scope: PackV2PatchRange;
  validation: PackV2ModelValidation;
  caveats: string[];
  smoke_test: PackV2SmokeTest;
}

export interface PackV2Artifact {
  path: string;
  format: "onnx";
  sha256: string;
  size: number;
  model_card_path: string;
}

export interface PackV2ModelDeclaration {
  model_id: string;
  release_status: PackV2ReleaseStatus;
  artifact: PackV2Artifact | null;
  model_card: PackV2ModelCard | null;
  release_reason: string | null;
}

export interface FindingsPackV2 {
  schema_version: 2;
  pack_version: string;
  generated_at: string;
  patch_range: PackV2PatchRange;
  dataset: PackV2Dataset;
  feature_contracts: PackV2FeatureContracts;
  provenance: Record<string, PackV2Provenance>;
  findings: PackV2Finding[];
  habits: PackV2Habit[];
  objectives: PackV2Objective[];
  comeback_odds: PackV2ComebackBand[];
  ban_context: PackV2BanContext[];
  tier_list: PackV2TierEntry[];
  matchup_examples: PackV2Matchup[];
  checkpoints: PackV2Checkpoint[];
  route_archetypes: PackV2RouteArchetype[];
  build_evidence: PackV2BuildEvidence;
  models?: Record<string, PackV2ModelDeclaration> | null;
}

export function isFindingsPackV2(value: unknown): value is FindingsPackV2 {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { schema_version?: unknown }).schema_version === 2
  );
}
