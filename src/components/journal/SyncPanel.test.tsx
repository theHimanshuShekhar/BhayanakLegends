import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { SseMessage } from "../../api/sse";
import { SyncPanel } from "./SyncPanel";
import { api } from "../../api/client";

let sseHandler: ((msg: SseMessage) => void) | undefined;

vi.mock("../../api/client", () => ({
  api: {
    health: vi.fn(),
    pack: vi.fn(),
    settings: vi.fn(),
    updateSettings: vi.fn(),
    startSync: vi.fn(),
    cancelSync: vi.fn(),
    syncStatus: vi.fn(),
    historySummary: vi.fn(),
    trajectories: vi.fn(),
    postgameLatest: vi.fn(),
    benchmarks: vi.fn(),
    liveStatus: vi.fn(),
  },
}));

vi.mock("../../api/sse", () => ({
  useEvents: vi.fn((cb?: (msg: SseMessage) => void) => {
    sseHandler = cb;
    return true;
  }),
}));

function renderPanel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <SyncPanel />
    </QueryClientProvider>,
  );
}

const settings = { riot_id: "SacredButtholio#OOF", region_route: "sea", has_key: false, auto_sync: true };
const idle = {
  state: "idle" as const,
  mode: "era_first" as const,
  total_queued: 0,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: null,
  started_at: null,
};
const running = {
  state: "running" as const,
  mode: "era_first" as const,
  total_queued: 25,
  downloaded: 5,
  skipped: 0,
  failed: 0,
  current_match_id: "EUW1_1",
  started_at: "2026-08-24T10:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  sseHandler = undefined;
  vi.mocked(api.settings).mockResolvedValue(settings);
  vi.mocked(api.syncStatus).mockResolvedValue(idle);
});

describe("SyncPanel", () => {
  it("shows the era-first explainer", async () => {
    renderPanel();
    expect(
      await screen.findByText("Current-patch games download first; older history fills in across sessions."),
    ).toBeInTheDocument();
  });

  it("saves settings via PUT, including a typed key, and shows inline confirmation", async () => {
    vi.mocked(api.updateSettings).mockResolvedValue(settings);
    renderPanel();

    fireEvent.change(await screen.findByTestId("input-riot-key"), {
      target: { value: "RGAPI-test" },
    });
    fireEvent.click(screen.getByTestId("save-settings"));

    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    expect(api.updateSettings).toHaveBeenCalledWith({
      riot_id: "SacredButtholio#OOF",
      region_route: "sea",
      auto_sync: true,
      riot_key: "RGAPI-test",
    });
    expect(await screen.findByTestId("save-ok")).toBeInTheDocument();
  });

  it("reflects polled sync status and overlays fresher SSE progress", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    renderPanel();

    // polled fallback shows zero progress
    await waitFor(() => expect(screen.getByTestId("sync-counters")).toHaveTextContent("0 / 0"));

    fireEvent.click(screen.getByTestId("start-sync"));
    await waitFor(() => expect(api.startSync).toHaveBeenCalledTimes(1));

    // SSE overlay: 10 of 25 downloaded -> 40%
    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: new Date().toISOString(),
        data: { ...running, downloaded: 10 },
      });
    });

    const bar = screen.getByTestId("sync-progress-bar");
    expect(bar).toHaveStyle({ width: "40%" });
    expect(screen.getByTestId("sync-current")).toHaveTextContent("EUW1_1");

    // while running, Start is disabled and Cancel is armed
    expect(screen.getByTestId("start-sync")).toBeDisabled();
    expect(screen.getByTestId("cancel-sync")).not.toBeDisabled();
  });

  it("cancels a running sync via the API", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    vi.mocked(api.cancelSync).mockResolvedValue({ ...running, state: "cancelled", current_match_id: null });
    renderPanel();

    fireEvent.click(await screen.findByTestId("start-sync"));
    await waitFor(() => expect(screen.getByTestId("cancel-sync")).not.toBeDisabled());

    fireEvent.click(screen.getByTestId("cancel-sync"));
    await waitFor(() => expect(api.cancelSync).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/queue resumes next session/)).toBeInTheDocument();
  });
});
