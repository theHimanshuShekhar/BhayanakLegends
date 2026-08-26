/// <reference lib="dom" />

import { expect, test, type APIRequestContext, type Locator, type Page, type TestInfo } from "@playwright/test";

const SIDECAR = "http://127.0.0.1:23122";
const LCU = "http://127.0.0.1:23123";
const LIVE = "http://127.0.0.1:23124";
const AUTH = {
  "X-BL-Token": "local-sidecar-development-token-32chars",
  Host: "127.0.0.1:23122",
};
const VIEWPORTS = [
  { width: 1280, height: 820 },
  { width: 980, height: 620 },
] as const;

type LivePlayer = {
  summoner: string;
  champion: string | null;
  level: number;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  ward_score: number;
  items: { id: number; count: number }[];
};

type LiveSnapshot = {
  active: boolean;
  clock_s: number;
  mode: string | null;
  local_summoner: string | null;
  local_champion: string | null;
  teams: { order: LivePlayer[]; chaos: LivePlayer[] };
  events: { name: string; t_s: number; actor: string | null; victim: string | null; detail: string | null }[];
};

async function setScenario(request: APIRequestContext, base: string, scenario: string) {
  const response = await request.post(`${base}/control`, { data: { scenario } });
  expect(response.ok()).toBeTruthy();
}

async function readIngame(request: APIRequestContext): Promise<LiveSnapshot> {
  const response = await request.get(`${SIDECAR}/live/ingame`, { headers: AUTH });
  expect(response.ok()).toBeTruthy();
  const snapshot = (await response.json()) as LiveSnapshot;
  expect(snapshot.active).toBe(true);
  expect(snapshot.teams).toEqual(expect.objectContaining({ order: expect.any(Array), chaos: expect.any(Array) }));
  return snapshot;
}

function containsForbiddenKeys(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenKeys);
  if (!value || typeof value !== "object") return false;
  return Object.entries(value).some(([key, child]) =>
    /ability|ultimate|cooldown|spell[_ -]?timer|current[_ -]?death|winner|lane[_ -]?advantage|item[_ -]?value|held[_ -]?gold/i.test(key) ||
    containsForbiddenKeys(child),
  );
}

function collectBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}

function expectNoBrowserErrors(errors: string[]) {
  expect(errors, `browser console/page errors:\n${errors.join("\n")}`).toEqual([]);
}

async function captureState(page: Page, testInfo: TestInfo, state: string) {
  const path = testInfo.outputPath(`${state}.png`);
  await page.screenshot({ path, fullPage: true });
  await testInfo.attach(`live-${state}`, { path, contentType: "image/png" });
}

async function expectNoHorizontalClipping(page: Page) {
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  expect(metrics.documentWidth, `horizontal overflow at ${metrics.viewport}px`).toBeLessThanOrEqual(metrics.viewport);
}

async function expectVisibleFocus(page: Page, locator: Locator) {
  await locator.focus();
  await expect.poll(() => locator.evaluate((node) => document.activeElement === node)).toBe(true);
  const outline = await locator.evaluate((node) => {
    const style = getComputedStyle(node);
    return `${style.outlineStyle} ${style.outlineWidth} ${style.boxShadow}`;
  });
  expect(outline).not.toMatch(/^none 0px(?: none)?$/);
}

function teamTotals(players: LivePlayer[]) {
  return players.reduce(
    (totals, player) => ({
      cs: totals.cs + player.cs,
      level: totals.level + player.level,
      kills: totals.kills + player.kills,
      deaths: totals.deaths + player.deaths,
    }),
    { cs: 0, level: 0, kills: 0, deaths: 0 },
  );
}

