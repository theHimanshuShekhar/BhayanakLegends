import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

// The single cross-route browser seam for #90: semantics, retained sections,
// overflow, keyboard/focus, Live Companion phases, state fixtures, Backfill
// lifecycle, reduced motion, 200% zoom, and computed-color contrast.
//
// The replay stack (booted by playwright.config.ts) is a real sidecar on
// 23122 backed by deterministic LCU/Live replays on 23123/23124. State
// fixtures that the seeded sidecar cannot produce (victory digest, error
// codes, delayed responses) are represented with Playwright route
// interception; SSE (/events) is never intercepted so live phases stay real.

const LIVE = "http://127.0.0.1:23124";
const LCU = "http://127.0.0.1:23123";
const SIDECAR = "http://127.0.0.1:23122";
const AUTH = {
  "X-BL-Token": "local-sidecar-development-token-32chars",
  Host: "127.0.0.1:23122",
};

const VIEWPORTS = [
  { width: 1280, height: 820 },
  { width: 980, height: 620 },
] as const;

// 200% zoom reflows the CSS viewport to half the window size; 640x410 is the
// layout-equivalent of a 1280x820 window at browser zoom 200%.
const ZOOM_200 = { width: 640, height: 410 };

const ROUTES = [
  { path: "/live", nav: "live", h1: "Live Companion: In Game", ready: "bridge-status" },
  { path: "/champ-select", nav: "champ-select", h1: "Live Companion: Champ Select", ready: "card-ban-advisor" },
  { path: "/postgame", nav: "postgame", h1: "Post-game Review", ready: "verdict-header" },
  { path: "/progress", nav: "progress", h1: "Trajectory", ready: null },
  { path: "/champions", nav: "champions", h1: "Champion Evidence", ready: "role-MIDDLE" },
  { path: "/history", nav: "history", h1: "Improvement Journal", ready: "summary-matches" },
] as const;

type Route = (typeof ROUTES)[number];

async function setScenario(request: APIRequestContext, base: string, scenario: string) {
  const response = await request.post(`${base}/control`, { data: { scenario } });
  expect(response.ok()).toBeTruthy();
}

async function resetScenarios(request: APIRequestContext) {
  await setScenario(request, LCU, "idle");
  await setScenario(request, LIVE, "idle");
}

type LiveStatusShape = {
  champ_select: { active: boolean };
  ingame: { active: boolean };
};

/**
 * Reset replay scenarios and wait until the sidecar observes the idle
 * baseline, so suites that run after replay-active are deterministic.
 */
async function idleBaseline(request: APIRequestContext) {
  await resetScenarios(request);
  await expect
    .poll(
      async () => {
        const response = await request.get(`${SIDECAR}/live/status`, { headers: AUTH });
        const body = (await response.json()) as LiveStatusShape;
        return body.champ_select.active || body.ingame.active;
      },
      { timeout: 30_000 },
    )
    .toBe(false);
}

function collectBrowserErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}

type Evidence = {
  route?: string;
  state?: string;
  viewport?: string;
  finding: string;
  data?: unknown;
};

function makeEvidence() {
  const entries: Evidence[] = [];
  return {
    add(finding: string, rest: Omit<Evidence, "finding"> = {}) {
      entries.push({ finding, ...rest });
    },
    all(): Evidence[] {
      return entries;
    },
  };
}

type ContrastPair = {
  ok: boolean;
  kind: string;
  text: string;
  fg: string;
  bg: string;
  ratio: number;
  threshold: number;
};

function stableDigest(value: string): string {
  // FNV-1a: dependency-free digest so run-to-run evidence stays comparable.
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/** Persist the evidence matrix as an artifact next to the run's screenshots. */
async function attachEvidence(testInfo: TestInfo, name: string, payload: unknown): Promise<string> {
  const body = JSON.stringify(payload, null, 2);
  await testInfo.attach(name, { body, contentType: "application/json" });
  return `${name}.json fnv1a:${stableDigest(body)}`;
}

async function screenshot(page: Page, testInfo: TestInfo, name: string): Promise<string> {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await testInfo.attach(name, { path, contentType: "image/png" });
  return `${name}.png`;
}

function clickNav(page: Page, route: Route) {
  return page.getByTestId(`nav-${route.nav}`).click();
}

async function gotoRoute(page: Page, route: Route) {
  await page.goto(route.path);
  const h1 = page.getByRole("heading", { level: 1, name: route.h1 });
  await expect(h1).toBeVisible();
  if (route.ready) {
    await expect(page.getByTestId(route.ready)).toBeVisible({ timeout: 15_000 });
  }
  return h1;
}

type OverflowRow = {
  key: string;
  scrollWidth: number;
  clientWidth: number;
  exception: boolean;
};

/**
 * Overflow on document, shell (.rc-screen), every main, and every labelled
 * region. Local table scrollers (.live-table-scroll / .table-scroll) are the
 * explicitly labelled exceptions allowed to scroll horizontally.
 */
function measureOverflow(page: Page): Promise<OverflowRow[]> {
  return page.evaluate(() => {
    const rows: OverflowRow[] = [];
    const push = (key: string, el: Element) => {
      rows.push({
        key,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        exception:
          el.classList.contains("live-table-scroll") || el.classList.contains("table-scroll"),
      });
    };
    push("document", document.documentElement);
    const shell = document.querySelector(".rc-screen");
    if (shell) push("shell(.rc-screen)", shell);
    document.querySelectorAll("main").forEach((main, i) => push(`main#${i}`, main));
    document.querySelectorAll('[role="region"]').forEach((region, i) => {
      const label =
        region.getAttribute("aria-label") ??
        region
          .getAttribute("aria-labelledby")
          ?.split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent?.trim())
          .join(" ") ??
        `region#${i}`;
      push(`region:${label.trim()}`, region);
    });
    return rows;
  });
}

