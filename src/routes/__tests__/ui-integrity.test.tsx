import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as ClientApi from "../../api/client";
import type {
  BenchmarkResponse,
  HistorySummary,
  InGameSnapshot,
  LiveStatus,
  PostGameDigest,
  Settings,
  SyncStatus,
} from "../../api/types";
import { ChampSelectPage } from "../champ-select";
import { ChampionsPage } from "../champions";
import { HistoryPage } from "../history";
import { LiveMatchPage } from "../live-match";
import { PostGamePage } from "../postgame";
import { ProgressPage } from "../progress";
import {
  idleIngame,
  idleSession,
  idleStatus,
  makePack,
} from "./fixtures";

const historySummary: HistorySummary = {
  matches: 4,
  patches: ["16.15", "16.16"],
  by_role: [{ role: "MIDDLE", games: 4, wins: 2 }],
  win_rate: 0.5,
};

const settings: Settings = {
  riot_id: null,
  region_route: "sea",
  has_key: false,
  auto_sync: false,
};

const syncStatus: SyncStatus = {
  state: "idle",
  mode: "era_first",
  total_queued: 0,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: null,
  started_at: null,
};

const postgame: PostGameDigest = {
  match_id: "fixture-match",
  played_at: "2026-08-24T00:00:00Z",
  champion: "Ahri",
  role: "MIDDLE",
  win: true,
  duration_s: 1800,
  checkpoints: { gold_diff_10: 100, gold_diff_15: -500, gold_diff_20: 250 },
  habits: [],
  headline: "A measured game",
};

const benchmarks: BenchmarkResponse = { state: "contract-suppressed", rows: [] };

const liveState = vi.hoisted(() => ({
  status: null as LiveStatus | null,
  session: null as typeof idleSession | null,
  ingame: null as InGameSnapshot | null,
}));

// This is the union mock graph for every route. Keeping all API exports present
// avoids the invalid-element collision caused by co-importing route modules with
// partial, route-specific client mocks.
vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof ClientApi>();
  return {
    ...actual,
    api: {
      health: vi.fn(async () => ({ status: "ok", app_version: "test", pack_version: "v1" })),
      pack: vi.fn(async () => makePack()),
      settings: vi.fn(async () => settings),
      updateSettings: vi.fn(async () => settings),
      startSync: vi.fn(async () => syncStatus),
      cancelSync: vi.fn(async () => syncStatus),
      syncStatus: vi.fn(async () => syncStatus),
      historySummary: vi.fn(async () => historySummary),
      trajectories: vi.fn(async () => []),
      patchAggregates: vi.fn(async () => []),
      postgameLatest: vi.fn(async () => postgame),
      benchmarks: vi.fn(async () => benchmarks),
      liveStatus: vi.fn(async () => liveState.status),
      liveSession: vi.fn(async () => liveState.session),
      liveIngame: vi.fn(async () => liveState.ingame),
    },
    connection: vi.fn(async () => ({ base: "", token: "t", status: "ok" as const })),
    eventsUrl: vi.fn(async () => "http://127.0.0.1:1/events?token=t"),
    actionableErrorMessage: actual.actionableErrorMessage,
  };
});

// Real react-query hooks are intentionally retained. Their query functions use
// the complete client fixture above, matching production loading/loaded states.
// The stream is inert for this detector; route tests separately exercise frames.
vi.mock("../../api/sse", () => ({
  useEvents: () => false,
  subscribeToEvents: () => () => undefined,
}));

function renderRoute(page: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{page}</QueryClientProvider>);
}

const routes = [
  ["champ-select", <ChampSelectPage />, () => screen.findByTestId("card-ban-advisor")],
  ["live-match", <LiveMatchPage />, () => screen.findByTestId("bridge-status")],
  ["postgame", <PostGamePage />, () => screen.findByTestId("verdict-header")],
  ["progress", <ProgressPage />, () => screen.findByRole("heading", { name: "Benchmarks" })],
  ["champions", <ChampionsPage />, () => screen.findByTestId("role-MIDDLE")],
  ["history", <HistoryPage />, () => screen.findByTestId("summary-matches")],
] as const;

beforeEach(() => {
  liveState.status = idleStatus;
  liveState.session = idleSession;
  liveState.ingame = idleIngame;
});

afterEach(() => {
  document.body.replaceChildren();
});

function assertHeadingHierarchy() {
  const headings = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")];
  expect(headings.filter((heading) => heading.tagName === "H1")).toHaveLength(1);
  let previous = 1;
  for (const heading of headings) {
    const level = Number(heading.tagName.slice(1));
    expect(level).toBeLessThanOrEqual(previous + 1);
    previous = level;
  }
}

function assertNamedSections() {
  for (const section of document.querySelectorAll('section[aria-label], section[aria-labelledby]')) {
    const label = section.getAttribute("aria-label");
    const labelledBy = section.getAttribute("aria-labelledby");
    const labelledNode = labelledBy ? document.getElementById(labelledBy) : null;
    expect(
      Boolean(label?.trim()) || Boolean(labelledNode?.textContent?.trim()),
      `unnamed section: ${section.outerHTML.slice(0, 160)}`,
    ).toBe(true);
  }
}

function assertNoUnlabelledDashValues() {
  const dashes = [...document.querySelectorAll("*")].filter(
    (element) => element.childElementCount === 0 && element.textContent?.trim() === "—",
  );
  for (const dash of dashes) {
    const owner = dash.closest("[aria-label], [aria-labelledby]");
    const label = owner?.getAttribute("aria-label") ?? "";
    const labelledBy = owner?.getAttribute("aria-labelledby");
    const labelledNode = labelledBy ? document.getElementById(labelledBy) : null;
    expect(
      Boolean(label.trim()) || Boolean(labelledNode?.textContent?.trim()),
      `unlabelled em-dash placeholder: ${dash.outerHTML}`,
    ).toBe(true);
  }
}

describe("route UI integrity", () => {
  it.each(routes)("%s has a stable accessible document", async (_name, page, ready) => {
    renderRoute(page);
    await ready();
    await waitFor(() => expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0));
    expect(document.querySelectorAll("h1")).toHaveLength(1);
    assertHeadingHierarchy();
    assertNamedSections();
    expect(document.querySelectorAll('div[role="table"], div[role="list"], div[role="progressbar"]')).toHaveLength(0);
    expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0);
    expect(screen.queryByText(/^loading…$/i)).not.toBeInTheDocument();
    assertNoUnlabelledDashValues();
  });
});
