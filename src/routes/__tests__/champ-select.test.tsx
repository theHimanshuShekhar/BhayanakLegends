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
  it("shows the policy empty-state while no champ select is detected", async () => {
    renderPage();
    const empty = await screen.findByTestId("empty-state");
    expect(empty).toHaveTextContent("Waiting for champ select");
    expect(empty).toHaveTextContent(
      "The app detects the League client automatically. Ranked enemy names stay hidden by policy.",
    );
    expect(await screen.findByTestId("detection-status")).toHaveTextContent(/LCU not detected/);
  });
});

describe("ChampSelectPage — active", () => {
  beforeEach(() => {
    vi.mocked(api.liveStatus).mockResolvedValue(champSelectActive);
  });

  it("renders role-labeled ally slots with the session phase", async () => {
    renderPage();
    await screen.findByTestId("team-slots-ally");
    for (const role of ["TOP", "JGL", "MID", "BOT", "SUP"]) {
      expect(screen.getByTestId(`ally-slot-${role}`)).toHaveTextContent("locked");
    }
  });

  // COMPLIANCE (Riot policy): ranked enemy summoner names/tags must never
  // render. There is deliberately NO prop-drilling API for enemy names — the
  // enemy TeamSlots variant accepts only `side` and `phase`, and LiveStatus
  // carries no roster, so an enemy summoner name has no data path into this
  // tree. The forbidden fixture string below asserts that nothing resembling a
  // name leaks through any other channel either.
  it("renders enemy slots strictly as role + ??? and never shows enemy names", async () => {
    vi.mocked(api.pack).mockResolvedValue(makePack());
    renderPage();
    await screen.findByTestId("team-slots-enemy");
    for (const role of ["TOP", "JGL", "MID", "BOT", "SUP"]) {
      const slot = screen.getByTestId(`enemy-slot-${role}`);
      expect(slot).toHaveTextContent("???");
      expect(slot).not.toHaveTextContent(forbiddenEnemyName);
    }
    expect(screen.queryByText(forbiddenEnemyName)).toBeNull();
  });

  it("suggests picks for the default MIDDLE role and labels each basis honestly", async () => {
    renderPage();
    await screen.findByTestId("card-your-pool");
    await screen.findByText("Ahri"); // best pick: highest S/A wr (.534)
    expect(screen.getByText("by highest S/A win rate")).toBeInTheDocument();
    expect(screen.getByText("Sylas")).toBeInTheDocument(); // pocket: highest wr overall (.541)
    expect(screen.getByText("Viktor")).toBeInTheDocument(); // comfort: highest pick rate (.201)
    expect(
      screen.getByText("Population-level suggestions from the Findings Pack — not your history."),
    ).toBeInTheDocument();
  });

  it("updates from SSE live.state frames without waiting for the next poll", async () => {
    renderPage();
    await waitFor(() => expect(pushSse).toBeTruthy());
    pushSse!({ type: "live.state", ts: "t", data: idleStatus });
    await screen.findByTestId("empty-state");
  });
});
