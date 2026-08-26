import { expect, test } from "@playwright/test";

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

  test("champ select idle keeps policy note and population intel visible", async ({ page }) => {
    await page.goto("/champ-select");
    await expect(page.getByText("champion-level intel only").first()).toBeVisible();
    await expect(page.getByText("Recommend ban").first()).toBeVisible();
  });

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
