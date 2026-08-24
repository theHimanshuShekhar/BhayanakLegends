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
  gold10_median: number | null;
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
  games: number;
  wins: number;
  rolling_wr: number;
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

export interface RoleBenchmark {
  role: string;
  personal: { cs10: number | null; level10: number | null; gold10: number | null };
  population: {
    cs10_median: number;
    level10_median: number | null;
    gold10_median: number | null;
    sample: number;
  };
}

export interface LiveStatus {
  champ_select: { active: boolean; phase: string | null };
  ingame: { active: boolean; game_id: number | null; mode: string | null; clock_s: number };
  last_error: string | null;
}
