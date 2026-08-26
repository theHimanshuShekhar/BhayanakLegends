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
  PatchAggregate,
  PostGameDigest,
  Settings,
  SyncStatus,
  TrajectoryPoint,
} from "../../api/types";
import { ChampSelectPage } from "../champ-select";
import { ChampionsPage } from "../champions";
import { HistoryPage } from "../history";
import { LiveMatchPage } from "../live-match";
import { PostGamePage } from "../postgame";
import { ProgressPage } from "../progress";
import {
  champSelectActive,
  champSelectSession,
  idleIngame,
  idleSession,
  idleStatus,
  ingameActive,
  ingameSnapshot,
  makePack,
} from "./fixtures";

const victoryDigest: PostGameDigest = {
  match_id: "fixture-victory",
  played_at: "2026-08-24T00:00:00Z",
  champion: "Ahri",
  role: "MIDDLE",
  win: true,
  duration_s: 1800,
  checkpoints: { gold_diff_10: 100, gold_diff_15: -500, gold_diff_20: 250 },
  habits: [],
  headline: "A measured game",
};

const defeatDigest: PostGameDigest = {
  ...victoryDigest,
  match_id: "fixture-defeat",
  win: false,
};

// Unavailable scalars: every checkpoint null and no contracted habit outcome.
const unavailableScalarsDigest: PostGameDigest = {
  ...victoryDigest,
  checkpoints: { gold_diff_10: null, gold_diff_15: null, gold_diff_20: null },
};

const loadedSummary: HistorySummary = {
  matches: 4,
  patches: ["16.15", "16.16"],
  by_role: [{ role: "MIDDLE", games: 4, wins: 2 }],
  win_rate: 0.5,
};

const emptySummary: HistorySummary = {
  matches: 0,
  patches: [],
  by_role: [],
  win_rate: 0,
};

const settings: Settings = {
  riot_id: null,
  region_route: "sea",
  has_key: false,
  auto_sync: false,
};

const idleSync: SyncStatus = {
  state: "idle",
  mode: "era_first",
  total_queued: 0,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: null,
  started_at: null,
};

// Unknown totals: a running Backfill whose queue size is not known yet.
const unknownTotalsSync: SyncStatus = {
  state: "running",
  mode: "era_first",
  total_queued: 0,
  downloaded: 0,
  skipped: 0,
  failed: 0,
  current_match_id: "MATCH-UNKNOWN-TOTALS",
  started_at: "2026-08-24T00:00:00Z",
};

// Benchmarks where personal and population sides carry missing scalars: only
// metric pairs with BOTH values present may render a comparison card.
const partialBenchmarks: BenchmarkResponse = {
  state: "available",
  rows: [
    {
      role: "MIDDLE",
      personal: { cs10: 121 },
      population: { cs10_median: 128, level10_median: 12.4, sample: 26000 },
    },
    {
      role: "BOTTOM",
      personal: {},
      population: { sample: 26000 },
    },
  ],
};

const fixtureState = vi.hoisted(() => ({
  // `null` is a meaningful fixture (a missing digest), so UNSET marks "no
  // override" distinctly. It lives inside the hoisted store because hoisting
  // runs before any module-level initialization.
  UNSET: Symbol("unset-fixture"),
  historySummary: null as unknown,
  postgame: null as unknown,
  benchmarks: null as unknown,
  syncStatus: null as unknown,
  // data → resolve fixtures; held → park until flushed.
  mode: "data" as "data" | "held",
  pending: [] as Array<() => void>,
  // Endpoints forced to reject for error-fixture runs.
  failing: [] as string[],
}));

function respond<T>(endpoint: string, value: T): Promise<T> {
  if (fixtureState.failing.includes(endpoint)) {
    return Promise.reject(new Error("sidecar fixture failure"));
  }
  if (fixtureState.mode === "held") {
    return new Promise<T>((resolve) => {
      fixtureState.pending.push(() => resolve(value));
    });
  }
  return Promise.resolve(value);
}

function pickOverride<T>(override: unknown, fallback: T): T {
  // Fixture override or module default; shared by every parked endpoint.
  return (override === fixtureState.UNSET ? fallback : override) as T;
}

