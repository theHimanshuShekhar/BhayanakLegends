/** Historical Findings Pack v1 response shape.
 *
 * This type intentionally keeps v1 comeback anchors and checkpoint names. The
 * v2-only consumers narrow on schema_version instead of translating them.
 */

export type RoleV1 = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY" | "UNKNOWN";

export interface FindingsPackV1Dataset {
  matches: number;
  player_games: number;
  patches: string[];
}
export interface FindingsPackV1Benchmark {
  role: RoleV1;
  cs10_median?: number;
  level10_median?: number;
  gold_diff_10_median?: number;
  feature_contract: {
    cs10_median?: "cs10" | "lane_minions_first_10m";
    level10_median?: "level10";
    gold_diff_10_median?: "gold_diff_10";
  };
  sample: number;
}

export interface FindingsPackV1 {
  schema_version: 1;
  pack_version: string;
  generated_at: string;
  comeback_feature_contract: {
    feature: string;
    feature_contract_version: string;
  };
  provenance: Record<string, {
    source_document: string;
    source_section: string;
    feature_store_manifest_sha256: string;
    generator_revision: string;
    feature_contract_version: "loltrends-parity-v1";
  }>;
  dataset: FindingsPackV1Dataset;
  findings: Array<{
    key: string;
    tier: "actionable" | "diagnostic" | "a-lite";
    title: string;
    statement: string;
    value?: number | null;
    unit?: string | null;
    source_ref: string;
  }>;
  habits: Array<{ key: string; label: string; effect_per_sd: number }>;
  objectives: Record<string, number>;
  comeback_odds: Array<{ gold_deficit_at_15: number; win_rate: number }>;
  ban_advisor: Array<{
    champion: string;
    win_rate: number;
    ban_rate: number;
    recommendation: "real-threat" | "fear-ban" | "skip";
  }>;
  trap_picks: Array<{ champion: string; win_rate: number }>;
  tier_list: Array<{
    champion: string;
    role: RoleV1;
    games: number;
    pick_rate: number;
    win_rate: number;
    tier: "S" | "A" | "B" | "C";
  }>;
  matchup_examples: Array<{
    champion: string;
    opponent: string;
    role: RoleV1;
    wr: number;
    ci: number;
    games: number;
  }>;
  benchmarks: FindingsPackV1Benchmark[];
  checkpoints: Array<{
    gold_diff_bucket: "bottom_quartile_@20m" | "top_quartile_@20m";
    win_rate: number;
  }>;
}

export function isFindingsPackV1(value: unknown): value is FindingsPackV1 {
  if (typeof value !== "object" || value === null || !("schema_version" in value)) {
    return false;
  }
  return value.schema_version === 1;
}
