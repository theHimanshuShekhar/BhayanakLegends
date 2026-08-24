import { expect, test } from "@playwright/test";

test.describe("Bhayanak Legends v1 smoke", () => {
  test("live match shows objectives priors from the Findings Pack", async ({ page }) => {
    await page.goto("/live");
    await expect(page.getByTestId("sidecar-dot")).toBeVisible();
    await expect(page.getByText("81.4%")).toBeVisible();
    await expect(page.getByText("27.6%")).toBeVisible();
    await expect(page.getByText(":2999 comes online at match start")).toBeVisible();
  });

  test("history shows the imported Personal History", async ({ page }) => {
    await page.goto("/history");
    await expect(page.getByTestId("summary-matches")).toHaveText(/^[1-9][\d,]*$/);
    await expect(page.getByRole("button", { name: "Start sync" })).toBeVisible();
  });

  test("post-game digest renders the latest real game", async ({ page }) => {
    await page.goto("/postgame");
    await expect(page.getByText("DIAGNOSTIC").first()).toBeVisible();
    await expect(page.getByText("Recall safely")).toBeVisible();
  });

  test("champ select idle keeps policy note and population intel visible", async ({ page }) => {
    await page.goto("/champ-select");
    await expect(page.getByText("Ranked enemy names stay hidden by policy.")).toBeVisible();
    await expect(page.getByText("Recommend ban").first()).toBeVisible();
  });

  test("champions tier list renders pack data", async ({ page }) => {
    await page.goto("/champions");
    await expect(page.getByText("Lillia").first()).toBeVisible();
  });

  test("progress renders trajectory for imported matches", async ({ page }) => {
    await page.goto("/progress");
    await expect(page.locator("svg").first()).toBeVisible();
    await expect(page.getByText("Rolling win rate per patch")).toBeVisible();
  });

  test("navigation between all routes works", async ({ page }) => {
    await page.goto("/");
    for (const route of ["champ-select", "live", "postgame", "progress", "champions", "history"]) {
      await page.getByTestId(`nav-${route}`).click();
      await expect(page).toHaveURL(new RegExp(route));
    }
  });
});
