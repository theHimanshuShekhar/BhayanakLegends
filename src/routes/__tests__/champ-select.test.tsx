import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChampSelectSnapshot, LiveStatus } from "../../api/types";
import type { SseMessage } from "../../api/sse";
import { ChampSelectPage } from "../champ-select";
import {
  champSelectSession,
  forbiddenEnemyName,
  idleSession,
  idleStatus,
  makePack,
} from "./fixtures";

// Mutable fixtures read lazily by the hook mocks below.
const liveState = vi.hoisted(() => ({
  status: null as LiveStatus | null,
  session: null as ChampSelectSnapshot | null,
}));

vi.mock("../../api/client", () => ({
  api: {
    pack: vi.fn(),
  },
  connection: () => ({ base: "", token: "t" }),
  eventsUrl: () => "http://127.0.0.1:1/events?token=t",
}));

// Real react-query hooks bound to the fixtures above, so SSE overlays that
// write into ["live-session"] / ["live-status"] re-render exactly like prod.
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

// SSE is mocked so tests can push champselect.state frames like the sidecar.
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

describe("ChampSelectPage — idle", () => {
  it("shows the slim policy banner while no champ select is detected", async () => {
    renderPage();
    const banner = await screen.findByTestId("cs-idle-banner");
    expect(banner).toHaveTextContent(
      "Ranked draft hides enemy summoner names — the app shows champion-level intel only.",
    );
    expect(banner).toHaveTextContent(/waiting for client/i);
    expect(await screen.findByTestId("detection-status")).toHaveTextContent(/LCU not detected/);
  });

  it("keeps the pack-driven three-column body rendered while idle", async () => {
    renderPage();
    await screen.findByTestId("cs-hero-pick");
    expect(screen.getByTestId("card-mastery")).toBeInTheDocument();
    expect(screen.getByTestId("card-ban-advisor")).toBeInTheDocument();
    expect(screen.getByTestId("cs-lock-button")).toBeDisabled();
  });

  it("shows the read-only loadout state without champion recommendations", async () => {
    renderPage();

    const loadout = await screen.findByTestId("card-loadout");
    expect(loadout).toHaveTextContent("LOADOUT · READ-ONLY");
    expect(screen.getByTestId("cs-loadout-unavailable")).toHaveTextContent(
      "no champion-specific loadout source",
    );
    expect(loadout).toHaveTextContent("Unavailable");
    expect(loadout).not.toHaveTextContent("Electrocute");
    expect(loadout).not.toHaveTextContent("Flash / TP");
    expect(screen.getByTestId("cs-apply-loadout")).toBeDisabled();
    expect(screen.getByTestId("cs-apply-loadout")).not.toHaveAttribute("title");
  });

  it("keeps the counterpick honesty caption verbatim", async () => {
    renderPage();
    const caption = await screen.findByTestId("honesty-caption");
    expect(caption).toHaveTextContent("≈ ±2.5pp, empirical-Bayes shrunk");
    expect(caption).toHaveTextContent("a nudge, not a verdict");
  });

  it("renders the mastery premium numbers parsed from the pack", async () => {
    renderPage();
    expect(await screen.findByText("50.6%")).toBeInTheDocument();
    expect(screen.getByText("46.9%")).toBeInTheDocument();
  });

  it("renders a real pack champion in the ban advisor with a Recommend ban pill", async () => {
    renderPage();
    const row = await screen.findByTestId("ban-advisor-row-Lillia");
    expect(row).toHaveTextContent("Lillia");
    expect(row).toHaveTextContent("54.8% WR at 1.7% ban rate");
    expect(screen.getByText(/recommend ban/i)).toBeInTheDocument();
  });

  it("suggests the best S/A middle champion with honest field stats", async () => {
    renderPage();
    const hero = await screen.findByTestId("cs-hero-pick");
    expect(hero).toHaveTextContent("Ahri"); // highest S/A wr (.534)
    expect(hero).toHaveTextContent("Best pick");
    expect(hero).toHaveTextContent("VS FIELD");
    expect(hero).toHaveTextContent("PICK RATE");
    expect(screen.getByTestId("cs-mini-Sylas")).toBeInTheDocument();
    expect(screen.getByTestId("cs-mini-Viktor")).toBeInTheDocument();
  });

  // COMPLIANCE (Riot policy): enemy summoner names must never render. The
  // forbidden fixture string asserts nothing resembling a name leaks through
  // any channel.
  it("never renders enemy summoner names while idle", async () => {
    renderPage();
    await screen.findByTestId("card-ban-advisor");
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();
  });

  it("flips to the live ban strip on an SSE champselect.state frame without waiting for the next poll", async () => {
    renderPage();
    await screen.findByTestId("cs-idle-banner");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "champselect.state", ts: "t", data: champSelectSession });
    await screen.findByTestId("cs-ban-strip");
  });
});

describe("ChampSelectPage — active session", () => {
  beforeEach(() => {
    liveState.session = champSelectSession;
  });

  it("renders REAL ban tiles with ally champion names and the ticking timer pill", async () => {
    renderPage();
    await screen.findByTestId("cs-ban-strip");

    const ally = screen.getByTestId("cs-ally-row");
    expect(ally).toHaveTextContent("Xayah"); // local locked champion
    expect(ally).toHaveTextContent("Lucian");
    expect(ally).toHaveTextContent("Amumu");
    expect(ally).toHaveTextContent("YOU"); // local slot highlighted

    // named ally bans get initials tiles; caption carries full names
    expect(screen.getByTestId("cs-bans-caption")).toHaveTextContent("Miss Fortune, Annie");
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();

    const pill = screen.getByTestId("cs-timer-pill");
    expect(pill).toHaveTextContent("ChampSelect");
    expect(pill).toHaveTextContent("00:23"); // timer_sec ticks down between frames
  });

  it("renders enemy champion-level intel with the Champion {id} fallback for unmapped ids", async () => {
    renderPage();
    const enemy = await screen.findByTestId("cs-enemy-row");
    expect(enemy).toHaveTextContent("Camille"); // mapped via Data Dragon
    expect(enemy).toHaveTextContent("Champion 999"); // unmapped id fallback
    expect(enemy).toHaveTextContent("picked");
  });

  // COMPLIANCE: enemy cells carry champion-level info only — the sidecar
  // strips theirTeam summoner names and no slot ever renders one.
  it("never renders enemy summoner names while active", async () => {
    renderPage();
    await screen.findByTestId("cs-enemy-row");
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();
    for (let cellId = 5; cellId <= 9; cellId++) {
      expect(screen.getByTestId(`cs-enemy-cell-${cellId}`)).not.toHaveTextContent(
        forbiddenEnemyName,
      );
    }
  });

  it("shows the locked local champion in your-side and lane cards", async () => {
    renderPage();
    await screen.findByTestId("cs-ban-strip");
    const side = screen.getByTestId("cs-your-side");
    expect(side).toHaveTextContent("Xayah · SacredButtholio");
    expect(side).toHaveTextContent("YOU");

    expect(screen.getByTestId("your-lane-champion")).toHaveTextContent("Xayah");
  });

  it("drops back to the idle banner when the session ends via SSE", async () => {
    renderPage();
    await screen.findByTestId("cs-ban-strip");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "champselect.state", ts: "t", data: idleSession });
    await screen.findByTestId("cs-idle-banner");
  });
});
