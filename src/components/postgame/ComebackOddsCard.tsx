import type { FindingsPack, PostGameDigest } from "../../api/types";
import { pct } from "../ui";
import { PanelHeading, Subheading, UnavailableValue } from "./bits";

/**
 * Domain-aware Findings Pack population lookup over the contracted comeback
 * anchors (-2,000g / -5,000g / -7,000g). A rate appears only when the Personal
 * History gold@15 is finite, negative, inside the supported domain, and the
 * pack declares the canonical gold_diff_15 input under loltrends-parity-v1.
 * Internal boundaries are arithmetic midpoints between adjacent anchors; an
 * exact midpoint belongs to the more severe (lower-rate) bucket so the UI
 * never overstates the population win rate. Outer anchors are inclusive.
 */

export type SuppressionReason =
  | "missing-personal-history"
  | "not-a-deficit"
  | "outside-domain"
  | "missing-pack"
  | "incompatible-declaration"
  | "malformed-table";

export type BucketMatch = {
  winRate: number;
  rangeLabel: string;
};

const CANONICAL_FEATURE = "gold_diff_15";
const CANONICAL_VERSION = "loltrends-parity-v1";

const SUPPRESSION_COPY: Record<SuppressionReason, string> = {
  "missing-personal-history":
    "No Personal History gold@15 checkpoint for this game, so no Findings Pack comparison is possible.",
  "not-a-deficit":
    "This game was not in a deficit cohort at 15 minutes, so no Findings Pack comeback rate applies.",
  "outside-domain":
    "The observed deficit is outside the Findings Pack's supported population domain, so no rate is shown.",
  "missing-pack": "Findings Pack population data is unavailable.",
  "incompatible-declaration":
    "The Findings Pack does not declare the canonical gold_diff_15 input for this comparison.",
  "malformed-table": "The Findings Pack comeback table failed validation.",
};

function declarationMatches(pack: FindingsPack | undefined): boolean {
  const declaration = pack?.comeback_feature_contract;
  return (
    !!declaration &&
    declaration.feature === CANONICAL_FEATURE &&
    declaration.feature_contract_version === CANONICAL_VERSION
  );
}

function tableIsMalformed(
  anchors: { gold_deficit_at_15: number; win_rate: number }[],
): boolean {
  if (anchors.length === 0) return true;
  const magnitudes = anchors.map((row) => row.gold_deficit_at_15);
  if (magnitudes.some((value) => !Number.isFinite(value) || value >= 0)) return true;
  if (anchors.some((row) => !Number.isFinite(row.win_rate))) return true;
  return new Set(magnitudes).size !== magnitudes.length;
}

/**
 * Returns a bucket only for finite negative deficits inside the shipped
 * domain; otherwise names why the rate is suppressed.
 */
export function matchComebackBucket(
  pack: FindingsPack | undefined,
  digest: PostGameDigest | null,
): { match: BucketMatch; reason: null } | { match: null; reason: SuppressionReason } {
  if (!digest || digest.checkpoints.gold_diff_15 == null) {
    return { match: null, reason: "missing-personal-history" };
  }
  const gold15 = digest.checkpoints.gold_diff_15;
  if (!pack) {
    return { match: null, reason: "missing-pack" };
  }
  if (!declarationMatches(pack)) {
    return { match: null, reason: "incompatible-declaration" };
  }
  // Mildest first: -2000 before -5000 before -7000.
  const anchors = [...(pack.comeback_odds ?? [])].sort(
    (a, b) => b.gold_deficit_at_15 - a.gold_deficit_at_15,
  );
  if (tableIsMalformed(anchors)) {
    return { match: null, reason: "malformed-table" };
  }
  if (!Number.isFinite(gold15) || gold15 >= 0) {
    return { match: null, reason: "not-a-deficit" };
  }
  const deficit = -gold15;
  const magnitudes = anchors.map((row) => -row.gold_deficit_at_15);
  // Bucket i spans from the lower boundary to the upper boundary where the
  // lower boundary of bucket 0 is the mildest anchor, internal boundaries are
  // midpoints between adjacent anchors, and the last bucket closes at the
  // most severe anchor. Midpoints therefore belong to the more severe side.
  for (let index = 0; index < magnitudes.length; index += 1) {
    const low =
      index === 0 ? magnitudes[0] : (magnitudes[index - 1] + magnitudes[index]) / 2;
    const isLast = index === magnitudes.length - 1;
    const high = isLast ? magnitudes[index] : (magnitudes[index] + magnitudes[index + 1]) / 2;
    const inBucket = deficit >= low && (isLast ? deficit <= high : deficit < high);
    if (inBucket) {
      return {
        match: {
          winRate: anchors[index].win_rate,
          rangeLabel: `[${fmtGold(low)}g, ${fmtGold(high)}g${isLast ? "]" : ")"}`,
        },
        reason: null,
      };
    }
  }
  return { match: null, reason: "outside-domain" };
}

function fmtGold(value: number): string {
  return Math.abs(value).toLocaleString("en-US");
}

/**
 * Population-bucket comeback read: describes what Findings Pack teams at a
 * deficit range do, never what the observed game did (ADR-0003 diagnostic).
 */
export function ComebackOddsCard({
  digest,
  pack,
}: {
  digest: PostGameDigest | null;
  pack: FindingsPack | undefined;
}) {
  const result = matchComebackBucket(pack, digest);
  const gold15 = digest?.checkpoints.gold_diff_15 ?? null;
  return (
    <section
      className="card3b"
      data-testid="comeback-odds"
      aria-labelledby="postgame-comeback-heading"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <PanelHeading color="var(--color-info)">
        <span id="postgame-comeback-heading">Comeback odds</span>
      </PanelHeading>
      <Subheading>Findings Pack population bucket</Subheading>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span
          className="mono-n"
          data-testid="comeback-value"
          style={{
            font: "700 22px var(--font-mono)",
            color: result.match ? "var(--color-danger)" : "var(--color-dimmer)",
          }}
        >
          {result.match ? pct(result.match.winRate) : <UnavailableValue />}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }} data-testid="comeback-range">
          {result.match ? result.match.rangeLabel : "—"}
        </span>
      </div>
      <p
        data-testid="comeback-note"
        style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "#cfd3e5" }}
      >
        {result.match
          ? `Teams in ${result.match.rangeLabel} down 3,500g+ at 15 won about ${pct(result.match.winRate)} of the time — Findings Pack population bucket.`
          : SUPPRESSION_COPY[result.reason]}
      </p>
      {result.match && gold15 != null && (
        <p
          data-testid="personal-checkpoint-note"
          style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dimmer)" }}
        >
          Your game was down {Math.abs(gold15).toLocaleString("en-US")}g at 15 — Personal
          History, shown separately above.
        </p>
      )}
    </section>
  );
}
