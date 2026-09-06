import type { Page } from "@playwright/test";

const PACK_URL = "http://127.0.0.1:23122/pack";

const EVIDENCE_METADATA = {
  patch_range: { min: "14.17", max: "16.17" },
  population_scope: "e2e v2 pooled population fixture",
  era_stability: "stable",
  caveats: ["Observational association; replay fixture only."],
  source_document: "e2e fixture",
  source_section: "Findings Pack v2 fixture",
  source_ref: "e2e-fixture#v2",
  metric_kind: "win_rate",
  unit: "rate",
  provenance_key: "e2e-fixture",
  sample: 600,
} as const;

const TIER_LIST = [
  {
    ...EVIDENCE_METADATA,
    champion: "Ahri",
    role: "MIDDLE",
    games: 600,
    observed_win_rate: 0.534,
    role_pick_rate: 0.142,
    rank_band: "S",
    minimum_games: 500,
    tier: "diagnostic",
    release_status: "available",
  },
  {
    ...EVIDENCE_METADATA,
    champion: "Qiyana",
    role: "MIDDLE",
    games: 500,
    observed_win_rate: 0.4233,
    role_pick_rate: 0.05,
    rank_band: "B",
    minimum_games: 500,
    tier: "diagnostic",
    release_status: "available",
  },
  {
    ...EVIDENCE_METADATA,
    champion: "Darius",
    role: "TOP",
    games: 610,
    observed_win_rate: 0.517,
    role_pick_rate: 0.224,
    rank_band: "A",
    minimum_games: 500,
    tier: "diagnostic",
    release_status: "available",
  },
  {
    ...EVIDENCE_METADATA,
    champion: "Garen",
    role: "TOP",
    games: 500,
    observed_win_rate: 0.51,
    role_pick_rate: 0.2,
    rank_band: "A",
    minimum_games: 500,
    tier: "diagnostic",
    release_status: "available",
  },
] as const;

const MATCHUP_EXAMPLES = [
  {
    ...EVIDENCE_METADATA,
    champion: "Ahri",
    opponent: "Zed",
    role: "MIDDLE",
    games: 41,
    estimate: 0.57,
    interval: { lower: 0.48, upper: 0.66, include_lower: true, include_upper: false },
    tier: "diagnostic",
    release_status: "available",
  },
  {
    ...EVIDENCE_METADATA,
    champion: "Ahri",
    opponent: "Yasuo",
    role: "MIDDLE",
    games: 33,
    estimate: 0.44,
    interval: { lower: 0.35, upper: 0.53, include_lower: true, include_upper: false },
    tier: "diagnostic",
    release_status: "available",
  },
  {
    ...EVIDENCE_METADATA,
    champion: "Darius",
    opponent: "Garen",
    role: "TOP",
    games: 42,
    estimate: 0.5902,
    interval: { lower: 0.503, upper: 0.677, include_lower: true, include_upper: false },
    tier: "diagnostic",
    release_status: "available",
  },
  {
    ...EVIDENCE_METADATA,
    champion: "Darius",
    opponent: "Teemo",
    role: "TOP",
    games: 42,
    estimate: 0.4098,
    interval: { lower: 0.323, upper: 0.497, include_lower: true, include_upper: false },
    tier: "diagnostic",
    release_status: "available",
  },
] as const;

/**
 * The bundled v2 pack truthfully has no qualifying tier rows. These browser
 * scenarios need a separate, explicit v2 fixture so role and directional
 * matchup journeys exercise their real UI contracts without changing the
 * shipped pack or weakening route readiness.
 */
export async function mockTierEvidencePack(page: Page): Promise<void> {
  await page.route(PACK_URL, async (route) => {
    const response = await route.fetch();
    const pack = (await response.json()) as Record<string, unknown>;
    const fixturePack = {
      ...pack,
      tier_list: TIER_LIST,
      matchup_examples: MATCHUP_EXAMPLES,
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixturePack),
    });
  });
}
