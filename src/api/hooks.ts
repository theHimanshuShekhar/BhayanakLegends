import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { useEvents } from "./sse";
import type { PatchAggregate, SettingsPatch } from "./types";
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
  useEvents((message) => {
    if (message.type === "live.status") qc.setQueryData(["live-status"], message.data);
  });
  return useQuery({
    queryKey: ["live-status"],
    queryFn: api.liveStatus,
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
