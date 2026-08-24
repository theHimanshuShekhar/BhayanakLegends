import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SseMessage } from "../../api/sse";
import { LiveMatchPage } from "../live-match";
import { forbiddenEnemyName, idleStatus, ingameActive, makePack } from "./fixtures";

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
  it("renders the design chrome: waiting pill, 0:00 clock and dash-only player rows", async () => {
    renderPage();
    expect(await screen.findByTestId("waiting-pill")).toHaveTextContent("waiting for :2999");
    expect(screen.getByTestId("game-clock")).toHaveTextContent("0:00");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent("waiting for :2999");

    const list = screen.getByTestId("player-list");
    expect(list).toHaveTextContent("PLAYER LIST · LEVEL · K/D/A · CS · WARD SCORE");
    expect(screen.getByTestId("score-strip")).toHaveTextContent("— kills · — turrets");
    // Skeleton rows are dash cells only — no roster names, enemy or ally.
    expect(within(list).queryByText(/ornn|viego|taliyah|syndra/i)).not.toBeInTheDocument();
    expect(within(list).getAllByText("—").length).toBeGreaterThan(20);
    expect(screen.queryByText(forbiddenEnemyName)).not.toBeInTheDocument();
  });

  it("labels the win probability card as a diagnostic checkpoint estimate with the honesty caption", async () => {
    renderPage();
    const band = await screen.findByTestId("wp-band");
    expect(band).toHaveTextContent("Checkpoint estimate");
    expect(band).toHaveTextContent("Diagnostic");
    expect(band).toHaveTextContent(/calibrated model ships with the next pack/);
    // No live game state → no number is claimed.
    expect(screen.getByTestId("wp-value")).toHaveTextContent("—");
  });

  it("binds the objectives cards to real pack numbers", async () => {
    renderPage();
    expect(await screen.findByText("95.4%")).toBeInTheDocument();
    expect(screen.getByTestId("objective-dragon")).toHaveTextContent("checkpoint, not weapon");
    expect(screen.getByTestId("objective-baron")).toHaveTextContent("comeback tool");
    expect(screen.getByTestId("objective-baron")).toHaveTextContent("81.4%");
    expect(screen.getByTestId("objectives-caption")).toHaveTextContent("60.3%");
    expect(screen.getByTestId("objectives-caption")).toHaveTextContent("+29.5pp");
  });

  it("renders habit nudges with ×-per-SD formatting and the trap line from the pack", async () => {
    renderPage();
    expect(await screen.findByTestId("habit-nudge-recall_safety")).toHaveTextContent(
      "Recall safely — worth ×2.24 per SD.",
    );
    expect(screen.getByTestId("habit-nudge-plates_by_14")).toHaveTextContent("×0.87 per SD");
    expect(screen.getByTestId("trap-nudge")).toHaveTextContent("Hecarim 41.5%");
  });

  it("keeps idle captions on the live-only panels", async () => {
    renderPage();
    expect(await screen.findByTestId("event-feed")).toHaveTextContent(
      "event feed lands with the LCU bridge",
    );
    expect(screen.getByTestId("item-value")).toHaveTextContent("Item values land with the LCU bridge.");
    expect(screen.getByTestId("dead-now")).toHaveTextContent("death tracker lands with the LCU bridge");
  });

  it("shows the enemy spells panel as an idle structure with no timer content", async () => {
    renderPage();
    const panel = await screen.findByTestId("enemy-spells");
    expect(panel).toHaveTextContent("ships after LCU bridge");
    expect(panel.textContent).not.toMatch(/flash\s*\d/i);
    expect(panel.textContent).not.toMatch(forbiddenEnemyName);
  });

  it("carries the lanes-ahead line from the pack finding", async () => {
    renderPage();
    const line = await screen.findByTestId("lanes-ahead");
    expect(line).toHaveTextContent("16.4%");
    expect(line).toHaveTextContent("83.8%");
    expect(line).toHaveTextContent("spread beats stacked");
  });
});

describe("LiveMatchPage — active game", () => {
  beforeEach(() => {
    vi.mocked(api.liveStatus).mockResolvedValue(ingameActive);
  });

  it("shows the nearest checkpoint bucket as the win probability estimate", async () => {
    renderPage();
    // clock 20:54 → nearest bucket "-1000..0 @20m"
    expect(await screen.findByText("28.2%")).toBeInTheDocument();
    const band = screen.getByTestId("wp-band");
    expect(band).toHaveTextContent("-1000..0 @20m");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("28.2%");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent(":2999 · 1s poll");
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
