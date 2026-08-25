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
  bans_ally: [],
  bans_enemy: [],
  ally: [],
  enemy: [],
};

describe("sidecar API boundary", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn());
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {},
    });
  });

  it("resolves a cold Tauri connection before REST and SSE URL construction", async () => {
    invoke.mockResolvedValue({ port: 24567, token: "cold-token" });
    vi.mocked(fetch).mockImplementation(async (input) =>
      response(String(input).endsWith("/live/session") ? validChampSelect : { active: false }),
    );
    // Dynamic import resets the module-level cold-launch connection cache per test.
    const { api, eventsUrl } = await import("./client");
    const [session, ingame, url] = await Promise.all([
      api.liveSession(),
      api.liveIngame(),
      eventsUrl(),
    ]);

    expect(session).toEqual(validChampSelect);
    expect(ingame).toEqual({ active: false });
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
  it("uses browser development defaults through the same async boundary", async () => {
    Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
    vi.mocked(fetch).mockImplementation(async () => response({ status: "ok" }));
    const { api, eventsUrl } = await import("./client");

    await api.health();
    expect(invoke).not.toHaveBeenCalled();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://127.0.0.1:23110/health",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-BL-Token": "local-sidecar-development-token-32chars",
        }),
      }),
    );
    await expect(eventsUrl()).resolves.toBe(
      "http://127.0.0.1:23110/events?token=local-sidecar-development-token-32chars",
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
});
