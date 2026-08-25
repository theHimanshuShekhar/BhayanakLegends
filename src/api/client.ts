import { invoke } from "@tauri-apps/api/core";
import { isChampSelectSnapshot } from "./liveValidation";
import type {
  ChampSelectSnapshot,
  FindingsPack,
  Health,
  HistorySummary,
  InGameSnapshot,
  LiveStatus,
  PatchAggregate,
  PostGameDigest,
  RoleBenchmark,
  Settings,
  SettingsPatch,
  SyncStatus,
  TrajectoryPoint,
} from "./types";

const MAX_ERROR_DETAIL = 240;

export interface SidecarConnection {
  base: string;
  token: string;
  status: "ok" | "degraded";
}

/**
 * Errors returned by the sidecar retain the HTTP status and a bounded,
 * display-safe detail. Callers can make an actionable decision without
 * exposing arbitrary response bodies in logs or UI.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail?: string;

  constructor(status: number, detail?: string) {
    super(`Sidecar request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let connectionPromise: Promise<SidecarConnection> | null = null;
function browserConnection(): SidecarConnection {
  return {
    base: `http://127.0.0.1:${import.meta.env.VITE_BL_PORT ?? 23110}`,
    token:
      import.meta.env.VITE_BL_TOKEN ??
      "local-sidecar-development-token-32chars",
    status: "ok",
  };
}

/**
 * Resolve the sidecar exactly once per frontend lifetime. Keeping this
 * asynchronous is important on a cold Tauri launch: both REST and SSE must
 * await `sidecar_info` before constructing a URL or reading its token.
 */
export function resolveConnection(): Promise<SidecarConnection> {
  if (!connectionPromise) {
    const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
    connectionPromise = (
      isTauri
        ? invoke<{ port: number; token: string; status: "ok" | "degraded" }>("sidecar_info").then(
            (info) => ({
              base: `http://127.0.0.1:${info.port}`,
              token: info.token,
              status: info.status,
            }),
          )
        : Promise.resolve(browserConnection())
    ).catch((error) => {
      connectionPromise = null;
      throw error;
    });
  }
  return connectionPromise;
}

/** Backwards-compatible named boundary for consumers that need connection info. */
export const connection = resolveConnection;

function boundedDetail(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const detail = value.replace(/[\u0000-\u001f\u007f]/g, " ").trim();
  if (!detail) return undefined;
  return detail.length > MAX_ERROR_DETAIL
    ? `${detail.slice(0, MAX_ERROR_DETAIL - 1)}…`
    : detail;
}

async function responseDetail(res: Response): Promise<string | undefined> {
  try {
    const body: unknown = await res.json();
    if (typeof body !== "object" || body === null || !("detail" in body)) return undefined;
    return boundedDetail(body.detail);
  } catch {
    return undefined;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { base, token } = await resolveConnection();
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-BL-Token": token,
      ...init?.headers,
    },
  });
  if (!res.ok) throw new ApiError(res.status, await responseDetail(res));
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
async function liveSession(): Promise<ChampSelectSnapshot> {
  const value = await request<unknown>("/live/session");
  if (!isChampSelectSnapshot(value)) throw new Error("Invalid /live/session response");
  return value;
}

export const api = {
  health: () => request<Health>("/health"),
  pack: () => request<FindingsPack>("/pack"),
  settings: () => request<Settings>("/settings"),
  updateSettings: (patch: SettingsPatch) =>
    request<Settings>("/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  startSync: () => request<SyncStatus>("/sync/start", { method: "POST" }),
  cancelSync: () => request<SyncStatus>("/sync/cancel", { method: "POST" }),
  syncStatus: () => request<SyncStatus>("/sync/status"),
  historySummary: () => request<HistorySummary>("/history/summary"),
  trajectories: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request<TrajectoryPoint[]>(
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
    request<PostGameDigest | null>("/postgame/latest"),
  benchmarks: () => request<RoleBenchmark[]>("/benchmarks"),
  liveStatus: () => request<LiveStatus>("/live/status"),
  liveSession,
  liveIngame: () => request<InGameSnapshot>("/live/ingame"),
};

export async function eventsUrl(): Promise<string> {
  const { base, token } = await resolveConnection();
  return `${base}/events?token=${encodeURIComponent(token)}`;
}

export type ActionableErrorKind =
  | "invalid-riot-id"
  | "invalid-riot-key"
  | "pack-unavailable"
  | "offline"
  | "unknown";

function errorText(error: unknown): string {
  return error instanceof ApiError
    ? (error.detail ?? "")
    : error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "";
}

export function classifyApiError(
  error: unknown,
  context?: "pack" | "sync",
): ActionableErrorKind {
  const detail = errorText(error).toLowerCase();
  if (
    (context === "pack" && error instanceof ApiError && error.status === 503) ||
    (error instanceof ApiError && error.status === 503 && detail.includes("pack"))
  ) {
    return "pack-unavailable";
  }
  if (
    detail.includes("riot id") ||
    detail.includes("riot_id") ||
    detail.includes("summoner") ||
    (error instanceof ApiError && error.status === 404)
  ) {
    return "invalid-riot-id";
  }
  if (
    detail.includes("riot key") ||
    detail.includes("riot_key") ||
    detail.includes("api key") ||
    (context === "sync" && error instanceof ApiError && [400, 401, 403].includes(error.status))
  ) {
    return "invalid-riot-key";
  }
  if (
    detail.includes("offline") ||
    (!(error instanceof ApiError) &&
      (error instanceof TypeError || /failed to fetch|network|load failed/i.test(detail)))
  ) {
    return "offline";
  }
  return "unknown";
}

export function actionableErrorMessage(
  error: unknown,
  context?: "pack" | "sync",
): string {
  switch (classifyApiError(error, context)) {
    case "invalid-riot-id":
      return "That Riot ID could not be found. Check the GameName#TAG and region route.";
    case "invalid-riot-key":
      return "That Riot API key was rejected. Check the key and save settings again.";
    case "pack-unavailable":
      return "The Findings Pack is unavailable. Restart the app or install the latest pack.";
    case "offline":
      return "The sidecar is offline. Reopen the app and try again.";
    default:
      return "Something went wrong. Check your settings and try again.";
  }
}
