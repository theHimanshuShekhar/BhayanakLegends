import { expect, test, type APIRequestContext } from "@playwright/test";

const SIDECAR = "http://127.0.0.1:23122";
const LCU = "http://127.0.0.1:23123";
const LIVE = "http://127.0.0.1:23124";
const AUTH = {
  "X-BL-Token": "local-sidecar-development-token-32chars",
  Host: "127.0.0.1:23122",
};

async function setScenario(request: APIRequestContext, base: string, scenario: string) {
  const response = await request.post(`${base}/control`, { data: { scenario } });
  expect(response.ok()).toBeTruthy();
}

function containsForbiddenKeys(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenKeys);
  if (!value || typeof value !== "object") return false;
  return Object.entries(value).some(([key, child]) =>
    /ability|ultimate|cooldown|spell_timer/i.test(key) || containsForbiddenKeys(child),
  );
}

test.describe("active Live Companion replay", () => {
  test("champ select transitions from idle and updates ally state over SSE", async ({ page, request }) => {
    await page.goto("/champ-select");
    await expect(page.getByTestId("champ-select-page")).toBeVisible();
    await expect(page.getByText("champion-level intel only").first()).toBeVisible();

    await setScenario(request, LCU, "champ-select");
    await expect(page.getByTestId("cs-your-side")).toContainText("Annie");
    await expect(page.getByTestId("cs-your-side")).toContainText("YOU");
    await expect(page.getByTestId("cs-your-side")).toContainText("Miss Fortune");
    await expect(page.getByText("FixturePlayer06", { exact: false })).toHaveCount(0);

    const sessionResponse = await request.get(`${SIDECAR}/live/session`, { headers: AUTH });
    expect(sessionResponse.ok()).toBeTruthy();
    const session = await sessionResponse.json();
    expect(session.active).toBe(true);
    expect(session.enemy.every((cell: { name: string | null }) => cell.name === null)).toBe(true);
    expect(JSON.stringify(session)).not.toContain("FixturePlayer06");

    await setScenario(request, LCU, "champ-select-update");
    await expect(page.getByTestId("cs-your-side")).toContainText("Miss Fortune");
    await expect(page).toHaveURL(/\/champ-select$/);
  });

  test("in-game replay renders teams, scores and events, then updates without reload", async ({ page, request }) => {
    await setScenario(request, LCU, "in-game");
    await setScenario(request, LIVE, "in-game");
    await page.goto("/live");

    await expect(page.getByTestId("bridge-status")).toContainText(":2999");
    await expect(page.getByTestId("player-row-local")).toContainText("Viktor");
    await expect(page.getByTestId("team-chaos")).toContainText("Camille");
    await expect(page.getByTestId("score-strip")).toContainText("kills");
    await expect(page.getByTestId("event-feed")).toContainText("DragonKill");

    const ingameResponse = await request.get(`${SIDECAR}/live/ingame`, { headers: AUTH });
    expect(ingameResponse.ok()).toBeTruthy();
    const ingame = await ingameResponse.json();
    expect(ingame.active).toBe(true);
    expect(ingame.teams.order.flatMap((player: { items: unknown[] }) => player.items).length).toBeGreaterThan(0);
    expect(containsForbiddenKeys(ingame)).toBe(false);

    await setScenario(request, LCU, "in-game-update");
    await setScenario(request, LIVE, "in-game-update");
    await expect(page.getByTestId("event-feed")).toContainText("BaronKill");
    await expect(page.getByTestId("active-kda")).toContainText("5 / 2 / 7");
    await expect(page.getByTestId("game-clock")).toContainText("13:32");
    await expect(page).toHaveURL(/\/live$/);
  });

  test("malformed and reconnect fixtures keep compliance boundaries deterministic", async ({ page, request }) => {
    await setScenario(request, LCU, "malformed");
    await setScenario(request, LIVE, "malformed");
    await page.goto("/live");
    await expect(page.getByTestId("player-list")).toBeVisible();

    await setScenario(request, LCU, "reconnect");
    await setScenario(request, LIVE, "reconnect");
    await expect(page.getByTestId("waiting-pill")).toBeVisible();
    const status = await request.get(`${SIDECAR}/live/status`, { headers: AUTH });
    expect(status.ok()).toBeTruthy();
    expect(containsForbiddenKeys(await status.json())).toBe(false);
  });
});
