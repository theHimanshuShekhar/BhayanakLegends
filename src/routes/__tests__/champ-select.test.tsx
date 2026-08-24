import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SseMessage } from "../../api/sse";
import { ChampSelectPage } from "../champ-select";
import {
  champSelectActive,
  forbiddenEnemyName,
  idleStatus,
  makePack,
} from "./fixtures";

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
      <ChampSelectPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  pushSse = null;
  vi.mocked(api.liveStatus).mockResolvedValue(idleStatus);
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

  it("updates from SSE live.state frames without waiting for the next poll", async () => {
    renderPage();
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "live.state", ts: "t", data: champSelectActive });
    await screen.findByTestId("cs-ban-strip");
  });
});

describe("ChampSelectPage — active", () => {
  beforeEach(() => {
    vi.mocked(api.liveStatus).mockResolvedValue(champSelectActive);
  });

  it("renders the live ban strip with role-only rosters and the session phase", async () => {
    renderPage();
    await screen.findByTestId("cs-ban-strip");
    const ally = screen.getByTestId("cs-ally-row");
    expect(ally).toHaveTextContent("MIDDLE");
    expect(ally).toHaveTextContent("locked"); // fixture phase
    const enemy = screen.getByTestId("cs-enemy-row");
    expect(enemy).toHaveTextContent("not revealed");
  });

  // COMPLIANCE: enemy slots stay champion-level/role-only — no names, ever.
  it("never renders enemy summoner names while active", async () => {
    renderPage();
    await screen.findByTestId("cs-enemy-row");
    for (const role of ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]) {
      expect(screen.getByTestId(`enemy-slot-${role}`)).not.toHaveTextContent(forbiddenEnemyName);
    }
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();
  });

  it("drops back to the idle banner when the session ends via SSE", async () => {
    renderPage();
    await screen.findByTestId("cs-ban-strip");
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "live.state", ts: "t", data: idleStatus });
    await screen.findByTestId("cs-idle-banner");
  });
});
