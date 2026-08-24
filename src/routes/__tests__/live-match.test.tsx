import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SseMessage } from "../../api/sse";
import { LiveMatchPage } from "../live-match";
import { idleStatus, ingameActive, makePack } from "./fixtures";

vi.mock("../../api/client", () => ({
  api: {
    liveStatus: vi.fn(),
    pack: vi.fn(),
  },
  eventsUrl: () => "http://127.0.0.1:1/events?token=t",
}));

// SSE is mocked so tests can push live.state frames the way the sidecar would.
let pushSse: ((msg: SseMessage) => void) | null = null;
vi.mock("../../api/sse", () => ({
  useEvents: (onMessage?: (msg: never) => void) => {
    pushSse = onMessage as (msg: SseMessage) => void;
    return true;
  },
}));

import { api } from "../../api/client";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LiveMatchPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  pushSse = null;
  vi.mocked(api.liveStatus).mockResolvedValue(idleStatus);
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("LiveMatchPage — idle", () => {
  it("shows the :2999 empty-state and keeps the objectives priors board visible", async () => {
    renderPage();
    const empty = await screen.findByTestId("empty-state");
    expect(empty).toHaveTextContent(":2999 comes online at match start");
    expect(empty).toHaveTextContent("Borderless-windowed mode required for the widget experience.");

    // Board works without a live game.
    expect(await screen.findByTestId("objective-baron")).toHaveTextContent("81.4%");
    expect(screen.getByTestId("objective-baron")).toHaveTextContent("+29.5pp");
    expect(screen.getByTestId("objective-dragon")).toHaveTextContent("95.4%");
    expect(screen.getByTestId("objective-dragon")).toHaveTextContent("60.3%");
    expect(screen.getByTestId("objective-herald")).toHaveTextContent("66.6%");
  });

  it("renders the comeback odds table and survivorship footnote", async () => {
    renderPage();
    await screen.findByTestId("comeback-row--5000");
    expect(screen.getByTestId("comeback-row--5000")).toHaveTextContent("-5,000g");
    expect(screen.getByTestId("comeback-row--5000")).toHaveTextContent("7.6%");
    expect(screen.getByText(/Survivorship bias documented/)).toBeInTheDocument();
  });

  it("renders the lanes-ahead explainer with pack-sourced endpoints", async () => {
    renderPage();
    await screen.findByTestId("lanes-ahead");
    expect(screen.getByTestId("lanes-ahead")).toHaveTextContent("16.4%");
    expect(screen.getByTestId("lanes-ahead")).toHaveTextContent("83.8%");
    expect(screen.getByTestId("lanes-ahead")).toHaveTextContent("spread beats stacked");
  });
});

describe("LiveMatchPage — active", () => {
  beforeEach(() => {
    vi.mocked(api.liveStatus).mockResolvedValue(ingameActive);
  });

  it("labels the win probability band as a diagnostic checkpoint estimate", async () => {
    renderPage();
    const band = await screen.findByTestId("wp-band");
    expect(band).toHaveTextContent("Checkpoint estimate");
    expect(band).toHaveTextContent("Diagnostic");
    expect(band).toHaveTextContent("28.2%"); // nearest bucket to clock 20:54 → "-1000..0 @20m"
    expect(band).toHaveTextContent("-1000..0 @20m");
    expect(band).toHaveTextContent(/pack model artifacts/);
  });

  it("renders an event feed panel with its landing-soon empty text", async () => {
    renderPage();
    const feed = await screen.findByTestId("event-feed");
    expect(feed).toHaveTextContent("event feed lands with LCU bridge");
  });

  it("renders all four habit nudges with × formatting and advice tags", async () => {
    renderPage();
    await screen.findByTestId("habit-nudges");
    const expected = [
      ["recall_safety", "Recall safely", "×2.24 per SD"],
      ["fast_first_dragon", "Fast first dragon", "×1.31 per SD"],
      ["spend_before_backing", "Spend before backing", "×1.12 per SD"],
      ["plates_by_14", "Plates by 14", "×0.87 per SD"],
    ] as const;
    for (const [key, label, effect] of expected) {
      const item = screen.getByTestId(`habit-nudge-${key}`);
      expect(item).toHaveTextContent(label);
      expect(item).toHaveTextContent(effect);
      expect(item).toHaveTextContent("advice");
    }
  });
  it("ticks the game clock forward between SSE live.state frames", async () => {
    // Keep poll responses consistent with the pushed frame so a refetch
    // cannot rewind the clock mid-test.
    vi.mocked(api.liveStatus).mockResolvedValue({
      champ_select: { active: false, phase: null },
      ingame: { active: true, game_id: 1, mode: "CLASSIC", clock_s: 120 },
      last_error: null,
    });
    renderPage();
    // Let the initial poll settle first so it cannot overwrite the SSE frame.
    await screen.findByTestId("game-clock");
    pushSse!({
      type: "live.state",
      ts: "t",
      data: {
        champ_select: { active: false, phase: null },
        ingame: { active: true, game_id: 1, mode: "CLASSIC", clock_s: 120 },
        last_error: null,
      },
    });
    await waitFor(() => expect(screen.getByTestId("game-clock")).toHaveTextContent("2:00"));
    // Local ticker advances ~1s per second without waiting for the next frame.
    await new Promise((r) => setTimeout(r, 2200));
    await waitFor(() =>
      expect(screen.getByTestId("game-clock").textContent).toMatch(/^2:0[2-9]$/),
    );
  });
});
