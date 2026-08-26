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
    { role: "TOP" as const, games: 60, wins: 34 },
    { role: "JUNGLE" as const, games: 68, wins: 35 },
  ],
  win_rate: 0.54,
};

const settings = { riot_id: null, region_route: "europe" as const, has_key: true, auto_sync: false };

const savedSettings = {
  riot_id: "Player#1234",
  region_route: "europe" as const,
  has_key: true,
  auto_sync: false,
};

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

  it("dresses the screen in the design system shells and pill buttons", async () => {
    renderPage(<HistoryPage />);

    const syncPanel = await screen.findByTestId("sync-panel");
    expect(syncPanel).toHaveClass("card3b");

    // canonical action hierarchy: Start Backfill primary lavender, Save settings secondary, Cancel tertiary
    const start = screen.getByTestId("start-sync");
    expect(start).toHaveClass("pill");
    expect(start).toHaveStyle({ background: "var(--color-accent)" });

    const save = screen.getByTestId("save-settings");
    expect(save).toHaveClass("pill");
    expect(save).toHaveStyle({ background: "var(--color-surface-2)" });
    expect(save).toHaveStyle({ color: "var(--color-dim)" });

    const cancel = screen.getByTestId("cancel-sync");
    expect(cancel).toHaveClass("pill");
    expect(cancel).toBeDisabled();
    expect(cancel).toHaveStyle({ background: "transparent" });
  });

  it("shows an empty identity and requires it before Backfill", async () => {
    renderPage(<HistoryPage />);

    const riotId = await screen.findByTestId("input-riot-id");
    const region = screen.getByTestId("input-region");
    await waitFor(() => expect(region).toHaveValue("europe"));
    expect(riotId).toHaveValue("");
    // pristine render: initially blank/default data shows no eager validation error
    expect(screen.queryByTestId("riot-id-error")).toBeNull();
    expect(riotId).toHaveAttribute("aria-invalid", "false");

    // saved settings carry no identity yet: Backfill stays gated behind a visible linked reason
    const startBtn = screen.getByTestId("start-sync");
    expect(startBtn).toBeDisabled();
    expect(startBtn).toHaveAttribute("aria-describedby", "start-disabled-reason");
    expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
      "Enter a valid Riot ID before starting Backfill.",
    );
    expect(screen.getByTestId("input-riot-key")).toHaveAttribute(
      "placeholder",
      "saved — leave blank to keep",
    );

    // blurring an invalid value reveals exactly one associated error
    fireEvent.blur(riotId);
    expect(screen.getByTestId("riot-id-error")).toHaveTextContent("GameName#TAG");
    expect(riotId).toHaveAttribute("aria-invalid", "true");
    expect(riotId).toHaveAttribute("aria-describedby", "riot-id-error");

    // entering a valid id clears it immediately
    fireEvent.change(riotId, { target: { value: "Player#1234" } });
    expect(screen.queryByTestId("riot-id-error")).toBeNull();
    expect(riotId).toHaveAttribute("aria-invalid", "false");
    expect(riotId).not.toHaveAttribute("aria-describedby");
  });

  it("starts a sync only after an explicit identity is saved", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    vi.mocked(api.updateSettings).mockResolvedValue(savedSettings);
    renderPage(<HistoryPage />);

    const startBtn = await screen.findByTestId("start-sync");
    expect(startBtn).toBeDisabled();

    // typing alone leaves local edits unsaved: clicking Start must not fire against stale settings
    fireEvent.change(screen.getByTestId("input-riot-id"), {
      target: { value: "Player#1234" },
    });
    expect(startBtn).toBeDisabled();
    expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
      "Save settings before starting Backfill.",
    );
    fireEvent.click(startBtn);
    expect(api.startSync).not.toHaveBeenCalled();

    // saving persists the identity and unlocks Backfill
    fireEvent.click(screen.getByTestId("save-settings"));
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(startBtn).not.toBeDisabled());
    expect(await screen.findByTestId("save-ok")).toBeInTheDocument();

    fireEvent.click(startBtn);
    await waitFor(() => expect(api.startSync).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("start-disabled-reason")).toHaveTextContent(
        "Backfill is running.",
      ),
    );
    expect(startBtn).toBeDisabled();
    expect(screen.getByText(/Current-patch games download first/)).toBeInTheDocument();
  });


  it("updates the progress bar from SSE sync.progress events", async () => {
    vi.mocked(api.startSync).mockResolvedValue(running);
    vi.mocked(api.updateSettings).mockResolvedValue(savedSettings);
    renderPage(<HistoryPage />);

    fireEvent.change(await screen.findByTestId("input-riot-id"), {
      target: { value: "Player#1234" },
    });
    fireEvent.click(screen.getByTestId("save-settings"));
    await waitFor(() => expect(api.updateSettings).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("start-sync")).not.toBeDisabled());
    fireEvent.click(screen.getByTestId("start-sync"));
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
