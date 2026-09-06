import type { PackV2Finding } from "../../api/pack-v2";
import { SectionHead } from "../ui";

export function LaneConversion({ finding }: { finding: PackV2Finding }) {
  if (finding.release_status !== "available" && finding.release_status !== "approximate") return null;
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
      <p style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}>
        {finding.caveats[0]} · {finding.sample.toLocaleString("en-US")} population exposures
      </p>
    </div>
  );
}
