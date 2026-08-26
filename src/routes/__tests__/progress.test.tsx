import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ProgressPage } from "../progress";
import { api } from "../../api/client";
import type { BenchmarkResponse, FindingsPack } from "../../api/types";

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
    patchAggregates: vi.fn(),
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
  { patch: "16.16", role: "TOP" as const, champion: null, played_at: "2026-02-01T00:00:00Z", index: 2, rolling_wr: 0.42 },
  { patch: "14.17", role: "TOP" as const, champion: null, played_at: "2026-01-01T00:00:00Z", index: 0, rolling_wr: 0.6 },
  { patch: "14.17", role: "MIDDLE" as const, champion: null, played_at: "2026-01-15T00:00:00Z", index: 1, rolling_wr: 0.25 },
];

const aggregates = [
  { patch: "16.16", games: 12, wins: 5, win_rate: 0.42 },
  { patch: "14.17", games: 18, wins: 8, win_rate: 8 / 18 },
];

const summary = {
  matches: 30,
  patches: ["14.17", "16.16"],
  by_role: [
    { role: "TOP" as const, games: 22, wins: 11 },
    { role: "MIDDLE" as const, games: 8, wins: 2 },
  ],
  win_rate: 0.433,
};

const benchmarkRows = [
  {
    role: "MIDDLE" as const,
    personal: { cs10: 77, level10: 8, gold_diff_10: 247 },
    population: { cs10_median: 64, sample: 52048 },
  },
  {
    role: "TOP" as const,
    personal: { cs10: 58.5, level10: 7, gold_diff_10: -12.5 },
    population: { cs10_median: 61, sample: 52048 },
  },
];
const benchmarks: BenchmarkResponse = { state: "available", rows: benchmarkRows };

