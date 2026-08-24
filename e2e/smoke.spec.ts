import { expect, test } from "@playwright/test";

test.describe("Bhayanak Legends v1 smoke", () => {
  test("live match shows objectives priors from the Findings Pack", async ({ page }) => {
    await page.goto("/live");
    await expect(page.getByTestId("sidecar-dot")).toBeVisible();
    await expect(page.getByText("81.4%").first()).toBeVisible();
    await expect(page.getByText("waiting for :2999").first()).toBeVisible();
  });

  test("post-game binds comeback odds to the played game", async ({ page }) => {
    await page.goto("/postgame");
    await expect(page.getByTestId("comeback-odds")).toBeVisible();
    await expect(page.getByText("Recall safely").first()).toBeVisible();
  });

  test("history shows the imported Personal History", async ({ page }) => {
    await page.goto("/history");
    await expect(page.getByTestId("summary-matches")).toHaveText(/^[1-9][\d,]*$/);
    await expect(page.getByRole("button", { name: "Start sync" })).toBeVisible();
  });

  test("post-game digest renders the latest real game", async ({ page }) => {
    await page.goto("/postgame");
    await expect(page.getByText("DIAGNOSTIC").first()).toBeVisible();
  });

  test("champ select idle keeps policy note and population intel visible", async ({ page }) => {
    await page.goto("/champ-select");
    await expect(page.getByText("champion-level intel only").first()).toBeVisible();
    await expect(page.getByText("Recommend ban").first()).toBeVisible();
  });

  test("champions tier list renders pack data", async ({ page }) => {
    await page.goto("/champions");
    await expect(page.getByText("Yasuo").first()).toBeVisible();
    await expect(page.getByText("MATCHUPS", { exact: false }).first()).toBeVisible();
  });

  test("progress renders design panels and suppresses dishonest benchmarks", async ({ page }) => {
    await page.goto("/progress");
    // Shipped-pack CS@10 medians are lane-minions-only; the feature contract
    // forbids comparing them with personal total-CS@10, so no card may render.
    await expect(page.getByTestId("lever-adoption")).toBeVisible();
    await expect(page.getByTestId("benchmark-cards")).toHaveCount(0);
  });

  test("navigation between all routes works", async ({ page }) => {
    await page.goto("/");
    for (const route of ["champ-select", "live", "postgame", "progress", "champions", "history"]) {
      await page.getByTestId(`nav-${route}`).click();
      await expect(page).toHaveURL(new RegExp(route));
    }
  });
});
