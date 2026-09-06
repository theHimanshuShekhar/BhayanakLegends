import type { ReactNode } from "react";
import type {
  FindingsPackV2,
  PackV2BuildEvidence,
  PackV2Finding,
  PackV2Habit,
  PackV2RouteArchetype,
} from "../api/pack-v2";
import { isFindingsPackV2 } from "../api/pack-v2";
import { formatPatchScope } from "./format";

export type EvidenceTier = "actionable" | "diagnostic" | "a-lite";
export type EvidenceReleaseStatus = "available" | "approximate" | "withheld" | "superseded";
export type EvidenceEraStability = "stable" | "sensitive" | "insufficient" | "not_evaluated";

export interface PatchRange {
  min: string;
  max: string;
}

export interface EvidenceMetadata {
  tier: EvidenceTier;
  releaseStatus: EvidenceReleaseStatus;
  metric: string;
  unit: string;
  sample: number | null;
  patchRange: PatchRange | null;
  populationScope: string | null;
  eraStability: EvidenceEraStability | null;
  caveats: string[];
  sourceDocument: string | null;
  sourceSection: string | null;
  sourceRef: string | null;
  releaseReason: string | null;
}

export interface MasteryEvidence {
  value: number | null;
  statement: string;
  metadata: EvidenceMetadata;
}

export interface BanCorrelationEvidence {
  champion: string | null;
  value: number | null;
  statement: string;
  sample: number | null;
  metadata: EvidenceMetadata;
}

export interface TierEvidenceRow {
  champion: string;
  role: string;
  games: number;
  pickRate: number;
  winRate: number;
  rankBand: "S" | "A" | "B" | "C";
  minimumGames: number;
  metadata: EvidenceMetadata;
}

export interface MatchupInterval {
  lower: number;
  upper: number;
  includeLower: boolean;
  includeUpper: boolean;
}

export interface MatchupEvidenceRow {
  champion: string;
  opponent: string;
  role: string;
  games: number;
  estimate: number;
  interval: MatchupInterval;
  metadata: EvidenceMetadata;
}

export interface RouteArchetypeEvidence {
  archetype: string;
  sample: number;
  observedOutcome: string;
  side: string | null;
  champion: string | null;
  coordinateValidation: string;
  metadata: EvidenceMetadata;
}

export interface BuildEvidence {
  metadata: EvidenceMetadata;
  statement: string;
}

type AnyRecord = Record<string, unknown>;

const EVIDENCE_TIERS: Record<EvidenceTier, true> = {
  actionable: true,
  diagnostic: true,
  "a-lite": true,
};
const RELEASE_STATUSES: Record<EvidenceReleaseStatus, true> = {
  available: true,
  approximate: true,
  withheld: true,
  superseded: true,
};
const ERA_STABILITIES: Record<EvidenceEraStability, true> = {
  stable: true,
  sensitive: true,
  insufficient: true,
  not_evaluated: true,
};
const RANK_BANDS: Record<TierEvidenceRow["rankBand"], true> = {
  S: true,
  A: true,
  B: true,
  C: true,
};
const MASTERY_PREMIUM = 1.94;
const BAN_CORRELATION = 0.062353;
const HABIT_SPECS: Record<
  string,
  { feature: string; effect: number; tier: EvidenceTier; era: EvidenceEraStability }
> = {
  recall_safety: {
    feature: "unseen_recall_share_by_15m",
    effect: 2.32,
    tier: "actionable",
    era: "stable",
  },
  fast_first_dragon: {
    feature: "first_dragon_by_20m_s",
    effect: 0.77,
    tier: "actionable",
    era: "stable",
  },
  spend_before_backing: {
    feature: "avg_banked_gold_at_recall_by_15m",
    effect: 0.8,
    tier: "actionable",
    era: "stable",
  },
  plates_by_14: {
    feature: "plates_taken_by_14m",
    effect: 1.03,
    tier: "diagnostic",
    era: "sensitive",
  },
};
const HABIT_METRIC = "odds_ratio_per_standard_deviation";
const HABIT_UNIT = "odds ratio per standard deviation";

