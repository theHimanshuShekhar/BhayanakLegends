import type {
  AssignedRole,
  ChampSelectAllyCell,
  ChampSelectBan,
  ChampSelectEnemyCell,
  ChampSelectSnapshot,
  CellState,
  GameflowPhase,
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
