import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChampSelectSnapshot, LiveStatus } from "../../api/types";
import type { FindingsPackV2 } from "../../api/pack-v2";
import type { SseMessage } from "../../api/sse";
import { ChampSelectPage } from "../champ-select";
import {
  champSelectSession,
  forbiddenEnemyName,
  idleSession,
  idleStatus,
  makePack,
  shippedLegacyPack,
} from "./fixtures";
const preLockChampSelectSession: ChampSelectSnapshot = {
  ...champSelectSession,
  ally: champSelectSession.ally.map((cell) =>
    cell.is_local ? { ...cell, state: "picked" as const } : cell,
  ),
};

const liveState = vi.hoisted(() => ({
  status: null as LiveStatus | null,
  session: null as ChampSelectSnapshot | null,
}));

vi.mock("../../api/client", () => ({
  api: { pack: vi.fn() },
  actionableErrorMessage: () => "Findings Pack unavailable",
  connection: () => ({ base: "", token: "t" }),
  eventsUrl: () => "http://127.0.0.1:1/events?token=t",
}));

vi.mock("../../api/hooks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/hooks")>();
  const { useQuery } = await import("@tanstack/react-query");
  return {
    ...actual,
    useLiveStatus: () =>
      useQuery({ queryKey: ["live-status"], queryFn: () => Promise.resolve(liveState.status!) }),
    useLiveSession: () =>
      useQuery({ queryKey: ["live-session"], queryFn: () => Promise.resolve(liveState.session!) }),
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
      <ChampSelectPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  pushSse = null;
  liveState.session = idleSession;
  liveState.status = idleStatus;
  vi.mocked(api.pack).mockResolvedValue(makePack());
});

describe("ChampSelectPage", () => {
  it("shows the policy banner and withholds role rows without an assigned role", async () => {
    renderPage();
    expect(await screen.findByTestId("cs-idle-banner")).toHaveTextContent(/waiting for client/i);
    expect(await screen.findByTestId("detection-status")).toHaveTextContent(/LCU not detected/);

    const tiers = await screen.findByTestId("card-role-tiers");
    expect(tiers).toHaveTextContent(/assigned role is unavailable/i);
    expect(screen.getByTestId("role-tiers-unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("card-mastery")).toHaveTextContent("+1.94 pp");
    expect(screen.getByTestId("card-ban-context")).toHaveTextContent("r=+0.06");
  });

  it("keeps historical v1 mastery, role tiers, and ban context visible", async () => {
    liveState.session = preLockChampSelectSession;
    vi.mocked(api.pack).mockResolvedValue(shippedLegacyPack);
    renderPage();

    await waitFor(() => expect(screen.getByTestId("card-role-tiers")).toHaveTextContent("Historical v1"));
    expect(screen.getByTestId("card-mastery")).toHaveTextContent("+3.70 pp");
    expect(screen.getByTestId("card-ban-context")).toHaveTextContent("r=+0.13");
    expect(screen.getByTestId("role-tier-rows")).toBeInTheDocument();
  });

  it("keeps loadout and gameplan surfaces read-only when v2 has no champion-specific finding", async () => {
    renderPage();
    expect(await screen.findByText(/no exact champion-specific loadout finding exists/i)).toBeInTheDocument();
    expect(await screen.findByText(/no exact champion-specific gameplan finding exists/i)).toBeInTheDocument();
    expect(screen.queryByTestId("cs-apply-loadout")).toBeNull();
  });

  it("shows the v2 population caveat without personal-history claims", async () => {
    renderPage();
    const mastery = await screen.findByText(/Same-direction era result: stable/);
    expect(mastery).toBeInTheDocument();
    expect(mastery).not.toHaveTextContent(/your pool|your top 3/i);
    const ban = screen.getByTestId("card-ban-context");
    expect(ban).toHaveTextContent(/selection context|diagnostic/i);
  });

  it("renders champion-level session facts without enemy summoner names", async () => {
    liveState.session = champSelectSession;
    renderPage();
    await waitFor(() => expect(screen.getByTestId("cs-ally-row")).toHaveTextContent("Xayah"));
    const ally = screen.getByTestId("cs-ally-row");
    const enemy = screen.getByTestId("cs-enemy-row");
    expect(ally).toHaveTextContent("Xayah");
    expect(screen.getByTestId("cs-your-side")).toHaveTextContent("2/5 PICKED");
    expect(enemy).toHaveTextContent("Camille");
    expect(enemy).toHaveTextContent("Champion 999");
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();
    expect(screen.getByTestId("cs-timer-pill")).toHaveTextContent("00:23");
  });

  it("keeps session facts visible when the v2 pack errors", async () => {
    liveState.session = preLockChampSelectSession;
    vi.mocked(api.pack).mockRejectedValue(new Error("pack unavailable"));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("cs-ally-row")).toHaveTextContent("Xayah"));

    expect(screen.getByTestId("card-comp-read")).toHaveTextContent("2/5 picked");
    expect(await screen.findByTestId("card-role-tiers")).toHaveTextContent(/could not be loaded/i);
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent(/could not be loaded/i);
  });

  it("keeps session facts visible while the v2 pack is loading", async () => {
    liveState.session = champSelectSession;
    const pending = new Promise<FindingsPackV2>(() => undefined);
    vi.mocked(api.pack).mockReturnValue(pending);
    renderPage();
    expect(await screen.findByTestId("card-role-tiers")).toHaveTextContent(/Loading… Findings Pack/i);
  });

  it("updates the live session immediately from champselect SSE", async () => {
    renderPage();
    await screen.findByTestId("cs-idle-banner");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "champselect.state", ts: "t", data: champSelectSession });
    expect(await screen.findByTestId("cs-ban-strip")).toHaveTextContent("Xayah");
  });

  it("does not show pre-lock role rows after the local champion is locked", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "MIDDLE",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, champion: "Annie", champion_id: 1, state: "locked" } : cell,
      ),
    };
    renderPage();
    await screen.findByTestId("cs-ban-strip");
    expect(await screen.findByTestId("cs-session-status")).toHaveTextContent(/Annie locked · MIDDLE/i);
    expect(screen.queryByTestId("card-role-tiers")).toBeNull();
    expect(screen.getByTestId("your-lane-tier")).toHaveTextContent(/LOCKED · MIDDLE/);
  });

  it("withholds recommendations when the pack is missing", async () => {
    liveState.session = preLockChampSelectSession;
    vi.mocked(api.pack).mockResolvedValue(null as never);
    renderPage();
    const tiers = await screen.findByTestId("card-role-tiers");
    await waitFor(() => expect(tiers).toHaveTextContent(/evidence is missing/i));
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent(/pack is missing/i);
    expect(screen.getByTestId("card-loadout")).toHaveTextContent(/pack is missing/i);
  });
});