function record(value: unknown): AnyRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as AnyRecord)
    : null;
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function probability(value: unknown): value is number {
  return finite(value) && value >= 0 && value <= 1;
}

function positiveInteger(value: unknown): value is number {
  return finite(value) && Number.isInteger(value) && value > 0;
}


function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
        .map((item) => item.trim())
    : [];
}

function readPatchRange(value: unknown): PatchRange | null {
  const item = record(value);
  const min = stringValue(item?.min);
  const max = stringValue(item?.max);
  return min && max ? { min, max } : null;
}

function readTier(value: unknown): EvidenceTier | null {
  return typeof value === "string" && value in EVIDENCE_TIERS
    ? (value as EvidenceTier)
    : null;
}

function readReleaseStatus(value: unknown): EvidenceReleaseStatus | null {
  return typeof value === "string" && value in RELEASE_STATUSES
    ? (value as EvidenceReleaseStatus)
    : null;
}

function readEraStability(value: unknown): EvidenceEraStability | null {
  return typeof value === "string" && value in ERA_STABILITIES
    ? (value as EvidenceEraStability)
    : null;
}

function readMetadata(
  value: unknown,
  options: {
    metric?: string;
    unit?: string;
    sampleRequired?: boolean;
  } = {},
): EvidenceMetadata | null {
  const item = record(value);
  if (!item) return null;

  const tier = readTier(item.tier);
  const releaseStatus = readReleaseStatus(item.release_status);
  const metric = stringValue(options.metric) ?? stringValue(item.metric_kind) ?? stringValue(item.metric);
  const unit = stringValue(options.unit) ?? stringValue(item.unit);
  const sample = positiveInteger(item.sample) ? item.sample : null;
  const patchRange = readPatchRange(item.patch_range);
  const populationScope = stringValue(item.population_scope);
  const eraStability = readEraStability(item.era_stability);
  const caveats = stringArray(item.caveats);
  const sourceDocument = stringValue(item.source_document);
  const sourceSection = stringValue(item.source_section);
  const sourceRef = stringValue(item.source_ref);
  const releaseReason = stringValue(item.release_reason);

  if (
    !tier ||
    !releaseStatus ||
    !metric ||
    !unit ||
    (options.sampleRequired !== false && sample == null) ||
    !patchRange ||
    !populationScope ||
    !eraStability ||
    caveats.length === 0 ||
    !sourceDocument ||
    !sourceSection ||
    !sourceRef
  ) {
    return null;
  }
  return {
    tier,
    releaseStatus,
    metric,
    unit,
    sample,
    patchRange,
    populationScope,
    eraStability,
    caveats,
    sourceDocument,
    sourceSection,
    sourceRef,
    releaseReason,
  };
}

export function packData(pack: FindingsPackV2 | undefined): FindingsPackV2 | null {
  return isFindingsPackV2(pack) ? pack : null;
}

export function packPatchLabel(pack: FindingsPackV2 | undefined): string | null {
  const range = packData(pack)?.patch_range;
  return range ? `${range.min}–${range.max}` : null;
}


export function evidenceUsable(metadata: EvidenceMetadata): boolean {
  return metadata.releaseStatus === "available" || metadata.releaseStatus === "approximate";
}

export function evidenceStatusLabel(metadata: EvidenceMetadata): string {
  if (metadata.releaseStatus === "withheld") return "Withheld";
  if (metadata.releaseStatus === "superseded") return "Superseded";
  if (metadata.releaseStatus === "approximate") return "Approximate";
  return "Available";
}

function findings(pack: FindingsPackV2): PackV2Finding[] {
  return Array.isArray(pack.findings) ? pack.findings : [];
}

