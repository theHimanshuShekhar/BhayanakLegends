import type { FindingsPackV2 } from "../../api/pack-v2";
import {
  EvidenceMeta,
  evidenceUsable,
  masteryEvidence,
} from "../populationEvidence";
import type { FindingsPackState } from "./shared";
import { SectionHead } from "../ui";

function unavailableReason(pack: FindingsPackV2 | undefined, packState: FindingsPackState): string | null {
  if (packState === "loading") return "Loading… Findings Pack mastery evidence.";
  if (packState === "error") return "Unavailable: Findings Pack mastery evidence could not be loaded.";
  if (packState === "missing") return "Unavailable: Findings Pack mastery evidence is missing.";
  const evidence = masteryEvidence(pack);
  if (!evidence) return "Unavailable: mastery evidence is malformed or incompatible with this app.";
  if (evidence.metadata.releaseStatus === "withheld") {
    return `Unavailable: mastery evidence is withheld${evidence.metadata.releaseReason ? ` — ${evidence.metadata.releaseReason}` : "."}`;
  }
  if (evidence.metadata.releaseStatus === "superseded") {
    return `Unavailable: mastery evidence is superseded${evidence.metadata.releaseReason ? ` — ${evidence.metadata.releaseReason}` : "."}`;
  }
  if (!evidenceUsable(evidence.metadata) || evidence.value == null) {
    return "Unavailable: mastery evidence is not released for this pack.";
  }
  return null;
}

// Mastery is population evidence. This card deliberately keeps it separate
// from Personal History and names the observational caveat supplied by v2.
export function MasteryCard({
  pack,
  packState,
}: {
  pack: FindingsPackV2 | undefined;
  packState: FindingsPackState;
}) {
  const evidence = masteryEvidence(pack);
  const unavailable = unavailableReason(pack, packState);
  const valueLabel = evidence?.value == null
    ? "—"
    : `${evidence.value >= 0 ? "+" : ""}${evidence.value.toFixed(2)} pp`;

  return (
    <div className="card3" data-testid="card-mastery" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionHead label="MASTERY · ACTIONABLE POPULATION EVIDENCE" color="var(--color-info)" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono-n" data-testid="mastery-premium" style={{ font: "700 22px var(--font-mono)", color: "var(--color-info)" }}>
          {valueLabel}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>top-three familiarity premium</span>
      </div>
      <p role="status" style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "var(--color-soft-text)" }}>
        {unavailable ?? evidence?.statement}
      </p>
      {evidence && (
        <EvidenceMeta metadata={evidence.metadata} testId="mastery-evidence-meta">
          <div>Same-direction era result: {evidence.metadata.eraStability ?? "not evaluated"}.</div>
        </EvidenceMeta>
      )}
    </div>
  );
}
