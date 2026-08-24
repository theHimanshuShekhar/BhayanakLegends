import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { PostGamePage } from "../postgame";
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

const digest = {
  match_id: "EUW1_123",
  played_at: "2026-08-23T21:04:00Z",
  champion: "Thresh",
  role: "UTILITY",
  win: true,
  duration_s: 1934,
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
});

describe("PostGamePage", () => {
  it("renders the empty state when no games were analyzed", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(null);
    renderPage(<PostGamePage />);

    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("No games analyzed yet")).toBeInTheDocument();
    expect(
      screen.getByText("Play a game with the app running, or import your history from the History tab."),
    ).toBeInTheDocument();
  });

  it("renders the digest header with a WIN tag and mono duration", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(digest);
    renderPage(<PostGamePage />);

    expect(await screen.findByText("Thresh")).toBeInTheDocument();
    expect(screen.getByText("UTILITY")).toBeInTheDocument();
    expect(screen.getByText("WIN")).toBeInTheDocument();
    expect(screen.getByTestId("digest-duration")).toHaveTextContent("32:14");
  });

  it("renders a LOSS tag for a lost game", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue({ ...digest, win: false });
    renderPage(<PostGamePage />);

    expect(await screen.findByText("LOSS")).toBeInTheDocument();
  });

  it("shows signed checkpoint gold, colored diagnostics, habit verdicts and headline", async () => {
    vi.mocked(api.postgameLatest).mockResolvedValue(digest);
    renderPage(<PostGamePage />);

    expect(await screen.findByText("+450")).toBeInTheDocument();
    expect(screen.getByText("-1,200")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2); // null @20 + n/a value
    expect(screen.getByText("n/a")).toBeInTheDocument();
    expect(screen.getByText(digest.headline)).toBeInTheDocument();
    expect(screen.getAllByText(/diagnostic/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Backfill/)).toBeInTheDocument();
  });
});
