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
    generated_at: "2026-08-01T00:00:00Z",
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
    ],
    matchup_examples: [
      { champion: "Ahri", opponent: "Zed", role: "MIDDLE", wr: 0.57, ci: 2.1, games: 41 },
      { champion: "Ahri", opponent: "Yasuo", role: "MIDDLE", wr: 0.44, ci: 1.8, games: 33 },
    ],
    benchmarks: [],
    checkpoints: [],
    ...overrides,
  };
}

// ADR-0003 phrasing discipline: the matchups caveat is Diagnostic — it must
// describe, never instruct.
const IMPERATIVE_RE =
  /\b(avoid|ban|pick|play|try|consider|use|stop|start|don't|dont|do not)\b/i;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.pack).mockResolvedValue(makePack());
  vi.mocked(api.trajectories).mockResolvedValue([
    { patch: "14.17", role: "MIDDLE", champion: null, games: 10, wins: 6, rolling_wr: 0.6 },
    { patch: "16.16", role: "MIDDLE", champion: null, games: 12, wins: 5, rolling_wr: 0.42 },
  ]);
});

describe("ChampionsPage", () => {
  it("renders the champion header from the first tier_list entry of the selected role", async () => {
    vi.mocked(api.pack).mockResolvedValue(
      makePack({
        ban_advisor: [
          { champion: "Ahri", win_rate: 0.534, ban_rate: 0.061, recommendation: "real-threat" },
        ],
      }),
    );
    renderPage(<ChampionsPage />);

    const header = await screen.findByTestId("champion-header");
    expect(within(header).getByText("Ahri")).toBeInTheDocument();
    expect(within(header).getByText("S tier")).toBeInTheDocument();
    expect(within(header).getByText("Middle · 340 games logged")).toBeInTheDocument();
    expect(within(header).getByText("14.2%")).toBeInTheDocument(); // pick
    expect(within(header).getByText("6.1%")).toBeInTheDocument(); // ban, from pack.ban_advisor
    expect(within(header).getByText("53.4%")).toBeInTheDocument(); // win
  });

  it("shows an em-dash ban cell when the pack carries no ban rate for the champion", async () => {
    renderPage(<ChampionsPage />);

    const header = await screen.findByTestId("champion-header");
    const banCell = within(header).getByText("BAN").parentElement!;
    expect(banCell).toHaveTextContent("—");
  });

  it("renders the item spike timing slot with the rolling-wr sparkline per patch", async () => {
    renderPage(<ChampionsPage />);

    const card = await screen.findByTestId("item-spike-card");
    expect(card.querySelector("polyline")).toBeInTheDocument();
    expect(within(card).getByText("14.17")).toBeInTheDocument();
    expect(within(card).getByText("16.16")).toBeInTheDocument();
  });

  it("filters header, tier list and matchups by role chip", async () => {
    renderPage(<ChampionsPage />);

    fireEvent.click(await screen.findByTestId("role-TOP"));

    await waitFor(() =>
      expect(screen.getByTestId("champion-header")).toHaveTextContent("Darius"),
    );
    const list = screen.getByTestId("tier-list");
    expect(within(list).getByText("Darius")).toBeInTheDocument();
    expect(within(list).queryByText("Ahri")).not.toBeInTheDocument();
    // no TOP matchups in the pack -> honest empty lines, no invented rows
    expect(screen.getByTestId("you-counter-list")).toHaveTextContent(/no clear edges/i);
  });

  it("splits matchups into you-counter / counters-you with wr ± ci and games", async () => {
    renderPage(<ChampionsPage />);

    const youCounter = await screen.findByTestId("you-counter-list");
    expect(within(youCounter).getByText("Zed")).toBeInTheDocument();
    expect(within(youCounter).getByText("57.0% ±2.1 · 41g")).toBeInTheDocument();

    const countersYou = screen.getByTestId("counters-you-list");
    expect(within(countersYou).getByText("Yasuo")).toBeInTheDocument();
    expect(within(countersYou).getByText("44.0% ±1.8 · 33g")).toBeInTheDocument();
  });

  it("renders real tier rows with the trap tag for pack trap picks", async () => {
    renderPage(<ChampionsPage />);

    const list = await screen.findByTestId("tier-list");
    expect(within(list).getByText("Ahri")).toBeInTheDocument();
    const qiyanaRow = within(list).getByText("Qiyana").closest("div")!;
    expect(qiyanaRow).toHaveTextContent("42.3%");
    expect(qiyanaRow).toHaveTextContent("· trap");
    // non-trap rows carry no trap tag
    const ahriRow = within(list).getByText("Ahri").closest("div")!;
    expect(ahriRow).not.toHaveTextContent("trap");
  });

  it("keeps the build-order card idle with its approximate-v1 caveat", async () => {
    renderPage(<ChampionsPage />);

    const card = await screen.findByTestId("build-order-card");
    expect(card).toHaveTextContent(/build analytics land after the data-dragon item refresh/i);
    expect(card).toHaveTextContent(/treat as approximate v1/i);
    // no invented build rows
    expect(within(card).queryByText(/Everfrost/i)).not.toBeInTheDocument();
  });

  it("renders comp, damage-fit and gold-waste cards when the pack carries them", async () => {
    vi.mocked(api.pack).mockResolvedValue(
      makePack({
        findings: [
          {
            key: "comp_ad_heavy",
            tier: "diagnostic",
            title: "AD-heavy comp",
            statement: "AD-heavy comps win 57% against this champion's pool.",
            value: 0.57,
            unit: "%",
            source_ref: "companion-app-content.md#5",
          },
          {
            key: "damage_fit",
            tier: "actionable",
            title: "Damage fit",
            statement: "Your AP burst lines up against their weaker resist axis.",
            value: 0.71,
            unit: null,
            source_ref: "companion-app-content.md#6",
          },
          {
            key: "gold_waste",
            tier: "diagnostic",
            title: "Gold waste",
            statement: "Average gold wasted per completed item.",
            value: 340,
            unit: "g",
            source_ref: "companion-app-content.md#8",
          },
        ],
      }),
    );
    renderPage(<ChampionsPage />);

    expect(await screen.findByTestId("comp-card")).toHaveTextContent("57%");
    expect(screen.getByTestId("damage-fit-card")).toHaveTextContent("0.71");
    expect(screen.getByTestId("gold-waste-card")).toHaveTextContent("340g");
  });

  it("omits comp / damage-fit / gold-waste cards when the pack lacks them", async () => {
    renderPage(<ChampionsPage />);
    await screen.findByTestId("champion-header");

    expect(screen.queryByTestId("comp-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("damage-fit-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("gold-waste-card")).not.toBeInTheDocument();
  });

  it("does not mistake the ban_waste_correlation finding for gold waste", async () => {
    vi.mocked(api.pack).mockResolvedValue(
      makePack({
        findings: [
          {
            key: "ban_waste_correlation",
            tier: "diagnostic",
            title: "Most bans are wasted",
            statement: "Ban-rate vs win-rate correlation is only +0.125.",
            value: 0.125,
            unit: "correlation",
            source_ref: "companion-app-content.md#9",
          },
        ],
      }),
    );
    renderPage(<ChampionsPage />);
    await screen.findByTestId("champion-header");

    expect(screen.queryByTestId("gold-waste-card")).not.toBeInTheDocument();
  });

  it("carries the population caveat footer once", async () => {
    renderPage(<ChampionsPage />);
    await screen.findByTestId("champion-header");

    expect(screen.getAllByTestId("population-caveat")).toHaveLength(1);
    expect(screen.getByText(/friend group's 26k games/)).toBeInTheDocument();
  });

  it("keeps diagnostic caveats descriptive only (ADR-0003)", async () => {
    renderPage(<ChampionsPage />);
    const card = await screen.findByTestId("matchups-card");

    const text = card.textContent ?? "";
    const offenders = text.match(new RegExp(IMPERATIVE_RE.source, "gi"));
    expect(offenders, `diagnostic copy must not instruct; found: ${offenders?.join(", ")}`).toBeNull();
  });
});
