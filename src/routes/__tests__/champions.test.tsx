import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ChampionsPage } from "../champions";
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

function makePack(overrides: Partial<FindingsPack> = {}): FindingsPack {
  return {
    schema_version: 1,
    comeback_feature_contract: {
      feature: "gold_diff_15",
      feature_contract_version: "loltrends-parity-v1",
    },
    pack_version: "v1",
    generated_at: "2026-08-01T00:00:00Z",
    provenance: {} as FindingsPack["provenance"],
    dataset: { matches: 26036, player_games: 260360, patches: ["14.17", "16.16"] },
    findings: [],
    habits: [],
    objectives: {},
    comeback_odds: [],
    ban_advisor: [],
    trap_picks: [{ champion: "Qiyana", win_rate: 0.4233 }],
    tier_list: [
      { champion: "Ahri", role: "MIDDLE", games: 340, pick_rate: 0.142, win_rate: 0.534, tier: "S" },
      { champion: "Qiyana", role: "MIDDLE", games: 200, pick_rate: 0.05, win_rate: 0.4233, tier: "B" },
      { champion: "Darius", role: "TOP", games: 610, pick_rate: 0.224, win_rate: 0.517, tier: "A" },
      { champion: "Garen", role: "TOP", games: 500, pick_rate: 0.2, win_rate: 0.51, tier: "A" },
    ],
    matchup_examples: [
      { champion: "Ahri", opponent: "Zed", role: "MIDDLE", wr: 0.57, ci: 2.1, games: 41 },
      { champion: "Ahri", opponent: "Yasuo", role: "MIDDLE", wr: 0.44, ci: 1.8, games: 33 },
      { champion: "Qiyana", opponent: "Qiyana", role: "MIDDLE", wr: 0.9, ci: 1, games: 1 },
      { champion: "Darius", opponent: "Garen", role: "TOP", wr: 0.4098, ci: 8.7, games: 42 },
      { champion: "Garen", opponent: "Darius", role: "TOP", wr: 0.5902, ci: 8.7, games: 42 },
      { champion: "Darius", opponent: "Darius", role: "TOP", wr: 0.5, ci: 0, games: 1 },
    ],
    benchmarks: [],
    checkpoints: [],
    ...overrides,
  };
}

const IMPERATIVE_RE =
  /\b(avoid|ban|pick|play|try|consider|use|stop|start|don't|dont|do not)\b/i;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.pack).mockResolvedValue(makePack());
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
    fireEvent.keyDown(row, { key: "Enter" });

    expect(row).toHaveFocus();
    expect(row).toHaveAttribute("aria-pressed", "true");
    const header = await screen.findByTestId("champion-header");
    expect(header).toHaveTextContent("Ahri");
    expect(screen.getByText("Ahri selected for MIDDLE")).toBeInTheDocument();
    // Champion Evidence header rates are Findings Pack population data: blue.
    for (const stat of within(header).getAllByText(/^\d+(?:\.\d)%$/)) {
      expect(stat).toHaveStyle({ color: "var(--color-info)" });
    }
    // A missing population ban rate names its unavailability instead of a dash.
    expect(within(header).getByText("Unavailable: ban rate unavailable")).toBeInTheDocument();
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
    expect(card).toHaveTextContent("FAVORABLE EXAMPLES FOR DARIUS");
    expect(card).toHaveTextContent("DIFFICULT EXAMPLES FOR DARIUS");
    expect(card).toHaveTextContent("Darius vs Garen");
    expect(card).toHaveTextContent("41.0% ±8.7 pp · 42 games");
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
      "Unavailable: the Findings Pack carries no item-sequence features",
    );
    expect(card).not.toHaveTextContent(/lands after|arrives|ships/);
  });
});