function assertOverflowRows(rows: OverflowRow[], context: string) {
  // scrollWidth rounds up while clientWidth rounds down, so fractional-pixel
  // layouts can differ by ~2px depending on webfont load timing. Genuine
  // overflow (e.g. the 200% zoom champions grid at 922 vs 640) exceeds this
  // allowance by orders of magnitude.
  const SUBPIXEL_TOLERANCE_PX = 2;
  for (const row of rows) {
    if (!row.exception) {
      expect(
        row.scrollWidth,
        `${context}: ${row.key} overflows (${row.scrollWidth} > ${row.clientWidth})`,
      ).toBeLessThanOrEqual(row.clientWidth + SUBPIXEL_TOLERANCE_PX);
    }
  }
}

/** Accessible names of every <section> inside the route screen. */
function collectSectionNames(page: Page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll(".rc-screen section"))
      .map((section) => {
        const labelledBy = section.getAttribute("aria-labelledby");
        const name =
          section.getAttribute("aria-label")?.trim() ||
          labelledBy
            ?.split(/\s+/)
            .map((id) => document.getElementById(id)?.textContent?.trim())
            .filter(Boolean)
            .join(" ")
            .trim();
        return {
          testid: section.getAttribute("data-testid"),
          name: name || null,
        };
      })
      .sort((a, b) => (a.testid ?? "").localeCompare(b.testid ?? "")),
  );
}

function focusedHeading(page: Page) {
  return page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active.tagName !== "H1") return null;
    return active.textContent?.trim() ?? "";
  });
}

async function expectFocusedH1(page: Page, name: string) {
  await expect
    .poll(() => focusedHeading(page), { timeout: 10_000, intervals: [50, 100, 250, 500] })
    .toBe(name);
}

type TabStop = { tag: string; label: string; x: number; y: number };

async function currentStop(page: Page): Promise<TabStop | null> {
  return page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active === document.body) return null;
    const rect = active.getBoundingClientRect();
    return {
      tag: active.tagName,
      label: (active.getAttribute("aria-label") ?? active.textContent ?? "")
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 60),
      x: Math.round(rect.x + rect.width / 2),
      y: Math.round(rect.y + rect.height / 2),
    };
  });
}

