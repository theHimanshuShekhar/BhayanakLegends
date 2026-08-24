import { useEffect, useRef, useSyncExternalStore } from "react";
import { eventsUrl } from "./client";
import type {
  ChampSelectSnapshot,
  GameMode,
  GameflowPhase,
  InGameSnapshot,
  LiveEvent,
  LiveEventName,
  LiveStatus,
  PlayerLive,
  SyncStatus,
} from "./types";

export type SseMessage =
  | { type: "sync.progress"; ts: string; data: SyncStatus }
  | { type: "sync.done"; ts: string; data: SyncStatus }
  | { type: "champselect.state"; ts: string; data: ChampSelectSnapshot }
  | { type: "live.state"; ts: string; data: InGameSnapshot }
  | { type: "live.status"; ts: string; data: LiveStatus }
  | { type: "pack.updated"; ts: string; data: { schema_version: number } }
  | { type: "hello"; ts: string; data: { app_version: string; pack_version: string | null } };

const GAME_MODES: readonly GameMode[] = [
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
const PHASES: readonly GameflowPhase[] = [
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
const CELL_STATES = ["intent", "picked", "hover", "none"] as const;
const SYNC_STATES = ["idle", "running", "cancelled", "error"] as const;
const SYNC_MODES = ["era_first", "import"] as const;

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

function isSyncStatus(value: unknown): value is SyncStatus {
  if (!isRecord(value)) return false;
  return (
    isEnum(SYNC_STATES, value.state) &&
    isEnum(SYNC_MODES, value.mode) &&
    isFiniteNumber(value.total_queued) &&
    isFiniteNumber(value.downloaded) &&
    isFiniteNumber(value.skipped) &&
    isFiniteNumber(value.failed) &&
    isNullableString(value.current_match_id) &&
    isNullableString(value.started_at)
  );
}

function isLiveStatus(value: unknown): value is LiveStatus {
  if (!isRecord(value) || !isRecord(value.champ_select) || !isRecord(value.ingame)) return false;
  const champSelect = value.champ_select;
  const ingame = value.ingame;
  return (
    typeof champSelect.active === "boolean" &&
    (champSelect.phase === null || isEnum(PHASES, champSelect.phase)) &&
    typeof ingame.active === "boolean" &&
    (ingame.game_id === null || isFiniteNumber(ingame.game_id)) &&
    (ingame.mode === null || isEnum(GAME_MODES, ingame.mode)) &&
    isFiniteNumber(ingame.clock_s) &&
    isNullableString(value.last_error)
  );
}

function isChampSelectSnapshot(value: unknown): value is ChampSelectSnapshot {
  if (!isRecord(value) || !Array.isArray(value.bans_ally) || !Array.isArray(value.bans_enemy)) return false;
  if (!Array.isArray(value.ally) || !Array.isArray(value.enemy)) return false;
  const isBan = (ban: unknown): boolean =>
    isRecord(ban) && Number.isInteger(ban.champion_id) && isNullableString(ban.name);
  const isAlly = (cell: unknown): boolean =>
    isRecord(cell) &&
    Number.isInteger(cell.cell_id) &&
    Number.isInteger(cell.champion_id) &&
    isNullableString(cell.champion) &&
    isNullableString(cell.name) &&
    typeof cell.is_local === "boolean" &&
    isEnum(CELL_STATES, cell.state);
  const isEnemy = (cell: unknown): boolean =>
    isRecord(cell) &&
    Number.isInteger(cell.cell_id) &&
    Number.isInteger(cell.champion_id) &&
    isNullableString(cell.champion) &&
    cell.name === null &&
    isEnum(CELL_STATES, cell.state);
  return (
    typeof value.active === "boolean" &&
    (value.phase === null || isEnum(PHASES, value.phase)) &&
    (value.timer_sec === null || isFiniteNumber(value.timer_sec)) &&
    value.bans_ally.every(isBan) &&
    value.bans_enemy.every(isBan) &&
    value.ally.every(isAlly) &&
    value.enemy.every(isEnemy)
  );
}

function isPlayerLive(value: unknown): value is PlayerLive {
  if (!isRecord(value) || typeof value.summoner !== "string" || !isNullableString(value.champion)) return false;
  if (!isFiniteNumber(value.level) || !isFiniteNumber(value.kills) || !isFiniteNumber(value.deaths)) return false;
  if (!isFiniteNumber(value.assists) || !isFiniteNumber(value.cs) || !isFiniteNumber(value.ward_score)) return false;
  if (!Array.isArray(value.items)) return false;
  return value.items.every(
    (item) => isRecord(item) && Number.isInteger(item.id) && Number.isInteger(item.count),
  );
}

function isLiveEvent(value: unknown): value is LiveEvent {
  return (
    isRecord(value) &&
    isEnum(LIVE_EVENT_NAMES, value.name) &&
    isFiniteNumber(value.t_s) &&
    isNullableString(value.actor) &&
    isNullableString(value.victim) &&
    isNullableString(value.detail)
  );
}

function isInGameSnapshot(value: unknown): value is InGameSnapshot {
  if (!isRecord(value) || !isRecord(value.teams)) return false;
  return (
    typeof value.active === "boolean" &&
    isFiniteNumber(value.clock_s) &&
    (value.mode === null || isEnum(GAME_MODES, value.mode)) &&
    isNullableString(value.local_summoner) &&
    isNullableString(value.local_champion) &&
    Array.isArray(value.teams.order) &&
    value.teams.order.every(isPlayerLive) &&
    Array.isArray(value.teams.chaos) &&
    value.teams.chaos.every(isPlayerLive) &&
    Array.isArray(value.events) &&
    value.events.every(isLiveEvent)
  );
}

/** Parses and validates one JSON-decoded SSE envelope. Invalid frames are dropped. */
export function parseSseMessage(value: unknown): SseMessage | null {
  if (!isRecord(value) || typeof value.type !== "string" || typeof value.ts !== "string") return null;
  const { type, ts, data } = value;
  switch (type) {
    case "sync.progress":
      return isSyncStatus(data) ? { type, ts, data } : null;
    case "sync.done":
      return isSyncStatus(data) ? { type, ts, data } : null;
    case "champselect.state":
      return isChampSelectSnapshot(data) ? { type, ts, data } : null;
    case "live.state":
      return isInGameSnapshot(data) ? { type, ts, data } : null;
    case "live.status":
      return isLiveStatus(data) ? { type, ts, data } : null;
    case "pack.updated":
      return isRecord(data) && isFiniteNumber(data.schema_version)
        ? { type, ts, data: { schema_version: data.schema_version } }
        : null;
    case "hello":
      return isRecord(data) &&
        typeof data.app_version === "string" &&
        isNullableString(data.pack_version)
        ? { type, ts, data: { app_version: data.app_version, pack_version: data.pack_version } }
        : null;
    default:
      return null;
  }
}

type EventListener = (message: SseMessage) => void;
type StatusListener = () => void;

const eventListeners = new Set<EventListener>();
const statusListeners = new Set<StatusListener>();
let source: EventSource | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let resolvingUrl = false;
let connected = false;
let generation = 0;

function hasSubscribers() {
  return eventListeners.size > 0 || statusListeners.size > 0;
}

function notifyStatus() {
  for (const listener of statusListeners) listener();
}

function stopConnection() {
  generation += 1;
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  resolvingUrl = false;
  connected = false;
  source?.close();
  source = null;
}

function scheduleReconnect() {
  if (!hasSubscribers() || reconnectTimer !== null) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 2_000);
}

function connect() {
  if (!hasSubscribers() || source !== null || resolvingUrl || reconnectTimer !== null) return;
  resolvingUrl = true;
  const attempt = ++generation;
  void eventsUrl()
    .then((url) => {
      resolvingUrl = false;
      if (attempt !== generation || !hasSubscribers()) return;
      try {
        const next = new EventSource(url);
        source = next;
        next.onopen = () => {
          if (source !== next) return;
          connected = true;
          notifyStatus();
        };
        next.onmessage = (event) => {
          if (source !== next) return;
          try {
            const raw: unknown = JSON.parse(event.data);
            const message = parseSseMessage(raw);
            if (!message) return;
            for (const listener of eventListeners) listener(message);
          } catch {
            // Malformed JSON is not a contracted event and is ignored.
          }
        };
        next.onerror = () => {
          if (source !== next) return;
          source = null;
          next.close();
          connected = false;
          notifyStatus();
          scheduleReconnect();
        };
      } catch {
        if (attempt !== generation) return;
        connected = false;
        notifyStatus();
        scheduleReconnect();
      }
    })
    .catch(() => {
      resolvingUrl = false;
      if (attempt !== generation || !hasSubscribers()) return;
      connected = false;
      notifyStatus();
      scheduleReconnect();
    });
}

function subscribeStatus(listener: StatusListener) {
  statusListeners.add(listener);
  connect();
  return () => {
    statusListeners.delete(listener);
    if (!hasSubscribers()) stopConnection();
  };
}

function subscribeEvents(listener: EventListener) {
  eventListeners.add(listener);
  connect();
  return () => {
    eventListeners.delete(listener);
    if (!hasSubscribers()) stopConnection();
  };
}

function getConnected() {
  return connected;
}

/** Subscribes to the app-wide event stream; all callers share one EventSource. */
export function useEvents(onMessage?: EventListener) {
  const connectedNow = useSyncExternalStore(subscribeStatus, getConnected, () => false);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  useEffect(() => {
    if (!onMessage) return;
    return subscribeEvents((message) => handlerRef.current?.(message));
  }, []);

  return connectedNow;
}

/** Exposed for query hooks that consume typed events without opening another connection. */
export function subscribeToEvents(listener: EventListener) {
  return subscribeEvents(listener);
}

