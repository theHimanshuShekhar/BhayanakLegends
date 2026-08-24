import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ProgressPage } from "../progress";
import { api } from "../../api/client";
import type { FindingsPack } from "../../api/types";

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

const benchmarks = [
  {
    role: "MIDDLE",
    personal: { cs10: 77, level10: 8, gold10: 247 },
    population: { cs10_median: 64, level10_median: null, gold10_median: null, sample: 52048 },
  },
  {
    role: "TOP",
    personal: { cs10: 58.5, level10: 7, gold10: -12.5 },
    population: { cs10_median: 61, level10_median: null, gold10_median: null, sample: 52048 },
  },
];

function makePack(overrides: Partial<FindingsPack> = {}): FindingsPack {
  return {
    schema_version: 1,
    generated_at: "2026-08-01T00:00:00Z",
    dataset: { matches: 26036, player_games: 260360, patches: ["14.17", "16.16"] },
    findings: [
      {
        key: "lane_win_conversion_gap",
        tier: "actionable",
        title: "Lane leads are raw material",
        statement: "Real cases turned +121g@10 lane leads into 42.7% win rates.",
        value: 42.7,
        unit: "%",
        source_ref: "companion-app-content.md#24",
      },
    ],
    habits: [
      { key: "recall_safety", label: "Recall safely", effect_per_sd: 2.24 },
      { key: "fast_first_dragon", label: "Fast first dragon", effect_per_sd: 0.83 },
      { key: "spend_before_backing", label: "Spend gold before backing", effect_per_sd: 0.88 },
      { key: "plates_by_14", label: "Turret plates by 14m", effect_per_sd: 1.08 },
    ],
    objectives: {},
    comeback_odds: [],
    ban_advisor: [],
    trap_picks: [],
    tier_list: [],
    matchup_examples: [],
    benchmarks: [],
    checkpoints: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.trajectories).mockResolvedValue(points);
  vi.mocked(api.historySummary).mockResolvedValue(summary);
  vi.mocked(api.benchmarks).mockResolvedValue(benchmarks);
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("ProgressPage", () => {
  it("renders benchmark cards with real personal vs population medians and bars", async () => {
    renderPage(<ProgressPage />);

    const mid = await screen.findByTestId("benchmark-MIDDLE");
    expect(within(mid).getByText("77.0")).toBeInTheDocument();
    expect(within(mid).getByText("pop median 64 · 52k games")).toBeInTheDocument();
    expect(within(mid).getByText("+13.0")).toBeInTheDocument();
    // personal 77 vs median 64 -> bar scaled to max(77,64), median tick at 83.1%
    const midBar = screen.getByTestId("benchmark-bar-MIDDLE");
    expect(midBar.firstElementChild).toHaveStyle({ width: "100%" });
    expect(midBar.querySelector("[title='population median 64']")).toHaveStyle({
      left: "83.1%",
    });

    const top = screen.getByTestId("benchmark-TOP");
    expect(within(top).getByText("58.5")).toBeInTheDocument();
    expect(within(top).getByText("-2.5")).toBeInTheDocument();
    // personal 58.5 vs median 61 -> 95.9% of the track, tick at the right edge
    expect(screen.getByTestId("benchmark-bar-TOP").firstElementChild).toHaveStyle({
      width: "95.9%",
    });
  });

  it("renders the four pack habits with neutral pending bars", async () => {
    renderPage(<ProgressPage />);

    expect(await screen.findByTestId("habit-row-recall_safety")).toBeInTheDocument();
    expect(screen.getByTestId("habit-row-fast_first_dragon")).toBeInTheDocument();
    expect(screen.getByTestId("habit-row-spend_before_backing")).toBeInTheDocument();
    expect(screen.getByTestId("habit-row-plates_by_14")).toBeInTheDocument();

    for (const key of ["recall_safety", "fast_first_dragon", "spend_before_backing", "plates_by_14"]) {
      const bar = screen.getByTestId(`habit-bar-${key}`);
      const fill = bar.firstElementChild as HTMLElement;
      // neutral: zero-width fill, no trend color claimed
      expect(fill.style.width).toMatch(/^0(px)?$/);
      expect(bar.parentElement).not.toHaveTextContent(/trending|regressing/i);
    }
    expect(screen.getByTestId("lever-adoption")).toHaveTextContent(
      /timeline features land with the loltrends wheel/i,
    );
  });

  it("parks the what-if simulator: disabled inputs and the model-bearing caption", async () => {
    renderPage(<ProgressPage />);

    await screen.findByTestId("what-if-panel");
    for (const key of ["gold10", "plates14", "safe-recalls"]) {
      expect(screen.getByTestId(`what-if-input-${key}`)).toBeDisabled();
    }
    expect(screen.getByTestId("what-if-caption")).toHaveTextContent(
      /what-if activates with the model-bearing pack/i,
    );
    expect(screen.getByTestId("what-if-panel")).toHaveTextContent("Predicted win rate");
    // no invented prediction
    expect(screen.getByTestId("what-if-prediction")).toHaveTextContent("—");
  });

  it("renders the rolling win-rate sparkline per patch with mono patch labels", async () => {
    renderPage(<ProgressPage />);

    const chart = await screen.findByTestId("rolling-wr-svg");
    expect(chart.querySelector("polyline")).toBeInTheDocument();
    const wrap = screen.getByTestId("rolling-wr-chart");
    expect(within(wrap).getByText("14.17")).toBeInTheDocument();
    expect(within(wrap).getByText("16.16")).toBeInTheDocument();
    // 14.17 aggregates TOP+MIDDLE with all patches charted: 12+10+8 games
    expect(within(wrap).getByText(/30 synced games/)).toBeInTheDocument();
  });

  it("shows the honest empty state when no games are tracked", async () => {
    vi.mocked(api.trajectories).mockResolvedValue([]);
    renderPage(<ProgressPage />);

    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("No tracked games yet")).toBeInTheDocument();
  });

  it("binds the lane conversion card from the pack finding", async () => {
    renderPage(<ProgressPage />);

    const card = await screen.findByTestId("lane-conversion");
    expect(within(card).getByText("Lane conversion")).toBeInTheDocument();
    expect(card).toHaveTextContent(/\+121g@10 lane leads/);
  });

  it("carries the population caveat footer once", async () => {
    renderPage(<ProgressPage />);
    await screen.findByTestId("lane-conversion");

    expect(screen.getAllByTestId("population-caveat")).toHaveLength(1);
    expect(screen.getByText(/friend group's 26k games/)).toBeInTheDocument();
  });
});
