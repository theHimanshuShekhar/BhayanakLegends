import type { AssignedRole } from "../../api/types";
import type { FindingsPackV2 } from "../../api/pack-v2";
import { EvidenceMeta, packPatchLabel, tierEvidence } from "../populationEvidence";
import { formatCount, formatRate } from "../format";
import { SectionHead } from "../ui";
import type { FindingsPackState } from "./shared";
import { CS_ROLES } from "./shared";

export function PopulationRoleTiers({
  pack,
  role,
  packState,
  locked = false,
}: {
  pack: FindingsPackV2 | undefined;
  role: AssignedRole | null;
  packState: FindingsPackState;
  locked?: boolean;
}) {
  if (locked) return null;

  const validRole = role && CS_ROLES.includes(role) ? role : null;
  const rows = tierEvidence(pack, validRole);
  const first = rows[0] ?? null;
  const unavailable = packState === "loading"
    ? "Loading… Findings Pack role-tier evidence."
    : packState === "error"
      ? "Unavailable: Findings Pack role-tier evidence could not be loaded."
      : packState === "missing"
        ? "Unavailable: Findings Pack role-tier evidence is missing."
        : !validRole
          ? "Unavailable: assigned role is unavailable; population tiers are withheld."
          : rows.length === 0
            ? `Unavailable: no qualifying ${validRole} population rows meet the 500-game floor.`
            : null;

  return (
    <section className="card3" data-testid="card-role-tiers" aria-labelledby="cs-role-tiers-heading" style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionHead label={<span id="cs-role-tiers-heading">POPULATION ROLE TIERS · PRE-LOCK</span>} color="var(--color-info)" right={validRole ? <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-info)" }}>{validRole}</span> : undefined} />
      <p data-testid="role-tiers-caption" style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        {unavailable ?? "Diagnostic scouting context: S/A/B/C are within-role rank bands from a pooled population, not a recommendation or a statement about your history."}
      </p>
      {unavailable ? (
        <div data-testid="role-tiers-unavailable" role="status" style={{ padding: 13, borderRadius: 12, background: "var(--color-deep)", color: "var(--color-dim)", fontSize: 10.5 }}>
          {unavailable}
        </div>
      ) : (
        <>
          <div data-testid="role-tier-rows" style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 7 }}>
            {rows.slice(0, 6).map((row) => (
              <div key={`${row.role}-${row.champion}`} data-testid={`role-tier-row-${row.champion}`} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 9px", borderRadius: 11, background: "var(--color-surface-3)" }}>
                <span className="pill" style={{ width: 20, justifyContent: "center", padding: "3px 0", background: row.rankBand === "S" || row.rankBand === "A" ? "var(--color-info-low)" : "var(--color-surface-2)", color: row.rankBand === "S" || row.rankBand === "A" ? "var(--color-info)" : "var(--color-dim)" }}>{row.rankBand}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ font: "600 11px var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.champion}</div>
                  <div style={{ fontSize: 8.5, color: "var(--color-dimmer)" }}>{formatCount(row.games, "games")} · {formatRate(row.pickRate)} role pick</div>
                </div>
                <span className="mono-n" style={{ fontSize: 9.5, color: "var(--color-info)" }}>{formatRate(row.winRate)}</span>
              </div>
            ))}
          </div>
          {first && (
            <EvidenceMeta metadata={first.metadata} testId="role-tiers-evidence-meta">
              <div>Qualification floor: {first.minimumGames.toLocaleString("en-US")} games per champion-role row.</div>
            </EvidenceMeta>
          )}
        </>
      )}
      <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
        Pooled patch scope: {packPatchLabel(pack) ?? "unavailable"}; rows below the 500-game floor stay out of v2.
      </div>
    </section>
  );
}
