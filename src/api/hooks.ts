import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { useEvents } from "./sse";
import type { SseMessage } from "./sse";
import type {
  HistoryInsights,
  LiveStatus,
  PatchAggregate,
  Settings,
  SettingsPatch,
  SyncStatus,
} from "./types";

interface LiveStatusArbiter {
  champSelectRevision: number;
  inGameRevision: number;
  champSelectActive?: boolean;
  champSelectPhase?: LiveStatus["champ_select"]["phase"];
  inGameActive?: boolean;
  latest?: LiveStatus;
  hasConnected: boolean;
  wasConnected: boolean;
}

interface SettingsArbiter {
  generation: number;
  ownerKey?: string | null;
  ownerState?: string;
  latest?: Settings;
}

interface SyncRequestToken {
  ownerKey: string | null;
  ownerGeneration: number;
  ownerEpoch: number;
  serial: number;
  observerId: number | null;
}

interface SyncStatusArbiter {
  serial: number;
  latestSerial: number;
  ownerKey: string | null;
  ownerGeneration: number;
  ownerEpoch: number;
  nextObserverId: number;
  observers: Set<number>;
  latest?: SyncStatus;
}

const IDLE_LIVE_STATUS: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};
const liveStatusArbiters = new WeakMap<object, LiveStatusArbiter>();
const settingsArbiters = new WeakMap<object, SettingsArbiter>();
const syncStatusArbiters = new WeakMap<object, SyncStatusArbiter>();

function liveStatusArbiterFor(queryClient: QueryClient): LiveStatusArbiter {
  const existing = liveStatusArbiters.get(queryClient);
  if (existing) return existing;
  const created: LiveStatusArbiter = {
    champSelectRevision: 0,
    inGameRevision: 0,
    hasConnected: false,
    wasConnected: false,
  };
  liveStatusArbiters.set(queryClient, created);
  return created;
}

function settingsArbiterFor(queryClient: QueryClient): SettingsArbiter {
  const existing = settingsArbiters.get(queryClient);
  if (existing) return existing;
  const created: SettingsArbiter = { generation: 0 };
  settingsArbiters.set(queryClient, created);
  return created;
}

function syncStatusArbiterFor(queryClient: QueryClient): SyncStatusArbiter {
  const existing = syncStatusArbiters.get(queryClient);
  if (existing) return existing;
  const created: SyncStatusArbiter = {
    serial: 0,
    latestSerial: 0,
    ownerKey: null,
    ownerGeneration: 0,
    ownerEpoch: 0,
    nextObserverId: 1,
    observers: new Set(),
  };
  syncStatusArbiters.set(queryClient, created);
  return created;
}

function ownerKey(settings: Settings | undefined): string | null {
  return settings?.owner_key ?? null;
}

function ownerGeneration(settings: Settings | undefined): number {
  return settings?.generation ?? 0;
}

function ownerIsActive(settings: Settings | undefined): boolean {
  return settings?.owner_state === "active";
}

function ownerQueryKey(
  name: string,
  settings: Settings | undefined,
): readonly [string, string | null, number] {
  return [name, ownerKey(settings), ownerGeneration(settings)];
}

function ensureSyncOwner(
  arbiter: SyncStatusArbiter,
  nextOwnerKey: string | null,
  nextGeneration: number,
): void {
  if (
    arbiter.ownerKey === nextOwnerKey &&
    arbiter.ownerGeneration === nextGeneration
  ) {
    return;
  }
  arbiter.ownerKey = nextOwnerKey;
  arbiter.ownerGeneration = nextGeneration;
  arbiter.ownerEpoch += 1;
  arbiter.latest = undefined;
  arbiter.latestSerial = arbiter.serial;
}

function useSyncObserver(arbiter: SyncStatusArbiter): number {
  const idRef = useRef<number | null>(null);
  if (idRef.current == null) idRef.current = arbiter.nextObserverId++;
  const id = idRef.current;
  arbiter.observers.add(id);
  useEffect(
    () => () => {
      arbiter.observers.delete(id);
      if (arbiter.observers.size === 0) {
        arbiter.ownerEpoch += 1;
        arbiter.latest = undefined;
        arbiter.latestSerial = arbiter.serial;
      }
    },
    [arbiter, id],
  );
  return id;
}

function beginSyncRequest(
  arbiter: SyncStatusArbiter,
  ownerKeyValue: string | null,
  generation: number,
  observerId: number | null,
  expectedOwnerEpoch = arbiter.ownerEpoch,
): SyncRequestToken {
  return {
    ownerKey: ownerKeyValue,
    ownerGeneration: generation,
    ownerEpoch: expectedOwnerEpoch,
    serial: ++arbiter.serial,
    observerId,
  };
}

