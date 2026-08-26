import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PostGamePage } from "../postgame";
import { api } from "../../api/client";
import { makePack } from "./fixtures";
import { matchComebackBucket } from "../../components/postgame/ComebackOddsCard";
import { pct } from "../../components/ui";

vi.mock("../../api/client", () => ({
  eventsUrl: vi.fn(
    async () =>
      "http://127.0.0.1:23110/events?token=local-sidecar-development-token-32chars",
  ),
  api: {
    pack: vi.fn(),
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

const digest = {
  match_id: "EUW1_123",
  played_at: "2026-08-23T21:04:00Z",
  champion: "Thresh",
  role: "UTILITY" as const,
  win: false,
  duration_s: 1992,
  checkpoints: { gold_diff_10: 450, gold_diff_15: -1200, gold_diff_20: null },
  habits: [
    { key: "recall_safety", label: "Recall safely", value: "92%", verdict: "good" as const },
    { key: "plates_by_14", label: "Plates by 14", value: "1", verdict: "bad" as const },
    { key: "fast_first_dragon", label: "Fast first dragon", value: "—", verdict: "n/a" as const },
  ],
  headline: "Your early lead came from clean recalls around plate windows.",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("PostGamePage — no digest yet", () => {
  it("keeps the window chrome and shows the idle banner", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(null);
    renderPage();

    expect(await screen.findByTestId("empty-state")).toHaveTextContent(
      "No games analyzed yet — Backfill from History",
    );
    expect(screen.getByTestId("verdict")).toHaveTextContent("No game analyzed");
    expect(screen.getByText(/post-game review · the 30 seconds after the game/i)).toBeInTheDocument();
  });
});

describe("PostGamePage — digest rendered into the design", () => {
  beforeEach(() => {
    vi.mocked(api.postgameLatest).mockResolvedValue(digest);
  });

  it("renders the DEFEAT verdict tile with champion, role and duration", async () => {
    renderPage();

    expect(await screen.findByText("Defeat")).toBeInTheDocument();
    expect(screen.getByTestId("verdict-sub")).toHaveTextContent("Thresh · UTILITY · 33:12");
    expect(screen.getByTestId("verdict-header").textContent).toContain("TH");
  });

  it("renders the VICTORY tile for a won game", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue({ ...digest, win: true });
    renderPage();

    expect(await screen.findByText("Victory")).toBeInTheDocument();
  });

  it("shows signed checkpoint gold with red/green reads", async () => {
    renderPage();

    expect(await screen.findByText("+450")).toBeInTheDocument();
    expect(screen.getByTestId("checkpoint-15")).toHaveTextContent("-1,200");
    expect(screen.getByTestId("checkpoint-20")).toHaveTextContent("—");
    expect(screen.getByTestId("checkpoint-source")).toHaveTextContent("Diagnostic");
  });

  it("renders habit rows with verdict tags and the headline in the accent box", async () => {
    renderPage();

    expect(await screen.findByText(digest.headline)).toBeInTheDocument();
    expect(screen.getByTestId("digest-headline")).toBeInTheDocument();
    expect(screen.getByTestId("habit-recall_safety")).toHaveTextContent("good");
    expect(screen.getByTestId("habit-plates_by_14")).toHaveTextContent("bad");
    expect(screen.getByTestId("habit-fast_first_dragon")).toHaveTextContent("n/a");
  });

  it("shows an honest unavailable state when no contracted habit can be computed", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue({ ...digest, habits: [] });
    renderPage();

    expect(await screen.findByTestId("habit-unavailable")).toHaveTextContent(
      "No habit outcomes available",
    );
    expect(screen.queryByTestId("habit-outcomes")).not.toBeInTheDocument();
  });

  it("binds objective read cards and comeback odds to pack + digest numbers", async () => {
    renderPage();

    expect(await screen.findByText("denial 95.4%")).toBeInTheDocument();
    expect(screen.getByTestId("read-baron")).toHaveTextContent("+29.5pp lift");
    // gold@15 -1,200 is milder than the 2,000g anchor → outside the contracted domain.
    expect(await screen.findByTestId("comeback-value")).toHaveTextContent("—");
    expect(screen.getByTestId("comeback-note")).toHaveTextContent(
      "outside the Findings Pack's supported population domain",
    );
    expect(screen.getByText("Backfill context")).toBeInTheDocument();
  });

describe("comeback bucket contract", () => {
  const pack = makePack();
  const base = { ...digest };

  function reasonFor(gold15: number | null) {
    return matchComebackBucket(pack, {
      ...base,
      checkpoints: { ...base.checkpoints, gold_diff_15: gold15 },
    });
  }

  it.each([
    [-2000, "27.6%", "[2,000g, 3,500g)" ],
    [-3499.5, "27.6%", "[2,000g, 3,500g)"],
    [-3500, "7.6%", "[3,500g, 6,000g)"],
    [-5999.5, "7.6%", "[3,500g, 6,000g)"],
    [-6000, "3.0%", "[6,000g, 7,000g]"],
    [-7000, "3.0%", "[6,000g, 7,000g]"],
  ])("deficit %j maps to %s in %s", (gold15, rate, range) => {
    const result = reasonFor(gold15);
    expect(result.reason).toBeNull();
    if (result.match === null) throw new Error("expected a bucket match");
    expect(pct(result.match.winRate)).toBe(rate);
    expect(result.match.rangeLabel).toBe(range);
  });

  it.each([
    [null, "missing-personal-history"],
    [0, "not-a-deficit"],
    [1500, "not-a-deficit"],
    [-1999.5, "outside-domain"],
    [-7000.5, "outside-domain"],
  ] as const)("suppresses %j (%s)", (gold15, reason) => {
    const result = reasonFor(gold15 as number | null);
    expect(result).toEqual({ match: null, reason });
  });

  it("treats non-finite deficits as missing input rather than a cohort", () => {
    const result = matchComebackBucket(pack, {
      ...base,
      checkpoints: { ...base.checkpoints, gold_diff_15: Number.NaN },
    });
    expect(result).toEqual({ match: null, reason: "not-a-deficit" });
  });

  it("suppresses when the declaration names a different canonical feature", () => {
    // Simulate wire data violating the typed literal: a pack declaring cs10.
    const mismatched = makePack();
    const declaration: { feature: string; feature_contract_version: string } = {
      feature: "cs10",
      feature_contract_version: "loltrends-parity-v1",
    };
    mismatched.comeback_feature_contract =
      declaration as typeof mismatched.comeback_feature_contract;
    const result = matchComebackBucket(mismatched, { ...base, checkpoints: { ...base.checkpoints, gold_diff_15: -3500 } });
    expect(result).toEqual({ match: null, reason: "incompatible-declaration" });
  });

  it("renders the population range separately from the Personal History checkpoint", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue({
      ...digest,
      checkpoints: { ...digest.checkpoints, gold_diff_15: -3500 },
    });
    vi.mocked(api.pack).mockResolvedValue(makePack());
    renderPage();

    expect(await screen.findByText("7.6%")).toBeInTheDocument();
    expect(screen.getByTestId("comeback-range")).toHaveTextContent("[3,500g, 6,000g)");
    expect(screen.getByTestId("personal-checkpoint-note")).toHaveTextContent("down 3,500g at 15");
  });
});

describe("comeback bucket contract — page level", () => {
  it("keeps the surrender read as a structure-only placeholder", async () => {
    renderPage();

    const card = await screen.findByTestId("surrender-read");
    expect(within(card).getAllByText("—").length).toBeGreaterThan(0);
    expect(card).toHaveTextContent(/surrender advisor ships with the next Findings Pack/);
    expect(card).toHaveTextContent(/survivorship bias/);
  });
});
});
