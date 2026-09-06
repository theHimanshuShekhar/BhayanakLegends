import { act, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { InGameSnapshot } from "../../api/types";
import type { SseMessage } from "../../api/sse";
import type { api as ApiObject } from "../../api/client";
import { LiveMatchPage } from "../live-match";
import { forbiddenEnemyName, idleIngame, ingameSnapshot, makePack } from "./fixtures";

type ClientModule = { api: typeof ApiObject; [key: string]: unknown };
const liveState = vi.hoisted(() => ({
  ingame: null as InGameSnapshot | null,
  error: null as unknown,
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<ClientModule>();
  return {
    ...actual,
    api: { ...actual.api, pack: vi.fn() },
    connection: () => ({ base: "", token: "t" }),
    eventsUrl: () => "http://127.0.0.1:1/events?token=t",
  };
});

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

let pushSse: ((msg: SseMessage) => void) | null = null;
vi.mock("../../api/sse", () => ({
  useEvents: (onMessage?: (msg: never) => void) => {
    pushSse = onMessage as (msg: SseMessage) => void;
    return true;
  },
}));

import { api } from "../../api/client";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("LiveMatchPage", () => {
  it("renders the idle bridge and withholds live model output", async () => {
    renderPage();
    expect(await screen.findByTestId("live-route-status")).toHaveTextContent("Waiting for Live Companion game data");
    expect(screen.getByTestId("bridge-status")).toHaveTextContent("Live Companion idle");
    expect(screen.getByTestId("game-clock")).toHaveTextContent("0:00");
    await waitFor(() =>
      expect(screen.getByTestId("wp-value")).toHaveTextContent(
        "Unavailable: live model contract unavailable",
      ),
    );
    expect(screen.getByTestId("objectives-caption")).toHaveTextContent(
      "Typed possession, timing, contest, and no-objective rows describe population context.",
    );
    expect(screen.getByTestId("objectives-caption")).toHaveTextContent(
      "no objective row is a causal swing claim",
    );
  });

  it("renders the strict in-game roster, events, totals, and items", async () => {
    liveState.ingame = ingameSnapshot;
    renderPage();
    const localRow = await screen.findByTestId("player-row-local");
    expect(localRow).toHaveTextContent("FixturePlayer03");
    expect(localRow).toHaveTextContent("Viktor");
    expect(localRow).toHaveTextContent("4/2/7");
    expect(localRow).toHaveTextContent("213");
    expect(within(screen.getByTestId("event-feed")).getByText("DragonKill · Infernal")).toBeInTheDocument();
    expect(screen.getByTestId("items-by-player")).toHaveTextContent("Item 3065");
    expect(screen.getByTestId("team-totals")).toHaveTextContent("800");
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();
  });

  it("keeps active live probability unavailable when the v2 model declaration is withheld", async () => {
    liveState.ingame = ingameSnapshot;
    renderPage();
    await screen.findByTestId("player-row-local");
    const band = screen.getByTestId("wp-band");
    expect(band).toHaveTextContent("live model contract unavailable");
    expect(band).not.toHaveTextContent(/bottom quartile|top quartile|\d+(?:\.\d+)?%/i);
  });

  it("drops malformed live.state frames and clears retained values", async () => {
    liveState.ingame = ingameSnapshot;
    renderPage();
    await screen.findByTestId("player-row-local");
    act(() => pushSse!({ type: "live.state", ts: "malformed", data: { active: true } } as never));
    await waitFor(() => expect(screen.getByTestId("live-route-status")).toHaveTextContent("Waiting for Live Companion game data"));
    expect(screen.queryByTestId("player-row-local")).not.toBeInTheDocument();
    expect(screen.getByTestId("event-feed")).toHaveTextContent("No snapshot");
  });

  it("updates snapshot values in place from live.state SSE", async () => {
    liveState.ingame = ingameSnapshot;
    renderPage();
    await screen.findByTestId("player-row-local");
    const updated: InGameSnapshot = {
      ...ingameSnapshot,
      teams: {
        ...ingameSnapshot.teams,
        order: ingameSnapshot.teams.order.map((player) =>
          player.summoner === "FixturePlayer03" ? { ...player, kills: 8, cs: 240 } : player,
        ),
      },
      events: [
        ...ingameSnapshot.events,
        { name: "ChampionKill", t_s: 1300, actor: "FixturePlayer01", victim: null, detail: null },
      ],
    };
    act(() => pushSse!({ type: "live.state", ts: "update", data: updated }));
    await waitFor(() => expect(screen.getByTestId("active-kda")).toHaveTextContent("8 / 2 / 7"));
    expect(screen.getByTestId("active-stat-cs")).toHaveTextContent("240");
    expect(screen.getByTestId("event-feed")).toHaveTextContent("7 events");
  });

  it("keeps pack version labels v2-only and rejects non-v2 update frames", async () => {
    vi.mocked(api.pack).mockResolvedValueOnce(makePack({ pack_version: "v2" }));
    renderPage();
    expect(await screen.findByText("Findings Pack v2")).toBeInTheDocument();
    const packCallsBeforeUpdate = vi.mocked(api.pack).mock.calls.length;
    act(() => pushSse!({ type: "pack.updated", ts: "now", data: { schema_version: 2, pack_version: "v2" } }));
    await waitFor(() =>
      expect(vi.mocked(api.pack).mock.calls.length).toBeGreaterThan(packCallsBeforeUpdate),
    );
    await waitFor(() => expect(screen.getByText("Findings Pack v2")).toBeInTheDocument());

    act(() => {
      pushSse!({ type: "pack.updated", ts: "old", data: { schema_version: 1, pack_version: "v1" } } as never);
      pushSse!({ type: "pack.updated", ts: "bad", data: { schema_version: 3, pack_version: "v3" } } as never);
    });
    expect(screen.getByText("Findings Pack v2")).toBeInTheDocument();
  });
});
