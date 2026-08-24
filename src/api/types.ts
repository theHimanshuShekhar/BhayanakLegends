export type FindingTier = "actionable" | "diagnostic" | "a-lite";

export interface Health {
  status: "ok";
  app_version: string;
  pack_version: string;
}

export interface FindingsPack {
  schema_version: number;
  generated_at: string;
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
  checkpoints: { gold_diff_bucket: string; win_rate: number }[];
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
  role: string;
  games: number;
  pick_rate: number;
  win_rate: number;
  tier: "S" | "A" | "B" | "C";
}

export interface MatchupExample {
  champion: string;
  opponent: string;
  role: string;
  wr: number;
  ci: number;
  games: number;
}

export interface BenchmarkRow {
  role: string;
  cs10_median: number | null;
  level10_median: number | null;
  gold_diff_10_median: number | null;
  feature_contract: {
    cs10_median: string;
    level10_median: string;
    gold_diff_10_median: string;
  };
  sample: number;
}

export interface Settings {
  riot_id: string | null;
  region_route: string;
  has_key: boolean;
  auto_sync: boolean;
}
export interface SettingsPatch {
  riot_id?: string | null;
  region_route?: string;
  riot_key?: string | null;
  auto_sync?: boolean;
}

export interface SyncStatus {
  state: "idle" | "running" | "cancelled" | "error";
  mode: "era_first" | "import";
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
  role: string;
  games: number;
  wins: number;
}

export interface TrajectoryPoint {
  patch: string;
  role: string;
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
  role: string;
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

export interface RoleBenchmark {
  role: string;
  personal: Partial<Record<BenchmarkMetric, number>>;
  population: Partial<Record<`${BenchmarkMetric}_median`, number>> & {
    sample: number;
  };
}

export interface LiveStatus {
  champ_select: { active: boolean; phase: string | null };
  ingame: { active: boolean; game_id: number | null; mode: string | null; clock_s: number };
  last_error: string | null;
}

// Rich LCU-bridge snapshots (GET /live/session + SSE "champselect.state").
// COMPLIANCE: enemy summoner names are stripped at the sidecar service layer —
// ChampSelectEnemyCell.name is always null.
export interface ChampSelectBan {
  champion_id: number;
  name: string | null; // null → UI renders "Champion {id}"
}

export type CellState = "intent" | "picked" | "hover" | "none";

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
  phase: string | null;
  timer_sec: number | null;
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
  name: string;
  t_s: number;
  actor: string | null;
  victim: string | null;
  detail: string | null; // DragonType on DragonKill
}

export interface InGameSnapshot {
  active: boolean;
  clock_s: number;
  mode: string | null;
  local_summoner: string | null;
  local_champion: string | null;
  teams: { order: PlayerLive[]; chaos: PlayerLive[] };
  events: LiveEvent[];
}
