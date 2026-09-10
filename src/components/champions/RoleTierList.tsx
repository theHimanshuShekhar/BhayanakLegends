import type { CSSProperties } from "react";
import {
  EvidenceMeta,
  sortTierRows,
} from "../populationEvidence";
import type { TierEvidenceRow } from "../populationEvidence";
import { formatRate } from "../format";
import { SectionHead } from "../ui";

export { sortTierRows };

// Tier rank is Findings Pack population evidence: blue, not teal.
const TIER_PILL: Record<TierEvidenceRow["rankBand"], CSSProperties> = {
  S: { background: "var(--color-info-low)", color: "var(--color-info)" },
  A: { background: "var(--color-info-low)", color: "var(--color-info)" },
  B: { background: "var(--color-amber-low)", color: "var(--color-amber)" },
  C: { background: "var(--color-surface-3)", color: "var(--color-dim)" },
};

export function RoleTierList({
  role,
  rows,
  selectedChampion,
  onSelect,
}: {
  role: string;
  rows: TierEvidenceRow[];
  selectedChampion: string | null;
  onSelect: (champion: string) => void;
}) {
  const first = rows[0] ?? null;
  const legacy = first?.legacy === true;
  return (
    <section className="card3" data-testid="tier-list-card" aria-labelledby="tier-list-heading" style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionHead label={<span id="tier-list-heading">ROLE TIERS · {role}</span>} color="var(--color-info)" />
      <div data-testid="tier-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {rows.map((row) => {
          const selected = row.champion === selectedChampion;
          return (
            <button
              key={`${row.champion}-${row.role}`}
              type="button"
              data-testid={`tier-row-${row.champion}`}
              aria-pressed={selected}
              aria-label={`${row.champion}, ${row.rankBand} tier, ${role}`}
              onClick={() => onSelect(row.champion)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                width: "100%",
                border: 0,
                borderRadius: 5,
                textAlign: "left",
                cursor: "pointer",
                color: "inherit",
                background: selected ? "var(--color-surface-3)" : "transparent",
              }}
            >
              <span className="pill" style={{ ...TIER_PILL[row.rankBand], width: 20, justifyContent: "center", padding: "3px 0", fontSize: 10 }}>
                {row.rankBand}
              </span>
              <span style={{ flex: 1, fontSize: 10.5 }}>{row.champion}</span>
              <span className="mono-n" style={{ fontSize: 9.5, color: "var(--color-info)" }}>
                {formatRate(row.winRate)}
              </span>
            </button>
          );
        })}
        {rows.length === 0 && (
          <div data-testid="tier-list-unavailable" role="status" style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>
            {legacy ? "Unavailable: no historical champion-role rows are available." : "Unavailable: no qualifying champion-role rows meet the 500-game floor."}
          </div>
        )}
      </div>
      {first && (
        <EvidenceMeta metadata={first.metadata} testId="tier-list-evidence-meta">
          <div>{legacy ? "Historical v1 rank-band evidence; source rows retain their original role and pick-rate definitions." : `S/A/B/C are within-role rank bands; rows qualify at ${first.minimumGames.toLocaleString("en-US")} games.`}</div>
        </EvidenceMeta>
      )}
      <p style={{ margin: 0, fontSize: 9, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        {legacy
          ? "Historical v1 pooled scouting context; this does not identify a best pick or describe a current patch."
          : "Diagnostic pooled scouting context; this does not identify a best pick or describe a current patch."}
      </p>
    </section>
  );
}
