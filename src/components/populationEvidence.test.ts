import { describe, expect, it } from "vitest";
import { makePack } from "../routes/__tests__/fixtures";
import { habitEvidence } from "./populationEvidence";

describe("Findings Pack v2 habit evidence", () => {
  it("exposes the expanded-corpus multipliers with directional labels", () => {
    const rows = Object.fromEntries(habitEvidence(makePack()).map((row) => [row.key, row]));

    expect(rows.safe_recall_share).toMatchObject({
      effect: 2.32,
      label: "Higher safe-recall share",
      expectedFeature: "unseen_recall_share",
      feature: "unseen_recall_share",
      unit: "odds_ratio_per_standard_deviation",
      releaseStatus: "available",
      eraStability: "stable",
    });
    expect(rows.first_dragon_timing).toMatchObject({
      effect: 0.77,
      label: "Later first-dragon timing",
      expectedFeature: "first_dragon_s",
      feature: "first_dragon_s",
      unit: "odds_ratio_per_standard_deviation",
      releaseStatus: "available",
      eraStability: "stable",
    });
    expect(rows.banked_gold_at_recall).toMatchObject({
      effect: 0.8,
      label: "More banked gold at recall",
      expectedFeature: "avg_banked_gold_at_recall",
      feature: "avg_banked_gold_at_recall",
      unit: "odds_ratio_per_standard_deviation",
      releaseStatus: "available",
      eraStability: "stable",
    });
  });

  it("keeps available siblings when one canonical row is missing", () => {
    const source = makePack();
    const pack = makePack({
      habits: source.habits.filter((row) => row.key !== "first_dragon_timing"),
    });
    const rows = Object.fromEntries(habitEvidence(pack).map((row) => [row.key, row]));

    expect(rows.first_dragon_timing).toMatchObject({
      releaseStatus: null,
      effect: null,
      sample: null,
      feature: null,
    });
    expect(rows.first_dragon_timing.releaseReason).toBeNull();
    expect(rows.first_dragon_timing.contractIssue).toMatch(/missing/i);
    expect(rows.safe_recall_share).toMatchObject({ releaseStatus: "available", effect: 2.32 });
    expect(rows.banked_gold_at_recall).toMatchObject({ releaseStatus: "available", effect: 0.8 });
  });

  it("withholds only a malformed row and preserves the row-local reason", () => {
    const source = makePack();
    const pack = makePack({
      habits: source.habits.map((row) =>
        row.key === "banked_gold_at_recall" ? { ...row, effect: 1.282502 } : row,
      ),
    });
    const rows = Object.fromEntries(habitEvidence(pack).map((row) => [row.key, row]));

    expect(rows.banked_gold_at_recall.releaseStatus).toBe("available");
    expect(rows.banked_gold_at_recall.effect).toBeNull();
    expect(rows.banked_gold_at_recall.contractIssue).toMatch(/contract/i);
    expect(rows.safe_recall_share).toMatchObject({ releaseStatus: "available", effect: 2.32 });
    expect(rows.first_dragon_timing).toMatchObject({ releaseStatus: "available", effect: 0.77 });
  });
});