function applyLiveStatusEvent(
  queryClient: QueryClient,
  arbiter: LiveStatusArbiter,
  message: SseMessage,
) {
  if (message.type === "live.status") {
    arbiter.champSelectRevision += 1;
    arbiter.inGameRevision += 1;
    arbiter.champSelectActive = message.data.champ_select.active;
    arbiter.champSelectPhase = message.data.champ_select.phase;
    arbiter.inGameActive = message.data.ingame.active;
    arbiter.latest = message.data;
    queryClient.setQueryData(["live-status"], message.data);
    return;
  }
  if (message.type === "champselect.state") {
    arbiter.champSelectRevision += 1;
    arbiter.champSelectActive = message.data.active;
    arbiter.champSelectPhase = message.data.phase;
    arbiter.latest = {
      ...(arbiter.latest ?? IDLE_LIVE_STATUS),
      champ_select: {
        ...(arbiter.latest?.champ_select ?? IDLE_LIVE_STATUS.champ_select),
        active: message.data.active,
        phase: message.data.phase,
      },
    };
    queryClient.setQueryData(["live-status"], arbiter.latest);
    return;
  }
  if (message.type === "live.state") {
    arbiter.inGameRevision += 1;
    arbiter.inGameActive = message.data.active;
    arbiter.latest = {
      ...(arbiter.latest ?? IDLE_LIVE_STATUS),
      ingame: {
        ...(arbiter.latest?.ingame ?? IDLE_LIVE_STATUS.ingame),
        active: message.data.active,
      },
    };
    queryClient.setQueryData(["live-status"], arbiter.latest);
  }
}

function sameSyncOwner(
  status: SyncStatus,
  owner_key: string | null,
  generation: number,
): boolean {
  return status.owner_key === owner_key && status.generation === generation;
}

function acceptSyncObservation(
  queryClient: QueryClient,
  arbiter: SyncStatusArbiter,
  status: SyncStatus,
  token: SyncRequestToken,
): SyncStatus {
  const ownerIsCurrent =
    token.ownerEpoch === arbiter.ownerEpoch &&
    token.ownerKey === arbiter.ownerKey &&
    token.ownerGeneration === arbiter.ownerGeneration;
  const observerIsCurrent =
    token.observerId === null || arbiter.observers.has(token.observerId);
  if (!ownerIsCurrent || !observerIsCurrent || !sameSyncOwner(status, token.ownerKey, token.ownerGeneration)) {
    return arbiter.latest ?? status;
  }
  if (token.serial < arbiter.latestSerial) return arbiter.latest ?? status;
  arbiter.latestSerial = token.serial;
  arbiter.latest = status;
  queryClient.setQueryData(
    ["sync-status", token.ownerKey, token.ownerGeneration],
    status,
  );
  return status;
}

function removeOwnerQueries(queryClient: QueryClient): void {
  const prefixes: Record<string, true> = {
    "history-summary": true,
    "history-insights": true,
    trajectories: true,
    "patch-aggregates": true,
    "postgame-latest": true,
    benchmarks: true,
    "sync-status": true,
  };
  queryClient.removeQueries({
    predicate: (query) =>
      typeof query.queryKey[0] === "string" &&
      prefixes[query.queryKey[0]] === true,
  });
  const arbiter = syncStatusArbiters.get(queryClient);
  if (arbiter) {
    arbiter.latest = undefined;
    arbiter.latestSerial = arbiter.serial;
    arbiter.ownerEpoch += 1;
  }
}

function settingsResponseIsStale(
  next: Settings,
  arbiter: SettingsArbiter,
): boolean {
  const nextGeneration = next.generation ?? 0;
  if (nextGeneration < arbiter.generation) return true;
  const current = arbiter.latest;
  if (!current || nextGeneration > (current.generation ?? 0)) return false;
  const rank: Record<string, number> = {
    unassigned: 0,
    resolving: 1,
    error: 1,
    active: 2,
  };
  const currentRank = rank[current.owner_state ?? "unassigned"] ?? 0;
  const nextRank = rank[next.owner_state ?? "unassigned"] ?? 0;
  if (nextRank < currentRank) return true;
  return Boolean(
    current.owner_key &&
      next.owner_key !== undefined &&
      next.owner_key !== current.owner_key,
  );
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health });
}

export function usePack() {
  const qc = useQueryClient();
  useEvents((message) => {
    if (message.type === "pack.updated") void qc.invalidateQueries({ queryKey: ["pack"] });
  });
  return useQuery({ queryKey: ["pack"], queryFn: api.pack });
}

export function useSettings() {
  const qc = useQueryClient();
  const arbiter = settingsArbiterFor(qc);
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const next = await api.settings();
      if (settingsResponseIsStale(next, arbiter) && arbiter.latest) {
        return arbiter.latest;
      }
      const generation = next.generation ?? 0;
      arbiter.generation = Math.max(arbiter.generation, generation);
      arbiter.ownerKey = next.owner_key ?? null;
      arbiter.ownerState = next.owner_state;
      arbiter.latest = next;
      return next;
    },
  });
}

