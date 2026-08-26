import { act, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FindingsPack, InGameSnapshot } from "../../api/types";
import type { SseMessage } from "../../api/sse";
import type { api as ApiObject } from "../../api/client";
import { LiveMatchPage } from "../live-match";
import {
  forbiddenEnemyName,
  idleIngame,
  ingameSnapshot,
  makePack,
} from "./fixtures";

type ClientModule = { api: typeof ApiObject; [key: string]: unknown };

// Mutable fixtures read lazily by the hook mocks below.
const liveState = vi.hoisted(() => ({
  ingame: null as InGameSnapshot | null,
  error: null as unknown,
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<ClientModule>();
  return {
    ...actual,
    api: {
      ...actual.api,
      pack: vi.fn(),
    },
    connection: () => ({ base: "", token: "t" }),
    eventsUrl: () => "http://127.0.0.1:1/events?token=t",
  };
});

// Real react-query hooks bound to the fixtures above, so SSE overlays that
// write into ["live-ingame"] re-render exactly like production.
vi.mock("../../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/hooks")>();
  const { useQuery } = await import("@tanstack/react-query");
  return {
    ...actual,
    useLiveIngame: () =>
      useQuery({
        queryKey: ["live-ingame"],
        queryFn: () => liveState.error ? Promise.reject(liveState.error) : Promise.resolve(liveState.ingame!),
      }),
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
  liveState.error = null;
  vi.mocked(api.pack).mockClear();
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("LiveMatchPage — idle", () => {
  it("renders one waiting announcement and neutral live regions", async () => {
    renderPage();
    expect(await screen.findByTestId("live-route-status")).toHaveTextContent("Waiting for Live Companion game data");
    expect(screen.getAllByText("Waiting for Live Companion game data")).toHaveLength(1);
    expect(screen.queryByText(/waiting for :2999/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("bridge-status")).toHaveTextContent("Live Companion idle");
    expect(screen.getByTestId("game-clock")).toHaveTextContent("0:00");

    const list = screen.getByTestId("player-list");
    expect(list).toHaveTextContent("PLAYER ROSTER");
    expect(screen.getByTestId("score-strip")).toHaveTextContent("Unavailable: kills and turrets not reported");
    const bridgeDot = within(screen.getByTestId("bridge-status")).getByTestId("bridge-dot");
    expect(bridgeDot).toHaveStyle({ background: "var(--color-dimmer)" });
    expect(bridgeDot).not.toHaveStyle({ boxShadow: "0 0 8px var(--color-teal)" });
    const skeletons = list.querySelectorAll<HTMLElement>(".live-skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
    for (const shape of skeletons) {
      expect(shape).toHaveStyle({ background: "var(--color-surface-3)" });
    }
    expect(skeletons[0].closest("tbody")).toHaveAttribute("aria-hidden", "true");
    expect(within(list).queryByText(/ornn|viego|taliyah|syndra/i)).not.toBeInTheDocument();
    expect(within(list).queryByText(forbiddenEnemyName)).not.toBeInTheDocument();
    expect(screen.queryByText(forbiddenEnemyName)).not.toBeInTheDocument();
  });

  it("keeps the unsupported live probability unavailable without a future-pack promise", async () => {
    renderPage();
    const band = await screen.findByTestId("wp-band");
    expect(band).toHaveTextContent("Unavailable: compatible live inputs unavailable");
    expect(band).toHaveTextContent(
      "The current Findings Pack lacks the compatible live input, quartile boundaries, and model inputs needed to map this game.",
    );
    expect(band).toHaveTextContent("Personal History");
    expect(band).not.toHaveTextContent(/next pack|future pack/i);
    expect(band).not.toHaveTextContent(/bottom quartile|top quartile/i);
    expect(screen.getByTestId("wp-value")).toHaveTextContent("Unavailable: compatible live inputs unavailable");
  });

  it("binds the objectives cards to real pack numbers", async () => {
    renderPage();
    expect(await screen.findByText("95.4%")).toBeInTheDocument();
    expect(screen.getByTestId("objective-dragon")).toHaveTextContent("checkpoint, not weapon");
    expect(screen.getByTestId("objective-baron")).toHaveTextContent("comeback tool");
    expect(screen.getByTestId("objective-baron")).toHaveTextContent("81.4%");
    expect(screen.getByTestId("objectives-caption")).toHaveTextContent("60.3%");
    expect(screen.getByTestId("objectives-caption")).toHaveTextContent("+29.5 pp");
  });

  it("renders habit nudges with ×-per-SD formatting and the trap line from the pack", async () => {
    renderPage();
    expect(await screen.findByTestId("habit-nudge-recall_safety")).toHaveTextContent(
      "Recall safely — worth ×2.24 effect per SD.",
    );
    expect(screen.getByTestId("habit-nudge-plates_by_14")).toHaveTextContent("×1.08 effect per SD");
    expect(screen.getByTestId("trap-nudge")).toHaveTextContent("Hecarim 41.5%");
  });

  it("keeps live panels honest when the snapshot is unavailable", async () => {
    renderPage();
    expect(await screen.findByTestId("event-feed")).toHaveTextContent("No snapshot");
    expect(screen.getByTestId("items-by-player")).toHaveTextContent("No snapshot");
    expect(screen.queryByTestId("dead-now")).not.toBeInTheDocument();
    expect(screen.queryByTestId("enemy-spells")).not.toBeInTheDocument();
    expect(screen.queryByText(/Lanes ahead/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Team totals land with the LCU bridge/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Item values land with the LCU bridge/i)).not.toBeInTheDocument();
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


  it("renders real feed events including DragonKill with its dragon type", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const feed = screen.getByTestId("event-feed");
    expect(feed).toHaveTextContent("6 events");
    expect(feed).toHaveTextContent("DragonKill · Infernal");
    expect(feed).toHaveTextContent("FixturePlayer03 → FixturePlayer09");
    expect(feed).toHaveTextContent("FirstBrick");
  });
  it("renders snapshot-derived team totals and every player item", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");

    const totals = screen.getByTestId("team-totals");
    expect(within(totals).getByTestId("team-total-order-cs")).toHaveTextContent("800");
    expect(within(totals).getByTestId("team-total-order-level")).toHaveTextContent("57");
    expect(within(totals).getByTestId("team-total-order-kills")).toHaveTextContent("15");
    expect(within(totals).getByTestId("team-total-order-deaths")).toHaveTextContent("12");
    expect(within(totals).getByTestId("team-total-chaos-cs")).toHaveTextContent("739");
    expect(within(totals).getByTestId("team-total-chaos-level")).toHaveTextContent("55");
    expect(within(totals).getByTestId("team-total-chaos-kills")).toHaveTextContent("8");
    expect(within(totals).getByTestId("team-total-chaos-deaths")).toHaveTextContent("18");

    const items = screen.getByTestId("items-by-player");
    expect(items).toHaveTextContent("FixturePlayer01");
    expect(items).toHaveTextContent("Item 3065");
    expect(items).toHaveTextContent("×1");
    expect(items).toHaveTextContent("Item 2003");
    expect(items).toHaveTextContent("×2");
    expect(items).toHaveTextContent("FixturePlayer07");
    expect(within(items).getByTestId("items-player-chaos-FixturePlayer07")).toHaveTextContent("No items reported");
    expect(items).not.toHaveTextContent(/price|gold|value|icon/i);
  });

  it("shows zero totals and item counts from a zeroed snapshot", async () => {
    liveState.ingame = {
      ...ingameSnapshot,
      teams: {
        order: [{ ...ingameSnapshot.teams.order[0], level: 0, kills: 0, deaths: 0, cs: 0, items: [{ id: 0, count: 0 }] }],
        chaos: [],
      },
    };
    renderPage();
    await screen.findByTestId("team-order");
    expect(within(screen.getByTestId("team-order")).getByTestId("row-kda")).toHaveTextContent("0/0/4");
    expect(screen.getByTestId("player-list")).toHaveTextContent(/deaths \(cumulative\)/i);
    const totals = screen.getByTestId("team-totals");
    expect(within(totals).getByTestId("team-total-order-cs")).toHaveTextContent("0");
    expect(within(totals).getByTestId("team-total-order-level")).toHaveTextContent("0");
    expect(within(totals).getByTestId("team-total-order-kills")).toHaveTextContent("0");
    expect(within(totals).getByTestId("team-total-order-deaths")).toHaveTextContent("0");
    expect(within(totals).getByTestId("team-total-chaos-cs")).toHaveTextContent("0");
    expect(screen.getByTestId("items-player-order-FixturePlayer01")).toHaveTextContent("×0");
  });
  it("binds the active player panel to the local player's stats", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    expect(screen.getByTestId("active-player-sub")).toHaveTextContent("FixturePlayer03 · Viktor");
    expect(screen.getByTestId("active-kda")).toHaveTextContent("4 / 2 / 7");
    expect(screen.getByTestId("active-stat-cs")).toHaveTextContent("213");
    expect(screen.getByTestId("active-stat-level")).toHaveTextContent("12");
    expect(screen.getByTestId("active-stat-ward")).toHaveTextContent("1.4");
  });
  it("labels roster deaths as cumulative and keeps active fields contract-truthful", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const list = screen.getByTestId("player-list");
    expect(list).toHaveTextContent(/deaths \(cumulative\)/i);
    expect(list).toHaveTextContent("5/1/3");
    const active = screen.getByTestId("active-player");
    expect(active).toHaveTextContent("FixturePlayer03 · Viktor");
    expect(active).toHaveTextContent("12");
    expect(active).toHaveTextContent("4 / 2 / 7");
    expect(active).toHaveTextContent("213");
    expect(active).toHaveTextContent("1.4");
    expect(active).not.toHaveTextContent(/health|held gold|current.dead|respawn|role|spell/i);
  });

  it.each([
    ["null", null],
    ["unmatched", "MissingPlayer"],
  ] as const)("shows one unavailable state for a %s local summoner without a roster substitution", async (_, localSummoner) => {
    liveState.ingame = { ...ingameSnapshot, local_summoner: localSummoner };
    renderPage();
    await screen.findByTestId("player-list");
    const active = screen.getByTestId("active-player");
    expect(within(active).getByText("Local player unavailable")).toBeInTheDocument();
    expect(within(active).getAllByText("Local player unavailable")).toHaveLength(1);
    expect(within(active).queryByText("FixturePlayer03")).not.toBeInTheDocument();
    expect(within(active).queryByText("SacredButtholio")).not.toBeInTheDocument();
    expect(active).not.toHaveTextContent("—");
    expect(within(active).queryByTestId("active-player-sub")).not.toBeInTheDocument();
    expect(active).not.toHaveTextContent(/health|held gold|current.dead|respawn|role|spell/i);
  });

  it("keeps an active empty roster neutral and does not announce bridge waiting twice", async () => {
    liveState.ingame = { ...ingameSnapshot, teams: { order: [], chaos: [] }, local_summoner: null };
    renderPage();
    const list = await screen.findByTestId("player-list");
    expect(await within(list).findByText("Player roster unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("active-player")).toHaveTextContent("Local player unavailable");
    expect(list).not.toHaveTextContent("waiting for :2999");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent(":2999 · 1s poll");
  });


  it("suppresses unsupported live probability for any active-game clock", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const band = screen.getByTestId("wp-band");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("Unavailable: compatible live inputs unavailable");
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
  it("updates snapshot-confirmed values in place and keeps events oldest first", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const updated = {
      ...ingameSnapshot,
      teams: {
        ...ingameSnapshot.teams,
        order: ingameSnapshot.teams.order.map((player) =>
          player.summoner === "FixturePlayer03" ? { ...player, kills: 8, cs: 240 } : player,
        ),
      },
      events: [
        ...ingameSnapshot.events,
        { name: "ChampionKill" as const, t_s: 1300, actor: "FixturePlayer01", victim: null, detail: null },
      ],
    };
    act(() => {
      pushSse!({ type: "live.state", ts: "update", data: updated });
    });
    await waitFor(() => expect(screen.getByTestId("active-kda")).toHaveTextContent("8 / 2 / 7"));
    expect(screen.getByTestId("active-stat-cs")).toHaveTextContent("240");
    expect(screen.getByTestId("event-feed")).toHaveTextContent("7 events");
    expect(screen.getByTestId("event-name-0")).toHaveTextContent("GameStart");
    expect(screen.getByTestId("event-name-6")).toHaveTextContent("ChampionKill");
  });

  it("caps oversized event fixtures at the last 40 records in oldest-first order", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    const events = Array.from({ length: 41 }, (_, index) => ({
      name: "GameStart" as const,
      t_s: index + 1,
      actor: null,
      victim: null,
      detail: null,
    }));
    act(() => {
      pushSse!({ type: "live.state", ts: "oversized", data: { ...ingameSnapshot, events } });
    });
    await waitFor(() => expect(screen.getByTestId("event-feed")).toHaveTextContent("40 events"));
    const rows = within(screen.getByTestId("event-feed-rows")).getAllByRole("listitem");
    expect(rows).toHaveLength(40);
    expect(rows[0]).toHaveTextContent("0:02");
    expect(rows[39]).toHaveTextContent("0:41");
  });

  it("clears retained live values for malformed and reconnect-to-idle frames", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    act(() => {
      pushSse!({ type: "live.state", ts: "malformed", data: { active: true } } as never);
    });
    await waitFor(() => expect(screen.getByTestId("live-route-status")).toHaveTextContent("Waiting for Live Companion game data"));
    expect(screen.queryByTestId("player-row-local")).not.toBeInTheDocument();
    expect(screen.getByTestId("event-feed")).toHaveTextContent("No snapshot");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent("Live Companion idle");
  });
  it("replaces waiting with the actionable live request error and clears stale values", async () => {
    liveState.error = new Error("sidecar unavailable");
    renderPage();
    const error = await screen.findByTestId("ingame-error");
    expect(error).toHaveTextContent("Something went wrong. Check your settings and try again.");
    expect(screen.queryByTestId("live-route-status")).not.toBeInTheDocument();
    expect(screen.queryByText("Waiting for Live Companion game data")).not.toBeInTheDocument();
    expect(screen.queryByTestId("player-row-local")).not.toBeInTheDocument();
    expect(screen.getByTestId("event-feed")).toHaveTextContent("No snapshot");
  });

  it("drops back to idle chrome when the game ends via SSE", async () => {
    renderPage();
    await screen.findByTestId("player-row-local");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "live.state", ts: "t", data: idleIngame });
    await screen.findByTestId("player-list");
    expect(screen.getByTestId("live-route-status")).toHaveTextContent("Waiting for Live Companion game data");
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

  it("keeps loading state unavailable with canonical live probability copy", async () => {
    vi.mocked(api.pack).mockReturnValueOnce(new Promise<FindingsPack>(() => {}));
    renderPage();
    const band = await screen.findByTestId("wp-band");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("Unavailable: compatible live inputs unavailable");
    expect(band).not.toHaveTextContent(/v\d/);
  });

  it("keeps pack errors bounded while the probability card stays suppressed", async () => {
    vi.mocked(api.pack).mockRejectedValueOnce(new Error("sensitive pack detail"));
    renderPage();
    expect(await screen.findByText("Something went wrong. Check your settings and try again.")).toBeInTheDocument();
    const band = screen.getByTestId("wp-band");
    expect(screen.getByTestId("wp-value")).toHaveTextContent("Unavailable: compatible live inputs unavailable");
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
