import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { SettingsPatch } from "./types";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health });
}

export function usePack() {
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

function cleanParams(filters: TrajectoryFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v != null) out[k] = v;
  }
  return out;
}

export function useTrajectories(filters: TrajectoryFilters = {}) {
  const params = cleanParams(filters);
  return useQuery({
    queryKey: ["trajectories", params],
    queryFn: () => api.trajectories(params),
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
  // polled as the SSE fallback; SSE updates overlay this via SyncPanel state
  return useQuery({
    queryKey: ["sync-status"],
    queryFn: api.syncStatus,
    refetchInterval: 5_000,
  });
}
