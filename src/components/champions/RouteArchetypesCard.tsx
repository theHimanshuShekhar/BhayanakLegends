import type { FindingsPackV2 } from "../../api/pack-v2";
import { EvidenceMeta, routeArchetypeEvidence } from "../populationEvidence";
import { SectionHead, Unavailable } from "../ui";

export function RouteArchetypesCard({ pack }: { pack: FindingsPackV2 | undefined }) {
  const rows = routeArchetypeEvidence(pack);
  return (
    <section
      className="card3b"
      data-testid="route-archetypes-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead label="ROUTE ARCHETYPES · DESCRIPTIVE" color="var(--color-info)" />
      {rows.length === 0 ? (
        <div style={{ padding: "10px 9px", borderRadius: 12, background: "var(--color-surface-3)", fontSize: 10, lineHeight: 1.45, color: "var(--color-dim)" }}>
          <Unavailable reason="approximate route evidence unavailable" />
        </div>
      ) : (
        <ul aria-label="Approximate route archetype evidence" style={{ display: "flex", flexDirection: "column", gap: 7, listStyle: "none", margin: 0, padding: 0 }}>
          {rows.map((row) => (
            <li key={row.archetype} data-testid={`route-archetype-${row.archetype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} style={{ padding: "8px 9px", borderRadius: 12, background: "var(--color-surface-3)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <strong style={{ flex: 1, font: "600 10.5px var(--font-mono)" }}>{row.archetype}</strong>
                <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-soft-blue)", fontSize: 8, padding: "2px 7px" }}>{row.observedOutcome}</span>
              </div>
              <div style={{ marginTop: 4, fontSize: 8.5, color: "var(--color-dimmer)" }}>
                {row.side ?? "side context unavailable"} · {row.champion ?? "champion context unavailable"} · {row.sample.toLocaleString("en-US")} observations · {row.coordinateValidation}
              </div>
              <EvidenceMeta metadata={row.metadata} testId={`route-evidence-${row.archetype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`} />
            </li>
          ))}
        </ul>
      )}
      <p style={{ margin: 0, fontSize: 9, lineHeight: 1.45, color: "var(--color-dimmer)" }}>
        Approximate route context is descriptive only; it does not rank builds or prescribe a route.
      </p>
    </section>
  );
}
