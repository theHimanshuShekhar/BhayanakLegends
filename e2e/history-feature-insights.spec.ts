import { expect, test } from "@playwright/test";

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