export function useOwnerContext() {
  const settings = useSettings();
  return {
    ...settings,
    ownerKey: ownerKey(settings.data),
    generation: ownerGeneration(settings.data),
    active: ownerIsActive(settings.data),
  };
}

export function useHistorySummary() {
  const owner = useOwnerContext();
  return useQuery({
    queryKey: ownerQueryKey("history-summary", owner.data),
    queryFn: api.historySummary,
    enabled: owner.active,
  });
}

export interface TrajectoryFilters {
  patch?: string;
  role?: string;
  champion?: string;
}

export interface TrajectoryQueryOptions {
  enabled?: boolean;
}
function cleanParams(filters: TrajectoryFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && v !== "") out[k] = v;
  }
  return out;
}

export function useTrajectories(
  filters: TrajectoryFilters = {},
  options: TrajectoryQueryOptions = {},
) {
  const owner = useOwnerContext();
  const params = cleanParams(filters);
  const enabled =
    owner.active &&
    (options.enabled ??
      ((filters.role == null && filters.champion == null) ||
        Boolean(params.role && params.champion)));
  return useQuery({
    queryKey: [...ownerQueryKey("trajectories", owner.data), params],
    queryFn: () => api.trajectories(params),
    enabled,
  });
}

export function usePatchAggregates(
  filters: TrajectoryFilters = {},
  options: TrajectoryQueryOptions = {},
) {
  const owner = useOwnerContext();
  const params = cleanParams(filters);
  const enabled =
    owner.active &&
    (options.enabled ??
      ((filters.role == null && filters.champion == null) ||
        Boolean(params.role && params.champion)));
  return useQuery<PatchAggregate[]>({
    queryKey: [...ownerQueryKey("patch-aggregates", owner.data), params],
    queryFn: () => api.patchAggregates(params),
    enabled,
  });
}

export function useHistoryInsights(filters: { role?: string; champion?: string } = {}) {
  const owner = useOwnerContext();
  const params = cleanParams(filters);
  return useQuery<HistoryInsights>({
    queryKey: [...ownerQueryKey("history-insights", owner.data), params],
    queryFn: () => api.historyInsights(params),
    enabled: owner.active,
  });
}

export function usePostgameLatest() {
  const owner = useOwnerContext();
  return useQuery({
    queryKey: ownerQueryKey("postgame-latest", owner.data),
    queryFn: api.postgameLatest,
    enabled: owner.active,
  });
}

export function useBenchmarks() {
  const owner = useOwnerContext();
  return useQuery({
    queryKey: ownerQueryKey("benchmarks", owner.data),
    queryFn: api.benchmarks,
    enabled: owner.active,
  });
}

export function useWhatIf() {
  const owner = useOwnerContext();
  const mutation = useMutation({
    mutationKey: ["history-what-if", owner.ownerKey, owner.generation],
    mutationFn: (adjustments: Record<string, number>) => api.whatIf(adjustments),
  });
  const ownerRef = useRef<{ key: string | null; generation: number } | null>(null);
  const currentOwner = { key: owner.ownerKey, generation: owner.generation };
  const isCurrent =
    ownerRef.current?.key === currentOwner.key &&
    ownerRef.current.generation === currentOwner.generation;
  const data = isCurrent ? mutation.data : undefined;
  const mutate = (adjustments: Record<string, number>) => {
    ownerRef.current = currentOwner;
    mutation.mutate(adjustments);
  };
  return {
    ...mutation,
    data,
    error: isCurrent ? mutation.error : null,
    isPending: isCurrent && mutation.isPending,
    isSuccess: isCurrent && mutation.isSuccess,
    isError: isCurrent && mutation.isError,
    mutate,
  };
}

export function useSaveSettings() {
  const qc = useQueryClient();
  const arbiter = settingsArbiterFor(qc);
  return useMutation({
    mutationFn: (patch: SettingsPatch) => api.updateSettings(patch),
    onSuccess: (saved) => {
      const generation = saved.generation ?? 0;
      if (generation < arbiter.generation && arbiter.latest) return;
      arbiter.generation = Math.max(arbiter.generation, generation);
      arbiter.ownerKey = saved.owner_key ?? null;
      arbiter.ownerState = saved.owner_state;
      arbiter.latest = saved;
      qc.setQueryData(["settings"], saved);
      removeOwnerQueries(qc);
    },
  });
}
export function useStartSync() {
  const qc = useQueryClient();
  const owner = useOwnerContext();
  const arbiter = syncStatusArbiterFor(qc);
  ensureSyncOwner(arbiter, owner.ownerKey, owner.generation);
  const observerId = useSyncObserver(arbiter);
  const ownerEpochAtRender = arbiter.ownerEpoch;
  return useMutation({
    mutationFn: async () => {
      const token = beginSyncRequest(
        arbiter,
        owner.ownerKey,
        owner.generation,
        observerId,
        ownerEpochAtRender,
      );
      const status = await api.startSync();
      return acceptSyncObservation(qc, arbiter, status, token);
    },
  });
}

