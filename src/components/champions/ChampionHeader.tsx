import type { TierEvidenceRow } from "../populationEvidence";
import { EvidenceMeta } from "../populationEvidence";
import { formatCount, formatInitials, formatRate } from "../format";

export function titleCase(role: string): string {
  return role.charAt(0).toUpperCase() + role.slice(1).toLowerCase();
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 8, borderRadius: 12, background: "rgba(10,11,22,.5)", textAlign: "center" }}>
      <div className="mono-n" style={{ font: "700 15px var(--font-mono)", color: "var(--color-info)" }}>
        {value}
      </div>
      <div style={{ fontSize: 8, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>{label}</div>
    </div>
  );
}

export function ChampionHeader({ entry }: { entry: TierEvidenceRow }) {
  return (
    <div
      className="card3b"
      data-testid="champion-header"
      style={{ padding: 15, background: "linear-gradient(165deg,#2b2650,var(--color-surface-2) 65%)", boxShadow: "var(--shadow-z2)" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
        <div
          aria-hidden="true"
          style={{ width: 60, height: 60, borderRadius: 19, background: "linear-gradient(150deg,var(--color-accent),#4b4180)", display: "grid", placeItems: "center", font: "700 17px var(--font-mono)", color: "var(--color-bg)", boxShadow: "var(--shadow-z2)", flex: "none" }}
        >
          {formatInitials(entry.champion)}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ font: "700 21px var(--font-mono)", letterSpacing: "-.02em" }}>{entry.champion}</span>
            <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-info)" }}>
              {entry.rankBand} rank band
            </span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--color-dim)", marginTop: 2 }}>
            {titleCase(entry.role)} · {formatCount(entry.games, "games")} logged
          </div>
        </div>
      </div>
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <StatCell label="ROLE PICK" value={formatRate(entry.pickRate)} />
        <StatCell label="OBSERVED WIN" value={formatRate(entry.winRate)} />
      </div>
      <EvidenceMeta metadata={entry.metadata} testId="champion-evidence-meta">
        <div>Rank bands are pooled, within-role scouting context.</div>
      </EvidenceMeta>
    </div>
  );
}
