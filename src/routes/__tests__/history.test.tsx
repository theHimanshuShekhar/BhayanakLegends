import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { SseMessage } from "../../api/sse";
import { HistoryPage } from "../history";
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

function renderPage(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const summary = {
  matches: 128,
  patches: ["14.17", "15.5", "16.16"],
  by_role: [
    { role: "TOP", games: 60, wins: 34 },
    { role: "JUNGLE", games: 68, wins: 35 },
  ],
  win_rate: 0.54,
};

const settings = { riot_id: null, region_route: "europe", has_key: true, auto_sync: false };

const running = {
  state: "running" as const,
  mode: "era_first" as const,
  total_queued: 40,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: null,
  started_at: "2026-08-24T10:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  sseHandler = undefined;
  vi.mocked(api.historySummary).mockResolvedValue(summary);
  vi.mocked(api.settings).mockResolvedValue(settings);
  vi.mocked(api.syncStatus).mockResolvedValue({
    ...running,
    state: "idle",
    total_queued: 0,
    started_at: null,
  });
});

describe("HistoryPage", () => {
  it("renders the summary stat row and by-role table", async () => {
    renderPage(<HistoryPage />);

    expect(await screen.findByTestId("summary-matches")).toHaveTextContent("128");
    expect(screen.getByText("54.0%")).toBeInTheDocument();
    expect(screen.getByText("14.17 → 16.16")).toBeInTheDocument();

    const table = screen.getByTestId("by-role-table");
    expect(within(table).getByText("TOP")).toBeInTheDocument();
    expect(within(table).getByText("JUNGLE")).toBeInTheDocument();
    expect(within(table).getByText("56.7%")).toBeInTheDocument(); // 34/60
  });

  it("prefills the settings form defaults and shows saved-key state", async () => {
    renderPage(<HistoryPage />);

    const riotId = await screen.findByTestId("input-riot-id");
    expect(riotId).toHaveValue("SacredButtholio#OOF");
    const region = screen.getByTestId("input-region");
    await waitFor(() => expect(region).toHaveValue("europe"));
    expect(screen.getByTestId("input-riot-key")).toHaveAttribute(
      "placeholder",
      "saved — leave blank to keep",
    );
  });

  it("starts a sync via the API and disables Start while running", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    renderPage(<HistoryPage />);

    const startBtn = await screen.findByTestId("start-sync");
    await waitFor(() => expect(startBtn).not.toBeDisabled());

    fireEvent.click(startBtn);

    await waitFor(() => expect(api.startSync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(startBtn).toBeDisabled());
    expect(screen.getByText(/Current-patch games download first/)).toBeInTheDocument();
  });

  it("updates the progress bar from SSE sync.progress events", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    renderPage(<HistoryPage />);

    fireEvent.click(await screen.findByTestId("start-sync"));
    await waitFor(() => expect(api.startSync).toHaveBeenCalled());

    await act(async () => {
      sseHandler?.({
        type: "sync.progress",
        ts: new Date().toISOString(),
        data: { ...running, downloaded: 12, failed: 1, current_match_id: "EUW1_999" },
      });
    });

    const bar = screen.getByTestId("sync-progress-bar");
    expect(bar).toHaveStyle({ width: "30%" }); // 12 / 40
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("12 / 40 matches");
    expect(screen.getByTestId("sync-counters")).toHaveTextContent("1 failed");
    expect(screen.getByTestId("sync-current")).toHaveTextContent("EUW1_999");

    // terminal event flips the bar to its done color
    await act(async () => {
      sseHandler?.({
        type: "sync.done",
        ts: new Date().toISOString(),
        data: { ...running, state: "idle", downloaded: 40 },
      });
    });
    expect(bar.className).toContain("bg-teal");
  });
});
