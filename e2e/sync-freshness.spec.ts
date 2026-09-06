import { expect, test, type Page } from "@playwright/test";
import type { Settings, SyncStatus } from "../src/api/types";

const VIEWPORTS = [
  { width: 1280, height: 820 },
  { width: 980, height: 620 },
] as const;

const ownerA = {
  owner_key: "fixture-owner-a",
  generation: 1,
  owner_state: "active" as const,
  owner_error: null,
};
const ownerB = {
  owner_key: "fixture-owner-b",
  generation: 2,
  owner_state: "active" as const,
  owner_error: null,
};
const settingsA: Settings = {
  ...ownerA,
  riot_id: "FirstPlayer#A001",
  region_route: "sea",
  has_key: true,
  auto_sync: false,
};
const settingsB: Settings = {
  ...ownerB,
  riot_id: "SecondPlayer#B002",
  region_route: "europe",
  has_key: true,
  auto_sync: false,
};

function syncStatus(owner: typeof ownerA | typeof ownerB, overrides: Partial<SyncStatus> = {}): SyncStatus {
  return {
    ...owner,
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

const idleA = syncStatus(ownerA);
const runningA = syncStatus(ownerA, {
  state: "running",
  total_queued: 25,
  downloaded: 5,
  current_match_id: "A-RUNNING",
  started_at: "2026-09-06T00:00:00Z",
});
const completedA = syncStatus(ownerA, {
  total_queued: 25,
  downloaded: 25,
});
const idleB = syncStatus(ownerB);

const emptySummary = {
  matches: 0,
  patches: [],
  by_role: [],
  win_rate: 0,
};
const emptyInsights = {
  state: "empty",
  sample_size: 0,
  filters: { role: null, champion: null },
  roles: [],
  champions: [],
  windows: null,
  feature_contract_version: null,
  feature_contract_status: "unavailable",
};

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

async function mockJournalData(
  page: Page,
  settings: Settings,
  statuses: readonly SyncStatus[],
): Promise<void> {
  let statusIndex = 0;
  await page.route("**/settings", (route) => route.fulfill({ json: settings }));
  await page.route("**/history/summary", (route) => route.fulfill({ json: emptySummary }));
  await page.route("**/history/insights**", (route) => route.fulfill({ json: emptyInsights }));
  await page.route("**/events**", (route) => route.abort());
  await page.route("**/sync/status", (route) => {
    const status = statuses[Math.min(statusIndex++, statuses.length - 1)];
    return route.fulfill({ json: status });
  });
}

async function expectResponsiveHistory(page: Page): Promise<void> {
  const panel = page.getByTestId("sync-panel");
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("input-riot-id")).toBeVisible();
  const overflow = await page.evaluate(
    "document.documentElement.scrollWidth - document.documentElement.clientWidth",
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const start = page.getByRole("button", { name: "Start Backfill" });
  await start.focus();
  await expect(start).toBeFocused();
}

test.describe("sync freshness browser evidence", () => {
  for (const viewport of VIEWPORTS) {
    test(`poll recovery and controls remain truthful with SSE disconnected at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await mockJournalData(page, settingsA, [idleA, runningA, completedA]);
      await page.goto("/history");

      await expect(page.getByTestId("input-riot-id")).toHaveValue(settingsA.riot_id ?? "");
      await expect(page.getByTestId("sync-counters")).toHaveText("0 / 0 matches");
      await expect(page.getByRole("button", { name: "Start Backfill" })).toBeEnabled();
      await expectResponsiveHistory(page);

      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("sync-counters")).toHaveText("5 / 25 matches");
      await expect(page.getByRole("button", { name: "Start Backfill" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "Cancel" })).toBeEnabled();
      await expect(page.getByTestId("sync-current")).toHaveText("A-RUNNING");

      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("sync-counters")).toHaveText("25 / 25 matches");
      await expect(page.getByRole("button", { name: "Start Backfill" })).toBeEnabled();
      await expect(page.getByRole("button", { name: "Cancel" })).toBeDisabled();
      await expect(page.getByTestId("sync-progress-bar")).toHaveClass(/bg-teal/);
      await expectResponsiveHistory(page);
    });

    test(`delayed old-owner status and event cannot populate the switched account at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      let settings = settingsA;
      let statusCalls = 0;
      const firstStatusStarted = deferred();
      const releaseFirstStatus = deferred();
      const releaseOldOwnerStatus = deferred();
      const releaseRunningEvent = deferred();

      await page.route("**/settings", (route) => route.fulfill({ json: settings }));
      await page.route("**/history/summary", (route) => route.fulfill({ json: emptySummary }));
      await page.route("**/history/insights**", (route) => route.fulfill({ json: emptyInsights }));
      await page.route("**/sync/status", async (route) => {
        statusCalls += 1;
        if (statusCalls === 1) {
          firstStatusStarted.resolve();
          await releaseFirstStatus.promise;
          await route.fulfill({ json: idleA });
          return;
        }
        if (statusCalls === 2) {
          await releaseOldOwnerStatus.promise;
          await route.fulfill({ json: runningA });
          return;
        }
        await route.fulfill({ json: idleB });
      });
      let eventFrames = 0;
      await page.route("**/events**", async (route) => {
        eventFrames += 1;
        if (eventFrames > 1) {
          await route.abort();
          return;
        }
        await releaseRunningEvent.promise;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
          },
          body: `data: ${JSON.stringify({ type: "sync.progress", ts: "e2e-running", data: runningA })}\n\n`,
        });
      });

      await page.goto("/history", { waitUntil: "domcontentloaded" });
      await firstStatusStarted.promise;
      releaseRunningEvent.resolve();
      await expect(page.getByTestId("sync-counters")).toHaveText("5 / 25 matches");
      releaseFirstStatus.resolve();
      await expect(page.getByTestId("sync-counters")).toHaveText("5 / 25 matches");

      settings = settingsB;
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("input-riot-id")).toHaveValue(settingsB.riot_id ?? "");
      releaseOldOwnerStatus.resolve();
      await expect(page.getByTestId("sync-progress")).toHaveCount(0);
      await expect(page.getByTestId("sync-current")).toHaveCount(0);

      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("input-riot-id")).toHaveValue(settingsB.riot_id ?? "");
      await expect(page.getByTestId("sync-counters")).toHaveText("0 / 0 matches");
      await expect(page.getByTestId("sync-current")).toHaveCount(0);
      await expectResponsiveHistory(page);
    });
  }
});
