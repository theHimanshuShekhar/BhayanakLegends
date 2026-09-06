import type { PostGameDigest } from "../../api/types";
import type { FindingsPackV2, PackV2ComebackBand } from "../../api/pack-v2";
import { isFindingsPackV2 } from "../../api/pack-v2";
import { formatRate } from "../format";
import { SectionHead, Unavailable } from "../ui";

type Eligibility = "eligible" | "ineligible" | "unknown";

export type SuppressionReason =
  | "missing-personal-history"
  | "invalid-input"
  | "ineligible-observation"
  | "not-a-deficit"
  | "outside-domain"
  | "missing-pack"
  | "incompatible-declaration"
  | "malformed-table"
  | "withheld";

export type BucketMatch = {
  winRate: number;
  rangeLabel: string;
};

const CANONICAL_FEATURE = "team_gold_diff_15m";
const CANONICAL_VERSION = "loltrends-parity-v2";
const CHECKPOINT_SECONDS = 900;
const EXPECTED_BOUNDS = [
  { lower: 2000, upper: 3000 },
  { lower: 3000, upper: 5000 },
  { lower: 5000, upper: null },
] as const;

const SUPPRESSION_COPY: Record<SuppressionReason, string> = {
  "missing-personal-history":
    "No v2 Personal History team state is available at 15 minutes, so no Findings Pack comparison is possible.",
  "invalid-input": "The v2 team-gold checkpoint is invalid, so no Findings Pack comparison is shown.",
  "ineligible-observation":
    "This match is not a played-out eligible observation, so no comeback floor applies.",
  "not-a-deficit":
    "Your team was not in a gold deficit at 15 minutes; the personal checkpoint cannot substitute for a team-state cohort.",
  "outside-domain":
    "The team deficit is below the Findings Pack's minimum 2,000g cohort, so no rate is shown.",
  "missing-pack": "Findings Pack population data is unavailable.",
  "incompatible-declaration":
    "The active pack does not declare the v2 team-state contract for this comparison.",
  "malformed-table": "The Findings Pack comeback bands failed validation.",
  withheld: "The matching Findings Pack comeback band is withheld because exact team-state exposures are unavailable.",
};

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function v2DigestFields(digest: PostGameDigest | null): {
  eligibility: Eligibility | null;
  teamGoldDiff: number | null;
  teamGoldPresent: boolean;
  observedThrough: number | null;
  nonSurrendered: boolean | null;
  contractVersion: string | null;
  teamStateContractValid: boolean;
} {
  const value = digest;
  const features = asRecord(value?.features);
  const teamState = asRecord(value?.team_state);
  const eligibility =
    value?.personal_history_eligibility === "eligible" ||
    value?.personal_history_eligibility === "ineligible" ||
    value?.personal_history_eligibility === "unknown"
      ? value.personal_history_eligibility
      : null;
  const featureValue = features?.[CANONICAL_FEATURE];
  const teamStateValue = teamState?.[CANONICAL_FEATURE];
  const rawTeamGold = featureValue !== undefined ? featureValue : teamStateValue;
  const teamStateContractValid =
    teamState?.feature === CANONICAL_FEATURE &&
    teamState?.feature_contract_version === CANONICAL_VERSION;
  return {
    eligibility,
    teamGoldDiff: finite(rawTeamGold) ? rawTeamGold : null,
    teamGoldPresent: rawTeamGold !== undefined && rawTeamGold !== null,
    observedThrough: finite(teamState?.observed_through_s) ? teamState.observed_through_s : null,
    nonSurrendered: typeof teamState?.non_surrendered === "boolean" ? teamState.non_surrendered : null,
    contractVersion:
      value?.feature_contract_version === CANONICAL_VERSION
        ? value.feature_contract_version
        : null,
    teamStateContractValid,
  };
}

function rangeLabel(lowerBound: number, upperBound: number | null): string {
  return upperBound == null
    ? `[${lowerBound.toLocaleString("en-US")}g, ∞)`
    : `[${lowerBound.toLocaleString("en-US")}g, ${upperBound.toLocaleString("en-US")}g)`;
}

function validBand(row: PackV2ComebackBand, index: number): boolean {
  const expected = EXPECTED_BOUNDS[index];
  if (!expected) return false;
  const available = row.release_status === "available" || row.release_status === "approximate";
  const withheld = row.release_status === "withheld" || row.release_status === "superseded";
  const valueValid = available
    ? finite(row.rate) && row.rate >= 0 && row.rate <= 1 && row.sample > 0
    : withheld && row.rate === null && row.sample === 0;
  return (
    row.feature === CANONICAL_FEATURE &&
    row.feature_contract_version === CANONICAL_VERSION &&
    row.checkpoint_seconds === CHECKPOINT_SECONDS &&
    row.unit === "gold" &&
    row.lower_bound === expected.lower &&
    row.upper_bound === expected.upper &&
    row.include_lower === true &&
    row.include_upper === false &&
    row.tier === "diagnostic" &&
    typeof row.population_scope === "string" &&
    row.population_scope.trim().length > 0 &&
    Array.isArray(row.caveats) &&
    row.caveats.length > 0 &&
    row.caveats.every((caveat) => typeof caveat === "string" && caveat.trim().length > 0) &&
    typeof row.source_document === "string" &&
    row.source_document.trim().length > 0 &&
    typeof row.source_section === "string" &&
    row.source_section.trim().length > 0 &&
    typeof row.source_ref === "string" &&
    row.source_ref.trim().length > 0 &&
    typeof row.provenance_key === "string" &&
    row.provenance_key.trim().length > 0 &&
    valueValid
  );
}

