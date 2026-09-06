import type { FindingsPackV2, PackV2Objective, PackV2ObservationWindow } from "../api/pack-v2";
import { isFindingsPackV2 } from "../api/pack-v2";

export const OBJECTIVE_ORDER = ["dragon", "herald", "baron"] as const;
export type ObjectiveName = (typeof OBJECTIVE_ORDER)[number];

export function objectiveRows(pack: FindingsPackV2 | undefined): PackV2Objective[] {
  return isFindingsPackV2(pack) ? pack.objectives : [];
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
  return (
    (row.release_status === "available" || row.release_status === "approximate") &&
    Number.isFinite(row.rate) &&
    row.rate >= 0 &&
    row.rate <= 1 &&
    row.sample > 0 &&
    row.population_scope.trim().length > 0 &&
    row.caveats.length > 0 &&
    row.caveats.every((caveat) => caveat.trim().length > 0)
  );
}

export function objectiveCaveat(row: PackV2Objective): string {
  return row.caveats[0] ?? "Population association; selection effects may remain.";
}
