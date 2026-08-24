import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ChampionsPage } from "../champions";
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

const pack = {
  schema_version: 1,
  generated_at: "2026-08-01T00:00:00Z",
  dataset: { matches: 26036, player_games: 260360, patches: ["14.17", "16.16"] },
  findings: [
    {
      key: "damage_fit_comp",
      tier: "actionable" as const,
      title: "Damage fit",
      statement: "Pair your champion with a frontline before locking in.",
      value: 3.7,
      unit: "pp",
      source_ref: "companion-app-content.md#7",
    },
    {
      key: "mastery_premium",
      tier: "diagnostic" as const,
      title: "Mastery premium",
      statement: "Experienced players gained 3.7 pp per SD of mastery.",
      value: 3.7,
      unit: "pp",
      source_ref: "companion-app-content.md#2",
    },
  ],
  habits: [],
  objectives: {},
  comeback_odds: [],
  ban_advisor: [],
  trap_picks: [
    { champion: "Hecarim", win_rate: 0.415 },
    { champion: "Skarner", win_rate: 0.448 },
  ],
  tier_list: [
    { champion: "Thresh", role: "UTILITY", games: 340, pick_rate: 0.142, win_rate: 0.534, tier: "S" as const },
    { champion: "Ahri", role: "MIDDLE", games: 300, pick_rate: 0.13, win_rate: 0.52, tier: "A" as const },
    { champion: "Yasuo", role: "MIDDLE", games: 280, pick_rate: 0.19, win_rate: 0.485, tier: "C" as const },
  ],
  matchup_examples: [
    { champion: "Ahri", opponent: "Zed", role: "MIDDLE", wr: 0.57, ci: 2.1, games: 41 },
    { champion: "Ahri", opponent: "Yasuo", role: "MIDDLE", wr: 0.44, ci: 1.8, games: 33 },
  ],
  benchmarks: [],
  checkpoints: [],
};

// ADR-0003 phrasing discipline: the trap-picks card is Diagnostic — it must
// describe, never instruct. No imperative verbs allowed anywhere in its text.
const IMPERATIVE_RE =
  /\b(avoid|ban|pick|play|try|consider|use|stop|start|don't|dont|do not|stop picking)\b/i;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.pack).mockResolvedValue(pack);
});

describe("ChampionsPage", () => {
  it("groups the tier list by the active role chip", async () => {
    renderPage(<ChampionsPage />);

    expect(await screen.findByText("Thresh")).toBeInTheDocument();
    expect(screen.getByTestId("role-MIDDLE")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("role-MIDDLE"));

    await waitFor(() => expect(screen.queryByText("Thresh")).not.toBeInTheDocument());
    const list = screen.getByTestId("tier-list");
    expect(within(list).getByText("Ahri")).toBeInTheDocument();
    expect(within(list).getByText("Yasuo")).toBeInTheDocument();
  });

  it("renders S/A/B/C tier badges with rates and games", async () => {
    renderPage(<ChampionsPage />);

    const list = await screen.findByTestId("tier-list");
    expect(within(list).getByText("S")).toBeInTheDocument();
    expect(within(list).getByText("A")).toBeInTheDocument();
    expect(within(list).getByText("C")).toBeInTheDocument();
    expect(within(list).getAllByText(/\d+g$/).length).toBeGreaterThan(0);
  });

  it("shows the trap picks card with DIAGNOSTIC framing only (no imperatives)", async () => {
    renderPage(<ChampionsPage />);

    const card = await screen.findByTestId("card-trap-picks");
    expect(card).toHaveTextContent("Hecarim");
    expect(card).toHaveTextContent("Skarner");
    expect(card).toHaveTextContent(/looks strong, isn't/i);
    expect(within(card).getByText(/diagnostic/i)).toBeInTheDocument();

    const text = card.textContent ?? "";
    const offenders = text.match(new RegExp(IMPERATIVE_RE.source, "gi"));
    expect(offenders, `diagnostic copy must not instruct; found: ${offenders?.join(", ")}`).toBeNull();
  });

  it("splits matchups into you-counter / counters-you with wr±ci and games", async () => {
    renderPage(<ChampionsPage />);

    const youCounter = await screen.findByTestId("you-counter-list");
    expect(within(youCounter).getByText("Zed")).toBeInTheDocument();
    expect(within(youCounter).getByText("57.0% ±2.1")).toBeInTheDocument();
    expect(within(youCounter).getByText("41g")).toBeInTheDocument();

    const countersYou = screen.getByTestId("counters-you-list");
    expect(within(countersYou).getByText("Yasuo")).toBeInTheDocument();
    expect(within(countersYou).getByText("44.0% ±1.8")).toBeInTheDocument();
  });

  it("renders comp advice from findings honoring tier tags", async () => {
    renderPage(<ChampionsPage />);

    const findings = await screen.findByTestId("comp-findings");
    expect(findings).toHaveTextContent("Pair your champion with a frontline before locking in.");
    expect(within(findings).getByText("advice")).toBeInTheDocument();
    // diagnostic finding is filtered out of the comp-advice card
    expect(findings).not.toHaveTextContent("Mastery premium");
  });

  it("carries the population caveat footer once", async () => {
    renderPage(<ChampionsPage />);
    await screen.findByTestId("tier-list");
    expect(screen.getAllByTestId("population-caveat")).toHaveLength(1);
    expect(screen.getByText(/friend group's 26k games/)).toBeInTheDocument();
  });
});