function makePack(overrides: Partial<FindingsPack> = {}): FindingsPack {
  return {
    provenance: {} as FindingsPack["provenance"],
    schema_version: 1,
    pack_version: "v1",
    generated_at: "2026-08-01T00:00:00Z",
    comeback_feature_contract: {
      feature: "gold_diff_15",
      feature_contract_version: "loltrends-parity-v1",
    },
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
  vi.mocked(api.patchAggregates).mockResolvedValue(aggregates);
  vi.mocked(api.historySummary).mockResolvedValue(summary);
  vi.mocked(api.benchmarks).mockResolvedValue(benchmarks);
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("ProgressPage", () => {
  it("names trajectory panels and repeated benchmark records", async () => {
    renderPage(<ProgressPage />);

    expect(await screen.findByRole("heading", { level: 1, name: "Trajectory" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /personal history/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /patch win rate/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: /benchmarks/i })).toBeInTheDocument();
    expect(await screen.findByRole("list", { name: /benchmarks/i })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem", { name: /CS@10|LEVEL@10|GOLD DIFF@10/i }).length).toBeGreaterThan(0);
  });

  it("renders benchmark evidence in the two data worlds: population blue, personal teal", async () => {
    renderPage(<ProgressPage />);

    const mid = await screen.findByTestId("benchmark-MIDDLE");
    expect(within(mid).getByText("77.0")).toBeInTheDocument();
    expect(screen.getByTestId("benchmark-pop-MIDDLE")).toHaveTextContent(
      "pop median 64 · 52,048 games",
    );
    expect(within(mid).getByText("+13.0")).toBeInTheDocument();
    // The Personal History value stays teal even when unfavorable; the delta
    // pill carries favorable/unfavorable framing instead of recoloring values.
    expect(within(mid).getByText("77.0")).toHaveStyle({ color: "var(--color-teal)" });
    // personal 77 vs median 64 -> bar scaled to max(77,64), median tick at 83.1%
    const midBar = screen.getByTestId("benchmark-bar-MIDDLE");
    expect(midBar.firstElementChild).toHaveStyle({ width: "100%" });
    const midTick = midBar.querySelector("[title='population median 64']");
    expect(midTick).toHaveStyle({ left: "83.1%" });
    // The population median marker is Findings Pack evidence: blue, not teal.
    expect(midTick).toHaveStyle({ background: "var(--color-info)" });

    const top = screen.getByTestId("benchmark-TOP");
    expect(within(top).getByText("58.5")).toBeInTheDocument();
    expect(within(top).getByText("-2.5")).toBeInTheDocument();
    expect(within(top).getByText("58.5")).toHaveStyle({ color: "var(--color-teal)" });
    // personal 58.5 vs median 61 -> 95.9% of the track, tick at the right edge
    expect(screen.getByTestId("benchmark-bar-TOP").firstElementChild).toHaveStyle({
      width: "95.9%",
    });
  });

  it("renders no benchmark cards and names contract suppression", async () => {
    vi.mocked(api.benchmarks).mockResolvedValue({
      state: "contract-suppressed",
      rows: [],
    });
    renderPage(<ProgressPage />);

    await screen.findByTestId("benchmarks-contract-suppressed");
    expect(screen.queryByTestId("benchmark-MIDDLE")).not.toBeInTheDocument();
    expect(screen.queryByTestId("benchmark-TOP")).not.toBeInTheDocument();
    // Only the insufficient-history state may mention Backfill.
    expect(screen.queryByText(/Backfill/i)).not.toBeInTheDocument();
  });

  it("renders the Backfill copy only for insufficient personal history", async () => {
    vi.mocked(api.benchmarks).mockResolvedValue({
      state: "insufficient-personal-history",
      rows: [],
    });
    renderPage(<ProgressPage />);

    await screen.findByTestId("benchmarks-insufficient");
    expect(screen.getByTestId("benchmarks-insufficient")).toHaveTextContent("Backfill");
    expect(screen.queryByTestId("benchmark-MIDDLE")).not.toBeInTheDocument();
  });


  it("renders the four pack habits with canonical multiplier units and neutral bars", async () => {
    renderPage(<ProgressPage />);

    expect(await screen.findByTestId("habit-row-recall_safety")).toHaveTextContent(
      "×2.24 effect per SD",
    );
    expect(screen.getByTestId("habit-row-recall_safety")).not.toHaveTextContent(/WR per SD|% per SD/);
    expect(screen.getByTestId("habit-row-fast_first_dragon")).toHaveTextContent(
      "×0.83 effect per SD",
    );
    expect(screen.getByTestId("habit-row-spend_before_backing")).toHaveTextContent(
      "×0.88 effect per SD",
    );
    expect(screen.getByTestId("habit-row-plates_by_14")).toHaveTextContent(
      "×1.08 effect per SD",
    );

    for (const key of ["recall_safety", "fast_first_dragon", "spend_before_backing", "plates_by_14"]) {
      const bar = screen.getByTestId(`habit-bar-${key}`);
      const fill = bar.firstElementChild as HTMLElement;
      // neutral: zero-width fill, no trend color claimed
      expect(fill.style.width).toMatch(/^0(px)?$/);
      expect(bar.parentElement).not.toHaveTextContent(/trending|regressing/i);
    }
    expect(screen.getByTestId("lever-adoption")).toHaveTextContent(
      /timeline features are unavailable in the Findings Pack/i,
    );
    expect(screen.getByTestId("lever-adoption")).not.toHaveTextContent(/lands in the Findings Pack/i);
  });

  it("shows the unavailable what-if state without fabricated personal estimates", async () => {
    renderPage(<ProgressPage />);

    const panel = await screen.findByTestId("what-if-panel");
    expect(screen.getByTestId("what-if-caption")).toHaveTextContent(
      "Personal what-if estimates are unavailable because the Honest Model contract is absent.",
    );
    expect(panel).toHaveTextContent("Unavailable");
    expect(panel).not.toHaveTextContent(/ships/);
    expect(panel).not.toHaveTextContent("−280g");
    expect(panel).not.toHaveTextContent("1 of 6");
    expect(panel).not.toHaveTextContent("62%");
    expect(screen.getByTestId("what-if-prediction")).toHaveTextContent("Unavailable");
  });

  it("renders the patch win-rate sparkline from true patch aggregates", async () => {
    renderPage(<ProgressPage />);

    const chart = await screen.findByTestId("rolling-wr-svg");
    expect(chart.querySelector("polyline")).toBeInTheDocument();
    const wrap = screen.getByTestId("rolling-wr-chart");
    expect(within(wrap).getByText("14.17")).toBeInTheDocument();
    expect(within(wrap).getByText("16.16")).toBeInTheDocument();
    expect(within(wrap).getByText(/30 synced games|30/)).toBeInTheDocument();
    expect(api.trajectories).not.toHaveBeenCalled();
  });

  it("shows the honest empty state when no games are tracked", async () => {
    vi.mocked(api.patchAggregates).mockResolvedValue([]);
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

  it("replaces the speculative deaths-by-minute roadmap copy with an unavailable reason", async () => {
    renderPage(<ProgressPage />);

    const panel = await screen.findByTestId("deaths-panel");
    expect(panel).toHaveTextContent(
      "Unavailable: timeline features are not in the Findings Pack",
    );
    expect(panel).not.toHaveTextContent(/lands|ships/);
    // Backfill remains the named remediation source.
    expect(panel).toHaveTextContent(/sync games from the History tab/i);
  });
});
