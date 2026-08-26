import type { FindingsPack } from "../../api/types";
import type { ChampSelectSessionView, FindingsPackState } from "./shared";

const PERCENT = /\d+(?:\.\d+)?%/g;

// Mastery is population-only in the Findings Pack. It must not imply that
// Personal History was used to produce this result.
export function MasteryCard({
  pack,
  session: _session,
  packState,
}: {
  pack: FindingsPack | undefined;
  session: ChampSelectSessionView;
  packState: FindingsPackState;
}) {
  const mastery = pack?.findings.find((f) => f.key === "mastery_premium");
  const nums = mastery ? (mastery.statement.match(PERCENT) ?? []) : [];
  const delta =
    mastery && mastery.value != null && mastery.unit
      ? `${mastery.value >= 0 ? "+" : ""}${mastery.value}${mastery.unit}`
      : null;
  const unavailable =
    packState === "loading"
      ? "Loading Findings Pack mastery cohort result."
      : packState === "error"
        ? "Unavailable: Findings Pack mastery cohort result could not be loaded."
        : packState === "missing" || !mastery
          ? "Unavailable: Findings Pack mastery cohort result is missing."
          : null;

  return (
    <div className="card3" data-testid="card-mastery" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-info)" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          MASTERY · FINDINGS PACK COHORT
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono-n" style={{ font: "700 22px var(--font-mono)", color: "var(--color-teal)" }}>
          {nums[0] ?? "—"}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>cohort result vs</span>
        <span className="mono-n" style={{ font: "700 16px var(--font-mono)", color: "var(--color-dim)" }}>
          {nums[1] ?? "—"}
        </span>
      </div>
      <p role="status" style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#cfd3e5" }}>
        {unavailable ??
          `Findings Pack cohort result: ${nums[0]} vs ${nums[1]}${delta ? ` (${delta})` : ""}.`}
      </p>
    </div>
  );
}
