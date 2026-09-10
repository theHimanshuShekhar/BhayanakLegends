
export type RegionRoute = "sea" | "americas" | "europe" | "asia";
export type Role = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY" | "UNKNOWN";
export type AssignedRole = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY";
export type HealthStatus = "ok" | "degraded";
export type SyncState = "idle" | "running" | "cancelled" | "error";
export type SyncMode = "era_first" | "import";
export type OwnerState = "unassigned" | "resolving" | "active" | "error";
export type GameflowPhase =
  | "None"
  | "Lobby"
  | "Matchmaking"
  | "RankedGame"
  | "ChampSelect"
  | "GameStart"
  | "InProgress"
  | "WaitingForStats"
  | "EndOfGame";
export type GameMode =
  | "CLASSIC"
  | "ODIN"
  | "ARAM"
  | "TUTORIAL"
  | "URF"
  | "ONEFORALL"
  | "DOOM_BOTS"
  | "ASCENSION"
  | "FIRSTBLOOD"
  | "KING_PORO"
  | "SIEGE"
  | "PROJECT"
  | "SNOWDOWN"
  | "NEXUSBLITZ"
  | "ULTBOOK"
  | "CHERRY";
export type LiveEventName =
  | "GameStart"
  | "MinionsSpawning"
  | "FirstBrick"
  | "DragonKill"
  | "HeraldKill"
  | "BaronKill"
  | "ChampionKill"
  | "TurretKilled"
  | "InhibKilled"
  | "GameEnd";

export interface Health {
  status: HealthStatus;
  app_version: string;
  pack_version: string | null;
}


export interface OwnerContext {
  owner_key: string | null;
  generation: number;
  owner_state: OwnerState;
  owner_error: string | null;
}

export interface Settings extends OwnerContext {
  riot_id: string | null;
  region_route: RegionRoute;
  has_key: boolean;
  auto_sync: boolean;
}
export interface SettingsPatch {
  riot_id?: string | null;
  region_route?: RegionRoute;
  riot_key?: string | null;
  auto_sync?: boolean;
}
export interface SyncStatus extends OwnerContext {
  state: SyncState;
  mode: SyncMode;
  total_queued: number;
  downloaded: number;
  skipped: number;
  failed: number;
  current_match_id: string | null;
  started_at: string | null;
}

export type InsightSampleStatus = "insufficient" | "review";
export type InsightWindowCompleteness = "full" | "partial" | "unavailable";
export interface RoleInsight {
  role: Role;
  games: number;
  wins: number;
  win_rate: number;
  sample_status: InsightSampleStatus;
}
export interface ChampionInsight {
  champion: string;
  games: number;
  wins: number;
  win_rate: number;
  roles: Role[];
  sample_status: InsightSampleStatus;
}
export interface InsightWindow {
  name: "latest" | "preceding";
  games: number;
  wins: number;
  win_rate: number;
  sample_status: InsightSampleStatus;
  completeness: InsightWindowCompleteness;
}
export interface HistoryInsights {
  state: "empty" | "available";
  sample_size: number;
  filters: { role: Role | null; champion: string | null };
  roles: RoleInsight[];
  champions: ChampionInsight[];
  windows: Record<string, InsightWindow>;
  feature_contract_version: string | null;
  feature_contract_status: "available" | "mixed" | "unavailable";
  feature_insights: HistoryFeatureInsight[];
  feature_trajectories: HistoryFeatureTrajectoryPoint[];
}
export type HistoryFeatureStatus = "available" | "insufficient-sample" | "unavailable";
export type HistoryFeatureKey =
  | "cs10"
  | "level10"
  | "gold_diff_10"
  | "team_gold_diff_15m"
  | "recalls_before_15m"
  | "avg_banked_gold_at_recall_by_15m"
  | "avg_banked_gold_at_recall_by_20m"
  | "unseen_recall_share_by_15m"
  | "unseen_recall_share_by_20m"
  | "first_dragon_by_20m_s"
  | "first_riftherald_by_20m_s"
  | "first_baron_by_20m_s"
  | "smite_contests_before_15m"
  | "smite_contests_before_20m"
  | "early_fight_participation_rate"
  | "plates_taken_by_14m";
export interface HistoryFeatureInsight {
  feature_key: string;
  current_value: number | null;
  role_baseline: number | null;
  delta: number | null;
  sample_size: number;
  status: HistoryFeatureStatus;
  caveat: string;
}
export interface HistoryFeatureTrajectoryPoint {
  feature_key: string;
  played_at: string;
  value: number | null;
  sample_size: number;
  status: HistoryFeatureStatus;
  caveat: string;
}


export interface HistorySummary {
  matches: number;
  patches: string[];
  by_role: RoleRow[];
  win_rate: number;
}
export interface RoleRow {
  role: Role;
  games: number;
  wins: number;
}

export interface TrajectoryPoint {
  patch: string;
  role: Role;
  champion: string | null;
  played_at: string;
  index: number;
  rolling_wr: number;
}

