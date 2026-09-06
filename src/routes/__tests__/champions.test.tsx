import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import type { Settings } from "../../api/types";
import { ChampionsPage } from "../champions";
import { api } from "../../api/client";
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

const evidenceMetadata = {
  patch_range: { min: "14.17", max: "16.17" },
  population_scope: "fixture v2 pooled population",
  era_stability: "stable",
  caveats: ["Observational association; fixture only."],
  source_document: "fixture",
  source_section: "fixture evidence",
  source_ref: "fixture#v2",
  provenance_key: "fixture",
  metric_kind: "win_rate",
  unit: "rate",
} as const;

const tierRows = [
  { champion: "Ahri", role: "MIDDLE", games: 600, observed_win_rate: 0.534, role_pick_rate: 0.142, rank_band: "S" },
  { champion: "Qiyana", role: "MIDDLE", games: 500, observed_win_rate: 0.4233, role_pick_rate: 0.05, rank_band: "B" },
  { champion: "Darius", role: "TOP", games: 610, observed_win_rate: 0.517, role_pick_rate: 0.224, rank_band: "A" },
  { champion: "Garen", role: "TOP", games: 500, observed_win_rate: 0.51, role_pick_rate: 0.2, rank_band: "A" },
].map((row) => ({
  ...evidenceMetadata,
  ...row,
  minimum_games: 500,
  tier: "diagnostic",
  release_status: "available",
}));

const matchupRows = [
  { champion: "Ahri", opponent: "Zed", role: "MIDDLE", games: 41, estimate: 0.57, lower: 0.48, upper: 0.66 },
  { champion: "Ahri", opponent: "Yasuo", role: "MIDDLE", games: 33, estimate: 0.44, lower: 0.35, upper: 0.53 },
  { champion: "Darius", opponent: "Garen", role: "TOP", games: 42, estimate: 0.5902, lower: 0.503, upper: 0.677 },
  { champion: "Darius", opponent: "Teemo", role: "TOP", games: 42, estimate: 0.4098, lower: 0.323, upper: 0.497 },
].map((row) => ({
  ...evidenceMetadata,
  ...row,
  interval: { lower: row.lower, upper: row.upper, include_lower: true, include_upper: false },
  tier: "diagnostic",
  release_status: "available",
}));

function makePack(overrides: Record<string, unknown> = {}) {
  return makeV2Pack({
    tier_list: tierRows,
    matchup_examples: matchupRows,
    ...overrides,
  });
}

const IMPERATIVE_RE =
  /\b(avoid|ban|pick|play|try|consider|use|stop|start|don't|dont|do not)\b/i;
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
  vi.mocked(api.pack).mockResolvedValue(makePack());
  vi.mocked(api.settings).mockResolvedValue(activeSettings);
  vi.mocked(api.trajectories).mockResolvedValue([]);
  vi.mocked(api.patchAggregates).mockResolvedValue([]);
});