export function useCancelSync() {
  const qc = useQueryClient();
  const owner = useOwnerContext();
  const arbiter = syncStatusArbiterFor(qc);
  ensureSyncOwner(arbiter, owner.ownerKey, owner.generation);
  const observerId = useSyncObserver(arbiter);
  const ownerEpochAtRender = arbiter.ownerEpoch;
  return useMutation({
    mutationFn: async () => {
      const token = beginSyncRequest(
        arbiter,
        owner.ownerKey,
        owner.generation,
        observerId,
        ownerEpochAtRender,
      );
      const status = await api.cancelSync();
      return acceptSyncObservation(qc, arbiter, status, token);
    },
  });
}

export function useSyncStatus() {
  const qc = useQueryClient();
  const settings = useSettings();
  const arbiter = syncStatusArbiterFor(qc);
  const nextOwnerKey = ownerKey(settings.data);
  const nextGeneration = ownerGeneration(settings.data);
  ensureSyncOwner(arbiter, nextOwnerKey, nextGeneration);
  const observerId = useSyncObserver(arbiter);
  const ownerEpochAtRender = arbiter.ownerEpoch;
  useEvents((message) => {
    if (message.type !== "sync.progress" && message.type !== "sync.done") return;
    const token = beginSyncRequest(
      arbiter,
      arbiter.ownerKey,
      arbiter.ownerGeneration,
      observerId,
    );
    acceptSyncObservation(qc, arbiter, message.data, token);
  });
  const key = ["sync-status", nextOwnerKey, nextGeneration] as const;
  return useQuery({
    queryKey: key,
    queryFn: async () => {
      const token = beginSyncRequest(
        arbiter,
        nextOwnerKey,
        nextGeneration,
        observerId,
        ownerEpochAtRender,
      );
      const status = await api.syncStatus();
      return acceptSyncObservation(qc, arbiter, status, token);
    },
    enabled: settings.data !== undefined,
    refetchInterval: 5_000,
  });
}

export function useLiveStatus() {
  const qc = useQueryClient();
  const arbiter = liveStatusArbiterFor(qc);
  useEvents(
    (message) => applyLiveStatusEvent(qc, arbiter, message),
    {
      onConnectionChange: (connected: boolean) => {
        if (!connected) {
          arbiter.wasConnected = false;
          return;
        }
        if (arbiter.wasConnected) return;
        if (arbiter.hasConnected) {
          void qc.refetchQueries({ queryKey: ["live-status"], type: "active" });
        }
        arbiter.hasConnected = true;
        arbiter.wasConnected = true;
      },
    },
  );
  return useQuery({
    queryKey: ["live-status"],
    queryFn: async () => {
      const champSelectRevision = arbiter.champSelectRevision;
      const inGameRevision = arbiter.inGameRevision;
      const status = await api.liveStatus();
      const next: LiveStatus = {
        ...status,
        champ_select:
          arbiter.champSelectRevision > champSelectRevision && arbiter.champSelectActive !== undefined
            ? {
                ...status.champ_select,
                active: arbiter.champSelectActive,
                phase:
                  arbiter.champSelectPhase !== undefined
                    ? arbiter.champSelectPhase
                    : status.champ_select.phase,
              }
            : status.champ_select,
        ingame:
          arbiter.inGameRevision > inGameRevision && arbiter.inGameActive !== undefined
            ? { ...status.ingame, active: arbiter.inGameActive }
            : status.ingame,
      };
      arbiter.latest = next;
      arbiter.champSelectActive = next.champ_select.active;
      arbiter.champSelectPhase = next.champ_select.phase;
      arbiter.inGameActive = next.ingame.active;
      return next;
    },
    refetchInterval: 3_000,
  });
}

export function useLiveSession() {
  const qc = useQueryClient();
  useEvents((message) => {
    if (message.type === "champselect.state") qc.setQueryData(["live-session"], message.data);
  });
  return useQuery({
    queryKey: ["live-session"],
    queryFn: api.liveSession,
    refetchInterval: 2_000,
  });
}

export function useLiveIngame() {
  const qc = useQueryClient();
  useEvents((message) => {
    if (message.type === "live.state") qc.setQueryData(["live-ingame"], message.data);
  });
  return useQuery({
    queryKey: ["live-ingame"],
    queryFn: api.liveIngame,
    refetchInterval: 2_000,
  });
}
