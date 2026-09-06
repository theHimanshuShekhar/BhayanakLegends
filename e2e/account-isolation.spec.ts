import { expect, test, type Page } from "@playwright/test";
import type {
  HistoryInsights,
  HistorySummary,
  LiveStatus,
  OwnerContext,
  Settings,
  SyncStatus,
} from "../src/api/types";

type BrowserInsights = Omit<HistoryInsights, "windows"> & {
  windows: HistoryInsights["windows"] | null;
};

const VIEWPORTS = [
  { width: 1280, height: 820 },
  { width: 980, height: 620 },
] as const;

type AccountFixture = {
  settings: Settings;
  status: SyncStatus;
  summary: HistorySummary;
  insights: BrowserInsights;
};

function owner(
  owner_key: string | null,
  generation: number,
  owner_state: OwnerContext["owner_state"],
  owner_error: string | null = null,
): OwnerContext {
  return { owner_key, generation, owner_state, owner_error };
}

function syncStatus(
  context: OwnerContext,
  overrides: Partial<SyncStatus> = {},
): SyncStatus {
  return {
    ...context,
    state: "idle",
    mode: "era_first",
    total_queued: 0,
    downloaded: 0,
    skipped: 0,
    failed: 0,
    current_match_id: null,
    started_at: null,
    ...overrides,
  };
}

function insightsFor(
  champion: string,
  wins: number,
  sampleSize: number,
): BrowserInsights {
  return {
    state: "available",
    sample_size: sampleSize,
    filters: { role: null, champion: null },
    roles: [
      {
        role: "MIDDLE",
        games: sampleSize,
        wins,
        win_rate: sampleSize ? wins / sampleSize : 0,
        sample_status: "insufficient",
      },
    ],
    champions: [
      {
        champion,
        games: sampleSize,
        wins,
        win_rate: sampleSize ? wins / sampleSize : 0,
        roles: ["MIDDLE"],
        sample_status: "insufficient",
      },
    ],
    windows: {
      latest: {
        name: "latest",
        games: sampleSize,
        wins,
        win_rate: sampleSize ? wins / sampleSize : 0,
        sample_status: "insufficient",
        completeness: "partial",
      },
      preceding: {
        name: "preceding",
        games: 0,
        wins: 0,
        win_rate: 0,
        sample_status: "insufficient",
        completeness: "unavailable",
      },
    },
    feature_contract_version: "v2",
    feature_contract_status: "available",
    feature_insights: [],
    feature_trajectories: [],
  };
}

const emptySummary: HistorySummary = {
  matches: 0,
  patches: [],
  by_role: [],
  win_rate: 0,
};
const emptyInsights: BrowserInsights = {
  state: "empty",
  sample_size: 0,
  filters: { role: null, champion: null },
  roles: [],
  champions: [],
  windows: null,
  feature_contract_version: null,
  feature_contract_status: "unavailable",
  feature_insights: [],
  feature_trajectories: [],
};

const accountA: AccountFixture = {
  settings: {
    ...owner("owner-a", 1, "active"),
    riot_id: "FirstPlayer#A001",
    region_route: "sea",
    has_key: true,
    auto_sync: false,
  },
  status: syncStatus(owner("owner-a", 1, "active"), {
    total_queued: 2,
    downloaded: 2,
  }),
  summary: {
    matches: 2,
    patches: ["16.1"],
    by_role: [{ role: "MIDDLE", games: 2, wins: 2 }],
    win_rate: 1,
  },
  insights: insightsFor("Ahri", 2, 2),
};

const accountB: AccountFixture = {
  settings: {
    ...owner("owner-b", 2, "active"),
    riot_id: "SecondPlayer#B002",
    region_route: "europe",
    has_key: true,
    auto_sync: false,
  },
  status: syncStatus(owner("owner-b", 2, "active"), {
    total_queued: 2,
    downloaded: 1,
    skipped: 1,
  }),
  summary: {
    matches: 2,
    patches: ["16.1"],
    by_role: [{ role: "MIDDLE", games: 2, wins: 0 }],
    win_rate: 0,
  },
  insights: insightsFor("Jinx", 0, 2),
};

