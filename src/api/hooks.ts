import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { useEvents } from "./sse";
import type { SseMessage } from "./sse";
import type { LiveStatus, PatchAggregate, SettingsPatch } from "./types";

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

const IDLE_LIVE_STATUS: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};
const liveStatusArbiters = new WeakMap<object, LiveStatusArbiter>();

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

export function useHistorySummary() {
  return useQuery({ queryKey: ["history-summary"], queryFn: api.historySummary });
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
    if (v != null) out[k] = v;
  }
  return out;
}

export function useTrajectories(
  filters: TrajectoryFilters = {},
  options: TrajectoryQueryOptions = {},
) {
  const params = cleanParams(filters);
  const enabled =
    options.enabled ??
    ((filters.role == null && filters.champion == null) ||
      Boolean(params.role && params.champion));
  return useQuery({
    queryKey: ["trajectories", params],
    queryFn: () => api.trajectories(params),
    enabled,
  });
}

export function usePatchAggregates(
  filters: TrajectoryFilters = {},
  options: TrajectoryQueryOptions = {},
) {
  const params = cleanParams(filters);
  const enabled =
    options.enabled ??
    ((filters.role == null && filters.champion == null) ||
      Boolean(params.role && params.champion));
  return useQuery<PatchAggregate[]>({
    queryKey: ["patch-aggregates", params],
    queryFn: () => api.patchAggregates(params),
    enabled,
  });
}


export function usePostgameLatest() {
  return useQuery({ queryKey: ["postgame-latest"], queryFn: api.postgameLatest });
}

export function useBenchmarks() {
  return useQuery({ queryKey: ["benchmarks"], queryFn: api.benchmarks });
}

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: api.settings });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: SettingsPatch) => api.updateSettings(patch),
    onSuccess: (saved) => qc.setQueryData(["settings"], saved),
  });
}

export function useStartSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.startSync(),
    onSuccess: (status) => qc.setQueryData(["sync-status"], status),
  });
}

export function useCancelSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.cancelSync(),
    onSuccess: (status) => qc.setQueryData(["sync-status"], status),
  });
}

export function useSyncStatus() {
  const qc = useQueryClient();
  useEvents((message) => {
    if (message.type === "sync.progress" || message.type === "sync.done") {
      qc.setQueryData(["sync-status"], message.data);
    }
  });
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: api.syncStatus,
    refetchInterval: 5_000,
  });
}

export function useLiveStatus() {
  const qc = useQueryClient();
  const arbiter = liveStatusArbiterFor(qc);
  useEvents(
    (message) => applyLiveStatusEvent(qc, arbiter, message),
    {
      onConnectionChange: (connected) => {
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
