import { beforeEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const validChampSelect = {
  active: false,
  phase: null,
  timer_sec: null,
  local_assigned_role: null,
  bans_ally: [],
  bans_enemy: [],
  ally: [],
  enemy: [],
};
const validInGame = {
  active: false,
  clock_s: 0,
  mode: null,
  local_summoner: null,
  local_champion: null,
  teams: { order: [], chaos: [] },
  events: [],
  inference: {
    status: "suppressed",
    probability: null,
    observed_game_time_s: null,
    model_version: null,
    pack_version: null,
    reason: "no active game",
  },
  event_deltas: [],
};
const validWhatIf = {
  status: "available",
  probability: 0.6,
  baseline_probability: 0.5,
  adjusted_features: { unseen_recall_share_by_20m: 0.75 },
  model_version: "personal-what-if-v2",
  pack_version: "v4",
  rejected_fields: [],
  reason: null,
};


describe("sidecar API boundary", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.unstubAllEnvs();
    vi.stubGlobal("fetch", vi.fn());
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {},
    });
  });


  it("resolves a cold Tauri connection before REST and SSE URL construction", async () => {
    invoke.mockResolvedValue({ port: 24567, token: "cold-token" });
    vi.mocked(fetch).mockImplementation(async (input) =>
      response(String(input).endsWith("/live/session") ? validChampSelect : validInGame),
    );
    // Dynamic import resets the module-level cold-launch connection cache per test.
    const { api, eventsUrl } = await import("./client");
    const [session, ingame, url] = await Promise.all([
      api.liveSession(),
      api.liveIngame(),
      eventsUrl(),
    ]);

    expect(session).toEqual(validChampSelect);
    expect(ingame).toEqual(validInGame);
    expect(invoke).toHaveBeenCalledOnce();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://127.0.0.1:24567/live/session",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-BL-Token": "cold-token" }),
      }),
    );
    expect(url).toBe("http://127.0.0.1:24567/events?token=cold-token");
  });

  it("rejects malformed live sessions before consumers receive data", async () => {
    invoke.mockResolvedValue({ port: 24567, token: "cold-token" });
    vi.mocked(fetch).mockResolvedValue(
      response({
        ...validChampSelect,
        bans_ally: [{ champion_id: 25, name: "Miss Fortune" }],
      }),
    );
    const { api } = await import("./client");

    await expect(api.liveSession()).rejects.toThrow("Invalid /live/session response");
  });

  it("accepts a contract-valid What-If response at the API boundary", async () => {
    invoke.mockResolvedValue({ port: 24567, token: "cold-token", status: "ok" });
    vi.mocked(fetch).mockResolvedValue(response(validWhatIf));
    const { api } = await import("./client");

    await expect(api.whatIf({ unseen_recall_share_by_20m: 0.75 })).resolves.toEqual(validWhatIf);
  });

  it("rejects malformed What-If responses before consumers receive data", async () => {
    invoke.mockResolvedValue({ port: 24567, token: "cold-token", status: "ok" });
    vi.mocked(fetch).mockResolvedValue(
      response({
        ...validWhatIf,
        adjusted_features: { unseen_recall_share_by_20m: "bad" },
      }),
    );
    const { api } = await import("./client");

    await expect(api.whatIf({ unseen_recall_share_by_20m: 0.75 })).rejects.toThrow(
      "Invalid /history/what-if response",
    );
  });
  it.each([
    ["missing", undefined],
    ["blank", ""],
    ["short", "short-token"],
    ["dev", "dev"],
    ["whitespace-padded", " browser-token-012345678901234567890123 "],
  ])("fails closed for %s browser token configuration", async (_label, token) => {
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    if (token === undefined) {
      Reflect.deleteProperty(import.meta.env, "VITE_BL_TOKEN");
    } else {
      vi.stubEnv("VITE_BL_TOKEN", token);
    }
    const { api, eventsUrl } = await import("./client");

    await expect(api.health()).rejects.toThrow(/VITE_BL_TOKEN must be explicitly configured/);
    await expect(eventsUrl()).rejects.toThrow(/VITE_BL_TOKEN must be explicitly configured/);
    expect(invoke).not.toHaveBeenCalled();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("uses an explicitly configured browser token through the same async boundary", async () => {
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    const token = "browser-test-token-012345678901234567890123";
    vi.stubEnv("VITE_BL_TOKEN", token);
    vi.mocked(fetch).mockImplementation(async () => response({ status: "ok" }));
    const { api, eventsUrl } = await import("./client");

    await api.health();
    expect(invoke).not.toHaveBeenCalled();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://127.0.0.1:23110/health",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-BL-Token": token }),
      }),
    );
    await expect(eventsUrl()).resolves.toBe(
      `http://127.0.0.1:23110/events?token=${encodeURIComponent(token)}`,
    );
  });


  it("exposes bounded safe details from non-success JSON responses", async () => {
    invoke.mockResolvedValue({ port: 24567, token: "dev-token" });
    const detail = `riot key rejected\n${"x".repeat(400)}`;
    vi.mocked(fetch).mockResolvedValue(response({ detail }, 401));
    const { ApiError, api } = await import("./client");
    const error = await api.liveStatus().catch((value: unknown) => value);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 401,
      detail: expect.stringMatching(/^riot key rejected x+…$/),
    });
    if (error instanceof ApiError) {
      expect(error.message).not.toContain("riot key rejected");
      expect(error.detail?.length).toBeLessThanOrEqual(240);
    }
  });

  it("does not let an in-flight generation overwrite a newer resolution", async () => {
    // The configured ES2022 test target does not expose Promise.withResolvers.
    let resolveFirst!: (value: { port: number; token: string; status: "ok" }) => void;
    const first = new Promise<{ port: number; token: string; status: "ok" }>((resolve) => {
      resolveFirst = resolve;
    });
    invoke
      .mockImplementationOnce(() => first)
      .mockResolvedValueOnce({ port: 24568, token: "fresh-token", status: "ok" });
    const { resolveConnection, invalidateConnection } = await import("./client");

    const stale = resolveConnection();
    invalidateConnection();
    const fresh = resolveConnection();
    await expect(fresh).resolves.toMatchObject({
      base: "http://127.0.0.1:24568",
      token: "fresh-token",
    });
    resolveFirst({ port: 24567, token: "stale-token", status: "ok" });
    await expect(stale).resolves.toMatchObject({
      base: "http://127.0.0.1:24568",
      token: "fresh-token",
    });
    expect(invoke).toHaveBeenCalledTimes(2);
  });

  it("invalidates transport failures before the next REST attempt", async () => {
    invoke
      .mockResolvedValueOnce({ port: 24567, token: "old-token", status: "ok" })
      .mockResolvedValueOnce({ port: 24568, token: "fresh-token", status: "ok" });
    vi.mocked(fetch)
      .mockRejectedValueOnce(new TypeError("network down"))
      .mockResolvedValueOnce(response({ status: "ok" }));
    const { api } = await import("./client");

    await expect(api.health()).rejects.toThrow("network down");
    await expect(api.health()).resolves.toEqual({ status: "ok" });
    expect(invoke).toHaveBeenCalledTimes(2);
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
  });
});
