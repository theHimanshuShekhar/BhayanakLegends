import type { FindingsPackV2, PackV2Objective, PackV2ObservationWindow } from "../api/pack-v2";
import { isFindingsPackV2 } from "../api/pack-v2";

export const OBJECTIVE_ORDER = ["dragon", "herald", "baron"] as const;
export type ObjectiveName = (typeof OBJECTIVE_ORDER)[number];

const OBJECTIVE_METRIC_ORDER: Record<PackV2Objective["metric_kind"], number> = {
  possession_rate: 0,
  before_time_rate: 1,
  contested_first_rate: 2,
  no_objective_rate: 3,
  matched_effect: 4,
};

const EXPECTED_WINDOW: Record<
  Exclude<PackV2Objective["metric_kind"], "matched_effect">,
  PackV2Objective["window"]["kind"]
> = {
  possession_rate: "full_match",
  before_time_rate: "before_time",
  contested_first_rate: "full_match",
  no_objective_rate: "full_match",
};

export function objectiveRows(pack: FindingsPackV2 | undefined): PackV2Objective[] {
  return isFindingsPackV2(pack) ? pack.objectives : [];
}

export function objectiveRowsFor(
  pack: FindingsPackV2 | undefined,
  objective: ObjectiveName,
): PackV2Objective[] {
  return objectiveRows(pack)
    .filter((row) => row.objective === objective)
    .sort(
      (a, b) =>
        OBJECTIVE_METRIC_ORDER[a.metric_kind] - OBJECTIVE_METRIC_ORDER[b.metric_kind] ||
        a.window.kind.localeCompare(b.window.kind),
    );
}

export function objectiveLabel(objective: ObjectiveName): string {
  return objective === "dragon" ? "Dragon" : objective === "herald" ? "Herald" : "Baron";
}

export function objectiveMetricLabel(metric: PackV2Objective["metric_kind"]): string {
  switch (metric) {
    case "possession_rate":
      return "possession rate";
    case "before_time_rate":
      return "before-time rate";
    case "contested_first_rate":
      return "contested-first rate";
    case "no_objective_rate":
      return "no-objective rate";
    case "matched_effect":
      return "matched effect";
  }
}

export function objectiveWindowLabel(window: PackV2ObservationWindow): string {
  if (window.kind === "pooled" || window.kind === "full_match") return window.kind.replace("_", " ");
  const start = window.start_seconds == null ? null : `${window.start_seconds}s`;
  const end = window.end_seconds == null ? null : `${window.end_seconds}s`;
  if (start != null && end != null) return `${start}–${end}`;
  if (end != null) return `before ${end}`;
  if (start != null) return `after ${start}`;
  return window.kind.replace("_", " ");
}

export function isObjectiveRenderable(row: PackV2Objective): boolean {
  if (
    (row.release_status !== "available" && row.release_status !== "approximate") ||
    !Number.isFinite(row.rate) ||
    row.rate < 0 ||
    row.rate > 1 ||
    row.sample <= 0 ||
    row.population_scope.trim().length === 0 ||
    row.caveats.length === 0 ||
    row.caveats.some((caveat) => caveat.trim().length === 0) ||
    row.tier !== "diagnostic" ||
    row.metric_kind === "matched_effect"
  ) {
    return false;
  }
  const expectedWindow = EXPECTED_WINDOW[row.metric_kind];
  return expectedWindow == null || row.window.kind === expectedWindow;
}

export function objectiveCaveat(row: PackV2Objective): string {
  return row.caveats[0] ?? "Population association; selection effects may remain.";
}
