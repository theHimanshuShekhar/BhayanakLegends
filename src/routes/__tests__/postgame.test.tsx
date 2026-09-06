import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PostGamePage } from "../postgame";
import { api } from "../../api/client";
import type { PostGameDigest, Settings } from "../../api/types";
import { makePack } from "./fixtures";
import { matchComebackBucket } from "../../components/postgame/ComebackOddsCard";

vi.mock("../../api/client", () => ({
  eventsUrl: vi.fn(async () => "http://127.0.0.1:23110/events?token=fixture-token"),
  api: {
    pack: vi.fn(),
    settings: vi.fn(),
    postgameLatest: vi.fn(),
  },
}));

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <PostGamePage />
    </QueryClientProvider>,
  );
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

const digest: PostGameDigest = {
  match_id: "EUW1_123",
  played_at: "2026-08-23T21:04:00Z",
  champion: "Thresh",
  role: "UTILITY",
  win: false,
  duration_s: 1992,
  checkpoints: { gold_diff_10: 450, gold_diff_15: -1200, gold_diff_20: null },
  habits: [
    { key: "recall_safety", label: "Recall safely", value: "92%", verdict: "good" },
    { key: "plates_by_14", label: "Plates by 14", value: "1", verdict: "bad" },
    { key: "fast_first_dragon", label: "Fast first dragon", value: "—", verdict: "n/a" },
  ],
  headline: "Your early lead came from clean recalls around plate windows.",
  feature_contract_version: "loltrends-parity-v2",
  personal_history_eligibility: "eligible",
  features: { team_gold_diff_15m: -1200 },
  team_state: {
    feature: "team_gold_diff_15m",
    feature_contract_version: "loltrends-parity-v2",
    team_gold_diff_15m: -1200,
    observed_through_s: 1992,
    non_surrendered: true,
  },
};

function digestAt(gold15: number | null): PostGameDigest {
  return {
    ...digest,
    checkpoints: { ...digest.checkpoints, gold_diff_15: gold15 },
    features: { team_gold_diff_15m: gold15 },
    team_state: {
      ...digest.team_state!,
      team_gold_diff_15m: gold15,
    },
  };
}

function packWithAvailableComebackRates() {
  const base = makePack();
  return makePack({
    comeback_odds: base.comeback_odds.map((row, index) => ({
      ...row,
      release_status: "available",
      release_reason: null,
      rate: [0.276, 0.076, 0.03][index],
      sample: 1000,
    })),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.settings).mockResolvedValue(activeSettings);
  vi.mocked(api.pack).mockResolvedValue(makePack());
  vi.mocked(api.postgameLatest).mockResolvedValue(null);
});