export function findFinding(pack: FindingsPackV2 | undefined, key: string): PackV2Finding | null {
  const data = packData(pack);
  return data ? findings(data).find((finding) => finding.key === key) ?? null : null;
}

export interface FindingEvidence {
  key: string;
  title: string;
  statement: string;
  value: number | string | null;
  metadata: EvidenceMetadata;
}

export function findingEvidence(pack: FindingsPackV2 | undefined): FindingEvidence[] {
  const data = packData(pack);
  if (!data) return [];
  return findings(data)
    .map((item): FindingEvidence | null => {
      const metadata = readMetadata(item);
      const key = stringValue(item.key);
      const title = stringValue(item.title);
      const statement = stringValue(item.statement);
      if (!metadata || !key || !title || !statement) return null;
      const value = finite(item.value)
        ? item.value
        : typeof item.value === "string" && item.value.trim().length > 0
          ? item.value
          : null;
      return { key, title, statement, value, metadata };
    })
    .filter((item): item is FindingEvidence => item !== null);
}

export function masteryEvidence(pack: FindingsPackV2 | undefined): MasteryEvidence | null {
  const item = findFinding(pack, "mastery_premium");
  if (!item) return null;
  const metadata = readMetadata(item);
  if (
    !metadata ||
    metadata.metric !== "percentage_points" ||
    metadata.unit !== "percentage_points" ||
    metadata.tier !== "actionable"
  ) {
    return null;
  }
  const value = finite(item.value) && Math.abs(item.value - MASTERY_PREMIUM) < 1e-9
    ? item.value
    : null;
  if (value == null && evidenceUsable(metadata)) return null;
  return {
    value,
    statement: stringValue(item.statement) ?? "The mastery result is available from the Findings Pack.",
    metadata,
  };
}

export function banCorrelationEvidence(pack: FindingsPackV2 | undefined): BanCorrelationEvidence | null {
  const data = packData(pack);
  const item = data?.ban_context.find(
    (context) =>
      context.key === "ban_win_rate_correlation" &&
      context.metric_kind === "ban_rate_win_rate_correlation",
  );
  if (!item) return null;
  const metadata = readMetadata(item, { metric: item.metric_kind, unit: "correlation" });
  if (!metadata || metadata.tier !== "diagnostic") return null;
  const usable = evidenceUsable(metadata);
  const value = usable && finite(item.value) && item.value >= -1 && item.value <= 1 &&
    Math.abs(item.value - BAN_CORRELATION) < 1e-9
    ? item.value
    : null;
  if (value == null && usable) return null;
  return {
    champion: stringValue(item.champion),
    value,
    statement: "The pooled relationship is descriptive population context, not a deterministic ban signal.",
    sample: positiveInteger(item.sample) ? item.sample : null,
    metadata,
  };
}

export function habitEvidence(pack: FindingsPackV2 | undefined): PackV2Habit[] {
  const data = packData(pack);
  if (!data) return [];
  return data.habits.filter((habit) => {
    const expected = HABIT_SPECS[habit.key];
    if (
      !expected ||
      (habit.release_status !== "available" && habit.release_status !== "approximate") ||
      habit.feature !== expected.feature ||
      habit.metric_kind !== HABIT_METRIC ||
      habit.unit !== HABIT_UNIT ||
      habit.tier !== expected.tier ||
      habit.era_stability !== expected.era
    ) {
      return false;
    }
    return finite(habit.effect) && Math.abs(habit.effect - expected.effect) < 1e-9;
  });
}