const unresolved: AccountFixture = {
  settings: {
    ...owner(null, 3, "resolving"),
    riot_id: "Resolving#R003",
    region_route: "sea",
    has_key: true,
    auto_sync: false,
  },
  status: syncStatus(owner(null, 3, "resolving"), { state: "running" }),
  summary: emptySummary,
  insights: emptyInsights,
};

const empty: AccountFixture = {
  settings: {
    ...owner("owner-empty", 4, "active"),
    riot_id: "EmptyPlayer#E004",
    region_route: "asia",
    has_key: true,
    auto_sync: false,
  },
  status: syncStatus(owner("owner-empty", 4, "active")),
  summary: emptySummary,
  insights: emptyInsights,
};

const keyError: AccountFixture = {
  settings: {
    ...owner(null, 5, "error", "Riot API key required"),
    riot_id: "NeedsKey#K005",
    region_route: "americas",
    has_key: false,
    auto_sync: false,
  },
  status: syncStatus(owner(null, 5, "error", "Riot API key required"), {
    state: "error",
  }),
  summary: emptySummary,
  insights: emptyInsights,
};

const idleLiveStatus: LiveStatus = {
  champ_select: { active: false, phase: null },
  ingame: { active: false, game_id: null, mode: null, clock_s: 0 },
  last_error: null,
};

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

async function mockShell(page: Page, fixture: () => AccountFixture): Promise<void> {
  await page.route("**/settings", (route) =>
    route.fulfill({ json: fixture().settings }),
  );
  await page.route("**/history/summary", (route) =>
    route.fulfill({ json: fixture().summary }),
  );
  await page.route("**/history/insights**", (route) =>
    route.fulfill({ json: fixture().insights }),
  );
  await page.route("**/sync/status", (route) =>
    route.fulfill({ json: fixture().status }),
  );
  await page.route("**/live/status", (route) =>
    route.fulfill({ json: idleLiveStatus }),
  );
  await page.route("**/events**", (route) => route.abort());
}

