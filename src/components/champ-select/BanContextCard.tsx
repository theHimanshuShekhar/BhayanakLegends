import type { FindingsPack } from "../../api/pack-v2";
import {
  EvidenceMeta,
  banCorrelationEvidence,
  evidenceUsable,
} from "../populationEvidence";
import { formatCorrelation } from "../format";
import { SectionHead } from "../ui";
import { isFindingsPackV1 } from "../../api/pack-v1";

export function BanContextCard({ pack }: { pack: FindingsPack | undefined }) {
  const legacy = isFindingsPackV1(pack);
  const evidence = banCorrelationEvidence(pack);
  const unavailable = !evidence
    ? "Unavailable: pooled ban-rate/win-rate correlation evidence is missing or malformed."
    : evidence.metadata.releaseStatus === "withheld"
      ? `Unavailable: ban correlation evidence is withheld${evidence.metadata.releaseReason ? ` — ${evidence.metadata.releaseReason}` : "."}`
      : evidence.metadata.releaseStatus === "superseded"
        ? `Unavailable: ban correlation evidence is superseded${evidence.metadata.releaseReason ? ` — ${evidence.metadata.releaseReason}` : "."}`
        : !evidenceUsable(evidence.metadata)
          ? "Unavailable: ban correlation evidence is not released for this pack."
          : null;

  return (
    <div className="card3" data-testid="card-ban-context" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionHead label={legacy ? "BAN CONTEXT · HISTORICAL POPULATION EVIDENCE" : "BAN CONTEXT · DIAGNOSTIC POPULATION EVIDENCE"} color="var(--color-info)" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono-n" data-testid="ban-correlation" style={{ font: "700 22px var(--font-mono)", color: "var(--color-info)" }}>
          {evidence?.value == null ? "—" : `r=${formatCorrelation(evidence.value)}`}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>pooled ban rate ↔ win rate</span>
      </div>
      <p role="status" style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "var(--color-soft-text)" }}>
        {unavailable ?? "The pooled relationship is descriptive Diagnostic context, not a deterministic ban signal."}
      </p>
      {evidence && <EvidenceMeta metadata={evidence.metadata} testId="ban-evidence-meta" />}
    </div>
  );
}
