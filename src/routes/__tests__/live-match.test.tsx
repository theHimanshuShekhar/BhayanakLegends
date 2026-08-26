import { act, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FindingsPack, InGameSnapshot } from "../../api/types";
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
  actionableErrorMessage: (_error: unknown, context?: string) =>
    context === "pack" ? "The Findings Pack is unavailable." : "Something went wrong.",
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
  vi.mocked(api.pack).mockClear();
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("LiveMatchPage — idle", () => {
  it("renders the design chrome: waiting pill, 0:00 clock and dash-only player rows", async () => {
    renderPage();
    expect(await screen.findByTestId("waiting-pill")).toHaveTextContent("waiting for :2999");
    expect(screen.getByTestId("game-clock")).toHaveTextContent("0:00");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent("waiting for :2999");

    const list = screen.getByTestId("player-list");
    expect(list).toHaveTextContent("PLAYER ROSTER");
    expect(screen.getByTestId("score-strip")).toHaveTextContent("Unavailable kills · Unavailable turrets");
    // Skeleton rows carry no roster names — enemy or ally.
    expect(within(list).queryByText(/ornn|viego|taliyah|syndra/i)).not.toBeInTheDocument();
    expect(within(list).queryByText(forbiddenEnemyName)).not.toBeInTheDocument();
    expect(screen.queryByText(forbiddenEnemyName)).not.toBeInTheDocument();
  });

  it("keeps the unsupported live probability unavailable without a future-pack promise", async () => {
    renderPage();
    const band = await screen.findByTestId("wp-band");
    expect(band).toHaveTextContent("—");
    expect(band).toHaveTextContent(
      "The current Findings Pack lacks the compatible live input, quartile boundaries, and model inputs needed to map this game.",
    );
    expect(band).toHaveTextContent("Personal History");
    expect(band).not.toHaveTextContent(/next pack|future pack/i);
    expect(band).not.toHaveTextContent(/bottom quartile|top quartile/i);
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
    expect(localRow).toHaveTextContent("FixturePlayer03");
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
    expect(feed).toHaveTextContent("FixturePlayer03 → FixturePlayer09");
    expect(feed).toHaveTextContent("FirstBrick");
  });

  it("binds the active player panel to the local player's stats", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    expect(screen.getByTestId("active-player-sub")).toHaveTextContent("FixturePlayer03 · Viktor");
    expect(screen.getByTestId("active-kda")).toHaveTextContent("4 / 2 / 7");
    expect(screen.getByTestId("active-stat-cs")).toHaveTextContent("213");
    expect(screen.getByTestId("active-stat-level")).toHaveTextContent("12");
  });

  it("suppresses unsupported live probability for any active-game clock", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const band = screen.getByTestId("wp-band");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("—");
    expect(band).not.toHaveTextContent(/bottom quartile|top quartile/i);
    expect(band).not.toHaveTextContent(/\d+(?:\.\d+)?%/);
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

describe("LiveMatchPage — Findings Pack version parity", () => {
  it("seeds both live labels from hello while the pack query is loading", async () => {
    vi.mocked(api.pack).mockReturnValue(new Promise<FindingsPack>(() => {}));
    renderPage();
    await waitFor(() => expect(pushSse).toBeTruthy());
    act(() => {
      pushSse!({ type: "hello", ts: "now", data: { app_version: "dev", pack_version: "v2" } });
    });
    expect(await screen.findByText("Findings Pack v2")).toBeInTheDocument();
    expect(screen.getByTestId("wp-band")).toHaveTextContent("WIN PROBABILITY · FINDINGS PACK v2");
  });

  it("clears version claims when hello has no active pack version", async () => {
    vi.mocked(api.pack).mockReturnValue(new Promise<FindingsPack>(() => {}));
    renderPage();
    await waitFor(() => expect(pushSse).toBeTruthy());
    act(() => {
      pushSse!({ type: "hello", ts: "now", data: { app_version: "dev", pack_version: null } });
    });
    expect(await screen.findByText("Findings Pack", { exact: true })).toBeInTheDocument();
    expect(screen.getByTestId("wp-band")).toHaveTextContent("WIN PROBABILITY · FINDINGS PACK");
    expect(screen.getByTestId("wp-band")).not.toHaveTextContent(/v\d/);
  });

  it("shows a valid pack.updated version immediately and refreshes the pack query", async () => {
    let resolveUpdated!: (pack: FindingsPack) => void;
    vi.mocked(api.pack)
      .mockResolvedValueOnce(makePack({ pack_version: "v1" }))
      .mockReturnValueOnce(new Promise<FindingsPack>((resolve) => (resolveUpdated = resolve)));
    renderPage();
    expect(await screen.findByText("Findings Pack v1")).toBeInTheDocument();
    act(() => {
      pushSse!({ type: "pack.updated", ts: "now", data: { schema_version: 1, pack_version: "v2" } });
    });
    expect(await screen.findByText("Findings Pack v2")).toBeInTheDocument();
    expect(screen.getByTestId("wp-band")).toHaveTextContent("WIN PROBABILITY · FINDINGS PACK v2");
    await waitFor(() => expect(api.pack).toHaveBeenCalledTimes(2));
    resolveUpdated(makePack({ pack_version: "v2" }));
    await waitFor(() => expect(screen.getByTestId("wp-band")).toHaveTextContent("FINDINGS PACK v2"));
  });

  it("rejects malformed pack.updated frames without changing the active version or refreshing", async () => {
    vi.mocked(api.pack).mockResolvedValue(makePack({ pack_version: "v1" }));
    renderPage();
    expect(await screen.findByText("Findings Pack v1")).toBeInTheDocument();
    act(() => {
      pushSse!({ type: "pack.updated", ts: "now", data: { schema_version: 1.5, pack_version: "v2" } } as never);
      pushSse!({ type: "pack.updated", ts: "now", data: { schema_version: 1, pack_version: "" } } as never);
    });
    expect(screen.getByText("Findings Pack v1")).toBeInTheDocument();
    expect(api.pack).toHaveBeenCalledTimes(1);
  });

  it("keeps loading state dash-only with unavailable live probability copy", async () => {
    vi.mocked(api.pack).mockReturnValueOnce(new Promise<FindingsPack>(() => {}));
    renderPage();
    const band = await screen.findByTestId("wp-band");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("—");
    expect(band).toHaveTextContent("compatible live input");
    expect(band).not.toHaveTextContent(/bottom quartile|top quartile|\d+(?:\.\d+)?%/i);
    expect(band).not.toHaveTextContent(/v\d/);
  });

  it("keeps pack errors bounded while the probability card stays suppressed", async () => {
    vi.mocked(api.pack).mockRejectedValueOnce(new Error("sensitive pack detail"));
    renderPage();
    expect(await screen.findByText("The Findings Pack is unavailable.")).toBeInTheDocument();
    const band = screen.getByTestId("wp-band");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("—");
    expect(band).toHaveTextContent("compatible live input");
    expect(band).not.toHaveTextContent(/sensitive pack detail|bottom quartile|top quartile|\d+(?:\.\d+)?%/i);
  });

  it("suppresses version claims when a successful pack response has no version", async () => {
    vi.mocked(api.pack).mockResolvedValue({
      ...makePack(),
      pack_version: undefined,
    } as unknown as FindingsPack);
    renderPage();
    expect(await screen.findByText("Findings Pack", { exact: true })).toBeInTheDocument();
    expect(screen.getByTestId("wp-band")).not.toHaveTextContent(/v\d/);
  });

  it("keeps loading and error states version-claim-free", async () => {
    vi.mocked(api.pack).mockReturnValueOnce(new Promise<FindingsPack>(() => {}));
    renderPage();
    expect(await screen.findByText("Findings Pack", { exact: true })).toBeInTheDocument();
    expect(screen.getByTestId("wp-band")).not.toHaveTextContent(/v\d/);
  });
});