function parseBands(pack: FindingsPackV2 | undefined): PackV2ComebackBand[] | null {
  if (!isFindingsPackV2(pack) || !Array.isArray(pack.comeback_odds)) return null;
  if (pack.comeback_odds.length !== EXPECTED_BOUNDS.length) return null;
  return pack.comeback_odds.every(validBand) ? pack.comeback_odds : null;
}

/** Match only the declared v2 team-deficit interval; no personal-gold fallback or extrapolation. */
export function matchComebackBucket(
  pack: FindingsPackV2 | undefined,
  digest: PostGameDigest | null,
): { match: BucketMatch; reason: null } | { match: null; reason: SuppressionReason } {
  if (!digest) return { match: null, reason: "missing-personal-history" };
  const fields = v2DigestFields(digest);
  if (!fields.contractVersion || !fields.teamStateContractValid || !fields.teamGoldPresent) {
    return { match: null, reason: "missing-personal-history" };
  }
  if (!finite(fields.teamGoldDiff)) return { match: null, reason: "invalid-input" };
  if (
    fields.eligibility !== "eligible" ||
    fields.nonSurrendered !== true ||
    fields.observedThrough == null ||
    fields.observedThrough < CHECKPOINT_SECONDS
  ) {
    return { match: null, reason: "ineligible-observation" };
  }
  if (!pack) return { match: null, reason: "missing-pack" };
  const bands = parseBands(pack);
  if (!bands) return { match: null, reason: "malformed-table" };
  const deficit = -fields.teamGoldDiff;
  if (deficit <= 0) return { match: null, reason: "not-a-deficit" };
  if (deficit < EXPECTED_BOUNDS[0].lower) return { match: null, reason: "outside-domain" };
  const band = bands.find(
    (candidate) =>
      deficit >= candidate.lower_bound &&
      (candidate.upper_bound == null || deficit < candidate.upper_bound),
  );
  if (!band) return { match: null, reason: "outside-domain" };
  if (band.release_status !== "available" && band.release_status !== "approximate") {
    return { match: null, reason: "withheld" };
  }
  if (!finite(band.rate)) return { match: null, reason: "withheld" };
  return {
    match: {
      winRate: band.rate,
      rangeLabel: rangeLabel(band.lower_bound, band.upper_bound),
    },
    reason: null,
  };
}

/** The rate describes eligible played-out population states, not a personal prediction. */
export function ComebackOddsCard({
  digest,
  pack,
}: {
  digest: PostGameDigest | null;
  pack: FindingsPackV2 | undefined;
}) {
  const result = matchComebackBucket(pack, digest);
  const fields = v2DigestFields(digest);
  const unavailableReason = result.reason === "withheld" ? "population band withheld" : "no supported population band";
  return (
    <section
      className="card3b"
      data-testid="comeback-card"
      aria-labelledby="postgame-comeback-heading"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead color="var(--color-soft-blue)" label={<span id="postgame-comeback-heading">Comeback floor</span>} />
      <SectionHead level={3} dot={false} label="Findings Pack population band" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span
          className="mono-n"
          data-testid="comeback-value"
          style={{ font: "700 22px var(--font-mono)", color: result.match ? "var(--color-soft-blue)" : "var(--color-dimmer)" }}
        >
          {result.match ? formatRate(result.match.winRate) : <Unavailable reason={unavailableReason} />}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }} data-testid="comeback-range">
          {result.match ? result.match.rangeLabel : ""}
        </span>
      </div>
      <p
        data-testid="comeback-note"
        role="status"
        style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-soft-text)" }}
      >
        {result.match
          ? `Eligible, played-out team states in ${result.match.rangeLabel} down at 15 minutes won about ${formatRate(result.match.winRate)} of the time. This is population context, not a personal prediction.`
          : SUPPRESSION_COPY[result.reason]}
      </p>
      {result.match && fields.teamGoldDiff != null && (
        <p
          data-testid="personal-checkpoint-note"
          style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dimmer)" }}
        >
          Your team state was {Math.abs(Math.round(fields.teamGoldDiff)).toLocaleString("en-US")}g down at
          15 minutes · Personal History team feature.
        </p>
      )}
    </section>
  );
}
