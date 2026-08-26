import type { PackFinding } from "../../api/types";
import { SectionHead } from "../ui";

export function LaneConversion({ finding }: { finding: PackFinding }) {
  return (
    <div
      className="card3"
      data-testid="lane-conversion"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead
        level={3}
        label="LEADS ARE RAW MATERIAL"
        color="var(--color-info)"
        right={
          <span className="pill" style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}>
            Lane conversion
          </span>
        }
      />
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        {finding.statement}
      </p>
    </div>
  );
}