describe("PostGamePage", () => {
  it("keeps the window chrome and shows the idle banner without a digest", async () => {
    renderPage();
    expect(await screen.findByTestId("empty-state")).toHaveTextContent(
      "No games analyzed yet — Backfill from History",
    );
    expect(screen.getByTestId("verdict")).toHaveTextContent("No game analyzed");
    expect(screen.getByText(/post-game review · the 30 seconds after the game/i)).toBeInTheDocument();
  });

  it("renders the v2 digest verdict and checkpoints", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(digest);
    renderPage();

    expect(await screen.findByText("Defeat")).toBeInTheDocument();
    expect(screen.getByTestId("verdict-sub")).toHaveTextContent("Thresh · UTILITY · 33:12");
    expect(screen.getByTestId("verdict-header").textContent).toContain("TH");
    expect(screen.getByTestId("checkpoint-10")).toHaveTextContent("+450g");
    expect(screen.getByTestId("checkpoint-15")).toHaveTextContent("-1,200g");
    expect(screen.getByTestId("checkpoint-20")).toHaveTextContent("Unavailable: gold checkpoint not reported");
  });

  it("renders habit outcomes and digest headline without population substitution", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(digest);
    renderPage();

    expect(await screen.findByText(digest.headline)).toBeInTheDocument();
    expect(screen.getByTestId("habit-recall_safety")).toHaveTextContent("good");
    expect(screen.getByTestId("habit-plates_by_14")).toHaveTextContent("bad");
    expect(screen.getByTestId("habit-fast_first_dragon")).toHaveTextContent("n/a");
  });
  it("renders early-fight, local-team dragon, and plate observations separately", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue({
      ...digest,
      habits: [],
      features: {
        early_fight_participation_rate: 0.4,
        first_dragon_by_20m_s: 512,
        plates_taken_by_14m: 2,
      },
    });
    renderPage();

    const observations = await screen.findByTestId("habit-feature-observations");
    expect(observations).toHaveTextContent("Early-fight participation");
    expect(observations).toHaveTextContent("40.0%");
    expect(observations).toHaveTextContent("First local-team dragon timing");
    expect(observations).toHaveTextContent("8:32");
    expect(observations).toHaveTextContent("Plates taken by 14 minutes");
    expect(observations).toHaveTextContent("2 plates");
    expect(observations).toHaveTextContent(/Timing association only/i);
    expect(observations).toHaveTextContent(/Diagnostic · era-sensitive/i);
    expect(observations).not.toHaveTextContent(/fight more|take dragon|must/i);
  });

  it("shows v2 objective rates and withholds comeback bands when exact cohorts are unavailable", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(digest);
    renderPage();

    await screen.findByText("Defeat");
    await waitFor(() => expect(screen.getByTestId("read-dragon")).toHaveTextContent("60.3%"));
    expect(screen.getByTestId("read-herald")).toHaveTextContent("66.6%");
    expect(screen.getByTestId("read-baron")).toHaveTextContent("81.4%");
    expect(screen.getByTestId("comeback-value")).toHaveTextContent("Unavailable: no supported population band");
    expect(screen.getByTestId("comeback-note")).toHaveTextContent(/minimum 2,000g cohort/i);
    expect(screen.getByTestId("surrender-read")).toHaveTextContent(/release check failed/i);
  });

  it("reports a matching v2 comeback band as withheld instead of inventing a rate", async () => {
    const match = matchComebackBucket(makePack(), digestAt(-2500));
    expect(match).toEqual({ match: null, reason: "withheld" });

    vi.mocked(api.postgameLatest).mockResolvedValue(digestAt(-2500));
    renderPage();
    const card = await screen.findByTestId("comeback-card");
    await waitFor(() =>
      expect(within(card).getByTestId("comeback-value")).toHaveTextContent(
        "Unavailable: population band withheld",
      ),
    );
    expect(within(card).getByTestId("comeback-note")).toHaveTextContent(/exact team-state exposures are unavailable/i);
  });

  it("uses the canonical half-open v2 team-deficit bands", () => {
    const pack = packWithAvailableComebackRates();
    const cases = [
      [-2000, "[2,000g, 3,000g)", 0.276],
      [-2999.5, "[2,000g, 3,000g)", 0.276],
      [-3000, "[3,000g, 5,000g)", 0.076],
      [-4999.5, "[3,000g, 5,000g)", 0.076],
      [-5000, "[5,000g, ∞)", 0.03],
    ] as const;
    for (const [gold15, rangeLabel, winRate] of cases) {
      const result = matchComebackBucket(pack, digestAt(gold15));
      expect(result.reason).toBeNull();
      expect(result.match).toEqual({ winRate, rangeLabel });
    }
  });

  it("suppresses non-deficits, shallow deficits, and ineligible observations", () => {
    const pack = packWithAvailableComebackRates();
    expect(matchComebackBucket(pack, digestAt(null))).toEqual({ match: null, reason: "missing-personal-history" });
    expect(matchComebackBucket(pack, digestAt(100))).toEqual({ match: null, reason: "not-a-deficit" });
    expect(matchComebackBucket(pack, digestAt(-1999.5))).toEqual({ match: null, reason: "outside-domain" });
    expect(
      matchComebackBucket(pack, {
        ...digestAt(-2500),
        personal_history_eligibility: "ineligible",
      }),
    ).toEqual({ match: null, reason: "ineligible-observation" });
  });
});
