import type { FindingsPack } from "../../api/pack-v2";
import { isFindingsPackV2 } from "../../api/pack-v2";
import { formatEffectPerSd } from "../format";
import {
  habitEvidence,
  habitEvidenceReleased,
  habitFavorableDirection,
} from "../populationEvidence";
import { SectionHead, Unavailable } from "../ui";

export function LeverAdoption({ pack }: { pack: FindingsPack | undefined }) {
  const v2Pack = isFindingsPackV2(pack) ? pack : undefined;
  const habits = habitEvidence(v2Pack);
  return (
    <div
      className="card3b"
      data-testid="lever-adoption"
      style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <SectionHead
        level={3}
        label="LEVER ADOPTION"
        color="var(--color-info)"
        right={
          <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-soft-blue)" }}>
            {v2Pack ? `Findings Pack ${v2Pack.pack_version}` : "Findings Pack unavailable"}
          </span>
        }
      />
      <h3 className="route-subheading">Population evidence</h3>
      {habits.length === 0 ? (
        <div
          data-testid="habit-evidence-unavailable"
          style={{ padding: "12px 10px", borderRadius: 13, background: "var(--color-surface-3)", fontSize: 10, lineHeight: 1.45, color: "var(--color-dim)" }}
        >
          <Unavailable reason="compatible Findings Pack habit evidence unavailable" />
        </div>
      ) : (
        <ul
          aria-label="Improvement lever population evidence"
          style={{ display: "flex", flexDirection: "column", gap: 8, listStyle: "none", margin: 0, padding: 0 }}
        >
          {habits.map((habit) => {
            const available = habitEvidenceReleased(habit);
            const weakPlate = habit.key === "plates_by_14m";
            const unavailableReason =
              habit.releaseReason ?? habit.contractIssue ?? "effect unavailable";
            const sampleLabel =
              habit.sample == null
                ? "Sample unavailable"
                : `${habit.sample.toLocaleString("en-US")} exposures`;
            const eraLabel =
              habit.eraStability === "sensitive"
                ? "era-sensitive"
                : habit.eraStability ?? "era status unavailable";
            return (
              <li
                key={habit.key}
                data-testid={`habit-row-${habit.key}`}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  padding: "8px 10px",
                  borderRadius: 13,
                  background: "var(--color-surface-3)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ font: "600 11px var(--font-mono)" }}>{habit.label}</div>
                    <div style={{ fontSize: 9, color: "var(--color-dim)" }}>
                      {weakPlate ? "Diagnostic · era-sensitive" : habitFavorableDirection(habit)} ·{" "}
                      {habit.unit ?? "unit unavailable"}
                    </div>
                  </div>
                  <span
                    className="pill"
                    style={{
                      background: available ? "var(--color-info-low)" : "var(--color-surface-2)",
                      color: available ? "var(--color-soft-blue)" : "var(--color-dimmer)",
                      padding: "2px 7px",
                    }}
                  >
                    {available
                      ? formatEffectPerSd(habit.effect)
                      : <Unavailable reason={unavailableReason} />}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 8.5, color: "var(--color-dimmer)" }}>
                  <span>{sampleLabel}</span>
                  <span>{eraLabel}</span>
                </div>
                <div style={{ fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}>
                  {available
                    ? `Observational population association, not a guarantee. ${habit.caveats[0] ?? ""}`
                    : `Population association unavailable: ${unavailableReason}`}
                </div>
                <div
                  data-testid={`habit-bar-${habit.key}`}
                  aria-hidden="true"
                  style={{ height: 4, borderRadius: 999, background: "var(--color-deep)", overflow: "hidden" }}
                >
                  <div style={{ width: 0, height: "100%", background: "var(--color-surface-3)" }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}>
        These are Findings Pack population associations, not Personal History outcomes. Personal
        observations appear only when the local v2 extractor proves the required window.
      </p>
    </div>
  );
}
