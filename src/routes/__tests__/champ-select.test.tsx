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
  actionableErrorMessage: () => "Findings Pack unavailable",
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

  it("keeps the pack-driven body honest while role evidence is missing", async () => {
    renderPage();
    expect(await screen.findByTestId("suggestions-unavailable")).toHaveTextContent(/assigned role unavailable/i);
    expect(screen.queryByTestId("cs-hero-pick")).toBeNull();
    expect(screen.getByTestId("card-mastery")).toBeInTheDocument();
    expect(screen.getByTestId("card-ban-advisor")).toBeInTheDocument();
    expect(screen.getByTestId("cs-lock-button")).toBeDisabled();
  });

  it("shows the read-only loadout state without champion recommendations", async () => {
    renderPage();

    const loadout = await screen.findByTestId("card-loadout");
    await screen.findByText(/no exact champion-specific loadout finding exists/i);
    expect(loadout).toHaveTextContent("LOADOUT · READ-ONLY");
    expect(loadout).toHaveTextContent("Unavailable");
    expect(loadout).not.toHaveTextContent("Electrocute");
    expect(loadout).not.toHaveTextContent("Flash / TP");
    expect(screen.queryByTestId("cs-apply-loadout")).toBeNull();
    expect(loadout).not.toHaveTextContent("KEYSTONE");
    expect(loadout).not.toHaveTextContent("SUMMS");
  });

  it("keeps the role-unavailable caption explicit", async () => {
    renderPage();
    const caption = await screen.findByTestId("honesty-caption");
    expect(caption).toHaveTextContent(/assigned role unavailable/i);
    expect(caption).not.toHaveTextContent(/your pool|your top 3/i);
  });

  it("renders the mastery premium numbers parsed from the pack", async () => {
    renderPage();
    expect(await screen.findByText("50.6%")).toBeInTheDocument();
    expect(screen.getByText("46.9%")).toBeInTheDocument();
  });

  it("renders a real shipped pack champion in the ban advisor with a Recommend ban pill", async () => {
    renderPage();
    const row = await screen.findByTestId("ban-advisor-row-Taric");
    expect(row).toHaveTextContent("Taric");
    expect(row).toHaveTextContent("55.6% WR at 0.3% ban rate");
    expect(screen.getByText(/recommend ban/i)).toBeInTheDocument();
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
  it("filters suggestions to the locally assigned role", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "TOP",
      ally: champSelectSession.ally.map((cell) => (cell.is_local ? { ...cell, state: "picked" } : cell)),
    };

    vi.mocked(api.pack).mockResolvedValue(makePack());

    renderPage();

    const suggestions = await screen.findByText("Sett");
    const card = screen.getByTestId("card-suggested-picks");
    expect(card).toHaveTextContent("TOP");
    expect(suggestions).toBeInTheDocument();
    expect(card).not.toHaveTextContent("Malzahar");
    expect(card).toHaveTextContent("Findings Pack");
    expect(card).toHaveTextContent(/pre-lock/i);
  });
  it("withholds recommendations when the Findings Pack is unavailable", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "TOP",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, state: "picked" } : cell,
      ),
    };
    vi.mocked(api.pack).mockRejectedValue(new Error("pack unavailable"));

    renderPage();

    await screen.findByTestId("cs-ban-strip");
    expect(screen.getByTestId("suggestions-unavailable")).toHaveTextContent(/Findings Pack unavailable/i);
    expect(screen.queryByTestId("cs-hero-pick")).toBeNull();
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
  it("keeps session facts visible when the Findings Pack errors", async () => {
    vi.mocked(api.pack).mockRejectedValue(new Error("pack unavailable"));
    renderPage();

    await screen.findByTestId("cs-ban-strip");
    expect(screen.getByTestId("card-comp-read")).toHaveTextContent(/Lucian|Xayah/);
    expect(screen.getByTestId("card-comp-read")).toHaveTextContent("2/5 picked");
    expect(screen.getByTestId("cs-your-side")).toHaveTextContent("Xayah");
    expect(screen.getByTestId("cs-session-status")).toHaveTextContent(/Xayah locked · TOP/i);
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent(/Findings Pack could not be loaded/i);
    expect(screen.getByTestId("card-loadout")).toHaveTextContent(/unavailable/i);
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
    expect(side).toHaveTextContent("Xayah · FixturePlayer03");
    expect(side).toHaveTextContent("YOU");

    expect(screen.getByTestId("your-lane-champion")).toHaveTextContent("Xayah");
  });
  it("derives companion facts from the same live session view", async () => {
    renderPage();

    const comp = await screen.findByTestId("card-comp-read");
    await screen.findByText("2/5 picked");
    expect(comp).toHaveTextContent("Lucian");
    expect(comp).toHaveTextContent("Xayah");
    expect(comp).toHaveTextContent("2/5 picked");
    expect(comp).not.toHaveTextContent(/damage mix|%/i);
    expect(comp).not.toHaveTextContent(/Findings Pack|Personal History|advice/i);
  });

  it("labels mastery numbers as Findings Pack cohort data without personal claims", async () => {
    renderPage();

    const mastery = await screen.findByTestId("card-mastery");
    await screen.findByText("50.6%");
    expect(mastery).toHaveTextContent("Findings Pack cohort");
    expect(mastery).toHaveTextContent("50.6%");
    expect(mastery).toHaveTextContent("46.9%");
    expect(mastery).not.toHaveTextContent(/your pool|your top 3/i);
  });

  it("shows locked champion context and unavailable guidance without controls", async () => {
    renderPage();

    await screen.findByTestId("cs-ban-strip");
    expect(await screen.findByTestId("card-how-to-play")).toHaveTextContent(/Xayah/i);
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent(/unavailable/i);
    expect(screen.getByTestId("card-loadout")).toHaveTextContent(/Xayah/i);
    expect(screen.getByTestId("card-loadout")).toHaveTextContent(/unavailable/i);
    expect(screen.queryByTestId("cs-apply-loadout")).toBeNull();
  });

  it("keeps picked-not-locked guidance and the lock prompt visible", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "TOP",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, champion: "Sett", champion_id: 875, state: "picked" } : cell,
      ),
    };

    renderPage();

    await screen.findByTestId("cs-ban-strip");
    expect(screen.getByTestId("your-lane-champion")).toHaveTextContent("Sett");
    expect(screen.getByTestId("card-suggested-picks")).toHaveTextContent(/pre-lock/i);
    expect(screen.getByTestId("cs-your-side")).toHaveTextContent("2/5 PICKED");
    expect(screen.getByTestId("your-lane-tier")).toHaveTextContent(/not locked/i);
    expect(screen.getByTestId("cs-lock-button")).toBeInTheDocument();
    expect(screen.getByTestId("cs-session-status")).toHaveTextContent(/picked — not locked/i);
  });

  it("suppresses suggestions and lock controls after the local champion is locked", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "MIDDLE",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, champion: "Annie", champion_id: 1, state: "locked" } : cell,
      ),
    };

    renderPage();

    await screen.findByTestId("cs-ban-strip");
    await waitFor(() => expect(screen.getByTestId("cs-session-status")).toHaveTextContent(/Annie locked · MIDDLE/i));
    expect(screen.queryByTestId("card-suggested-picks")).toBeNull();
    expect(screen.queryByTestId("cs-lock-button")).toBeNull();
    expect(screen.getByTestId("your-lane-champion")).toHaveTextContent("Annie");
    expect(screen.getByTestId("your-lane-tier")).not.toHaveTextContent(/tier/i);
    expect(screen.queryByText(/Malzahar/)).toBeNull();
  });

  it("uses only an exact champion-and-role tier for a locked lane", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "TOP",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, champion: "Sett", champion_id: 875, state: "locked" } : cell,
      ),
    };
    renderPage();

    await screen.findByTestId("cs-ban-strip");
    await waitFor(() =>
      expect(screen.getByTestId("your-lane-tier")).toHaveTextContent("FINDINGS PACK · TIER S"),
    );
    expect(screen.getByTestId("your-lane-champion")).toHaveTextContent("Sett");
  });

  it("keeps every session card aligned through role and lock transitions", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "TOP",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, champion: "Sett", champion_id: 875, state: "picked" } : cell,
      ),
    };

    renderPage();
    await screen.findByTestId("cs-lock-button");
    await waitFor(() => expect(screen.getByTestId("card-comp-read")).toHaveTextContent("Sett"));
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent("Sett");
    expect(screen.getByTestId("card-loadout")).toHaveTextContent("Sett");

    pushSse!({
      type: "champselect.state",
      ts: "transition",
      data: {
        ...liveState.session,
        local_assigned_role: "MIDDLE",
        ally: liveState.session.ally.map((cell) =>
          cell.is_local ? { ...cell, champion: "Annie", champion_id: 1, state: "locked" } : cell,
        ),
      },
    });

    await waitFor(() => expect(screen.getByTestId("cs-session-status")).toHaveTextContent(/Annie locked · MIDDLE/i));
    expect(screen.getByTestId("card-comp-read")).toHaveTextContent("Annie");
    expect(screen.getByTestId("card-comp-read")).not.toHaveTextContent("Sett");
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent("Annie");
    expect(screen.getByTestId("card-how-to-play")).not.toHaveTextContent("Sett");
    expect(screen.getByTestId("card-loadout")).toHaveTextContent("Annie");
    expect(screen.getByTestId("card-loadout")).not.toHaveTextContent("Sett");
    expect(screen.getByTestId("cs-your-side")).toHaveTextContent("Annie");
    expect(screen.getByTestId("cs-your-side")).not.toHaveTextContent("Sett");
  });

  it("updates the visible controls when SSE supplies completed lock evidence", async () => {
    liveState.session = {
      ...champSelectSession,
      local_assigned_role: "TOP",
      ally: champSelectSession.ally.map((cell) =>
        cell.is_local ? { ...cell, champion: "Sett", champion_id: 875, state: "picked" } : cell,
      ),
    };

    renderPage();
    await screen.findByTestId("cs-lock-button");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({
      type: "champselect.state",
      ts: "t",
      data: {
        ...liveState.session,
        ally: liveState.session.ally.map((cell) =>
          cell.is_local ? { ...cell, state: "locked" } : cell,
        ),
      },
    });

    await waitFor(() => {
      expect(screen.queryByTestId("card-suggested-picks")).toBeNull();
      expect(screen.queryByTestId("cs-lock-button")).toBeNull();
    });
    expect(screen.getByTestId("cs-session-status")).toHaveTextContent(/Sett locked · TOP/i);
    expect(screen.getByTestId("card-comp-read")).toHaveTextContent("Sett");
    expect(screen.getByTestId("card-how-to-play")).toHaveTextContent("Sett");
    expect(screen.getByTestId("card-loadout")).toHaveTextContent("Sett");

  });
  it("drops back to the idle banner when the session ends via SSE", async () => {
    renderPage();
    await screen.findByTestId("cs-ban-strip");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "champselect.state", ts: "t", data: idleSession });
    await screen.findByTestId("cs-idle-banner");
  });
});