const liveState = vi.hoisted(() => ({
  status: null as LiveStatus | null,
  session: null as typeof champSelectSession | null,
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
      pack: vi.fn(async () => respond("pack", makePack())),
      settings: vi.fn(async () => respond("settings", settings)),
      updateSettings: vi.fn(async () => respond("settings", settings)),
      startSync: vi.fn(async () =>
        respond("sync", pickOverride(fixtureState.syncStatus, idleSync)),
      ),
      cancelSync: vi.fn(async () =>
        respond("sync", pickOverride(fixtureState.syncStatus, idleSync)),
      ),
      syncStatus: vi.fn(async () =>
        respond("sync", pickOverride(fixtureState.syncStatus, idleSync)),
      ),
      historySummary: vi.fn(async () =>
        respond("summary", pickOverride(fixtureState.historySummary, loadedSummary)),
      ),
      trajectories: vi.fn(async () => respond("trajectories", [] as TrajectoryPoint[])),
      patchAggregates: vi.fn(async () => respond("aggregates", [] as PatchAggregate[])),
      postgameLatest: vi.fn(async () =>
        respond("postgame", pickOverride(fixtureState.postgame, victoryDigest)),
      ),
      benchmarks: vi.fn(async () =>
        respond(
          "benchmarks",
          pickOverride(fixtureState.benchmarks, {
            state: "contract-suppressed",
            rows: [],
          } satisfies BenchmarkResponse),
        ),
      ),
      liveStatus: vi.fn(async () => liveState.status),
      liveSession: vi.fn(async () => liveState.session),
      liveIngame: vi.fn(async () => liveState.ingame),
    },
    connection: vi.fn(async () => ({ base: "", token: "t", status: "ok" as const })),
    eventsUrl: vi.fn(async () => "http://127.0.0.1:1/events?token=t"),
    actionableErrorMessage: actual.actionableErrorMessage,
    classifyApiError: actual.classifyApiError,
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

// Each entry names a query failure the owning route actually surfaces.
const errorSurfaces = [
  ["champ-select", routes[0], "pack"],
  ["live-match", routes[1], "pack"],
  ["postgame", routes[2], "postgame"],
  ["progress", routes[3], "benchmarks"],
  ["champions", routes[4], "pack"],
  ["history", routes[5], "summary"],
] as const;
beforeEach(() => {
  const unset = fixtureState.UNSET;
  fixtureState.mode = "data";
  fixtureState.historySummary = unset;
  fixtureState.postgame = unset;
  fixtureState.benchmarks = unset;
  fixtureState.syncStatus = unset;
  fixtureState.failing = [];
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
  for (const section of document.querySelectorAll("section")) {
    const label = section.getAttribute("aria-label");
    const labelledBy = section.getAttribute("aria-labelledby");
    const labelledNode = labelledBy ? document.getElementById(labelledBy) : null;
    expect(
      Boolean(label?.trim()) || Boolean(labelledNode?.textContent?.trim()),
      `unnamed section: ${section.outerHTML.slice(0, 160)}`,
    ).toBe(true);
  }
}

function accessibleName(element: Element): string {
  const label = element.getAttribute("aria-label");
  if (label?.trim()) return label.trim();
  const labelledBy = element.getAttribute("aria-labelledby");
  if (!labelledBy) return "";
  return labelledBy
    .split(/\s+/)
    .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
    .join(" ")
    .trim();
}

/** Collections must be native elements carrying their own accessible name. */
function assertNativeNamedCollections() {
  for (const substitute of document.querySelectorAll(
    '[role="table"]:not(table), [role="list"]:not(ul,ol), [role="progressbar"]:not(progress)',
  )) {
    expect.fail(`generic-div collection/progress substitute: ${substitute.outerHTML.slice(0, 120)}`);
  }
  for (const table of document.querySelectorAll("table")) {
    const named = table.caption?.textContent?.trim() || accessibleName(table);
    expect(named, `unnamed table: ${table.outerHTML.slice(0, 120)}`).not.toBe("");
  }
  for (const list of document.querySelectorAll("ul, ol")) {
    expect(accessibleName(list), `unnamed list: ${list.outerHTML.slice(0, 120)}`).not.toBe("");
  }
}

/**
 * A dash placeholder may exist only as decorative text inside an element that
 * carries its own context. It must never be the announced content of a live
 * region or an accessible name — repeated identical announcements are exactly
 * what this detector forbids.
 */
function assertNoRepeatedAccessibleDashes() {
  const dashes = [...document.querySelectorAll("*")].filter(
    (element) => element.childElementCount === 0 && element.textContent?.trim() === "—",
  );
  for (const dash of dashes) {
    const owner = dash.closest("[aria-label], [aria-labelledby]");
    expect(owner ? accessibleName(owner) : "", `unlabelled em-dash placeholder: ${dash.outerHTML}`).not.toBe("");
    for (const announcer of [dash, dash.parentElement]) {
      if (!announcer) continue;
      const role = announcer.getAttribute("role");
      expect(
        role !== null && ["status", "alert", "img"].includes(role),
        `dash exposed as ${role} announcement: ${announcer.outerHTML.slice(0, 120)}`,
      ).toBe(false);
      expect(
        announcer.getAttribute("aria-label")?.trim() === "—",
        `dash used as accessible name: ${announcer.outerHTML.slice(0, 120)}`,
      ).toBe(false);
    }
  }
}

function assertSettledIntegrity() {
  expect(document.querySelectorAll("h1")).toHaveLength(1);
  assertHeadingHierarchy();
  assertNamedSections();
  assertNativeNamedCollections();
  expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0);
  expect(screen.queryByText(/^loading…$/i)).not.toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
  assertNoRepeatedAccessibleDashes();
}

async function settledRoute(page: ReactElement, ready: () => Promise<unknown>) {
  renderRoute(page);
  await ready();
  await waitFor(() => expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0));
  assertSettledIntegrity();
}

describe("route UI integrity", () => {
  it.each(routes)("%s has a stable accessible document", async (_name, page, ready) => {
    await settledRoute(page, ready);
  });

  it("champ select active phase keeps the semantic contract", async () => {
    liveState.status = champSelectActive;
    liveState.session = champSelectSession;
    await settledRoute(routes[0][1], routes[0][2]);
  });

  it("in-game active phase keeps the semantic contract", async () => {
    liveState.status = ingameActive;
    liveState.ingame = ingameSnapshot;
    await settledRoute(routes[1][1], routes[1][2]);
  });

  it.each([
    ["victory", victoryDigest],
    ["defeat", defeatDigest],
    ["unavailable-scalars", unavailableScalarsDigest],
  ] as const)("postgame %s digest keeps the semantic contract", async (_name, digest) => {
    fixtureState.postgame = digest;
    renderRoute(routes[2][1]);
    const verdict = await screen.findByTestId("verdict");
    expect(verdict.textContent).toMatch(/Victory|Defeat|No game analyzed/);
    await waitFor(() => expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0));
    assertSettledIntegrity();
  });

  it("empty fixtures keep the semantic contract across routes", async () => {
    fixtureState.postgame = null;
    fixtureState.historySummary = emptySummary;
    fixtureState.benchmarks = { state: "insufficient-personal-history", rows: [] };

    // Post-game with no digest yet.
    renderRoute(routes[2][1]);
    expect(await screen.findByText("No digest yet")).toBeInTheDocument();
    assertSettledIntegrity();

    document.body.replaceChildren();

    // Trajectory with insufficient Personal History.
    renderRoute(routes[3][1]);
    expect(await screen.findByTestId("benchmarks-insufficient")).toBeInTheDocument();
    assertSettledIntegrity();

    document.body.replaceChildren();

    // Journal with zero synced matches.
    renderRoute(routes[5][1]);
    expect(await screen.findByTestId("summary-matches")).toHaveTextContent("0");
    expect(screen.getByTestId("summary-win-rate")).toBeInTheDocument();
    assertSettledIntegrity();
  });

  it("partial benchmark scalars render only complete comparisons", async () => {
    fixtureState.benchmarks = partialBenchmarks;
    renderRoute(routes[3][1]);
    const cards = await screen.findByTestId("benchmark-cards");
    // Only MIDDLE CS@10 has both sides; every other pair lacks a scalar.
    expect(cards.querySelectorAll("li")).toHaveLength(1);
    expect(cards.querySelector("li")).toHaveAttribute("aria-label", "CS@10 MIDDLE");
    await waitFor(() => expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0));
    assertSettledIntegrity();
  });

  it.each(errorSurfaces)("%s surfaces query errors without losing semantics", async (_name, route, endpoint) => {
    fixtureState.failing = [endpoint];
    renderRoute(route[1]);
    await screen.findAllByText(/Something went wrong|No local shards found/i);
    assertSettledIntegrity();
  });

  it("busy fixtures expose loading semantics and then settle clean", async () => {
    fixtureState.mode = "held";

    // Journal: visible skeleton plus an SR announcement while queries park.
    // jsdom's accname computation returns "" for this sr-only live region,
    // so match on content plus explicit role instead of role + name.
    const history = renderRoute(routes[5][1]);
    expect(document.querySelectorAll(".history-skeletons").length).toBeGreaterThan(0);
    const announcement = await history.findByText("Loading personal history");
    expect(announcement).toHaveAttribute("role", "status");

    // Trajectory: rail skeleton while the same graph stays parked.
    const progress = renderRoute(routes[3][1]);
    await progress.findByRole("heading", { name: "Benchmarks" });
    expect(document.querySelectorAll(".history-skeletons").length).toBeGreaterThan(0);

    // Release everything; skeletons must not survive into the settled UI.
    fixtureState.mode = "data";
    for (const release of fixtureState.pending.splice(0)) release();
    await waitFor(() => {
      expect(history.container.querySelectorAll(".history-skeletons")).toHaveLength(0);
      expect(progress.container.querySelectorAll(".history-skeletons")).toHaveLength(0);
    });
    expect(history.getByTestId("summary-matches")).toHaveTextContent("4");
  });

  it("running Backfill with unknown totals stays truthful", async () => {
    fixtureState.syncStatus = unknownTotalsSync;
    renderRoute(routes[5][1]);
    const counters = await screen.findByTestId("sync-counters");
    expect(counters.textContent).toContain("0 / 0 matches");
    expect(counters.textContent).not.toMatch(/NaN|Infinity/);
    expect(screen.getByTestId("sync-progress-bar")).toBeInTheDocument();
    await waitFor(() => expect(document.querySelectorAll(".history-skeletons")).toHaveLength(0));
    assertSettledIntegrity();
  });
});
