import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PostGamePage } from "../postgame";
import { api } from "../../api/client";
import { makePack } from "./fixtures";

vi.mock("../../api/client", () => ({
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
  role: "UTILITY",
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
    expect(screen.getByText(/post-game review · the 30 seconds after a loss/i)).toBeInTheDocument();
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
    expect(screen.getByText("Diagnostic")).toBeInTheDocument();
  });

  it("renders habit rows with verdict tags and the headline in the accent box", async () => {
    renderPage();

    expect(await screen.findByText(digest.headline)).toBeInTheDocument();
    expect(screen.getByTestId("digest-headline")).toBeInTheDocument();
    expect(screen.getByTestId("habit-recall_safety")).toHaveTextContent("good");
    expect(screen.getByTestId("habit-plates_by_14")).toHaveTextContent("bad");
    expect(screen.getByTestId("habit-fast_first_dragon")).toHaveTextContent("n/a");
  });

  it("binds objective read cards and comeback odds to pack + digest numbers", async () => {
    renderPage();

    expect(await screen.findByText("denial 95.4%")).toBeInTheDocument();
    expect(screen.getByTestId("read-baron")).toHaveTextContent("+29.5pp lift");
    // gold@15 -1,200 → nearest pack bucket -1000 → 27.6%
    expect(await screen.findByText("27.6%")).toBeInTheDocument();
    expect(screen.getByTestId("comeback-note")).toHaveTextContent("down 1,200g at 15");
    expect(screen.getByText("Backfill")).toBeInTheDocument();
  });

  it("keeps the surrender read as a structure-only placeholder", async () => {
    renderPage();

    const card = await screen.findByTestId("surrender-read");
    expect(within(card).getAllByText("—").length).toBeGreaterThan(0);
    expect(card).toHaveTextContent(/surrender advisor ships with the next Findings Pack/);
    expect(card).toHaveTextContent(/survivorship bias/);
  });
});
