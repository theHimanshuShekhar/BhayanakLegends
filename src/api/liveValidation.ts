import type {
  AssignedRole,
  ChampSelectAllyCell,
  ChampSelectEnemyCell,
  ChampSelectBan,
  ChampSelectSnapshot,
  CellState,
  GameflowPhase,
  GameMode,
  InGameSnapshot,
  LiveEventName,
  LiveInferenceStatus,
  PlayerLive,
} from "./types";

export const PHASES: readonly GameflowPhase[] = [
  "None",
  "Lobby",
  "Matchmaking",
  "RankedGame",
  "ChampSelect",
  "GameStart",
  "InProgress",
  "WaitingForStats",
  "EndOfGame",
];
const ASSIGNED_ROLES: readonly AssignedRole[] = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];
const CELL_STATES: readonly CellState[] = ["intent", "picked", "hover", "locked", "none"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isEnum<T extends string>(values: readonly T[], value: unknown): value is T {
  return typeof value === "string" && values.some((candidate) => candidate === value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return (
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

function isBan(value: unknown): value is ChampSelectBan {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["champion_id", "champion"]) &&
    Number.isInteger(value.champion_id) &&
    isNullableString(value.champion)
  );
}

function isAlly(value: unknown): value is ChampSelectAllyCell {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["cell_id", "champion_id", "champion", "name", "is_local", "state"]) &&
    Number.isInteger(value.cell_id) &&
    Number.isInteger(value.champion_id) &&
    isNullableString(value.champion) &&
    isNullableString(value.name) &&
    typeof value.is_local === "boolean" &&
    isEnum(CELL_STATES, value.state)
  );
}

function isEnemy(value: unknown): value is ChampSelectEnemyCell {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["cell_id", "champion_id", "champion", "name", "state"]) &&
    Number.isInteger(value.cell_id) &&
    Number.isInteger(value.champion_id) &&
    isNullableString(value.champion) &&
    value.name === null &&
    isEnum(CELL_STATES, value.state)
  );
}

/** Validates the strict wire shape shared by REST and champselect.state SSE. */
export function isChampSelectSnapshot(value: unknown): value is ChampSelectSnapshot {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "active",
      "phase",
      "timer_sec",
      "local_assigned_role",
      "bans_ally",
      "bans_enemy",
      "ally",
      "enemy",
    ]) &&
    (value.local_assigned_role === null || isEnum(ASSIGNED_ROLES, value.local_assigned_role)) &&
    typeof value.active === "boolean" &&
    (value.phase === null || isEnum(PHASES, value.phase)) &&
    (value.timer_sec === null || isFiniteNumber(value.timer_sec)) &&
    Array.isArray(value.bans_ally) &&
    value.bans_ally.every(isBan) &&
    Array.isArray(value.bans_enemy) &&
    value.bans_enemy.every(isBan) &&
    Array.isArray(value.ally) &&
    value.ally.every(isAlly) &&
    Array.isArray(value.enemy) &&
    value.enemy.every(isEnemy)
  );
}
const LIVE_MODES: readonly GameMode[] = [
  "CLASSIC",
  "ODIN",
  "ARAM",
  "TUTORIAL",
  "URF",
  "ONEFORALL",
  "DOOM_BOTS",
  "ASCENSION",
  "FIRSTBLOOD",
  "KING_PORO",
  "SIEGE",
  "PROJECT",
  "SNOWDOWN",
  "NEXUSBLITZ",
  "ULTBOOK",
  "CHERRY",
];
const LIVE_EVENT_NAMES: readonly LiveEventName[] = [
  "GameStart",
  "MinionsSpawning",
  "FirstBrick",
  "DragonKill",
  "HeraldKill",
  "BaronKill",
  "ChampionKill",
  "TurretKilled",
  "InhibKilled",
  "GameEnd",
];
const LIVE_INFERENCE_STATUSES: readonly LiveInferenceStatus[] = [
  "available",
  "suppressed",
  "stale",
  "incompatible",
  "unsupported-patch",
  "out-of-domain",
  "error",
];

function isNullableProbability(value: unknown): value is number | null {
  return value === null || (isFiniteNumber(value) && value >= 0 && value <= 1);
}

function isLivePlayer(value: unknown): value is PlayerLive {
  if (!isRecord(value) || !hasExactKeys(value, ["summoner", "champion", "level", "kills", "deaths", "assists", "cs", "ward_score", "items"])) {
    return false;
  }
  return (
    typeof value.summoner === "string" &&
    isNullableString(value.champion) &&
    ["level", "kills", "deaths", "assists", "cs", "ward_score"].every((key) => isFiniteNumber(value[key])) &&
    Array.isArray(value.items) &&
    value.items.every(
      (item) =>
        isRecord(item) &&
        hasExactKeys(item, ["id", "count"]) &&
        Number.isInteger(item.id) &&
        Number.isInteger(item.count),
    )
  );
}

function isLiveEvent(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["name", "t_s", "actor", "victim", "detail"]) &&
    isEnum(LIVE_EVENT_NAMES, value.name) &&
    isFiniteNumber(value.t_s) &&
    isNullableString(value.actor) &&
    isNullableString(value.victim) &&
    isNullableString(value.detail)
  );
}

function isLiveInference(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["status", "probability", "observed_game_time_s", "model_version", "pack_version", "reason"]) &&
    isEnum(LIVE_INFERENCE_STATUSES, value.status) &&
    isNullableProbability(value.probability) &&
    (value.observed_game_time_s === null ||
      (isFiniteNumber(value.observed_game_time_s) && value.observed_game_time_s >= 0)) &&
    isNullableString(value.model_version) &&
    isNullableString(value.pack_version) &&
    isNullableString(value.reason)
  );
}

function isLiveEventDelta(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasExactKeys(value, [
      "event_id",
      "name",
      "t_s",
      "baseline_probability",
      "event_probability",
      "delta_probability",
      "status",
      "reason",
    ]) &&
    typeof value.event_id === "string" &&
    isEnum(LIVE_EVENT_NAMES, value.name) &&
    isFiniteNumber(value.t_s) &&
    isNullableProbability(value.baseline_probability) &&
    isNullableProbability(value.event_probability) &&
    (value.delta_probability === null ||
      (isFiniteNumber(value.delta_probability) && value.delta_probability >= -1 && value.delta_probability <= 1)) &&
    isEnum(LIVE_INFERENCE_STATUSES, value.status) &&
    isNullableString(value.reason)
  );
}

/** Validates the strict wire shape shared by REST and live.state SSE. */
export function isInGameSnapshot(value: unknown): value is InGameSnapshot {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "active",
      "clock_s",
      "mode",
      "local_summoner",
      "local_champion",
      "teams",
      "events",
      "inference",
      "event_deltas",
    ]) ||
    !isRecord(value.teams) ||
    !hasExactKeys(value.teams, ["order", "chaos"])
  ) {
    return false;
  }
  return (
    typeof value.active === "boolean" &&
    isFiniteNumber(value.clock_s) &&
    (value.mode === null || isEnum(LIVE_MODES, value.mode)) &&
    isNullableString(value.local_summoner) &&
    isNullableString(value.local_champion) &&
    Array.isArray(value.teams.order) &&
    value.teams.order.every(isLivePlayer) &&
    Array.isArray(value.teams.chaos) &&
    value.teams.chaos.every(isLivePlayer) &&
    Array.isArray(value.events) &&
    value.events.every(isLiveEvent) &&
    isLiveInference(value.inference) &&
    Array.isArray(value.event_deltas) &&
    value.event_deltas.every(isLiveEventDelta)
  );
}