async function expectResponsiveHistory(page: Page): Promise<void> {
  await expect(page.getByTestId("sync-panel")).toBeVisible();
  const overflow = await page.evaluate(
    "document.documentElement.scrollWidth - document.documentElement.clientWidth",
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const riotId = page.getByTestId("input-riot-id");
  await riotId.focus();
  await expect(riotId).toBeFocused();
  const start = page.getByRole("button", { name: "Start Backfill" });
  if (await start.isEnabled()) {
    await start.focus();
    await expect(start).toBeFocused();
  }
}

async function expectActiveAccount(
  page: Page,
  fixture: AccountFixture,
): Promise<void> {
  await expect(page.getByTestId("sync-owner-status")).toHaveText(
    "Riot account active.",
  );
  await expect(page.getByTestId("input-riot-id")).toHaveValue(
    fixture.settings.riot_id ?? "",
  );
  await expect(page.getByTestId("summary-matches")).toHaveText(
    String(fixture.summary.matches),
  );
  if (fixture.insights.sample_size > 0) {
    await expect(page.getByTestId("insights-sample-size")).toContainText(
      `${fixture.insights.sample_size} filtered matches`,
    );
  } else {
    await expect(page.getByTestId("insights-empty")).toBeVisible();
  }
  const champion = fixture.insights.champions[0]?.champion;
  if (champion) {
    await expect(page.getByTestId("insights-champion-table")).toContainText(
      champion,
    );
  }
}

test.describe("account isolation browser evidence", () => {
  for (const viewport of VIEWPORTS) {
    test(`A→B→A keeps shared-game perspectives and responsive focus at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      let fixture = accountA;
      await mockShell(page, () => fixture);
      await page.goto("/history", { waitUntil: "domcontentloaded" });

      await expectActiveAccount(page, accountA);
      await expect(page.getByTestId("sync-counters")).toHaveText("2 / 2 matches");
      await expectResponsiveHistory(page);

      fixture = accountB;
      await page.reload({ waitUntil: "domcontentloaded" });
      await expectActiveAccount(page, accountB);
      await expect(page.getByTestId("sync-counters")).toContainText("1 / 2 matches");
      await expect(page.getByTestId("sync-counters")).toContainText("1 skipped");
      await expect(page.getByTestId("insights-champion-table")).not.toContainText("Ahri");

      fixture = accountA;
      await page.reload({ waitUntil: "domcontentloaded" });
      await expectActiveAccount(page, accountA);
      await expect(page.getByTestId("sync-counters")).toHaveText("2 / 2 matches");
      await expect(page.getByTestId("insights-champion-table")).not.toContainText("Jinx");
      await expectResponsiveHistory(page);
    });

    test(`old in-flight response cannot paint after an owner switch at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const summaryStarted = deferred();
      const releaseOldSummary = deferred();
      let summaryCalls = 0;
      let insightsCalls = 0;

      await page.route("**/settings", (route) =>
        route.fulfill({ json: accountA.settings }),
      );
      await page.route("**/history/summary", async (route) => {
        summaryCalls += 1;
        if (summaryCalls === 1) {
          summaryStarted.resolve();
          await releaseOldSummary.promise;
          await route.fulfill({ json: accountA.summary });
          return;
        }
        await route.fulfill({ json: accountB.summary });
      });
      await page.route("**/history/insights**", (route) => {
        insightsCalls += 1;
        return route.fulfill({
          json: insightsCalls === 1 ? accountA.insights : accountB.insights,
        });
      });
      await page.route("**/sync/status", async (route) => {
        await summaryStarted.promise;
        await route.fulfill({ json: accountB.status });
      });
      await page.route("**/live/status", (route) =>
        route.fulfill({ json: idleLiveStatus }),
      );
      await page.route("**/events**", (route) => route.abort());

      await page.goto("/history", { waitUntil: "domcontentloaded" });
      await summaryStarted.promise;
      await expect(page.getByTestId("input-riot-id")).toHaveValue(accountA.settings.riot_id ?? "");
      await expect(page.getByTestId("summary-matches")).toHaveText("2");
      await expect(page.getByTestId("insights-champion-table")).toContainText("Jinx");

      releaseOldSummary.resolve();
      await expect(page.getByTestId("insights-champion-table")).toContainText("Jinx");
      await expect(page.getByTestId("insights-champion-table")).not.toContainText("Ahri");
      await expectResponsiveHistory(page);
    });

    test(`unresolved, empty, and key-error states stay explicit at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      let fixture = unresolved;
      await mockShell(page, () => fixture);
      await page.goto("/history", { waitUntil: "domcontentloaded" });

      await expect(page.getByTestId("sync-owner-status")).toHaveText("Resolving Riot account…");
      await expect(page.getByTestId("summary-matches")).toHaveCount(0);
      await expect(page.getByTestId("insights-empty")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Start Backfill" })).toBeDisabled();
      await expect(page.getByTestId("start-disabled-reason")).toContainText("Resolving Riot account");
      await expectResponsiveHistory(page);

      fixture = empty;
      await page.reload({ waitUntil: "domcontentloaded" });
      await expectActiveAccount(page, empty);
      await expect(page.getByTestId("insights-empty")).toContainText("No Personal History yet");
      await expect(page.getByTestId("summary-patches")).toContainText("No patches in history");
      await expectResponsiveHistory(page);

      fixture = keyError;
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("sync-owner-status")).toContainText("Riot API key required");
      await expect(page.getByTestId("summary-matches")).toHaveCount(0);
      await expect(page.getByTestId("insights-empty")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Start Backfill" })).toBeEnabled();
      await expectResponsiveHistory(page);
    });
  }
});
