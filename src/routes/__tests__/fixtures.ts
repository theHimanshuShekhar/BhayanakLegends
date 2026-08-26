import type {
  ChampSelectSnapshot,
  FindingsPack,
  InGameSnapshot,
  LiveStatus,
} from "../../api/types";
import shippedFindingsPack from "../../../pack/findings-pack.v1.json";

export const idleStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: "LCU not detected on port 2999",
};

export const idleSession: ChampSelectSnapshot = {
  active: false,
  phase: null,
  timer_sec: null,
  local_assigned_role: null,
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
  local_assigned_role: "TOP",
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
    { cell_id: 2, champion_id: 498, champion: "Xayah", name: "FixturePlayer03", is_local: true, state: "locked" },
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

const shippedPack = shippedFindingsPack as unknown as FindingsPack;

export function makePack(overrides: Partial<FindingsPack> = {}): FindingsPack {
  return {
    ...shippedPack,
    pack_version: "v1",
    ...overrides,
  };
}
