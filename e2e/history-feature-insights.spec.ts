import { expect, test, type APIRequestContext } from "@playwright/test";

const SIDECAR = "http://127.0.0.1:23122";
const LCU = "http://127.0.0.1:23123";
const AUTH = {
  "X-BL-Token": "local-sidecar-development-token-32chars",
  Host: "127.0.0.1:23122",
};
const WHAT_IF_CONTROLS = [
  "avg_banked_gold_at_recall_by_20m",
  "unseen_recall_share_by_20m",
  "plates_taken_by_14m",
] as const;

type WhatIfBody = {
  status: string;
  probability: number | null;
  baseline_probability: number | null;
  model_version: string | null;
  pack_version: string | null;
  reason: string | null;
};

async function setHistorySeed(request: APIRequestContext, eligibility: "eligible" | "ineligible") {
  const response = await request.post(`${LCU}/control`, {
    data: { scenario: `history-${eligibility}` },
  });
  expect(response.ok()).toBeTruthy();
}

const FEATURE_INSIGHTS = {
  state: "available",
  sample_size: 8,
  filters: { role: null, champion: null },
  roles: [
    { role: "MIDDLE", games: 8, wins: 4, win_rate: 0.5, sample_status: "review" },
  ],
  champions: [
    { champion: "FixtureMage", games: 8, wins: 4, win_rate: 0.5, roles: ["MIDDLE"], sample_status: "review" },
  ],
  windows: {
    latest: { name: "latest", games: 8, wins: 4, win_rate: 0.5, sample_status: "review", completeness: "partial" },
    preceding: { name: "preceding", games: 0, wins: 0, win_rate: 0, sample_status: "insufficient", completeness: "unavailable" },
  },
  feature_contract_version: "loltrends-parity-v2",
  feature_contract_status: "available",
  feature_insights: [
    {
      feature_key: "early_fight_participation_rate",
      current_value: 0.4,
      role_baseline: 0.32,
      delta: 0.08,
      sample_size: 8,
      status: "available",
      caveat: "Descriptive participation association; not a causal recommendation.",
    },
    {
      feature_key: "first_dragon_by_20m_s",
      current_value: 512,
      role_baseline: 540,
      delta: -28,
      sample_size: 6,
      status: "available",
      caveat: "Timing association only; possession and denial remain separate.",
    },
    {
      feature_key: "plates_taken_by_14m",
      current_value: 2,
      role_baseline: 1.4,
      delta: 0.6,
      sample_size: 7,
      status: "available",
      caveat: "Weak, era-sensitive diagnostic association.",
    },
  ],
  feature_trajectories: [
    {
      feature_key: "early_fight_participation_rate",
      played_at: "2026-08-01T00:00:00Z",
      value: 0.4,
      sample_size: 1,
      status: "available",
      caveat: "Descriptive participation association; not a causal recommendation.",
    },
    {
      feature_key: "first_dragon_by_20m_s",
      played_at: "2026-08-01T00:00:00Z",
      value: 512,
      sample_size: 1,
      status: "available",
      caveat: "Timing association only; possession and denial remain separate.",
    },
    {
      feature_key: "plates_taken_by_14m",
      played_at: "2026-08-01T00:00:00Z",
      value: 2,
      sample_size: 1,
      status: "available",
      caveat: "Weak, era-sensitive diagnostic association.",
    },
  ],
};

const POSTGAME_DIGEST = {
  match_id: "FIXTURE_MATCH_01",
  played_at: "2026-08-01T00:00:00Z",
  champion: "FixtureMage",
  role: "MIDDLE",
  win: true,
  duration_s: 1800,
  checkpoints: { gold_diff_10: 100, gold_diff_15: 250, gold_diff_20: null },
  habits: [],
  headline: "Won as FixtureMage in a 30-minute game",
  feature_contract_version: "loltrends-parity-v2",
  personal_history_eligibility: "eligible",
  features: {
    early_fight_participation_rate: 0.4,
    first_dragon_by_20m_s: 512,
    plates_taken_by_14m: 2,
  },
  team_state: {
    feature: "team_gold_diff_15m",
    feature_contract_version: "loltrends-parity-v2",
    team_gold_diff_15m: 250,
    observed_through_s: 1800,
    non_surrendered: true,
  },
};

const ACTIVE_SETTINGS = {
  owner_key: "replay#E2E",
  generation: 1,
  owner_state: "active",
  owner_error: null,
  riot_id: "replay#E2E",
  region_route: "sea",
  has_key: true,
  auto_sync: false,
};

test.describe("Personal History feature insights", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/settings", (route) =>
      route.fulfill({ status: 200, json: ACTIVE_SETTINGS }),
    );
  });
  test("shows role-adjusted comparisons and feature trajectories in the Journal", async ({ page }) => {

    await page.route("**/history/insights*", async (route) => {
      await route.fulfill({ json: FEATURE_INSIGHTS });
    });

    await page.goto("/history");

    const card = page.getByTestId("journal-feature-insights");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("feature-insight-early_fight_participation_rate")).toContainText("40.0%");
    await expect(card.getByTestId("feature-insight-early_fight_participation_rate")).toContainText("matching-role reference 32.0%");
    await expect(card.getByTestId("feature-insight-first_dragon_by_20m_s")).toContainText("8:32");
    await expect(card.getByTestId("feature-trajectory-plates_taken_by_14m")).toContainText("2 plates");
    await expect(card).toContainText(/timing association only/i);
    await expect(card).toContainText(/era-sensitive/i);
    await expect(card).not.toContainText(/fight more|take dragon|must/i);

    await page.getByTestId("insights-role-filter").focus();
    await expect(page.getByTestId("insights-role-filter")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByTestId("insights-champion-filter")).toBeFocused();
  });

  test("shows the same observations in post-game without a habit verdict", async ({ page }) => {
    await page.route("**/postgame/latest", async (route) => {
      await route.fulfill({ json: POSTGAME_DIGEST });
    });

    await page.goto("/postgame");

    const observations = page.getByTestId("habit-feature-observations");
    await expect(observations).toBeVisible();
    await expect(observations).toContainText("40.0%");
    await expect(observations).toContainText("8:32");
    await expect(observations).toContainText("2 plates");
    await expect(observations).toContainText(/possession and denial are separate/i);
    await expect(observations).toContainText(/Weak, era-sensitive review context unavailable/i);
    await expect(page.getByTestId("habit-outcomes")).toHaveCount(0);
  });
});

