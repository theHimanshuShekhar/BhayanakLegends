import { expect, test, type APIRequestContext } from "@playwright/test";

const LCU = "http://127.0.0.1:23123";
const SIDECAR = "http://127.0.0.1:23122";
const AUTH = {
  "X-BL-Token": "local-sidecar-development-token-32chars",
  Host: "127.0.0.1:23122",
};

async function setScenario(request: APIRequestContext, scenario: string) {
  const response = await request.post(`${LCU}/control`, { data: { scenario } });
  expect(response.ok()).toBeTruthy();
}

const VIEWPORTS = [
  { width: 1280, height: 820 },
  { width: 980, height: 620 },
];

test.describe("Bhayanak Legends v1 smoke", () => {
  test("health endpoint of the owned replay stack is used", async ({ request }) => {
    // The replay stack owns 23122 exclusively; this keeps the assertion tied
    // to the configured webServer rather than any external sidecar.
    const response = await request.get("http://127.0.0.1:23122/events?token=dev");
    expect(response.status()).toBeLessThan(500);
  });

  test("live match shows objectives priors from the Findings Pack", async ({ page }) => {
    await page.goto("/live");
    await expect(page.getByTestId("sidecar-dot")).toBeVisible();
    await expect(page.getByText("81.4%").first()).toBeVisible();
  });

  test("post-game suppresses comeback rate for the replayed mild deficit", async ({ page }) => {
    await page.goto("/postgame");
    await expect(page.getByTestId("comeback-odds")).toBeVisible();
    // Replayed gold@15 is milder than the 2,000g anchor -> domain suppression.
    await expect(page.getByTestId("comeback-value")).toContainText("—");
    const card = page.getByTestId("comeback-odds");
    await expect(card).not.toContainText(/Backfill/);
  });

  test("history shows the imported Personal History", async ({ page }) => {
    await page.goto("/history");
    await expect(page.getByTestId("summary-matches")).toHaveText(/^[1-9][\d,]*$/);
    await expect(page.getByRole("button", { name: "Start sync" })).toBeVisible();
  });

  test("champ select idle keeps policy note and population intel visible", async ({ page }) => {
    await page.goto("/champ-select");
    await expect(page.getByText("champion-level intel only").first()).toBeVisible();
    await expect(page.getByText("Recommend ban").first()).toBeVisible();
  });
  for (const viewport of VIEWPORTS) {
    test(`champ-select replay lock flow is truthful at ${viewport.width}x${viewport.height}`, async ({ page, request }) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ reducedMotion: "reduce" });

      await setScenario(request, "champ-select-assigned-unlocked");
      await page.goto("/champ-select");
      await expect(page.getByTestId("champ-select-page")).toBeVisible();
      await expect(page.getByTestId("your-lane-tier")).toHaveText(/TOP · AWAITING PICK/);
      await expect(page.getByTestId("suggested-role")).toHaveText("TOP");
      const suggestions = page.getByTestId("card-suggested-picks");
      await expect(suggestions).toBeVisible();
      await expect(suggestions).not.toContainText("MIDDLE");
      await expect(page.getByTestId("cs-lock-status")).toContainText("Choose a pick");

      // The route keeps semantic keyboard order and a visible focus target while
      // the replay transitions underneath it.
      const liveNav = page.getByTestId("nav-live");
      const champSelectNav = page.getByTestId("nav-champ-select");
      await liveNav.focus();
      await expect(liveNav).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(champSelectNav).toBeFocused();

      await setScenario(request, "champ-select-picked-not-locked");
      await expect(page.getByTestId("your-lane-champion")).toHaveText("Annie");
      await expect(page.getByTestId("your-lane-tier")).toHaveText(/not locked/i);
      await expect(page.getByTestId("cs-session-status")).toContainText("Annie picked — not locked");
      await expect(page.getByTestId("cs-lock-status")).toContainText("Lock Annie");
      await expect(suggestions).toBeVisible();

      await setScenario(request, "champ-select-completed-lock");
      await expect(page.getByTestId("cs-session-status")).toHaveText(/Annie locked · MIDDLE/i);
      await expect(page.getByTestId("your-lane-champion")).toHaveText("Annie");
      await expect(page.getByTestId("card-suggested-picks")).toHaveCount(0);
      await expect(page.getByTestId("cs-lock-status")).toHaveCount(0);
      await expect(page.getByText("Malzahar", { exact: false })).toHaveCount(0);

      const sessionResponse = await request.get(`${SIDECAR}/live/session`, { headers: AUTH });
      expect(sessionResponse.ok()).toBeTruthy();
      const session = await sessionResponse.json();
      expect(session.local_assigned_role).toBe("MIDDLE");
      expect(session.ally.find((cell: { is_local: boolean }) => cell.is_local).state).toBe("locked");
      expect(session.enemy.every((cell: { name: string | null }) => cell.name === null)).toBe(true);
      const rendered = await page.locator("body").innerText();
      expect(rendered).not.toContain("FixturePlayer06");
      expect(rendered).not.toContain("FixturePlayer07");
    });
  }

  for (const viewport of VIEWPORTS) {
    test(`champions shipped-pack directional flow at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/champions");

      // Initial state: no role chosen and no champion selected, so the page
      // must not present any directional claim yet.
      const topChip = page.getByTestId("role-TOP");
      const dariusRow = page.getByRole("button", { name: /Darius/i }).first();
      await expect(topChip).toBeVisible();
      // The matchups panel exists but must not claim any direction yet.
      const initialCard = page.getByTestId("matchups-card");
      await expect(initialCard).toBeVisible();
      await expect(initialCard).not.toContainText(/Darius|Garen/i);

      // Choose the TOP role to reveal the shipped tier rows for it.
      await topChip.click();
      await expect(dariusRow).toBeVisible();

      // Keyboard-only selection of the actual shipped Darius tier row.
      await dariusRow.focus();
      await page.keyboard.press("Enter");

      // The shipped table contains exactly one direction: Darius -> Garen at
      // 0.4098 wr. It must render; the reverse row must never be claimed as
      // this game's complement.
      await expect(page.getByText(/Darius/i).first()).toBeVisible();
      await expect(page.getByText("Garen").first()).toBeVisible();
      const body = await page.locator("body").innerText();
      expect(body).toContain("Darius");
      expect(body).not.toContain("wr 59.02%"); // reverse-direction value must not be reoriented

      // Changing role clears champion-specific claims until re-selection.
      await page.getByTestId("role-JUNGLE").click();
      const clearedCard = page.getByTestId("matchups-card");
      await expect(clearedCard).toBeVisible();
      await expect(clearedCard).not.toContainText(/Darius/i);
    });

    test(`progress contract-suppressed benchmarks at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto("/progress");

      // Shipped-pack CS@10 medians are lane-minions-only; #82 classifies this
      // as contract-suppressed, which is the only honest unavailable state.
      await expect(page.getByTestId("benchmarks-contract-suppressed")).toBeVisible();
      expect(await page.getByTestId("benchmark-cards").count()).toBe(0);

      // No horizontal overflow at either viewport.
      const overflow = await page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth",
      );
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }

  test("navigation between all routes works", async ({ page }) => {
    await page.goto("/");
    for (const route of ["champ-select", "live", "postgame", "progress", "champions", "history"]) {
      await page.goto(`/${route}`);
      await expect(page.locator("h1").first()).toBeVisible();
    }
  });
});
