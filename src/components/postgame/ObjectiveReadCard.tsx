import type { FindingsPackV2, PackV2Objective } from "../../api/pack-v2";
import { formatRate } from "../format";
import { SectionHead, Unavailable } from "../ui";
import {
  OBJECTIVE_ORDER,
  isObjectiveRenderable,
  objectiveCaveat,
  objectiveLabel,
  objectiveMetricLabel,
  objectiveRows,
  objectiveWindowLabel,
} from "../objectiveEvidence";

export function ObjectiveReadCard({ pack }: { pack: FindingsPackV2 | undefined }) {
  const rows: PackV2Objective[] = objectiveRows(pack);
  return (
    <section
      className="card3"
      data-testid="objective-read"
      aria-labelledby="postgame-objectives-heading"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead color="var(--color-soft-blue)" label={<span id="postgame-objectives-heading">Objectives</span>} />
      <SectionHead level={3} dot={false} label="Typed population reads" />
      <ul
        aria-label="Objective reads"
        style={{ display: "flex", flexDirection: "column", gap: 8, listStyle: "none", margin: 0, padding: 0 }}
      >
        {OBJECTIVE_ORDER.map((objective) => {
          const row = rows.find((candidate) => candidate.objective === objective);
          const available = row != null && isObjectiveRenderable(row);
          return (
            <li
              key={objective}
              data-testid={`objective-${objective}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 9,
                padding: "8px 9px",
                borderRadius: 12,
                background: "var(--color-surface-2)",
                boxShadow: "var(--shadow-z1)",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ font: "600 11px var(--font-mono)" }}>{objectiveLabel(objective)}</div>
                {row ? (
                  <>
                    <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
                      {objectiveMetricLabel(row.metric_kind)} · {objectiveWindowLabel(row.window)} · {row.sample.toLocaleString("en-US")} team states
                    </div>
                    <div style={{ marginTop: 4, fontSize: 9, lineHeight: 1.4, color: "var(--color-dim)" }}>
                      {objectiveCaveat(row)}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>No compatible typed row in this pack.</div>
                )}
              </div>
              <span
                className="pill"
                data-testid={`read-${objective}`}
                style={{
                  background: available ? "var(--color-info-low)" : "var(--color-surface-3)",
                  color: available ? "var(--color-soft-blue)" : "var(--color-dimmer)",
                  fontSize: 8,
                  padding: "2px 7px",
                  whiteSpace: "nowrap",
                }}
              >
                {available ? formatRate(row.rate) : <Unavailable reason={row?.release_status === "withheld" ? "evidence withheld" : "objective metric unavailable"} />}
              </span>
            </li>
          );
        })}
      </ul>
      <p style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Possession, timing, contest, and no-objective rows remain separate. These are
        observational population associations with selection effects, not causal swing claims.
      </p>
    </section>
  );
}