test.describe("Personal History What-If sidecar replay", () => {
  test("uses the authenticated eligible seed, declared controls, provenance, stale clearing, and ineligible suppression", async ({ page, request }) => {
    test.setTimeout(90_000);
    await setHistorySeed(request, "eligible");

    const settingsResponse = await request.get(`${SIDECAR}/settings`, { headers: AUTH });
    expect(settingsResponse.ok()).toBeTruthy();
    expect(await settingsResponse.json()).toMatchObject({
      riot_id: "replay#E2E",
      owner_state: "active",
    });

    const digestResponse = await request.get(`${SIDECAR}/postgame/latest`, { headers: AUTH });
    expect(digestResponse.ok()).toBeTruthy();
    expect(await digestResponse.json()).toMatchObject({
      match_id: "what-if-eligible",
      feature_contract_version: "loltrends-parity-v2",
      personal_history_eligibility: "eligible",
      features: {
        avg_banked_gold_at_recall_by_20m: 700,
        unseen_recall_share_by_20m: 0.5,
        plates_taken_by_14m: 7.5,
      },
    });

    const directAvailable = await request.post(`${SIDECAR}/history/what-if`, {
      headers: AUTH,
      data: { adjustments: { unseen_recall_share_by_20m: 0.75 } },
    });
    expect(directAvailable.ok()).toBeTruthy();
    const directBody = (await directAvailable.json()) as WhatIfBody;
    expect(directBody).toMatchObject({
      status: "available",
      model_version: "personal-what-if-v2",
      pack_version: "v4",
      reason: null,
    });
    expect(directBody.probability).toEqual(expect.any(Number));
    expect(directBody.baseline_probability).toEqual(expect.any(Number));


    await page.goto("/history");
    await expect(page.getByRole("heading", { level: 1, name: "Improvement Journal" })).toBeVisible();
    await expect(page.getByTestId("what-if-panel")).toHaveCount(1);
    await expect(page.locator('[data-testid^="what-if-control-"]')).toHaveCount(3);
    for (const control of WHAT_IF_CONTROLS) {
      await expect(page.getByTestId(`what-if-control-${control}`)).toBeEnabled();
    }
    await expect(page.getByTestId("what-if-caption")).toContainText(/association only; not causal/i);

    const recallGold = page.getByTestId("what-if-control-avg_banked_gold_at_recall_by_20m");
    const unseenRecall = page.getByTestId("what-if-control-unseen_recall_share_by_20m");
    const plates = page.getByTestId("what-if-control-plates_taken_by_14m");
    await recallGold.fill("900");
    await unseenRecall.fill("0.75");
    await plates.fill("8");
    const browserRequest = page.waitForRequest(
      (outgoing) => outgoing.method() === "POST" && outgoing.url().endsWith("/history/what-if"),
    );
    await page.getByTestId("what-if-run").click();
    const browserMutation = await browserRequest;

    await expect(page.getByTestId("what-if-current")).toHaveText(/\d+(?:\.\d+)?%/);
    await expect(page.getByTestId("what-if-prediction")).toHaveText(/\d+(?:\.\d+)?%/);
    await expect(page.getByTestId("what-if-provenance")).toHaveText(
      "Model personal-what-if-v2 · Pack v4",
    );
    expect(browserMutation.headers()["x-bl-token"]).toBe(AUTH["X-BL-Token"]);
    expect(
      (browserMutation.postDataJSON() as { adjustments: Record<string, number> }).adjustments,
    ).toEqual({
      avg_banked_gold_at_recall_by_20m: 900,
      unseen_recall_share_by_20m: 0.75,
      plates_taken_by_14m: 8,
    });

    await unseenRecall.fill("0.25");
    await expect(page.getByTestId("what-if-current")).toHaveText("Unavailable");
    await expect(page.getByTestId("what-if-prediction")).toHaveText("Unavailable");
    await expect(page.getByTestId("what-if-provenance")).toHaveCount(0);

    await setHistorySeed(request, "ineligible");
    const suppressedResponse = await request.post(`${SIDECAR}/history/what-if`, {
      headers: AUTH,
      data: { adjustments: { unseen_recall_share_by_20m: 0.25 } },
    });
    expect(suppressedResponse.ok()).toBeTruthy();
    expect(await suppressedResponse.json()).toMatchObject({
      status: "suppressed",
      probability: null,
      baseline_probability: null,
      reason: "Personal History seed is not eligible",
    });

    await page.reload();
    await expect(page.getByTestId("what-if-run")).toBeDisabled();
    await expect(page.getByTestId("what-if-current")).toHaveText("Unavailable");
    await expect(page.getByTestId("what-if-prediction")).toHaveText("Unavailable");
    await expect(page.getByTestId("what-if-provenance")).toHaveCount(0);
    await expect(page.getByTestId("what-if-caption")).toContainText(/baseline is unavailable/i);
    await setHistorySeed(request, "eligible");
  });
});
