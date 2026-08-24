import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, connection } from "./client";
import type { ChampSelectSnapshot, InGameSnapshot, PatchAggregate, SettingsPatch } from "./types";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health });
}

// Live snapshot fetchers. client.ts is frozen for the bridge pass, so these
// mirror its request shape (X-BL-Token header) against connection().
async function liveRequest<T>(path: string): Promise<T> {
  const { base, token } = connection();
  const res = await fetch(`${base}${path}`, { headers: { "X-BL-Token": token } });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export const liveApi = {
  session: () => liveRequest<ChampSelectSnapshot>("/live/session"),
  ingame: () => liveRequest<InGameSnapshot>("/live/ingame"),
};

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

export function usePatchAggregates(filters: TrajectoryFilters = {}) {
  const params = cleanParams(filters);
  return useQuery<PatchAggregate[]>({
    queryKey: ["patch-aggregates", params],
    queryFn: () => api.patchAggregates(params),
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

export function useLiveStatus() {
  // coarse health; polled as the SSE fallback for the live screens
  return useQuery({
    queryKey: ["live-status"],
    queryFn: api.liveStatus,
    refetchInterval: 3_000,
  });
}

export function useLiveSession() {
  // rich champ-select snapshot; SSE "champselect.state" overlays this cache
  return useQuery({
    queryKey: ["live-session"],
    queryFn: liveApi.session,
    refetchInterval: 2_000,
  });
}

export function useLiveIngame() {
  // rich in-game snapshot; SSE "live.state" overlays this cache
  return useQuery({
    queryKey: ["live-ingame"],
    queryFn: liveApi.ingame,
    refetchInterval: 2_000,
  });
}