describe("ChampionsPage", () => {
  it("starts with no champion header or directional claim", async () => {
    renderPage(<ChampionsPage />);

    await screen.findByTestId("tier-list");
    expect(screen.queryByTestId("champion-header")).not.toBeInTheDocument();
    expect(screen.getByTestId("matchups-card")).toHaveTextContent(
      "Select a champion to see directional examples.",
    );
    expect(api.trajectories).not.toHaveBeenCalled();
    expect(api.patchAggregates).not.toHaveBeenCalled();
  });

  it("selects the exact tier row and announces it", async () => {
    renderPage(<ChampionsPage />);
    const row = await screen.findByRole("button", { name: /Ahri, S tier/i });

    row.focus();
    fireEvent.click(row);

    expect(row).toHaveFocus();
    expect(row).toHaveAttribute("aria-pressed", "true");
    const header = await screen.findByTestId("champion-header");
    expect(header).toHaveTextContent("Ahri");
    expect(screen.getByText("Ahri selected for MIDDLE")).toBeInTheDocument();
    // Champion Evidence header rates are Findings Pack population data: blue.
    for (const stat of within(header).getAllByText(/^\d+(?:\.\d)%$/)) {
      expect(stat).toHaveStyle({ color: "var(--color-info)" });
    }
  });

  it("clears selected champion and claims when the role changes", async () => {
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("tier-row-Ahri"));
    await screen.findByTestId("champion-header");

    fireEvent.click(screen.getByTestId("role-TOP"));

    await waitFor(() => expect(screen.queryByTestId("champion-header")).not.toBeInTheDocument());
    expect(screen.getByTestId("matchups-card")).toHaveTextContent(
      "Select a champion to see directional examples.",
    );
    expect(screen.getByTestId("trajectory-selection-guidance")).toBeInTheDocument();
  });

  it("filters matchup evidence directionally without relabeling reverse rows", async () => {
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("role-TOP"));
    fireEvent.click(await screen.findByTestId("tier-row-Darius"));

    const card = await screen.findByTestId("matchups-card");
    expect(card).toHaveTextContent("HIGHER OBSERVED ESTIMATES FOR DARIUS");
    expect(card).toHaveTextContent("LOWER OBSERVED ESTIMATES FOR DARIUS");
    expect(card).toHaveTextContent("Darius vs Garen");
    expect(card).toHaveTextContent("59.0% · 50.3%–67.7% · 42 games");
    expect(card).toHaveTextContent("Darius vs Teemo");
    expect(card).toHaveTextContent("41.0% · 32.3%–49.7% · 42 games");
    expect(card).not.toHaveTextContent("Garen vs Darius");
    expect(card).not.toHaveTextContent("Darius vs Darius");
    expect(card).toHaveTextContent("Findings Pack · matchup_examples");
    // Both directions are population evidence: blue rows, outcome words only.
    for (const bar of within(card).getAllByTestId(/^matchup-bar-/)) {
      expect(bar).toHaveStyle({ background: "var(--color-info)" });
    }
  });

  it("shows directional empty copy without numbers for a champion with no direction", async () => {
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("tier-row-Qiyana"));

    const card = await screen.findByTestId("matchups-card");
    expect(card).toHaveTextContent(
      "The current Findings Pack has no directional example for Qiyana.",
    );
    expect(within(card).queryByText(/%|games|±/)).not.toBeInTheDocument();
  });

  it("passes identical selected role and champion filters to both progress sources", async () => {
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("tier-row-Ahri"));

    await waitFor(() => {
      expect(api.trajectories).toHaveBeenCalledWith({ role: "MIDDLE", champion: "Ahri" });
      expect(api.patchAggregates).toHaveBeenCalledWith({ role: "MIDDLE", champion: "Ahri" });
    });
  });

  it("keeps every rolling point and displays aggregate values separately", async () => {
    vi.mocked(api.trajectories).mockResolvedValue([
      { patch: "16.16", role: "MIDDLE", champion: "Ahri", played_at: "2026-02-03T00:00:00Z", index: 2, rolling_wr: 0.4 },
      { patch: "14.17", role: "MIDDLE", champion: "Ahri", played_at: "2026-01-01T00:00:00Z", index: 0, rolling_wr: 0.6 },
      { patch: "14.17", role: "MIDDLE", champion: "Ahri", played_at: "2026-01-02T00:00:00Z", index: 1, rolling_wr: 0.55 },
    ]);
    vi.mocked(api.patchAggregates).mockResolvedValue([
      { patch: "14.17", games: 2, wins: 1, win_rate: 0.5 },
      { patch: "16.16", games: 1, wins: 0, win_rate: 0 },
    ]);
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("tier-row-Ahri"));

    const card = await screen.findByTestId("trajectory-card");
    await waitFor(() => expect(card.querySelector("polyline")).toHaveAttribute("points", "0,30 150,33 300,42"));
    expect(screen.getByTestId("trajectory-aggregates")).toHaveTextContent("1 wins · 2 games · 50.0%");
    expect(screen.getByTestId("trajectory-aggregates")).toHaveTextContent("0 wins · 1 games · 0.0%");
    expect(card).not.toHaveTextContent(/item timing|Data.?Dragon|item-completion/i);
  });

  it("renders Backfill for empty Personal History while keeping matchup data visible", async () => {
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("tier-row-Ahri"));

    expect(await screen.findByTestId("trajectory-empty")).toHaveTextContent("Backfill");
    expect(screen.getByTestId("matchups-card")).toHaveTextContent("Ahri vs Zed");
  });

  it("keeps diagnostic matchup copy descriptive", async () => {
    renderPage(<ChampionsPage />);
    fireEvent.click(await screen.findByTestId("tier-row-Ahri"));
    const card = await screen.findByTestId("matchups-card");
    expect(card.textContent).not.toMatch(IMPERATIVE_RE);
  });

  it("names the build-order gap as an unavailable pack feature, not roadmap speculation", async () => {
    renderPage(<ChampionsPage />);

    const card = await screen.findByTestId("build-order-card");
    expect(card).toHaveTextContent(
      "Unavailable: Controlled champion/role/patch/purchase-opportunity comparison unavailable",
    );
    expect(card).not.toHaveTextContent(/lands after|arrives|ships/);
  });

  it("shows approximate route context without ranking or recommendation language", async () => {
    renderPage(<ChampionsPage />);

    const card = await screen.findByTestId("route-archetypes-card");
    expect(card).toHaveTextContent("ROUTE ARCHETYPES · DESCRIPTIVE");
    expect(card).toHaveTextContent(/observed win rate/i);
    expect(card).toHaveTextContent(/descriptive only/i);
    expect(card.textContent).not.toMatch(/\b(avoid|ban|pick|play|try|consider|stop|start|don't|dont|do not)\b/i);
  });
});