function normalizeTierRow(
  item: unknown,
): TierEvidenceRow | null {
  const row = record(item);
  if (!row) return null;
  const champion = stringValue(row.champion);
  const role = stringValue(row.role);
  const games = positiveInteger(row.games) ? row.games : null;
  const pickRate = probability(row.role_pick_rate) ? row.role_pick_rate : null;
  const winRate = probability(row.observed_win_rate) ? row.observed_win_rate : null;
  const rankBand = typeof row.rank_band === "string" && row.rank_band in RANK_BANDS
    ? (row.rank_band as TierEvidenceRow["rankBand"])
    : null;
  const minimumGames = row.minimum_games === 500 ? 500 : null;
  const metadata = readMetadata(row, { sampleRequired: false });
  if (
    !champion ||
    !role ||
    games == null ||
    pickRate == null ||
    winRate == null ||
    !rankBand ||
    minimumGames == null ||
    games < minimumGames ||
    !metadata ||
    metadata.tier !== "diagnostic" ||
    !evidenceUsable(metadata)
  ) {
    return null;
  }
  return { champion, role, games, pickRate, winRate, rankBand, minimumGames, metadata };
}

export function tierEvidence(pack: FindingsPackV2 | undefined, role?: string | null): TierEvidenceRow[] {
  const data = packData(pack);
  if (!data) return [];
  const seen = new Set<string>();
  const rows = data.tier_list
    .map(normalizeTierRow)
    .filter((row): row is TierEvidenceRow => row !== null)
    .filter((row) => {
      const key = `${row.role}\u0000${row.champion}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return !role || row.role === role;
    });
  return sortTierRows(rows);
}

const RANK_ORDER: Record<TierEvidenceRow["rankBand"], number> = { S: 0, A: 1, B: 2, C: 3 };

export function sortTierRows(rows: TierEvidenceRow[]): TierEvidenceRow[] {
  return [...rows].sort(
    (a, b) =>
      RANK_ORDER[a.rankBand] - RANK_ORDER[b.rankBand] ||
      b.winRate - a.winRate ||
      b.games - a.games ||
      a.champion.localeCompare(b.champion),
  );
}

function normalizeMatchupRow(item: unknown): MatchupEvidenceRow | null {
  const row = record(item);
  if (!row) return null;
  const champion = stringValue(row.champion);
  const opponent = stringValue(row.opponent);
  const role = stringValue(row.role);
  const games = positiveInteger(row.games) ? row.games : null;
  const estimate = probability(row.estimate) ? row.estimate : null;
  const rawInterval = record(row.interval);
  const lower = rawInterval && probability(rawInterval.lower) ? rawInterval.lower : null;
  const upper = rawInterval && probability(rawInterval.upper) ? rawInterval.upper : null;
  const interval =
    lower != null && upper != null && lower <= upper
      ? {
          lower,
          upper,
          includeLower: rawInterval?.include_lower === true,
          includeUpper: rawInterval?.include_upper === true,
        }
      : null;
  const metadata = readMetadata(row, { sampleRequired: false });
  if (
    !champion ||
    !opponent ||
    champion === opponent ||
    !role ||
    games == null ||
    estimate == null ||
    !interval ||
    estimate < interval.lower ||
    estimate > interval.upper ||
    !metadata ||
    metadata.tier !== "diagnostic" ||
    !evidenceUsable(metadata)
  ) {
    return null;
  }
  return { champion, opponent, role, games, estimate, interval, metadata };
}

export function matchupEvidence(
  pack: FindingsPackV2 | undefined,
  role?: string | null,
  champion?: string | null,
): MatchupEvidenceRow[] {
  const data = packData(pack);
  if (!data) return [];
  const seen = new Set<string>();
  const normalized: MatchupEvidenceRow[] = [];
  for (const item of data.matchup_examples) {
    const row = normalizeMatchupRow(item);
    if (!row || row.champion === row.opponent || (role && row.role !== role) || (champion && row.champion !== champion)) continue;
    const key = `${row.champion}\u0000${row.opponent}\u0000${row.role}`;
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(row);
  }
  return normalized.sort(
    (a, b) => a.estimate - b.estimate || b.games - a.games || a.opponent.localeCompare(b.opponent),
  );
}

export function routeArchetypeEvidence(pack: FindingsPackV2 | undefined): RouteArchetypeEvidence[] {
  const data = packData(pack);
  if (!data) return [];
  const rows: RouteArchetypeEvidence[] = [];
  for (const route of data.route_archetypes as PackV2RouteArchetype[]) {
    const metadata = readMetadata(route, {
      metric: "win_rate",
      unit: "win_rate",
      sampleRequired: true,
    });
    const archetype = stringValue(route.label);
    const sample = positiveInteger(route.sample) ? route.sample : null;
    const observed = probability(route.observed_outcome)
      ? `${(route.observed_outcome * 100).toFixed(1)}% observed win rate`
      : null;
    const coordinateValidation = stringValue(route.coordinate_validation);
    const forbidden = /\b(best|optimal|recommend(?:ed)?|pick|choose|should|must|avoid)\b/i;
    if (
      !metadata ||
      metadata.releaseStatus !== "approximate" ||
      !archetype ||
      forbidden.test(archetype) ||
      sample == null ||
      !observed ||
      !coordinateValidation
    ) {
      continue;
    }
    rows.push({
      archetype,
      sample,
      observedOutcome: observed,
      side: stringValue(route.side_context),
      champion: stringValue(route.champion_context),
      coordinateValidation,
      metadata,
    });
  }
  return rows.sort((a, b) => b.sample - a.sample || a.archetype.localeCompare(b.archetype));
}

export function buildEvidence(pack: FindingsPackV2 | undefined): BuildEvidence | null {
  const data = packData(pack);
  const raw = data?.build_evidence as PackV2BuildEvidence | undefined;
  if (!raw || raw.release_status !== "withheld") return null;
  const metadata = readMetadata(
    {
      ...raw,
      tier: "diagnostic",
      metric_kind: "status",
      unit: "status",
      sample: 1,
    },
    { sampleRequired: false },
  );
  if (!metadata) return null;
  return {
    metadata,
    statement: stringValue(raw.release_reason) ?? "Controlled build evidence is not available.",
  };
}


export function EvidenceMeta({
  metadata,
  testId,
  children,
}: {
  metadata: EvidenceMetadata;
  testId?: string;
  children?: ReactNode;
}) {
  const scope = metadata.populationScope ?? "population scope unavailable";
  const patch = formatPatchScope(metadata.patchRange);
  const source = [metadata.sourceDocument, metadata.sourceSection, metadata.sourceRef]
    .filter(Boolean)
    .join(" · ") || "source unavailable";
  const release = evidenceStatusLabel(metadata);
  return (
    <div
      data-testid={testId}
      role="group"
      aria-label={`Evidence metadata: ${release}; ${patch}; ${scope}`}
      style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9, lineHeight: 1.45, color: "var(--color-dimmer)" }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        <span
          className="pill"
          style={{
            background:
              metadata.releaseStatus === "withheld"
                ? "var(--color-danger-low)"
                : metadata.releaseStatus === "approximate"
                  ? "var(--color-amber-low)"
                  : "var(--color-info-low)",
            color:
              metadata.releaseStatus === "withheld"
                ? "var(--color-danger)"
                : metadata.releaseStatus === "approximate"
                  ? "var(--color-amber)"
                  : "var(--color-info)",
          }}
        >
          {release}
        </span>
        <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
          {patch}
        </span>
        <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
          {metadata.tier === "actionable" ? "Actionable" : metadata.tier === "diagnostic" ? "Diagnostic" : "A-lite"}
        </span>
      </div>
      <div>Population scope: {scope}</div>
      {metadata.sample != null && <div>Sample: {metadata.sample.toLocaleString("en-US")} observations</div>}
      <div>Source: {source}</div>
      {metadata.caveats.map((caveat, index) => <div key={`${caveat}-${index}`}>Caveat: {caveat}</div>)}
      {metadata.releaseReason && <div>Release note: {metadata.releaseReason}</div>}
      {children}
    </div>
  );
}
