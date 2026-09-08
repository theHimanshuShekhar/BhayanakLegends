import type { FindingsPackV2 } from "../../api/pack-v2";
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

export function ObjectivesCard({ pack }: { pack: FindingsPackV2 | undefined }) {
  const rows = objectiveRows(pack);
  return (
    <section
      className="card3"
      data-testid="objectives-computed"
      aria-labelledby="objectives-computed-heading"
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead color="var(--color-info)" label={<span id="objectives-computed-heading">OBJECTIVES · COMPUTED</span>} />
      {OBJECTIVE_ORDER.map((objective) => {
        const objectiveRowsForName = rows.filter((row) => row.objective === objective);
        const displayedRows = objectiveRowsForName.length > 0 ? objectiveRowsForName : [null];
        return displayedRows.map((row, index) => {
          const available = row != null && isObjectiveRenderable(row);
          return (
            <div
              key={`${objective}-${row?.metric_kind ?? "unavailable"}-${index}`}
              data-testid={`objective-${objective}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "9px 10px",
                borderRadius: 13,
                background: objective === "dragon" ? "linear-gradient(140deg,#2b4a44,var(--color-surface-2) 78%)" : "var(--color-surface-2)",
                boxShadow: objective === "dragon" ? "0 3px 0 rgba(0,0,0,.5),0 0 0 1.5px rgba(87,207,180,.5)" : "var(--shadow-z1)",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ font: "600 11px var(--font-mono)" }}>{objectiveLabel(objective)}</div>
                {row ? (
                  <>
                    <div style={{ fontSize: 8.5, color: "var(--color-dimmer)" }}>
                      {objectiveMetricLabel(row.metric_kind)} · {objectiveWindowLabel(row.window)}
                    </div>
                    <div style={{ marginTop: 3, fontSize: 8.5, lineHeight: 1.35, color: "var(--color-dimmer)" }}>
                      {objectiveCaveat(row)}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 8.5, color: "var(--color-dimmer)" }}>No compatible typed row in this pack.</div>
                )}
              </div>
              <div style={{ textAlign: "right", flex: "0 1 45%", minWidth: 0 }}>
                <div
                  className="mono-n"
                  style={{
                    minWidth: 0,
                    font: "700 15px var(--font-mono)",
                    color: available ? "var(--color-soft-blue)" : "var(--color-dimmer)",
                    overflowWrap: "anywhere",
                  }}
                >
                  {available ? formatRate(row.rate) : <Unavailable reason={row?.release_status === "withheld" ? "evidence withheld" : "objective metric unavailable"} />}
                </div>
                <div style={{ fontSize: 7.5, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>
                  {row ? `${row.sample.toLocaleString("en-US")} TEAM STATES` : "PARTIAL"}
                </div>
              </div>
            </div>
          );
        });
      })}
      <p
        data-testid="objectives-caption"
        style={{ margin: 0, fontSize: 9, lineHeight: 1.45, color: "var(--color-dimmer)" }}
      >
        Typed possession, timing, contest, and no-objective rows describe population context.
        Selection effects remain; no objective row is a causal swing claim.
      </p>
    </section>
  );
}