test.describe("cross-route UI integrity", () => {
  test("semantic outline, retained sections, overflow, and wrapped statuses at both viewports", async ({ page, request }, testInfo) => {
    // Earlier suites leave LCU/Live replay scenarios behind; the semantic
    // contract is defined against the deterministic idle baseline.
    await idleBaseline(request);
    const evidence = makeEvidence();
    const errors = collectBrowserErrors(page);
    // Wider-viewport section names are the baseline the narrower pass checks.
    const baselineSections = new Map<string, string[]>();

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      const vp = `${viewport.width}x${viewport.height}`;

      for (let i = 0; i < ROUTES.length; i += 1) {
        const route = ROUTES[i];
        if (i === 0) {
          await gotoRoute(page, route);
        } else {
          await clickNav(page, route);
          await expectFocusedH1(page, route.h1);
        }

        // Exactly one h1 per route document.
        expect(await page.locator("h1").count()).toBe(1);

        // Every section carries an accessible name.
        const sections = await collectSectionNames(page);
        const unnamed = sections.filter((s) => !s.name);
        expect(unnamed, `unnamed sections on ${route.path} at ${vp}`).toEqual([]);

        // Retained names: everything reachable at the wider viewport must
        // remain reachable at the narrower one.
        const byName = sections.map((s) => s.name as string).sort();
        if (viewport.width === VIEWPORTS[0].width) {
          baselineSections.set(route.path, byName);
        } else {
          const missing = (baselineSections.get(route.path) ?? []).filter(
            (n) => !byName.includes(n),
          );
          expect(missing, `sections lost at ${vp} on ${route.path}: ${JSON.stringify(missing)}`).toEqual([]);
        }

        // Overflow across document/shell/main/regions; labelled table
        // scrollers are the only exemptions.
        const overflow = await measureOverflow(page);
        assertOverflowRows(overflow, `${route.path} @ ${vp}`);
        evidence.add("overflow measured", { route: route.path, viewport: vp, data: overflow });

        await screenshot(page, testInfo, `ui-integrity-${route.nav}-${vp}`);
        evidence.add("route rendered with a single named-outline h1", {
          route: route.path,
          viewport: vp,
          data: { h1: route.h1, sections },
        });
      }

      // Wrapped top/nav statuses stay fully inside the viewport at each size.
      const statusBoxes = await page.evaluate(() => {
        const within = (el: Element) => {
          const r = el.getBoundingClientRect();
          return {
            text: (el.textContent ?? "").trim().slice(0, 40),
            x: Math.round(r.x),
            right: Math.round(r.right),
            y: Math.round(r.y),
            bottom: Math.round(r.bottom),
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            fits:
              r.x >= -1 &&
              r.right <= window.innerWidth + 1 &&
              r.bottom <= window.innerHeight + 1,
          };
        };
        return Array.from(document.querySelectorAll(".rc-topbar-status > *, .rc-nav-status > *")).map(within);
      });
      for (const box of statusBoxes) {
        expect(box.fits, `status pill clipped at ${vp}: ${box.text}`).toBe(true);
      }
      evidence.add("top/nav statuses wrap without clipping", { viewport: vp, data: statusBoxes });

      // Every nav pill remains visible and unclipped.
      for (const route of ROUTES) {
        const link = page.getByTestId(`nav-${route.nav}`);
        const box = await link.boundingBox();
        expect(box, `nav ${route.nav} missing at ${vp}`).not.toBeNull();
        expect(box!.x >= -1 && box!.x + box!.width <= viewport.width + 1).toBe(true);
      }

      expect(errors, `browser errors during semantic pass at ${vp}`).toEqual([]);
    }

    await attachEvidence(testInfo, "ui-integrity-semantics-evidence", {
      viewports: VIEWPORTS.map((v) => `${v.width}x${v.height}`),
      routes: ROUTES.map((r) => r.path),
      states: ["loaded"],
      consoleFindings: errors,
      entries: evidence.all(),
    });
  });

  test("keyboard order follows visual/DOM order and focus lands on destination headings", async ({ page, request }, testInfo) => {
    const evidence = makeEvidence();
    const errors = collectBrowserErrors(page);
    await idleBaseline(request);
    await page.setViewportSize(VIEWPORTS[0]);

    // Collect Tab stops from a clean load of /live until the cycle repeats.
    await gotoRoute(page, ROUTES[0]);
    const stops: TabStop[] = [];
    for (let i = 0; i < 15; i += 1) {
      await page.keyboard.press("Tab");
      const stop = await currentStop(page);
      if (!stop) break;
      const repeated = stops.some(
        (t) =>
          t.tag === stop.tag &&
          t.label === stop.label &&
          Math.abs(t.x - stop.x) < 2 &&
          Math.abs(t.y - stop.y) < 2,
      );
      if (repeated) break;
      stops.push(stop);
    }
    expect(stops.length).toBeGreaterThanOrEqual(6); // at least the six nav pills
    evidence.add("tab stops", { data: stops });

    // DOM order: each subsequent stop follows the previous one in document order.
    for (let i = 1; i < stops.length; i += 1) {
      const inOrder = await page.evaluate(({ a, b }) => {
        const resolve = (label: string) =>
          Array.from(document.querySelectorAll("a[href], button, input, select")).find(
            (el) =>
              (el.getAttribute("aria-label") ?? el.textContent ?? "")
                .trim()
                .replace(/\s+/g, " ")
                .slice(0, 60) === label,
          );
        const ea = resolve(a.label);
        const eb = resolve(b.label);
        if (!ea || !eb) return true;
        return Boolean(ea.compareDocumentPosition(eb) & Node.DOCUMENT_POSITION_FOLLOWING);
      }, { a: stops[i - 1], b: stops[i] });
      expect(inOrder, `Tab leaves DOM order between ${stops[i - 1].label} and ${stops[i].label}`).toBe(true);
    }

    // Visual order: reading order (row-bucketed y, then x within a row).
    for (let i = 1; i < stops.length; i += 1) {
      const prev = stops[i - 1];
      const cur = stops[i];
      if (Math.abs(cur.y - prev.y) <= 24) {
        expect(cur.x, `same-row tab step moves left: ${prev.label} -> ${cur.label}`).toBeGreaterThanOrEqual(prev.x - 8);
      } else {
        expect(cur.y, `tab step jumps up: ${prev.label} -> ${cur.label}`).toBeGreaterThan(prev.y - 8);
      }
    }

    // Shift+Tab reverses whatever the last forward step was.
    const stopBefore = await currentStop(page);
    await page.keyboard.press("Shift+Tab");
    const after = await currentStop(page);
    expect(after, "Shift+Tab left no focused element").not.toBeNull();
    const idx = stopBefore
      ? stops.findIndex(
          (t) =>
            t.tag === stopBefore.tag &&
            t.label === stopBefore.label &&
            Math.abs(t.x - stopBefore.x) < 2 &&
            Math.abs(t.y - stopBefore.y) < 2,
        )
      : -1;
    if (idx > 0) {
      expect(after?.tag, "Shift+Tab did not reverse the last step").toBe(stops[idx - 1].tag);
      expect(after?.label, "Shift+Tab did not reverse the last step").toBe(stops[idx - 1].label);
    } else {
      expect(after?.label !== stopBefore?.label || after?.tag !== stopBefore?.tag).toBe(true);
    }

    // Keyboard-only Enter activation navigates and focuses the destination h1.
    let guard = 0;
    while ((await currentStop(page))?.label !== "Trajectory" && guard < 30) {
      await page.keyboard.press("Tab");
      guard += 1;
    }
    expect((await currentStop(page))?.label).toBe("Trajectory");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Trajectory" })).toBeVisible();
    await expectFocusedH1(page, "Trajectory");
    evidence.add("Enter on nav link focuses destination h1", { route: "/progress", data: "Trajectory" });

    // Browser back/forward keeps the seam: each history entry refocuses its h1.
    await page.goBack();
    await expectFocusedH1(page, "Live Companion: In Game");
    evidence.add("back focuses origin h1", { route: "/live", data: "Live Companion: In Game" });
    await page.goForward();
    await expectFocusedH1(page, "Trajectory");
    evidence.add("forward focuses destination h1", { route: "/progress", data: "Trajectory" });

    // Native Space toggles the Backfill form's checkbox.
    await clickNav(page, ROUTES[5]);
    await expectFocusedH1(page, "Improvement Journal");
    const autoSync = page.getByTestId("input-auto-sync");
    await autoSync.focus();
    const before = await autoSync.isChecked();
    await page.keyboard.press("Space");
    await expect(autoSync).toBeChecked({ checked: !before });
    await page.keyboard.press("Space");
    await expect(autoSync).toBeChecked({ checked: before });
    evidence.add("native Space toggles checkbox", { route: "/history" });

    expect(errors).toEqual([]);
    await attachEvidence(testInfo, "ui-integrity-keyboard-evidence", {
      interactions: ["tab-order", "shift-tab", "enter-navigation", "back-forward-focus", "space-toggle"],
      entries: evidence.all(),
    });
  });

  test("Live Companion idle/active phases and expansion disclosure retain focus", async ({ page, request }, testInfo) => {
    test.setTimeout(120_000);
    const evidence = makeEvidence();
    const errors = collectBrowserErrors(page);
    await page.setViewportSize(VIEWPORTS[0]);
    await resetScenarios(request);

    try {
      await gotoRoute(page, ROUTES[0]);

      // Idle: no disclosure control exists yet.
      const companion = page.getByTestId("live-companion");
      await expect(companion).toHaveAttribute("data-phase", "idle", { timeout: 20_000 });
      await expect(page.getByTestId("live-companion-mode")).toHaveText("idle");
      await expect(page.locator(".live-companion button")).toHaveCount(0);
      evidence.add("companion idle phase has no disclosure control");

      // Champ select phase arrives through the real sidecar pipeline.
      await setScenario(request, LCU, "champ-select");
      await expect(companion).toHaveAttribute("data-phase", "champ-select", { timeout: 30_000 });
      await expect(page.getByTestId("live-companion-mode")).toHaveText("champ select");
      evidence.add("companion champ-select phase announced");

      // In-game phase exposes the expand/collapse disclosure.
      await setScenario(request, LCU, "in-game");
      await setScenario(request, LIVE, "in-game");
      const toggle = page.getByRole("button", { name: /Expand Live Companion/ });
      await expect(toggle).toBeVisible({ timeout: 45_000 });
      await expect(companion).toHaveAttribute("data-phase", "in-game");
      evidence.add("companion in-game phase exposes disclosure");

      // Click expansion keeps focus on the disclosure; aria-expanded is truthful.
      await toggle.click();
      await expect(page.getByRole("button", { name: /Collapse Live Companion/ })).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      await expect
        .poll(() =>
          page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? ""),
        )
        .toBe("Collapse Live Companion");
      await screenshot(page, testInfo, "ui-integrity-companion-expanded");
      evidence.add("expansion retains disclosure focus");

      // Native Enter collapses again; focus stays on the control.
      await page.keyboard.press("Enter");
      await expect(toggle).toHaveAttribute("aria-expanded", "false");
      await expect
        .poll(() =>
          page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? ""),
        )
        .toBe("Expand Live Companion");
      evidence.add("collapse via native Enter keeps focus");
    } finally {
      await resetScenarios(request);
    }

    expect(errors, "browser errors during companion pass").toEqual([]);
    await attachEvidence(testInfo, "ui-integrity-companion-evidence", {
      states: ["idle", "champ-select", "in-game", "expanded", "collapsed"],
      entries: evidence.all(),
    });
  });

  test("representative loading, empty, error, victory, and defeat fixtures", async ({ page }, testInfo) => {
    const evidence = makeEvidence();
    await page.setViewportSize(VIEWPORTS[0]);
    const victoryDigest = {
      match_id: "e2e-victory",
      played_at: "2026-08-25T00:00:00Z",
      champion: "Ahri",
      role: "MIDDLE",
      win: true,
      duration_s: 1893,
      checkpoints: { gold_diff_10: 240, gold_diff_15: 610, gold_diff_20: 980 },
      habits: [],
      headline: "Clean early game",
    };

    // Loading: a delayed summary keeps the journal skeleton visible, then it settles away.
    await page.route("**/history/summary", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fallback();
    });
    await page.goto("/history");
    await expect(page.getByRole("heading", { level: 1, name: "Improvement Journal" })).toBeVisible();
    await expect(page.locator(".history-skeletons").first()).toBeVisible();
    await screenshot(page, testInfo, "ui-integrity-state-loading-history");
    evidence.add("loading fixture exposes skeleton then settles", { route: "/history" });
    await expect(page.getByTestId("summary-matches")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".history-skeletons")).toHaveCount(0);

    // Empty: no digest yet on postgame.
    await page.route("**/postgame/latest", (route) => route.fulfill({ status: 200, json: null }));
    await gotoRoute(page, ROUTES[2]);
    await expect(page.getByText("No game analyzed")).toBeVisible();
    await expect(page.getByText("No digest yet")).toBeVisible();
    await screenshot(page, testInfo, "ui-integrity-state-empty-postgame");
    evidence.add("empty fixture renders empty-state copy", { route: "/postgame" });

    // Error: benchmarks failure surfaces a role=alert with actionable copy.
    await page.route("**/benchmarks", (route) =>
      route.fulfill({ status: 503, json: { detail: "Findings Pack unavailable" } }),
    );
    await gotoRoute(page, ROUTES[3]);
    await expect(
      page.getByRole("alert").first(),
    ).toContainText(/Findings Pack is unavailable|Something went wrong/i, { timeout: 15_000 });
    await screenshot(page, testInfo, "ui-integrity-state-error-progress");
    evidence.add("error fixture surfaces alert", { route: "/progress" });

    // Victory: intercepted digest flips the verdict tile teal-side up.
    await page.unroute("**/benchmarks");
    await page.route("**/postgame/latest", (route) => route.fulfill({ status: 200, json: victoryDigest }));
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      await gotoRoute(page, ROUTES[2]);
      await expect(page.getByTestId("verdict")).toHaveText("Victory");
      await screenshot(page, testInfo, `ui-integrity-state-victory-${viewport.width}`);
      evidence.add("victory fixture", { route: "/postgame", viewport: `${viewport.width}` });
    }

    // Defeat: the seeded replay import ends in a loss without interception.
    await page.unroute("**/postgame/latest");
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      await gotoRoute(page, ROUTES[2]);
      await expect(page.getByTestId("verdict")).toHaveText("Defeat", { timeout: 15_000 });
      await screenshot(page, testInfo, `ui-integrity-state-defeat-${viewport.width}`);
      evidence.add("defeat fixture from seeded replay import", { route: "/postgame", viewport: `${viewport.width}` });
    }

    await attachEvidence(testInfo, "ui-integrity-states-evidence", {
      states: ["loading", "empty", "error", "victory", "defeat"],
      entries: evidence.all(),
    });
  });

  test("Backfill lifecycle: pristine, invalid, dirty, saved, running, unknown totals, error", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const evidence = makeEvidence();
    const errors = collectBrowserErrors(page);
    await page.setViewportSize(VIEWPORTS[0]);

    const savedSettings = {
      riot_id: "replay#E2E",
      region_route: "sea",
      has_key: true,
      auto_sync: false,
    };
    const idleStatus = {
      state: "idle",
      mode: "era_first",
      total_queued: 0,
      downloaded: 0,
      skipped: 0,
      failed: 0,
      current_match_id: null,
      started_at: null,
    };
    await page.route("**/settings", (route) => route.fulfill({ status: 200, json: savedSettings }));
    await page.route("**/sync/status**", (route) => route.fulfill({ status: 200, json: idleStatus }));
    await page.route("**/sync/start", (route) =>
      route.fulfill({
        status: 200,
        json: {
          state: "running",
          mode: "era_first",
          total_queued: 1200,
          downloaded: 480,
          skipped: 0,
          failed: 0,
          current_match_id: "MATCH-E2E-RUNNING",
          started_at: "2026-08-25T00:00:00Z",
        },
      }),
    );

    await gotoRoute(page, ROUTES[5]);

    // Pristine: valid saved settings and an idle queue enable Start Backfill.
    const start = page.getByTestId("start-sync");
    await expect(start).toBeEnabled();
    await expect(page.getByTestId("start-disabled-reason")).toHaveCount(0);
    await screenshot(page, testInfo, "ui-integrity-backfill-pristine");
    evidence.add("pristine enables Start Backfill");

    // Invalid: a malformed Riot ID blocks Start with a visible reason.
    const riotId = page.getByTestId("input-riot-id");
    await riotId.fill("not-a-valid-id");
    await riotId.blur();
    await expect(page.getByTestId("riot-id-error")).toBeVisible();
    await expect(start).toBeDisabled();
    await expect(page.getByTestId("start-disabled-reason")).toContainText("valid Riot ID");
    await screenshot(page, testInfo, "ui-integrity-backfill-invalid");
    evidence.add("invalid Riot ID disables Start with reason");

    // Dirty: edits exist but are unsaved, so Start still refuses.
    await riotId.fill("replay#E2E");
    await expect(page.getByTestId("start-disabled-reason")).toContainText(
      "Save settings before starting Backfill.",
    );
    evidence.add("dirty settings block Start");

    // Saved: saving clears dirty and re-enables Start.
    await page.getByTestId("save-settings").click();
    await expect(page.getByTestId("save-ok")).toHaveText("Saved.");
    await expect(start).toBeEnabled();
    await screenshot(page, testInfo, "ui-integrity-backfill-saved");
    evidence.add("saved settings re-enable Start");

    // Running: intercepted start returns progress; counters and bar reflect it.
    await start.click();
    await expect(page.getByTestId("sync-counters")).toContainText("480 / 1,200 matches");
    await expect(page.getByTestId("cancel-sync")).toBeEnabled();
    await expect(page.getByTestId("sync-progress-bar")).toHaveAttribute("style", /width:\s*40%/);
    await screenshot(page, testInfo, "ui-integrity-backfill-running");
    evidence.add("running counters truthful", { data: { progress: "480/1200 = 40%" } });

    // Unknown totals: a running queue of unknown size stays truthful (0 / 0).
    await page.unroute("**/sync/start");
    await page.unroute("**/sync/status**");
    await page.route("**/sync/status**", (route) =>
      route.fulfill({
        status: 200,
        json: {
          state: "running",
          mode: "era_first",
          total_queued: 0,
          downloaded: 0,
          skipped: 0,
          failed: 0,
          current_match_id: "MATCH-E2E-UNKNOWN",
          started_at: "2026-08-25T00:01:00Z",
        },
      }),
    );
    await page.reload();
    await expect(page.getByTestId("summary-matches")).toBeVisible();
    await expect(page.getByTestId("sync-counters")).toContainText("0 / 0 matches");
    const bodyText = await page.evaluate(() => document.body.textContent ?? "");
    expect(bodyText).not.toMatch(/NaN|Infinity/);
    await screenshot(page, testInfo, "ui-integrity-backfill-unknown-totals");
    evidence.add("unknown totals show 0 / 0 without NaN");

    // Error: a failed Backfill surfaces the dedicated alert copy.
    await page.unroute("**/sync/status**");
    await page.route("**/sync/status**", (route) =>
      route.fulfill({
        status: 200,
        json: {
          state: "error",
          mode: "era_first",
          total_queued: 1200,
          downloaded: 300,
          skipped: 0,
          failed: 12,
          current_match_id: "MATCH-E2E-ERROR",
          started_at: "2026-08-25T00:02:00Z",
        },
      }),
    );
    await page.reload();
    await expect(page.getByTestId("summary-matches")).toBeVisible();
    await expect(page.getByTestId("sync-status-error")).toContainText("Backfill stopped before completion");
    await screenshot(page, testInfo, "ui-integrity-backfill-error");
    evidence.add("error state surfaces dedicated alert");

    expect(errors).toEqual([]);
    await attachEvidence(testInfo, "ui-integrity-backfill-evidence", {
      states: ["pristine", "invalid", "dirty", "saved", "running", "unknown-totals", "error"],
      entries: evidence.all(),
    });
  });

  test("reduced motion removes authored motion and keeps information perceivable", async ({ page, request }, testInfo) => {
    const evidence = makeEvidence();
    const errors = collectBrowserErrors(page);
    await idleBaseline(request);
    await page.setViewportSize(VIEWPORTS[0]);
    await page.emulateMedia({ reducedMotion: "reduce" });

    await gotoRoute(page, ROUTES[0]);
    for (let i = 0; i < ROUTES.length; i += 1) {
      const route = ROUTES[i];
      if (i > 0) {
        await clickNav(page, route);
        await expectFocusedH1(page, route.h1);
      }
      // No authored animation or transition may be running anywhere.
      const running = await page.evaluate(() =>
        document.getAnimations().map((animation) => ({
          name: animation instanceof CSSAnimation ? animation.animationName : "(other)",
          state: animation.playState,
        })),
      );
      expect(running, `authored motion ran under reduce on ${route.path}`).toEqual([]);
      // Statuses stay perceivable without motion cues.
      await expect(page.getByTestId("connection-status")).toBeVisible();
      if (route.path === "/live") {
        await expect(page.getByTestId("bridge-status")).toBeVisible();
      } else {
        await expect(page.getByRole("heading", { level: 1, name: route.h1 })).toBeVisible();
      }
      evidence.add("no authored motion under reduce", { route: route.path });
    }

    // Focus remains perceivable: keyboard focus draws the authored outline.
    await page.keyboard.press("Tab");
    const outline = await page.evaluate(() => {
      const style = getComputedStyle(document.activeElement as Element);
      return `${style.outlineStyle} ${style.outlineWidth}`;
    });
    expect(outline).not.toBe("none 0px");
    evidence.add("keyboard focus outline under reduced motion", { data: outline });

    await screenshot(page, testInfo, "ui-integrity-reduced-motion-live");
    expect(errors).toEqual([]);
    await attachEvidence(testInfo, "ui-integrity-motion-evidence", {
      emulatedMedia: "prefers-reduced-motion: reduce",
      result: "no running animations across all six routes; statuses and focus perceivable",
      entries: evidence.all(),
    });
  });

  test("200% zoom keeps every route usable with no clipped controls", async ({ page, request }, testInfo) => {
    const evidence = makeEvidence();
    const errors = collectBrowserErrors(page);
    await idleBaseline(request);
    await page.setViewportSize(ZOOM_200);

    for (let i = 0; i < ROUTES.length; i += 1) {
      const route = ROUTES[i];
      if (i === 0) {
        await gotoRoute(page, route);
      } else {
        await clickNav(page, route);
        await expectFocusedH1(page, route.h1);
      }

      // Nothing interactive is clipped horizontally at zoom-equivalent width.
      const clipped = await page.evaluate(() => {
        const bad: Array<{ label: string; x: number; right: number; innerWidth: number }> = [];
        for (const el of Array.from(document.querySelectorAll("a[href], button, input, select"))) {
          const r = el.getBoundingClientRect();
          if (r.width === 0 && r.height === 0) continue;
          if (r.x < -1 || r.right > window.innerWidth + 1) {
            bad.push({
              label: ((el as HTMLElement).getAttribute("aria-label") ?? el.textContent ?? "")
                .trim()
                .slice(0, 40),
              x: Math.round(r.x),
              right: Math.round(r.right),
              innerWidth: window.innerWidth,
            });
          }
        }
        return bad;
      });
      expect(clipped, `clipped interactive controls on ${route.path} at 200% zoom`).toEqual([]);

      const overflow = await measureOverflow(page);
      assertOverflowRows(overflow, `${route.path} @ 200% zoom`);
      evidence.add("overflow measured at 200% zoom", { route: route.path, data: overflow });

      await screenshot(page, testInfo, `ui-integrity-zoom-${route.nav}`);
    }

    // Primary controls stay reachable at the zoomed size (history is the
    // loop's final route, already focused via the nav seam above).
    await expect(page.getByTestId("start-sync")).toBeVisible();
    await expect(page.getByTestId("save-settings")).toBeVisible();

    expect(errors).toEqual([]);
    await attachEvidence(testInfo, "ui-integrity-zoom-evidence", {
      zoom: "200% simulated as 640x410 CSS viewport (reflow-equivalent of a 1280x820 window)",
      result: "h1 visible per route, nav reachable, no clipped controls, no unlabelled overflow",
      entries: evidence.all(),
    });
  });

  test.describe("contrast", () => {
    // WCAG relative luminance + contrast ratio over resolved computed colors.
    const SAMPLER = () => {
      type Parsed = { r: number; g: number; b: number; a: number };
      const parse = (value: string): Parsed | null => {
        const m = value.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,/\s]+([\d.]+))?\)/);
        if (!m) return null;
        return {
          r: Number(m[1]),
          g: Number(m[2]),
          b: Number(m[3]),
          a: m[4] === undefined ? 1 : Number(m[4]),
        };
      };
      const blend = (top: Parsed, bottom: Parsed): Parsed => ({
        r: top.r * top.a + bottom.r * bottom.a * (1 - top.a),
        g: top.g * top.a + bottom.g * bottom.a * (1 - top.a),
        b: top.b * top.a + bottom.b * bottom.a * (1 - top.a),
        a: top.a + bottom.a * (1 - top.a),
      });
      const lum = ({ r, g, b }: Parsed) => {
        const channel = (c: number) => {
          const v = c / 255;
          return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        };
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
      };
      const gradientStops = (value: string): Parsed | null => {
        // Effective solid = premultiplied average of declared gradient stops.
        const m = value.match(/linear-gradient\((.*)\)$/);
        if (!m) return null;
        const tokens = m[1].match(/rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}/g) ?? [];
        const stops = tokens.map(parse).filter((c): c is Parsed => c !== null);
        if (!stops.length) return null;
        let r = 0;
        let g = 0;
        let b = 0;
        let a = 0;
        for (const c of stops) {
          r += c.r * c.a;
          g += c.g * c.a;
          b += c.b * c.a;
          a += c.a;
        }
        if (!a) return null;
        return { r: r / a, g: g / a, b: b / a, a: 1 };
      };
      const hex = ({ r, g, b }: Parsed) =>
        `#${[r, g, b]
          .map((c) => Math.round(Math.min(255, Math.max(0, c))).toString(16).padStart(2, "0"))
          .join("")}`;
      const backgroundOf = (element: Element): Parsed => {
        const layers: Array<Parsed & { solid: boolean }> = [];
        let node: Element | null = element;
        while (node) {
          const cs = getComputedStyle(node);
          const grad = gradientStops(cs.backgroundImage);
          if (grad) {
            layers.push({ ...grad, solid: true });
            break;
          }
          const bg = parse(cs.backgroundColor);
          if (bg && bg.a > 0) layers.push({ ...bg, solid: bg.a >= 1 });
          if (bg && bg.a >= 1) break;
          node = node.parentElement;
        }
        let color: Parsed = { r: 14, g: 16, b: 32, a: 1 }; // --color-bg fallback
        for (const layer of layers.reverse()) {
          color = layer.solid ? { ...layer } : blend(layer, color);
        }
        return color;
      };

      type Pair = {
        kind: string;
        text: string;
        fg: string;
        bg: string;
        ratio: number;
        threshold: number;
        fontSize: number;
        ok: boolean;
      };
      const pairs: Pair[] = [];
      const seen = new Set<string>();
      const record = (kind: string, el: Element, fgRaw: string, threshold: number) => {
        if (el.closest('[aria-hidden="true"]')) return;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        const style = getComputedStyle(el);
        if (style.visibility === "hidden" || Number(style.opacity) === 0) return;
        const fgParsed = parse(fgRaw);
        if (!fgParsed) return;
        const bg = backgroundOf(el);
        const fg = fgParsed.a < 1 ? blend(fgParsed, bg) : fgParsed;
        const l1 = lum(fg);
        const l2 = lum(bg);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        const text = (el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 48);
        const key = `${kind}|${text}|${fgRaw}|${bg.r},${bg.g},${bg.b}`;
        if (seen.has(key)) return;
        seen.add(key);
        pairs.push({
          kind,
          text,
          fg: hex(fg),
          bg: hex(bg),
          ratio: Math.round(ratio * 100) / 100,
          threshold,
          fontSize: parseFloat(style.fontSize),
          ok: ratio >= threshold,
        });
      };
      const hasOwnText = (el: Element) =>
        Array.from(el.childNodes).some((n) => n.nodeType === 3 && (n.textContent ?? "").trim().length > 0);

      for (const el of Array.from(document.querySelectorAll("body *"))) {
        const style = getComputedStyle(el);
        const size = parseFloat(style.fontSize);
        const bold = Number.parseInt(style.fontWeight, 10) >= 700;
        const large = size >= 24 || (bold && size >= 18.66);
        const threshold = large ? 3 : 4.5;
        const tag = el.tagName;
        if (tag === "A" && el.hasAttribute("href")) {
          record("link", el, style.color, threshold);
        } else if (tag === "BUTTON") {
          record("button", el, style.color, threshold);
        } else if (el.getAttribute("role") === "status") {
          record("status", el, style.color, threshold);
        } else if (el.getAttribute("role") === "alert") {
          record("error", el, style.color, threshold);
        } else if (tag === "TH") {
          record("table-header", el, style.color, threshold);
        } else if (hasOwnText(el)) {
          record("text", el, style.color, threshold);
        }
      }
      return pairs;
    };

    const sampleFocusPair = (page: Page) =>
      page.evaluate(() => {
        const parseChannels = (value: string): [number, number, number] | null => {
          const m = value.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/);
          return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
        };
        const lum = ([r, g, b]: [number, number, number]) => {
          const channel = (c: number) => {
            const v = c / 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
          };
          return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        const toHex = ([r, g, b]: [number, number, number]) =>
          `#${[r, g, b].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
        const active = document.activeElement as HTMLElement | null;
        if (!active || active === document.body) return null;
        const style = getComputedStyle(active);
        if (/none/.test(style.outlineStyle) || parseFloat(style.outlineWidth) === 0) return null;
        const oc = parseChannels(style.outlineColor);
        if (!oc) return null;
        let bg: [number, number, number] = [14, 16, 32];
        let node: Element | null = active;
        while (node) {
          const parsed = parseChannels(getComputedStyle(node).backgroundColor);
          if (parsed) {
            bg = parsed;
            break;
          }
          node = node.parentElement;
        }
        const ratio =
          (Math.max(lum(oc), lum(bg)) + 0.05) / (Math.min(lum(oc), lum(bg)) + 0.05);
        return {
          kind: "focus",
          text: (active.getAttribute("aria-label") ?? active.textContent ?? "").trim().slice(0, 48),
          fg: toHex(oc),
          bg: toHex(bg),
          ratio: Math.round(ratio * 100) / 100,
          threshold: 3,
          fontSize: parseFloat(style.fontSize),
          ok: ratio >= 3,
        };
      });

    for (const viewport of VIEWPORTS) {
      test(`computed-color contrast passes AA at ${viewport.width}x${viewport.height}`, async ({ page }, testInfo) => {
        test.setTimeout(150_000);
        await page.setViewportSize(viewport);
        const vp = `${viewport.width}x${viewport.height}`;
        const matrix: Array<{ route: string; state: string; pairs: ContrastPair[] }> = [];

        const harvest = async (route: string, state: string) => {
          const pairs = await page.evaluate(SAMPLER);
          matrix.push({ route, state, pairs });
        };

        // Loaded routes plus the keyboard focus indicator pair.
        for (let i = 0; i < ROUTES.length; i += 1) {
          const route = ROUTES[i];
          if (i === 0) {
            await gotoRoute(page, route);
          } else {
            await clickNav(page, route);
            await expectFocusedH1(page, route.h1);
          }
          await harvest(route.path, "loaded");
        }
        await page.keyboard.press("Tab"); // first nav link
        const focusPair = await sampleFocusPair(page);
        expect(focusPair, "no visible focus indicator after Tab").not.toBeNull();
        matrix.push({ route: "/live", state: "loaded:focus", pairs: focusPair ? [focusPair] : [] });

        // Loading state (journal skeleton visible).
        await page.route("**/history/summary", async (route) => {
          await new Promise((resolve) => setTimeout(resolve, 900));
          await route.fallback();
        });
        await page.goto("/history");
        await expect(page.locator(".history-skeletons").first()).toBeVisible();
        await harvest("/history", "loading");

        // Error state (benchmarks alert).
        await page.unroute("**/history/summary");
        await page.route("**/benchmarks", (route) =>
          route.fulfill({ status: 503, json: { detail: "Findings Pack unavailable" } }),
        );
        await page.goto("/progress");
        await expect(page.getByRole("alert").first()).toBeVisible({ timeout: 15_000 });
        await harvest("/progress", "error");

        // Victory and defeat verdict tiles.
        const victoryDigest = {
          match_id: "e2e-victory",
          played_at: "2026-08-25T00:00:00Z",
          champion: "Ahri",
          role: "MIDDLE",
          win: true,
          duration_s: 1893,
          checkpoints: { gold_diff_10: 240, gold_diff_15: 610, gold_diff_20: 980 },
          habits: [],
          headline: "Clean early game",
        };
        await page.unroute("**/benchmarks");
        await page.route("**/postgame/latest", (route) =>
          route.fulfill({ status: 200, json: victoryDigest }),
        );
        await page.goto("/postgame");
        await expect(page.getByTestId("verdict")).toHaveText("Victory");
        await harvest("/postgame", "victory");

        await page.unroute("**/postgame/latest");
        await page.goto("/postgame");
        await expect(page.getByTestId("verdict")).toHaveText("Defeat", { timeout: 15_000 });
        await harvest("/postgame", "defeat");

        // Report exact failing pairs with foreground/background and route/state.
        const failures = matrix.flatMap((entry) =>
          entry.pairs
            .filter((p) => !p.ok)
            .map((p) => ({ ...entry, pair: p })),
        );
        const report = failures
          .map(
            ({ route, state, pair }) =>
              `${route} [${state}] kind=${pair.kind} text="${pair.text}" fg=${pair.fg} bg=${pair.bg} ratio=${pair.ratio} needs=${pair.threshold}`,
          )
          .join("\n");
        expect(failures, `WCAG AA contrast failures at ${vp}:\n${report}`).toEqual([]);

        await screenshot(page, testInfo, `ui-integrity-contrast-${viewport.width}`);
        await attachEvidence(testInfo, `ui-integrity-contrast-evidence-${viewport.width}`, {
          viewport: vp,
          states: [...new Set(matrix.map((m) => m.state))],
          sampledPairs: matrix.reduce((sum, m) => sum + m.pairs.length, 0),
          note: "gradient backgrounds approximate to their nearest opaque solid ancestor layer",
          matrix,
        });
      });
    }
  });
});