async function expectRenderedSnapshot(page: Page, snapshot: LiveSnapshot) {
  for (const side of ["order", "chaos"] as const) {
    const players = snapshot.teams[side];
    const totals = teamTotals(players);
    for (const [field, value] of Object.entries(totals)) {
      await expect(page.getByTestId(`team-total-${side}-${field}`)).toHaveText(String(value));
    }

    const roster = page.getByTestId(`team-${side}`);
    await expect(roster.getByRole("row")).toHaveCount(players.length);
    for (const player of players) {
      const row = player.summoner === snapshot.local_summoner
        ? page.getByTestId("player-row-local")
        : page.getByTestId(`player-row-${side}-${player.summoner}`);
      await expect(row).toContainText(player.summoner);
      await expect(row).toContainText(player.champion ?? "Unavailable");
      await expect(row).toContainText(`${player.level}`);
      await expect(row).toContainText(new RegExp(`${player.kills}\\s*/\\s*${player.deaths}\\s*/\\s*${player.assists}`));
      await expect(row).toContainText(`${player.cs}`);

      const itemPlayer = page.getByTestId(`items-player-${side}-${player.summoner}`);
      await expect(itemPlayer).toHaveCount(1);
      for (const [index, item] of player.items.entries()) {
        await expect(page.getByTestId(`item-${side}-${player.summoner}-${index}`)).toHaveText(
          new RegExp(`^Item ${item.id}\\s+count ${item.count}$`),
        );
      }
      await expect(itemPlayer.getByRole("listitem")).toHaveCount(player.items.length);
    }
  }

  const events = snapshot.events.slice(-40);
  const eventRows = page.getByTestId("event-feed-rows").getByRole("listitem");
  await expect(eventRows).toHaveCount(events.length);
  for (const [index, event] of events.entries()) {
    await expect(page.getByTestId(`event-name-${index}`)).toContainText(event.name);
    if (event.detail) await expect(page.getByTestId(`event-name-${index}`)).toContainText(event.detail);
  }
}

async function expectLiveDataContractDetector(page: Page, snapshot?: LiveSnapshot) {
  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toMatch(
    /50\s*\/\s*50|empty grooves|lanes ahead|dead right now|spell(?:s)?\s*(?:placeholder|timer)|enemy[\s\S]{0,80}\b\d+:\d{2}\b/i,
  );
  expect(bodyText).not.toMatch(/\b(?:ability|ultimate|cooldown|current death|winner|lane advantage|item value|held gold)\b/i);
  const waiting = page.getByRole("status").filter({ hasText: /waiting for live companion game data/i });
  expect(await waiting.count()).toBeLessThanOrEqual(1);
  expect(await page.getByTestId("live-route-status").count()).toBe(1);
  if (snapshot?.active) {
    await expectRenderedSnapshot(page, snapshot);
  }
}

async function expectReducedMotion(page: Page) {
  const reducedMotion = await page.evaluate(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  expect(reducedMotion).toBe(true);
  const moving = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>(".rc-route, .bl-pulse, .bl-width, [role='progressbar']")).filter((node) => {
      const style = getComputedStyle(node);
      return style.animationName !== "none" || style.transitionDuration.split(",").some((duration) => Number.parseFloat(duration) > 0);
    }).map((node) => {
      const style = getComputedStyle(node);
      return `${node.dataset.testid ?? (node.className || node.tagName)} animation=${style.animationName} transition=${style.transitionDuration}`;
    }),
  );
  expect(moving, `animated elements under prefers-reduced-motion: ${moving.join(", ")}`).toEqual([]);
}
async function waitForPreloadedStatus(
  request: APIRequestContext,
  expected: { champSelect?: boolean; inGame?: boolean },
) {
  await expect
    .poll(async () => {
      const response = await request.get(`${SIDECAR}/live/status`, { headers: AUTH });
      expect(response.ok()).toBeTruthy();
      const status = (await response.json()) as {
        champ_select: { active: boolean };
        ingame: { active: boolean };
      };
      return (
        (expected.champSelect === undefined || status.champ_select.active === expected.champSelect) &&
        (expected.inGame === undefined || status.ingame.active === expected.inGame)
      );
    })
    .toBe(true);
}

