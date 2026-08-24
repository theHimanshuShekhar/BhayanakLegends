import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ProgressPage } from "../progress";
import { api } from "../../api/client";

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
  useEvents: vi.fn(() => true),
}));

function renderPage(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const points = [
  { patch: "16.16", role: "TOP", champion: null, games: 12, wins: 5, rolling_wr: 0.42 },
  { patch: "14.17", role: "TOP", champion: null, games: 10, wins: 6, rolling_wr: 0.6 },
  { patch: "14.17", role: "MIDDLE", champion: null, games: 8, wins: 2, rolling_wr: 0.25 },
];

const summary = {
  matches: 30,
  patches: ["14.17", "16.16"],
  by_role: [
    { role: "TOP", games: 22, wins: 11 },
    { role: "MIDDLE", games: 8, wins: 2 },
  ],
  win_rate: 0.433,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.trajectories).mockResolvedValue(points);
  vi.mocked(api.historySummary).mockResolvedValue(summary);
});

describe("ProgressPage", () => {
  it("renders the empty state when there are no tracked games", async () => {
    vi.mocked(api.trajectories).mockResolvedValue([]);
    renderPage(<ProgressPage />);

    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("No tracked games yet")).toBeInTheDocument();
  });

  it("plots one dot per patch for two patches and lists them in the table", async () => {
    renderPage(<ProgressPage />);

    await screen.findByTestId("trend-chart");
    const chart = screen.getByTestId("trend-chart");
    expect(chart.querySelectorAll("circle")).toHaveLength(2); // 14.17 + 16.16

    const table = screen.getByTestId("patch-table");
    expect(within(table).getByText("14.17")).toBeInTheDocument();
    expect(within(table).getByText("16.16")).toBeInTheDocument();
    // aggregated across roles for 14.17: games 10+8
    expect(within(table).getByText("18")).toBeInTheDocument();
  });

  it("filters by role chip", async () => {
    renderPage(<ProgressPage />);

    await screen.findByTestId("trend-chart");
    expect(screen.getByTestId("role-ALL")).toBeInTheDocument();
    expect(screen.getByTestId("role-TOP")).toBeInTheDocument();
    expect(screen.getByTestId("role-MIDDLE")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("role-MIDDLE"));

    const table = await screen.findByTestId("patch-table");
    expect(within(table).getByText("8")).toBeInTheDocument();
    expect(within(table).queryByText("18")).not.toBeInTheDocument();
    // MIDDLE only appears on one patch, so the chart collapses to a single dot
    const chart = screen.getByTestId("trend-chart");
    expect(chart.querySelectorAll("circle")).toHaveLength(1);
  });
});
