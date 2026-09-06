import type { FindingsPackV2 } from "../../api/pack-v2";
import { buildEvidence, EvidenceMeta } from "../populationEvidence";
import { SectionHead, Unavailable } from "../ui";

export function BuildOrderCard({ pack }: { pack: FindingsPackV2 | undefined }) {
  const evidence = buildEvidence(pack);
  return (
    <div
      className="card3"
      data-testid="build-order-card"
      style={{
        padding: 13,
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <SectionHead label="BUILD ORDER · BETA-BINOMIAL SHRUNK" />
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        <Unavailable reason={evidence?.statement ?? "controlled build evidence unavailable"} />
      </p>
      {evidence && <EvidenceMeta metadata={evidence.metadata} testId="build-order-evidence-meta" />}
    </div>
  );
}
