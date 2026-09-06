import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ProgressPage } from "../progress";
import { api } from "../../api/client";
import type { BenchmarkResponse, Settings } from "../../api/types";
import { makePack as makeV2Pack } from "./fixtures";

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

const evidenceMetadata = {
  patch_range: { min: "14.17", max: "16.17" },
  population_scope: "fixture v2 pooled population",
  era_stability: "stable",
  caveats: ["Observational association; fixture only."],
  source_document: "fixture",
  source_section: "findings",
  source_ref: "fixture#findings",
  provenance_key: "findings",
} as const;

function makePack(overrides: Record<string, unknown> = {}) {
  return makeV2Pack({
    findings: [
      {
        ...evidenceMetadata,
        key: "lane_conversion",
        tier: "actionable",
        release_status: "available",
        title: "Lane conversion",
        statement: "Real cases turned +121g@10 lane leads into 42.7% win rates.",
        metric_kind: "percentage_points",
        unit: "pp",
        sample: 1000,
        value: 0.427,
      },
    ],
    ...overrides,
  });
}

const activeSettings: Settings = {
  owner_key: "fixture-owner",
  generation: 1,
  owner_state: "active",
  owner_error: null,
  riot_id: "Fixture#EUW",
  region_route: "europe",
  has_key: true,
  auto_sync: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.settings).mockResolvedValue(activeSettings);
  vi.mocked(api.trajectories).mockResolvedValue(points);
  vi.mocked(api.patchAggregates).mockResolvedValue(aggregates);
  vi.mocked(api.historySummary).mockResolvedValue(summary);
  vi.mocked(api.benchmarks).mockResolvedValue(benchmarks);
  vi.mocked(api.postgameLatest).mockResolvedValue(null);
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


  it("withholds lever adoption when canonical habit evidence is absent", async () => {
    renderPage(<ProgressPage />);

    expect(await screen.findByTestId("habit-evidence-unavailable")).toHaveTextContent(
      "compatible v2 habit evidence unavailable",
    );
    expect(screen.queryByTestId("habit-row-recall_safety")).not.toBeInTheDocument();
    expect(screen.queryByTestId("habit-row-fast_first_dragon")).not.toBeInTheDocument();
    expect(screen.queryByTestId("habit-row-spend_before_backing")).not.toBeInTheDocument();
    expect(screen.queryByTestId("habit-row-plates_by_14")).not.toBeInTheDocument();
    expect(screen.getByTestId("lever-adoption")).toHaveTextContent("Findings Pack v2");
    expect(screen.getByTestId("lever-adoption")).toHaveTextContent(/population associations/i);
  });

  it("shows the unavailable what-if state without fabricated personal estimates", async () => {
    renderPage(<ProgressPage />);

    const panel = await screen.findByTestId("what-if-panel");
    await waitFor(() =>
      expect(screen.getByTestId("what-if-caption")).toHaveTextContent(
        /personal what-if estimates are unavailable because onnx artifact.*not present/i,
      ),
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
    expect(screen.getByText(/shipped population corpus/)).toBeInTheDocument();
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
