import type { ReactNode } from "react";
import type { FindingsPackV1, RoleV1 } from "../api/pack-v1";
import type {
  FindingsPackV2,
  PackV2BuildEvidence,
  PackV2Finding,
  PackV2RouteArchetype,
} from "../api/pack-v2";
import { isFindingsPackV1 } from "../api/pack-v1";
import { isFindingsPackV2 } from "../api/pack-v2";
import type { FindingsPack } from "../api/pack-v2";
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
  legacy?: boolean;
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
  legacy?: boolean;
}
export interface LegacyBenchmarkEvidence {
  role: RoleV1;
  cs10Median: number | null;
  level10Median: number | null;
  goldDiff10Median: number | null;
  sample: number;
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
  {
    feature: string;
    label: string;
    effect: number;
    tier: EvidenceTier;
    era: EvidenceEraStability;
  }
> = {
  safe_recall_share: {
    feature: "unseen_recall_share",
    label: "Higher safe-recall share",
    effect: 2.32,
    tier: "actionable",
    era: "stable",
  },
  first_dragon_timing: {
    feature: "first_dragon_s",
    label: "Later first-dragon timing",
    effect: 0.77,
    tier: "actionable",
    era: "stable",
  },
  banked_gold_at_recall: {
    feature: "avg_banked_gold_at_recall",
    label: "More banked gold at recall",
    effect: 0.8,
    tier: "actionable",
    era: "stable",
  },
  plates_by_14m: {
    feature: "plates_taken_by_14m",
    label: "Turret plates are weak review context",
    effect: 1.024972,
    tier: "a-lite",
    era: "sensitive",
  },
};
const HABIT_METRIC = "odds_ratio";
const HABIT_UNIT = "odds_ratio_per_standard_deviation";

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
function nonNegativeInteger(value: unknown): value is number {
  return finite(value) && Number.isInteger(value) && value >= 0;
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

export function packData(pack: FindingsPack | undefined): FindingsPack | null {
  return isFindingsPackV2(pack) || isFindingsPackV1(pack) ? pack : null;
}

function legacyPatchRange(pack: FindingsPackV1): PatchRange | null {
  const patches = pack.dataset.patches.filter((patch) => stringValue(patch));
  return patches.length > 0
    ? { min: patches[0], max: patches[patches.length - 1] }
    : null;
}

function legacyMetadata(
  pack: FindingsPackV1,
  key: string,
  tier: EvidenceTier,
  metric: string,
  unit: string,
  sample: number | null,
): EvidenceMetadata {
  const provenance = pack.provenance[key] ?? pack.provenance.findings;
  return {
    tier,
    releaseStatus: "available",
    metric,
    unit,
    sample: positiveInteger(sample) ? sample : null,
    patchRange: legacyPatchRange(pack),
    populationScope: `Historical v1 population evidence across ${pack.dataset.matches.toLocaleString("en-US")} matches.`,
    eraStability: "not_evaluated",
    caveats: ["Historical v1 evidence; its feature definition remains versioned and is not translated into v2."],
    sourceDocument: stringValue(provenance?.source_document),
    sourceSection: stringValue(provenance?.source_section),
    sourceRef: provenance
      ? `${provenance.source_document}#${provenance.source_section}`
      : null,
    releaseReason: null,
  };
}

export function packPatchLabel(pack: FindingsPack | undefined): string | null {
  const data = packData(pack);
  if (!data) return null;
  if (isFindingsPackV2(data)) {
    return `${data.patch_range.min}–${data.patch_range.max}`;
  }
  const range = legacyPatchRange(data);
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

type LegacyFinding = FindingsPackV1["findings"][number];

export function findFinding(
  pack: FindingsPack | undefined,
  key: string,
): PackV2Finding | LegacyFinding | null {
  const data = packData(pack);
  if (!data) return null;
  return isFindingsPackV2(data)
    ? findings(data).find((finding) => finding.key === key) ?? null
    : data.findings.find((finding) => finding.key === key) ?? null;
}

export interface FindingEvidence {
  key: string;
  title: string;
  statement: string;
  value: number | string | null;
  metadata: EvidenceMetadata;
}

function findingValue(item: LegacyFinding | PackV2Finding): number | string | null {
  return finite(item.value)
    ? item.value
    : typeof item.value === "string" && item.value.trim().length > 0
      ? item.value
      : null;
}

export function findingEvidence(pack: FindingsPack | undefined): FindingEvidence[] {
  const data = packData(pack);
  if (!data) return [];
  if (isFindingsPackV2(data)) {
    return findings(data)
      .map((item): FindingEvidence | null => {
        const metadata = readMetadata(item);
        const key = stringValue(item.key);
        const title = stringValue(item.title);
        const statement = stringValue(item.statement);
        if (!metadata || !key || !title || !statement) return null;
        return { key, title, statement, value: findingValue(item), metadata };
      })
      .filter((item): item is FindingEvidence => item !== null);
  }
  return data.findings
    .map((item): FindingEvidence | null => {
      const key = stringValue(item.key);
      const title = stringValue(item.title);
      const statement = stringValue(item.statement);
      if (!key || !title || !statement) return null;
      return {
        key,
        title,
        statement,
        value: findingValue(item),
        metadata: legacyMetadata(
          data,
          "findings",
          item.tier,
          item.unit ?? "value",
          item.unit ?? "value",
          data.dataset.player_games,
        ),
      };
    })
    .filter((item): item is FindingEvidence => item !== null);
}

export function masteryEvidence(pack: FindingsPack | undefined): MasteryEvidence | null {
  const data = packData(pack);
  if (!data) return null;
  if (isFindingsPackV1(data)) {
    const item = data.findings.find((finding) => finding.key === "mastery_premium");
    if (!item) return null;
    const value = finite(item.value) ? item.value : null;
    return {
      value,
      statement: stringValue(item.statement) ?? "The historical mastery result is available from the Findings Pack.",
      metadata: legacyMetadata(
        data,
        "findings",
        item.tier,
        item.unit ?? "value",
        item.unit ?? "value",
        data.dataset.player_games,
      ),
    };
  }
  const item = data.findings.find((finding) => finding.key === "mastery_premium");
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

export function banCorrelationEvidence(pack: FindingsPack | undefined): BanCorrelationEvidence | null {
  const data = packData(pack);
  if (!data) return null;
  if (isFindingsPackV1(data)) {
    const item = data.findings.find(
      (finding) => finding.key === "ban_waste_correlation" || finding.key === "ban_win_rate_correlation",
    );
    if (!item) return null;
    const value = finite(item.value) && item.value >= -1 && item.value <= 1 ? item.value : null;
    return {
      champion: null,
      value,
      statement: stringValue(item.statement) ?? "The historical pooled relationship is descriptive population context.",
      sample: data.dataset.player_games,
      metadata: legacyMetadata(
        data,
        "findings",
        item.tier,
        "correlation",
        item.unit ?? "correlation",
        data.dataset.player_games,
      ),
    };
  }
  const item = data.ban_context.find(
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
export interface HabitEvidenceView {
  key: string;
  label: string;
  expectedFeature: string;
  feature: string | null;
  metric: string | null;
  unit: string | null;
  tier: EvidenceTier | null;
  releaseStatus: EvidenceReleaseStatus | null;
  effect: number | null;
  sample: number | null;
  patchRange: PatchRange | null;
  populationScope: string | null;
  eraStability: EvidenceEraStability | null;
  caveats: string[];
  sourceDocument: string | null;
  sourceSection: string | null;
  sourceRef: string | null;
  provenanceKey: string | null;
  eligibility: string | null;
  releaseReason: string | null;
  contractIssue: string | null;
  strength: "weak" | null;
  reviewContextOnly: boolean;
}

function habitView(
  key: string,
  expected: (typeof HABIT_SPECS)[string],
  raw: AnyRecord | null,
  contractIssue: string | null = null,
): HabitEvidenceView {
  const status = readReleaseStatus(raw?.release_status);
  const effect = finite(raw?.effect) ? raw.effect : null;
  const feature = stringValue(raw?.feature);
  const metric = stringValue(raw?.metric_kind) ?? stringValue(raw?.metric);
  const unit = stringValue(raw?.unit);
  const tier = readTier(raw?.tier);
  const sample = nonNegativeInteger(raw?.sample) ? raw.sample : null;
  const patchRange = readPatchRange(raw?.patch_range);
  const eraStability = readEraStability(raw?.era_stability);
  const issue =
    contractIssue ??
    (raw !== null && (status === "available" || status === "approximate")
      ? "The habit row does not match the released contract."
      : raw !== null && status === null
        ? "The habit row metadata is malformed."
        : null);
  const releasedContract =
    (status === "available" || status === "approximate") &&
    raw?.label === expected.label &&
    feature === expected.feature &&
    metric === HABIT_METRIC &&
    unit === HABIT_UNIT &&
    tier === expected.tier &&
    eraStability === expected.era &&
    positiveInteger(sample) &&
    finite(effect) &&
    Math.abs(effect - expected.effect) < 1e-9 &&
    (key === "plates_by_14m" || !unsupportedHabitDetails(raw ?? {}));
  return {
    key,
    label: expected.label,
    expectedFeature: expected.feature,
    feature,
    metric,
    unit,
    tier,
    releaseStatus: status,
    effect: releasedContract ? effect : null,
    sample,
    patchRange,
    populationScope: stringValue(raw?.population_scope),
    eraStability,
    caveats: stringArray(raw?.caveats),
    sourceDocument: stringValue(raw?.source_document),
    sourceSection: stringValue(raw?.source_section),
    sourceRef: stringValue(raw?.source_ref),
    provenanceKey: stringValue(raw?.provenance_key),
    eligibility: stringValue(raw?.eligibility),
    releaseReason: stringValue(raw?.release_reason),
    contractIssue: issue,
    strength: raw?.strength === "weak" ? "weak" : null,
    reviewContextOnly: raw?.review_context_only === true,
  };
}

export function habitEvidenceReleased(
  row: Pick<HabitEvidenceView, "releaseStatus" | "effect" | "sample">,
): boolean {
  return (
    (row.releaseStatus === "available" || row.releaseStatus === "approximate") &&
    finite(row.effect) &&
    positiveInteger(row.sample)
  );
}

function unsupportedHabitDetails(row: AnyRecord): boolean {
  return [
    row.effect_interval,
    row.coefficient,
    row.p_value,
    row.significant,
    row.era_results,
  ].some((value) => value !== undefined && value !== null);
}

export function habitEvidence(pack: FindingsPackV2 | undefined): HabitEvidenceView[] {
  const data = packData(pack);
  if (!data || !isFindingsPackV2(data)) return [];

  const rowsByKey = new Map<string, AnyRecord[]>();
  const rawRows = Array.isArray(data.habits) ? data.habits : [];
  for (const item of rawRows) {
    const row = record(item);
    const key = stringValue(row?.key);
    if (!row || !key || !HABIT_SPECS[key]) continue;
    const rows = rowsByKey.get(key) ?? [];
    rows.push(row);
    rowsByKey.set(key, rows);
  }
  return Object.entries(HABIT_SPECS).map(([key, expected]) => {
    const rows = rowsByKey.get(key) ?? [];
    if (rows.length === 0) {
      return habitView(key, expected, null, "The habit row is missing from the active pack.");
    }
    const issue = rows.length > 1 ? "The habit row is duplicated." : null;
    return habitView(key, expected, rows[0], issue);
  });
}

export function habitFavorableDirection(row: Pick<HabitEvidenceView, "key" | "label">): string {
  if (row.key === "first_dragon_timing") {
    return "Earlier first-dragon timing is the favorable direction; the published association measures Later first-dragon timing";
  }
  if (row.key === "banked_gold_at_recall") {
    return "Lower banked gold at recall is the favorable direction; the published association measures more banked gold";
  }
  if (row.key === "plates_by_14m") {
    return "Diagnostic plate context only; not an actionable population lever";
  }
  return `${row.label} is the favorable direction`;
}

function normalizeTierRow(item: unknown): TierEvidenceRow | null {
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

function normalizeLegacyTierRow(
  pack: FindingsPackV1,
  item: FindingsPackV1["tier_list"][number],
): TierEvidenceRow | null {
  const champion = stringValue(item.champion);
  const role = stringValue(item.role);
  const rankBand = typeof item.tier === "string" && item.tier in RANK_BANDS
    ? (item.tier as TierEvidenceRow["rankBand"])
    : null;
  if (
    !champion ||
    !role ||
    !rankBand ||
    !positiveInteger(item.games) ||
    !probability(item.pick_rate) ||
    !probability(item.win_rate)
  ) {
    return null;
  }
  return {
    champion,
    role,
    games: item.games,
    pickRate: item.pick_rate,
    winRate: item.win_rate,
    rankBand,
    minimumGames: 0,
    metadata: legacyMetadata(pack, "tier_list", "diagnostic", "win_rate", "win_rate", item.games),
    legacy: true,
  };
}

export function tierEvidence(pack: FindingsPack | undefined, role?: string | null): TierEvidenceRow[] {
  const data = packData(pack);
  if (!data) return [];
  const rows = isFindingsPackV2(data)
    ? data.tier_list
        .map(normalizeTierRow)
        .filter((row): row is TierEvidenceRow => row !== null)
    : data.tier_list
        .map((row) => normalizeLegacyTierRow(data, row))
        .filter((row): row is TierEvidenceRow => row !== null);
  const seen = new Set<string>();
  return sortTierRows(
    rows.filter((row) => {
      const key = `${row.role}\u0000${row.champion}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return !role || row.role === role;
    }),
  );
}
export function legacyBenchmarkEvidence(pack: FindingsPack | undefined): LegacyBenchmarkEvidence[] {
  const data = packData(pack);
  if (!data || !isFindingsPackV1(data)) return [];
  return data.benchmarks
    .map((row): LegacyBenchmarkEvidence | null => {
      const role = stringValue(row.role) as RoleV1 | null;
      const values = {
        cs10Median: finite(row.cs10_median) ? row.cs10_median : null,
        level10Median: finite(row.level10_median) ? row.level10_median : null,
        goldDiff10Median: finite(row.gold_diff_10_median) ? row.gold_diff_10_median : null,
      };
      if (!role || !positiveInteger(row.sample) || Object.values(values).every((value) => value == null)) {
        return null;
      }
      return {
        role,
        ...values,
        sample: row.sample,
        metadata: legacyMetadata(data, "benchmarks", "diagnostic", "median", "historical_value", row.sample),
      };
    })
    .filter((row): row is LegacyBenchmarkEvidence => row !== null);
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

function normalizeLegacyMatchupRow(
  pack: FindingsPackV1,
  item: FindingsPackV1["matchup_examples"][number],
): MatchupEvidenceRow | null {
  const champion = stringValue(item.champion);
  const opponent = stringValue(item.opponent);
  const role = stringValue(item.role);
  const estimate = probability(item.wr) ? item.wr : null;
  const confidenceWidth = finite(item.ci) ? (item.ci > 1 ? item.ci / 100 : item.ci) : null;
  const games = positiveInteger(item.games) ? item.games : null;
  if (
    !champion ||
    !opponent ||
    champion === opponent ||
    !role ||
    estimate == null ||
    confidenceWidth == null ||
    confidenceWidth < 0 ||
    games == null
  ) {
    return null;
  }
  const interval = {
    lower: Math.max(0, estimate - confidenceWidth),
    upper: Math.min(1, estimate + confidenceWidth),
    includeLower: true,
    includeUpper: false,
  };
  return {
    champion,
    opponent,
    role,
    games,
    estimate,
    interval,
    metadata: legacyMetadata(pack, "matchup_examples", "diagnostic", "win_rate", "win_rate", games),
    legacy: true,
  };
}

export function matchupEvidence(
  pack: FindingsPack | undefined,
  role?: string | null,
  champion?: string | null,
): MatchupEvidenceRow[] {
  const data = packData(pack);
  if (!data) return [];
  const normalized: MatchupEvidenceRow[] = [];
  const seen = new Set<string>();
  const source = isFindingsPackV2(data)
    ? data.matchup_examples.map(normalizeMatchupRow)
    : data.matchup_examples.map((row) => normalizeLegacyMatchupRow(data, row));
  for (const row of source) {
    if (!row || (role && row.role !== role) || (champion && row.champion !== champion)) continue;
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
  if (!data || !isFindingsPackV2(data)) return [];
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
  if (!data || !isFindingsPackV2(data)) return null;
  const raw = data.build_evidence as PackV2BuildEvidence | undefined;
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