function countEventStreams(page: Page) {
  // Counts every EventSource construction so a flow can prove all subscribers
  // share exactly one stream instead of leaking duplicates per route/mount.
  return page.addInitScript(() => {
    class CountedEventSource extends EventSource {
      constructor(...args: ConstructorParameters<typeof EventSource>) {
        super(...args);
        const host = window as typeof window & { blEventStreams?: number };
        host.blEventStreams = (host.blEventStreams ?? 0) + 1;
      }
    }
    window.EventSource = CountedEventSource;
  });
}

test.describe("active Live Companion replay", () => {
  test("in-game replay proves idle → active → update → reconnect without reload", async ({ page, request }, testInfo) => {
    const browserErrors = collectBrowserErrors(page);
    await page.setViewportSize(VIEWPORTS[0]);
    await setScenario(request, LCU, "idle");
    await setScenario(request, LIVE, "idle");
    await page.goto("/live");
    await expect(page.getByTestId("live-route-status")).toHaveText("Waiting for Live Companion game data");
    await expect(page.getByRole("status").filter({ hasText: /waiting for live companion game data/i })).toHaveCount(1);
    await captureState(page, testInfo, "idle");

    await setScenario(request, LCU, "in-game");
    await setScenario(request, LIVE, "in-game");
    await expect(page.getByTestId("bridge-status")).toContainText(":2999");
    await expect(page.getByTestId("player-row-local")).toContainText("Viktor");
    const initial = await readIngame(request);
    await expect(initial.teams.order.flatMap((player) => player.items)).not.toHaveLength(0);
    await expect(page.getByTestId("team-chaos")).toContainText("Camille");
    await expect(page.getByTestId("score-strip")).toContainText("kills");
    await expect(page.getByTestId("event-feed")).toContainText("DragonKill");
    await expect(page.getByTestId("wp-value")).toHaveText("—");
    await expect(page.getByTestId("wp-band")).toContainText(
      "The current Findings Pack lacks the compatible live input, quartile boundaries, and model inputs needed to map this game.",
    );
    await expect(page.getByTestId("wp-band")).not.toContainText(/bottom quartile|top quartile/i);
    await expectRenderedSnapshot(page, initial);
    await expectLiveDataContractDetector(page, initial);
    await expectNoHorizontalClipping(page);
    await captureState(page, testInfo, "active");

    await setScenario(request, LCU, "in-game-update");
    await setScenario(request, LIVE, "in-game-update");
    await expect(page.getByTestId("event-feed")).toContainText("BaronKill");
    await expect(page.getByTestId("active-kda")).toContainText("5 / 2 / 7");
    await expect(page.getByTestId("game-clock")).toContainText("13:32");
    const updated = await readIngame(request);
    await expectRenderedSnapshot(page, updated);
    await expectLiveDataContractDetector(page, updated);
    await expect(page).toHaveURL(/\/live$/);
    await captureState(page, testInfo, "update");

    await setScenario(request, LCU, "reconnect");
    await setScenario(request, LIVE, "reconnect");
    await expect(page.getByTestId("live-route-status")).toHaveText("Waiting for Live Companion game data");
    await expect(page.getByTestId("player-row-local")).toHaveCount(0);
    await expect(page.getByTestId("live-route-status").filter({ hasText: /waiting/i })).toHaveCount(1);
    await expect(page).toHaveURL(/\/live$/);
    await expectNoHorizontalClipping(page);
    await captureState(page, testInfo, "reconnect");
    expectNoBrowserErrors(browserErrors);
  });

  test("live data contract detector", async ({ page, request }, testInfo) => {
    const browserErrors = collectBrowserErrors(page);
    await page.setViewportSize(VIEWPORTS[1]);
    await setScenario(request, LCU, "in-game");
    await setScenario(request, LIVE, "in-game");
    await page.goto("/live");
    await expect(page.getByTestId("player-row-local")).toBeVisible();
    const snapshot = await readIngame(request);
    await expectLiveDataContractDetector(page, snapshot);
    await expectNoHorizontalClipping(page);
    await setScenario(request, LCU, "in-game-empty");
    await setScenario(request, LIVE, "in-game-empty");
    await expect(page.getByText("No items reported", { exact: true })).toHaveCount(10);
    await expect(page.getByTestId("event-feed")).toHaveText(/No events reported/);
    const empty = await readIngame(request);
    expect(empty.teams.order.flatMap((player) => player.items)).toHaveLength(0);
    expect(empty.teams.chaos.flatMap((player) => player.items)).toHaveLength(0);
    expect(empty.events).toHaveLength(0);
    await expectLiveDataContractDetector(page);
    await captureState(page, testInfo, "empty");
    expectNoBrowserErrors(browserErrors);
  });

  test("live contrast", async ({ page, request }, testInfo) => {
    const browserErrors = collectBrowserErrors(page);
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      await setScenario(request, LCU, "idle");
      await setScenario(request, LIVE, "idle");
      await page.goto("/live");
      await expect(page.getByTestId("live-route-status")).toContainText("Waiting");
      await expectNoHorizontalClipping(page);
      await captureState(page, testInfo, `contrast-neutral-${viewport.width}`);

      await setScenario(request, LCU, "in-game");
      await setScenario(request, LIVE, "in-game");
      await expect(page.getByTestId("player-row-local")).toBeVisible();
      await expectNoHorizontalClipping(page);
      await captureState(page, testInfo, `contrast-active-${viewport.width}`);

      await page.route(`${SIDECAR}/live/ingame`, (route) => route.abort("failed"));
      await page.reload();
      await expect(page.getByTestId("ingame-error")).toBeVisible();
      await captureState(page, testInfo, `contrast-error-${viewport.width}`);
      await page.unroute(`${SIDECAR}/live/ingame`);

      for (const [outcome, win] of [["victory", true], ["defeat", false]] as const) {
        await page.route(`${SIDECAR}/postgame/latest`, async (route) => {
          const response = await route.fetch();
          const digest = (await response.json()) as Record<string, unknown> | null;
          if (digest) digest.win = win;
          await route.fulfill({ response, body: JSON.stringify(digest) });
        });
        await page.goto("/postgame");
        await expect(page.getByTestId("verdict")).toHaveText(outcome === "victory" ? "Victory" : "Defeat");
        await captureState(page, testInfo, `contrast-${outcome}-${viewport.width}`);
        await page.unroute(`${SIDECAR}/postgame/latest`);
      }
      await page.goto("/live");

      const ratios = await page.evaluate(() => {
        const luminance = (channel: number) => {
          const value = channel / 255;
          return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        };
        const color = (value: string) => {
          const match = value.match(/\d+/g)?.map(Number);
          return match && match.length >= 3 ? match.slice(0, 3) : null;
        };
        const contrast = (foreground: string, background: string) => {
          const fg = color(foreground);
          const bg = color(background);
          if (!fg || !bg) return null;
          const fgLum = 0.2126 * luminance(fg[0]) + 0.7152 * luminance(fg[1]) + 0.0722 * luminance(fg[2]);
          const bgLum = 0.2126 * luminance(bg[0]) + 0.7152 * luminance(bg[1]) + 0.0722 * luminance(bg[2]);
          return (Math.max(fgLum, bgLum) + 0.05) / (Math.min(fgLum, bgLum) + 0.05);
        };
        const ids = ["live-route-status", "bridge-status", "player-list", "team-totals", "event-feed", "items-by-player", "wp-band", "ingame-error"];
        return ids.flatMap((id) => {
          const node = document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
          if (!node) return [];
          const style = getComputedStyle(node);
          return [{ id, ratio: contrast(style.color, style.backgroundColor) }];
        });
      });
      for (const result of ratios) {
        if (result.ratio !== null) expect(result.ratio, `${result.id} contrast`).toBeGreaterThanOrEqual(4.5);
      }
    }
    expectNoBrowserErrors(browserErrors.filter((error) => !error.includes("ERR_FAILED")));
  });

  test("keyboard, reduced motion, malformed/reconnect and request-error states remain perceivable", async ({ page, request }, testInfo) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    const browserErrors = collectBrowserErrors(page);
    await setScenario(request, LCU, "idle");
    await setScenario(request, LIVE, "idle");
    await page.goto("/live");
    await setScenario(request, LCU, "in-game");
    await setScenario(request, LIVE, "in-game");
    await expect(page.getByTestId("player-row-local")).toBeVisible();
    await expectReducedMotion(page);
    await setScenario(request, LCU, "in-game-update");
    await setScenario(request, LIVE, "in-game-update");
    await expect(page.getByTestId("live-companion-mode")).toHaveText("in-game");
    const toggle = page.getByRole("button", { name: "Expand Live Companion" });
    await expectVisibleFocus(page, toggle);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Collapse Live Companion" })).toBeVisible();
    await page.keyboard.press(" ");
    await expect(page.getByRole("button", { name: "Expand Live Companion" })).toBeVisible();
    await page.goto("/champ-select");
    await page.goto("/live");
    await page.goBack();
    await expect(page).toHaveURL(/\/champ-select$/);
    await page.goForward();
    await expect(page).toHaveURL(/\/live$/);
    await captureState(page, testInfo, "keyboard-reduced-motion");

    await setScenario(request, LCU, "malformed");
    await setScenario(request, LIVE, "malformed");
    await expect(page.getByTestId("live-route-status")).toHaveText(/Waiting/);
    await expect(page.getByTestId("player-row-local")).toHaveCount(0);
    await captureState(page, testInfo, "malformed");
    const statusResponse = await request.get(`${SIDECAR}/live/status`, { headers: AUTH });
    expect(statusResponse.ok()).toBeTruthy();
    expect(containsForbiddenKeys(await statusResponse.json())).toBe(false);

    await page.route(`${SIDECAR}/live/ingame`, (route) => route.abort("failed"));
    await page.reload();
    await expect(page.getByTestId("ingame-error")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(1);
    await captureState(page, testInfo, "error");
    expectNoBrowserErrors(browserErrors.filter((error) => !error.includes("ERR_FAILED")));
  });
  test("startup hydration through champ select, in-game, game end, and reconnect is one continuous flow", async ({ page, request }, testInfo) => {
    test.setTimeout(180_000);
    const browserErrors = collectBrowserErrors(page);
    countEventStreams(page);

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);

      // Startup hydration: preload an active champ select before navigation so
      // no change frame can arrive during load — only the preloaded /live/status
      // fetch can explain the companion entering champ select mode.
      await setScenario(request, LCU, "champ-select");
      await setScenario(request, LIVE, "champ-select");
      await waitForPreloadedStatus(request, { champSelect: true });
      await page.goto("/champ-select");
      await expect(page.getByTestId("live-companion-mode")).toHaveText("champ select");
      await expect(page.getByTestId("champ-select-page")).toBeVisible();
      await expect(page.getByTestId("your-lane-champion")).toHaveText("Annie");
      await page.evaluate(() => {
        (window as typeof window & { blContinuousFlow?: boolean }).blContinuousFlow = true;
      });
      await captureState(page, testInfo, `flow-hydrated-${viewport.width}`);

      // Champ select → in-game happens reactively on the same document.
      await setScenario(request, LCU, "in-game");
      await setScenario(request, LIVE, "in-game");
      const expand = page.getByRole("button", { name: "Expand Live Companion" });
      await expect(expand).toBeVisible();
      await expect(page.getByTestId("live-companion-mode")).toHaveText("in-game");
      await expect(expand).toHaveAttribute("aria-expanded", "false");
      await expect(page.getByTestId("live-companion")).toContainText(
        "Borderless-windowed mode required; this companion is not click-through.",
      );
      await expect(page).toHaveURL(/\/champ-select$/);

      await expand.click();
      const collapse = page.getByRole("button", { name: "Collapse Live Companion" });
      await expect(collapse).toBeVisible();

      // Client-side route change keeps the same document and the expanded widget.
      await page.getByTestId("nav-live").click();
      await expect(page).toHaveURL(/\/live$/);
      await expect(collapse).toBeVisible();
      await expect(page.getByTestId("live-route-status")).toHaveText("Live Companion game data active");
      await expect(page.getByTestId("bridge-status")).toContainText(":2999 · 1s poll");

      const initial = await readIngame(request);
      await expect(initial.teams.order.flatMap((player) => player.items)).not.toHaveLength(0);
      await expectRenderedSnapshot(page, initial);
      await expectLiveDataContractDetector(page, initial);
      await expect(page.getByTestId("wp-value")).toHaveText("—");
      await expect(page.getByTestId("wp-band")).toContainText(
        "The current Findings Pack lacks the compatible live input, quartile boundaries, and model inputs needed to map this game.",
      );
      await expect(page.getByTestId("wp-band")).not.toContainText(/bottom quartile|top quartile/i);
      await expectNoHorizontalClipping(page);
      await captureState(page, testInfo, `flow-in-game-${viewport.width}`);

      // Repeated frames leave expansion untouched while the game continues.
      await setScenario(request, LCU, "in-game-update");
      await setScenario(request, LIVE, "in-game-update");
      await expect(page.getByTestId("event-feed")).toContainText("BaronKill");
      await expect(page.getByTestId("active-kda")).toContainText("5 / 2 / 7");
      await expect(page.getByTestId("game-clock")).toContainText("13:32");
      const updated = await readIngame(request);
      await expectRenderedSnapshot(page, updated);
      await expectLiveDataContractDetector(page, updated);
      await expect(collapse).toBeVisible();
      await captureState(page, testInfo, `flow-in-game-update-${viewport.width}`);

      // Authoritative game end returns the route to waiting and resets the widget.
      await setScenario(request, LCU, "idle");
      await setScenario(request, LIVE, "idle");
      await expect(page.getByTestId("live-route-status")).toHaveText("Waiting for Live Companion game data");
      await expect(page.getByTestId("live-companion-mode")).toHaveText("idle");
      await expect(page.getByRole("button", { name: /(?:Expand|Collapse) Live Companion/ })).toHaveCount(0);
      await expect(page.getByTestId("player-row-local")).toHaveCount(0);
      await expect(page.getByTestId("team-totals-unavailable")).toContainText("No snapshot");
      await expect(page.getByTestId("items-unavailable")).toContainText("No snapshot");
      await captureState(page, testInfo, `flow-game-end-${viewport.width}`);

      // Reconnect keeps the reconciled waiting state on the same single stream,
      // with no reload and no browser errors across the whole lifecycle.
      await setScenario(request, LCU, "reconnect");
      await setScenario(request, LIVE, "reconnect");
      await expect(page.getByTestId("live-route-status")).toHaveText("Waiting for Live Companion game data");
      await expect(page.getByTestId("live-companion-mode")).toHaveText("idle");
      await expect(page.getByTestId("bridge-status")).toContainText("Live Companion idle");
      await expect(page).toHaveURL(/\/live$/);
      await expectNoHorizontalClipping(page);
      await expectLiveDataContractDetector(page);
      await captureState(page, testInfo, `flow-reconnect-${viewport.width}`);
      expect(
        await page.evaluate(() => (window as typeof window & { blContinuousFlow?: boolean }).blContinuousFlow),
      ).toBe(true);
      expect(await page.evaluate(() => (window as typeof window & { blEventStreams?: number }).blEventStreams)).toBe(1);
      expectNoBrowserErrors(browserErrors);
    }
  });
});
