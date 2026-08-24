import { invoke } from "@tauri-apps/api/core";
import type { PatchAggregate } from "./types";

let base = "";
let token = "";

async function resolveConnection() {
  if (base) return;
  const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  if (isTauri) {
    const info = await invoke<{ port: number; token: string }>("sidecar_info");
    base = `http://127.0.0.1:${info.port}`;
    token = info.token;
  } else {
    base = `http://127.0.0.1:${import.meta.env.VITE_BL_PORT ?? 23110}`;
    token = import.meta.env.VITE_BL_TOKEN ?? "dev";
  }
}

export function connection() {
  return { base, token };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await resolveConnection();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-BL-Token": token,
      ...init?.headers,
    },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  health: () => request<import("./types").Health>("/health"),
  pack: () => request<import("./types").FindingsPack>("/pack"),
  settings: () => request<import("./types").Settings>("/settings"),
  updateSettings: (patch: import("./types").SettingsPatch) =>
    request<import("./types").Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  startSync: () => request<import("./types").SyncStatus>("/sync/start", { method: "POST" }),
  cancelSync: () => request<import("./types").SyncStatus>("/sync/cancel", { method: "POST" }),
  syncStatus: () => request<import("./types").SyncStatus>("/sync/status"),
  historySummary: () => request<import("./types").HistorySummary>("/history/summary"),
  trajectories: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request<import("./types").TrajectoryPoint[]>(
      `/progress/trajectories${qs ? `?${qs}` : ""}`,
    );
  },
  patchAggregates: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request<PatchAggregate[]>(
      `/progress/aggregates${qs ? `?${qs}` : ""}`,
    );
  },
  postgameLatest: () =>
    request<import("./types").PostGameDigest | null>("/postgame/latest"),
  benchmarks: () => request<import("./types").RoleBenchmark[]>("/benchmarks"),
  liveStatus: () => request<import("./types").LiveStatus>("/live/status"),
};

export function eventsUrl(): string {
  return `${base}/events?token=${encodeURIComponent(token)}`;
}
