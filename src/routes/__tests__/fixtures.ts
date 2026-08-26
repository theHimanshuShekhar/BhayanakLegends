import type {
  ChampSelectSnapshot,
  FindingsPack,
  InGameSnapshot,
  LiveStatus,
} from "../../api/types";

export const idleStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: "LCU not detected on port 2999",
};

export const idleSession: ChampSelectSnapshot = {
  active: false,
  phase: null,
  timer_sec: null,
  bans_ally: [],
  bans_enemy: [],
  ally: [],
  enemy: [],
};

/**
 * Mirrors backend/tests/fixtures/lcu/champselect_session.json through the
 * service layer: enemy summoner names stripped (name always null), champion
 * names resolved from Data Dragon (null → UI falls back to "Champion {id}").
 */
export const champSelectSession: ChampSelectSnapshot = {
  active: true,
  phase: "ChampSelect",
  timer_sec: 23,
  bans_ally: [
    { champion_id: 25, champion: "Miss Fortune" },
    { champion_id: 1, champion: "Annie" },
  ],
  bans_enemy: [{ champion_id: 412, champion: null }],
  ally: [
    { cell_id: 0, champion_id: 22, champion: "Lucian", name: "FixturePlayer01", is_local: false, state: "picked" },
    { cell_id: 1, champion_id: 121, champion: null, name: "FixturePlayer02", is_local: false, state: "intent" },
    { cell_id: 2, champion_id: 498, champion: "Xayah", name: "FixturePlayer03", is_local: true, state: "picked" },
    { cell_id: 3, champion_id: 0, champion: null, name: null, is_local: false, state: "none" },
    { cell_id: 4, champion_id: 34, champion: "Amumu", name: "FixturePlayer05", is_local: false, state: "intent" },
  ],
  enemy: [
    { cell_id: 5, champion_id: 238, champion: "Camille", name: null, state: "picked" },
    { cell_id: 6, champion_id: 999, champion: null, name: null, state: "picked" },
    { cell_id: 7, champion_id: 0, champion: null, name: null, state: "none" },
    { cell_id: 8, champion_id: 0, champion: null, name: null, state: "none" },
    { cell_id: 9, champion_id: 22, champion: "Lucian", name: null, state: "picked" },
  ],
};

export const idleIngame: InGameSnapshot = {
  active: false,
  clock_s: 0,
  mode: null,
  local_summoner: null,
  local_champion: null,
  teams: { order: [], chaos: [] },
  events: [],
};

/** Mirrors backend/tests/fixtures/lcu/allgamedata.json through the service. */
export const ingameSnapshot: InGameSnapshot = {
  active: true,
  clock_s: 1254,
  mode: "CLASSIC",
  local_summoner: "FixturePlayer03",
  local_champion: "Viktor",
  teams: {
    order: [
      { summoner: "FixturePlayer01", champion: "Ornn", level: 11, kills: 2, deaths: 3, assists: 4, cs: 178, ward_score: 0.8, items: [{ id: 3065, count: 1 }, { id: 2003, count: 2 }] },
      { summoner: "FixturePlayer02", champion: "Vi", level: 12, kills: 3, deaths: 2, assists: 6, cs: 141, ward_score: 1.1, items: [{ id: 3053, count: 1 }] },
      { summoner: "FixturePlayer03", champion: "Viktor", level: 12, kills: 4, deaths: 2, assists: 7, cs: 213, ward_score: 1.42, items: [{ id: 3157, count: 1 }, { id: 1056, count: 1 }, { id: 2003, count: 2 }] },
      { summoner: "FixturePlayer04", champion: "Xayah", level: 12, kills: 5, deaths: 1, assists: 3, cs: 236, ward_score: 0.4, items: [{ id: 3046, count: 1 }] },
      { summoner: "FixturePlayer05", champion: "Leona", level: 10, kills: 1, deaths: 4, assists: 12, cs: 32, ward_score: 2.6, items: [{ id: 3190, count: 1 }, { id: 3340, count: 1 }] },
    ],
    chaos: [
      { summoner: "FixturePlayer06", champion: "Camille", level: 12, kills: 3, deaths: 2, assists: 2, cs: 195, ward_score: 0.5, items: [{ id: 3142, count: 1 }] },
      { summoner: "FixturePlayer07", champion: "Lee Sin", level: 11, kills: 2, deaths: 3, assists: 4, cs: 128, ward_score: 0.9, items: [] },
      { summoner: "FixturePlayer08", champion: "Ahri", level: 11, kills: 2, deaths: 4, assists: 3, cs: 187, ward_score: 0.7, items: [{ id: 3089, count: 1 }] },
      { summoner: "FixturePlayer09", champion: "Ashe", level: 11, kills: 1, deaths: 5, assists: 2, cs: 201, ward_score: 0.3, items: [{ id: 3031, count: 1 }, { id: 6672, count: 1 }] },
      { summoner: "FixturePlayer10", champion: "Thresh", level: 10, kills: 0, deaths: 4, assists: 8, cs: 28, ward_score: 2.1, items: [] },
    ],
  },
  events: [
    { name: "GameStart", t_s: 0, actor: null, victim: null, detail: null },
    { name: "MinionsSpawning", t_s: 15.2, actor: null, victim: null, detail: null },
    { name: "FirstBrick", t_s: 310.48, actor: null, victim: null, detail: null },
    { name: "DragonKill", t_s: 612.9, actor: "Order", victim: null, detail: "Infernal" },
    { name: "ChampionKill", t_s: 700.14, actor: "FixturePlayer03", victim: "FixturePlayer09", detail: null },
    { name: "TurretKilled", t_s: 721.4, actor: "Order", victim: null, detail: null },
  ],
};

export const champSelectActive: LiveStatus = {
  champ_select: { active: true, phase: "ChampSelect" },
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
export const forbiddenEnemyName = "FixturePlayer03-BL03";

export function makePack(overrides: Partial<FindingsPack> = {}): FindingsPack {
  return {
    schema_version: 1,
    pack_version: "v1",
    generated_at: "2026-08-24T00:00:00Z",
    comeback_feature_contract: {
      feature: "gold_diff_15",
      feature_contract_version: "loltrends-parity-v1",
    },
    provenance: {} as FindingsPack["provenance"],
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
      { gold_deficit_at_15: -2000, win_rate: 0.42 },
      { gold_deficit_at_15: -5000, win_rate: 0.21 },
      { gold_deficit_at_15: -7000, win_rate: 0.11 },
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
      { gold_diff_bucket: "bottom_quartile_@20m", win_rate: 0.282 },
      { gold_diff_bucket: "top_quartile_@20m", win_rate: 0.718 },
    ],
    ...overrides,
  };
}
