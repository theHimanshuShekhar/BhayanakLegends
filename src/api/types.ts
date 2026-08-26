export type FindingTier = "actionable" | "diagnostic" | "a-lite";
export type RegionRoute = "sea" | "americas" | "europe" | "asia";
export type Role = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY" | "UNKNOWN";
export type AssignedRole = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY";
export type HealthStatus = "ok" | "degraded";
export type SyncState = "idle" | "running" | "cancelled" | "error";
export type SyncMode = "era_first" | "import";
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

export interface TableProvenance {
  source_document: string;
  source_section: string;
  feature_store_manifest_sha256: string;
  generator_revision: string;
  feature_contract_version: "loltrends-parity-v1";
}

export type PackProvenance = Record<
  | "dataset"
  | "findings"
  | "habits"
  | "objectives"
  | "comeback_odds"
  | "ban_advisor"
  | "trap_picks"
  | "tier_list"
  | "matchup_examples"
  | "benchmarks"
  | "checkpoints",
  TableProvenance
>;

export interface ComebackFeatureContract {
  feature: "gold_diff_15";
  feature_contract_version: "loltrends-parity-v1";
}

export interface FindingsPack {
  schema_version: number;
  pack_version: string;
  generated_at: string;
  comeback_feature_contract: ComebackFeatureContract;
  provenance: PackProvenance;
  dataset: { matches: number; player_games: number; patches: string[] };
  findings: PackFinding[];
  habits: HabitDef[];
  objectives: Record<string, number>;
  comeback_odds: { gold_deficit_at_15: number; win_rate: number }[];
  ban_advisor: BanAdvice[];
  trap_picks: { champion: string; win_rate: number }[];
  tier_list: TierEntry[];
  matchup_examples: MatchupExample[];
  benchmarks: BenchmarkRow[];
  checkpoints: {
    gold_diff_bucket: "bottom_quartile_@20m" | "top_quartile_@20m";
    win_rate: number;
  }[];
}

export interface PackFinding {
  key: string;
  tier: FindingTier;
  title: string;
  statement: string;
  value: number | null;
  unit: string | null;
  source_ref: string;
}

export interface HabitDef {
  key: string;
  label: string;
  /**
   * Normative unit: multiplier effect on the outcome for one standard-deviation
   * change of the underlying feature (per backend/tools/build_pack.py). Render
   * exactly as `×{value} effect per SD` — never as %, WR, or pp.
   */
  effect_per_sd: number;
}

export interface BanAdvice {
  champion: string;
  win_rate: number;
  ban_rate: number;
  recommendation: "real-threat" | "fear-ban" | "skip";
}

export interface TierEntry {
  champion: string;
  role: Role;
  games: number;
  pick_rate: number;
  win_rate: number;
  tier: "S" | "A" | "B" | "C";
}

export interface MatchupExample {
  champion: string;
  opponent: string;
  role: Role;
  wr: number;
  ci: number;
  games: number;
}

export interface BenchmarkRow {
  role: Role;
  cs10_median?: number;
  level10_median?: number;
  gold_diff_10_median?: number;
  feature_contract: {
    cs10_median?: string;
    level10_median?: string;
    gold_diff_10_median?: string;
  };
  sample: number;
}

export interface Settings {
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

export interface SyncStatus {
  state: SyncState;
  mode: SyncMode;
  total_queued: number;
  downloaded: number;
  skipped: number;
  failed: number;
  current_match_id: string | null;
  started_at: string | null;
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

export interface InGameSnapshot {
  active: boolean;
  clock_s: number;
  mode: GameMode | null;
  local_summoner: string | null;
  local_champion: string | null;
  teams: { order: PlayerLive[]; chaos: PlayerLive[] };
  events: LiveEvent[];
}
