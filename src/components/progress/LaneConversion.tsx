import { EvidenceMeta, evidenceUsable, type FindingEvidence } from "../populationEvidence";
import { SectionHead } from "../ui";

export function LaneConversion({ finding }: { finding: FindingEvidence }) {
  if (!evidenceUsable(finding.metadata)) return null;
  return (
    <div
      className="card3"
      data-testid="lane-conversion"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead
        level={3}
        label={finding.title}
        color="var(--color-info)"
        right={
          <span className="pill" style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}>
            Population context
          </span>
        }
      />
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        {finding.statement}
      </p>
      <EvidenceMeta metadata={finding.metadata} testId="lane-conversion-evidence-meta" />
    </div>
  );
}
