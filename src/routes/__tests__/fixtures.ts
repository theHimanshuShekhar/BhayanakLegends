import type { FindingsPack, LiveStatus } from "../../api/types";

export const idleStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: "LCU not detected on port 2999",
};

export const champSelectActive: LiveStatus = {
  champ_select: { active: true, phase: "locked" },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};

export const ingameActive: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: true, game_id: 4242, mode: "CLASSIC", clock_s: 1254 },
  last_error: null,
};

/**
 * Enemy summoner names have no data path into the UI (LiveStatus carries no
 * roster). This string exists purely to assert nothing resembling it renders.
 */
export const forbiddenEnemyName = "Gankruptcy-DADDY";

export function makePack(overrides: Partial<FindingsPack> = {}): FindingsPack {
  return {
    schema_version: 1,
    generated_at: "2026-08-24T00:00:00Z",
    dataset: { matches: 26036, player_games: 260360, patches: ["14.17", "16.16"] },
    findings: [
      {
        key: "counterpick_spread",
        tier: "diagnostic",
        title: "Counter-picking is the smallest lever in the game",
        statement:
          "Across all mid-lane matchups the total spread between best and worst counters stays near ±2.5pp; counter-picking is the smallest lever in the game.",
        value: 2.5,
        unit: "pp",
        source_ref: "companion-app-content.md#3",
      },
      {
        key: "mastery_premium",
        tier: "actionable",
        title: "The mastery premium dwarfs matchups",
        statement:
          "Games on a pocket pick win 50.6% of the time versus 46.9% on unfamiliar champions.",
        value: 3.7,
        unit: "pp",
        source_ref: "companion-app-content.md#7",
      },
      {
        key: "lanes_ahead",
        tier: "diagnostic",
        title: "Spread beats stacked",
        statement:
          "Teams even across lanes win 16.4% of games from behind, while teams ahead in all five lanes win 83.8% — spread beats stacked.",
        value: null,
        unit: null,
        source_ref: "companion-app-content.md#11",
      },
    ],
    habits: [
      { key: "recall_safety", label: "Recall safely", effect_per_sd: 2.24 },
      { key: "fast_first_dragon", label: "Fast first dragon", effect_per_sd: 1.31 },
      { key: "spend_before_backing", label: "Spend before backing", effect_per_sd: 1.12 },
      { key: "plates_by_14", label: "Plates by 14", effect_per_sd: 0.87 },
    ],
    objectives: {
      baron_pre25_win_rate: 0.814,
      baron_comeback_lift_pp: 29.5,
      dragon_denial_win_rate: 0.954,
      first_dragon_pre20_win_rate: 0.603,
      herald_pre20_win_rate: 0.666,
    },
    comeback_odds: [
      { gold_deficit_at_15: -1000, win_rate: 0.276 },
      { gold_deficit_at_15: -3000, win_rate: 0.152 },
      { gold_deficit_at_15: -5000, win_rate: 0.076 },
    ],
    ban_advisor: [
      { champion: "Lillia", win_rate: 0.548, ban_rate: 0.017, recommendation: "real-threat" },
      { champion: "Skarner", win_rate: 0.531, ban_rate: 0.041, recommendation: "fear-ban" },
    ],
    trap_picks: [
      { champion: "Hecarim", win_rate: 0.415 },
      { champion: "Kalista", win_rate: 0.428 },
      { champion: "Qiyana", win_rate: 0.442 },
    ],
    tier_list: [
      { champion: "Ahri", role: "MIDDLE", games: 340, pick_rate: 0.142, win_rate: 0.534, tier: "S" },
      { champion: "Viktor", role: "MIDDLE", games: 512, pick_rate: 0.201, win_rate: 0.521, tier: "A" },
      { champion: "Sylas", role: "MIDDLE", games: 280, pick_rate: 0.098, win_rate: 0.541, tier: "B" },
      { champion: "Darius", role: "TOP", games: 610, pick_rate: 0.224, win_rate: 0.517, tier: "A" },
    ],
    matchup_examples: [],
    benchmarks: [],
    checkpoints: [
      { gold_diff_bucket: "-2000..-1000 @15m", win_rate: 0.198 },
      { gold_diff_bucket: "-1000..0 @20m", win_rate: 0.282 },
      { gold_diff_bucket: "0..+1000 @25m", win_rate: 0.618 },
    ],
    ...overrides,
  };
}
