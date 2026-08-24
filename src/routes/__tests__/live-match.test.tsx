import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InGameSnapshot } from "../../api/types";
import type { SseMessage } from "../../api/sse";
import { LiveMatchPage } from "../live-match";
import {
  forbiddenEnemyName,
  idleIngame,
  ingameSnapshot,
  makePack,
} from "./fixtures";

// Mutable fixtures read lazily by the hook mocks below.
const liveState = vi.hoisted(() => ({
  ingame: null as InGameSnapshot | null,
}));

vi.mock("../../api/client", () => ({
  api: {
    pack: vi.fn(),
  },
  connection: () => ({ base: "", token: "t" }),
  eventsUrl: () => "http://127.0.0.1:1/events?token=t",
}));

// Real react-query hooks bound to the fixtures above, so SSE overlays that
// write into ["live-ingame"] re-render exactly like production.
vi.mock("../../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/hooks")>();
  const { useQuery } = await import("@tanstack/react-query");
  return {
    ...actual,
    useLiveIngame: () =>
      useQuery({ queryKey: ["live-ingame"], queryFn: () => Promise.resolve(liveState.ingame!) }),
  };
});

// SSE is mocked so tests can push live.state frames like the sidecar.
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
  liveState.ingame = idleIngame;
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
    liveState.ingame = ingameSnapshot;
  });

  it("renders REAL player rows with summoner, champion, level, K/D/A, CS and ward score", async () => {
    renderPage();
    const localRow = await screen.findByTestId("player-row-local"); // highlighted
    expect(localRow).toHaveTextContent("SacredButtholio");
    expect(localRow).toHaveTextContent("Viktor");
    expect(localRow).toHaveTextContent("12");
    expect(localRow).toHaveTextContent("4/2/7");
    expect(localRow).toHaveTextContent("213"); // CS from creepScore

    expect(screen.getByTestId("team-order")).toHaveTextContent("Ornn");
    expect(screen.getByTestId("team-chaos")).toHaveTextContent("Lee Sin");
    expect(within(localRow).getAllByTestId("row-ward")[0]).toHaveTextContent("1.4"); // ward score column
  });

  it("sums kills and turret events into the score strip", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    expect(screen.getByTestId("score-strip")).toHaveTextContent(
      "23 kills · 1 turrets", // (2+3+4+5+1) + (3+2+2+1+0), one TurretKilled event
    );
  });

  it("renders real feed events including DragonKill with its dragon type", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const feed = screen.getByTestId("event-feed");
    expect(feed).toHaveTextContent("6 events");
    expect(feed).toHaveTextContent("DragonKill · Infernal");
    expect(feed).toHaveTextContent("SacredButtholio → EnemyADC");
    expect(feed).toHaveTextContent("FirstBrick");
  });

  it("binds the active player panel to the local player's stats", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    expect(screen.getByTestId("active-player-sub")).toHaveTextContent("SacredButtholio · Viktor");
    expect(screen.getByTestId("active-kda")).toHaveTextContent("4 / 2 / 7");
    expect(screen.getByTestId("active-stat-cs")).toHaveTextContent("213");
    expect(screen.getByTestId("active-stat-level")).toHaveTextContent("12");
  });

  it("shows the nearest checkpoint bucket as the win probability estimate", async () => {
    renderPage();
    // clock 1254 → nearest bucket "-1000..0 @20m"
    expect(await screen.findByText("28.2%")).toBeInTheDocument();
    const band = screen.getByTestId("wp-band");
    expect(band).toHaveTextContent("-1000..0 @20m");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("28.2%");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent(":2999 · 1s poll");
  });

  it("ticks the game clock forward between SSE live.state frames", async () => {
    // Keep the underlying query fixture consistent with the pushed frame so a
    // refetch cannot rewind the clock mid-test.
    liveState.ingame = { ...ingameSnapshot, clock_s: 120 };
    renderPage();
    await screen.findByTestId("player-row-local");
    pushSse!({ type: "live.state", ts: "t", data: { ...ingameSnapshot, clock_s: 120 } });
    await waitFor(() => expect(screen.getByTestId("game-clock")).toHaveTextContent("2:00"));
    // Local ticker advances ~1s per second without waiting for the next frame.
    await new Promise((r) => setTimeout(r, 2200));
    await waitFor(() =>
      expect(screen.getByTestId("game-clock").textContent).toMatch(/^2:0[2-9]$/),
    );
  });

  it("drops back to idle chrome when the game ends via SSE", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "live.state", ts: "t", data: idleIngame });
    await screen.findByTestId("waiting-pill");
    expect(screen.queryByTestId("player-row-local")).toBeNull();
  });
});