export interface PatchAggregate {
  patch: string;
  games: number;
  wins: number;
  win_rate: number;
}
export interface TeamState {
  feature: "team_gold_diff_15m";
  feature_contract_version: "loltrends-parity-v2";
  team_gold_diff_15m: number | null;
  observed_through_s: number | null;
  non_surrendered: boolean | null;
}
export interface PostGameDigest {
  match_id: string;
  played_at: string;
  champion: string;
  role: Role;
  win: boolean;
  duration_s: number;
  checkpoints: {
    gold_diff_10: number | null;
    gold_diff_15: number | null;
    gold_diff_20: number | null;
  };
  habits: HabitOutcome[];
  headline: string;
  feature_contract_version: string | null;
  personal_history_eligibility: "eligible" | "ineligible" | "unknown";
  features: Record<string, number | null>;
  team_state: TeamState | null;
}

export interface HabitOutcome {
  key: string;
  label: string;
  value: string;
  verdict: "good" | "bad" | "neutral" | "n/a";
}

export type BenchmarkMetric = "cs10" | "level10" | "gold_diff_10";
export type BenchmarkState =
  | "available"
  | "contract-suppressed"
  | "insufficient-personal-history";

export interface RoleBenchmark {
  role: Role;
  personal: Partial<Record<BenchmarkMetric, number>>;
  population: Partial<Record<`${BenchmarkMetric}_median`, number>> & {
    sample: number;
  };
}

export interface BenchmarkResponse {
  state: BenchmarkState;
  rows: RoleBenchmark[];
}

export interface LiveStatus {
  champ_select: { active: boolean; phase: GameflowPhase | null };
  ingame: {
    active: boolean;
    game_id: number | null;
    mode: GameMode | null;
    clock_s: number;
  };
  last_error: string | null;
}

// Rich LCU-bridge snapshots (GET /live/session + SSE "champselect.state").
// COMPLIANCE: enemy summoner names are stripped at the sidecar service layer —
// ChampSelectEnemyCell.name is always null.
export interface ChampSelectBan {
  champion_id: number;
  champion: string | null; // null → UI renders "Champion {id}"
}

export type CellState = "intent" | "picked" | "hover" | "locked" | "none";

export interface ChampSelectAllyCell {
  cell_id: number;
  champion_id: number;
  champion: string | null; // Data Dragon display name; null → UI renders "Champion {id}"
  name: string | null;
  is_local: boolean;
  state: CellState;
}

export interface ChampSelectEnemyCell {
  cell_id: number;
  champion_id: number;
  champion: string | null;
  name: string | null; // always null — compliance
  state: CellState;
}

export interface ChampSelectSnapshot {
  active: boolean;
  phase: GameflowPhase | null;
  timer_sec: number | null;
  local_assigned_role: AssignedRole | null;
  bans_ally: ChampSelectBan[];
  bans_enemy: ChampSelectBan[];
  ally: ChampSelectAllyCell[];
  enemy: ChampSelectEnemyCell[];
}

// Rich in-game snapshots (GET /live/ingame + SSE "live.state"); Live Client
// Data API on :2999. Summoner names here are official spectator data.
export interface ItemLive {
  id: number;
  count: number;
}

export interface PlayerLive {
  summoner: string;
  champion: string | null;
  level: number;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  ward_score: number;
  items: ItemLive[];
}

export interface LiveEvent {
  name: LiveEventName;
  t_s: number;
  actor: string | null;
  victim: string | null;
  detail: string | null; // DragonType on DragonKill
}

export type LiveInferenceStatus =
  | "available"
  | "suppressed"
  | "stale"
  | "incompatible"
  | "unsupported-patch"
  | "out-of-domain"
  | "error";

export interface LiveInference {
  status: LiveInferenceStatus;
  probability: number | null;
  observed_game_time_s: number | null;
  model_version: string | null;
  pack_version: string | null;
  reason: string | null;
}

export interface LiveEventDelta {
  event_id: string;
  source_order: number;
  name: LiveEventName;
  t_s: number;
  baseline_probability: number | null;
  event_probability: number | null;
  delta_probability: number | null;
  pre_observed_game_time_s: number | null;
  post_observed_game_time_s: number | null;
  model_version: string | null;
  pack_version: string | null;
  suppression_status: LiveInferenceStatus;
  reason: string | null;
}

export interface InGameSnapshot {
  active: boolean;
  clock_s: number;
  mode: GameMode | null;
  local_summoner: string | null;
  local_champion: string | null;
  teams: { order: PlayerLive[]; chaos: PlayerLive[] };
  events: LiveEvent[];
  inference: LiveInference;
  event_deltas: LiveEventDelta[];
}

export type WhatIfStatus =
  | "available"
  | "suppressed"
  | "rejected"
  | "unsupported-patch"
  | "out-of-domain"
  | "error";

export interface WhatIfRequest {
  adjustments: Record<string, number>;
}

export interface WhatIfResponse {
  status: WhatIfStatus;
  probability: number | null;
  baseline_probability: number | null;
  adjusted_features: Record<string, number> | null;
  model_version: string | null;
  pack_version: string | null;
  rejected_fields: string[];
  reason: string | null;
}
