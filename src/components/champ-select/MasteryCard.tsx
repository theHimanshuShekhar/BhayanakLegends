import type { FindingsPack } from "../../api/types";
import type { FindingsPackState } from "./shared";
import { SectionHead } from "../ui";

const PERCENT = /\d+(?:\.\d+)?%/g;

// Mastery is population-only in the Findings Pack. It must not imply that
// Personal History was used to produce this result.
export function MasteryCard({
  pack,
  packState,
}: {
  pack: FindingsPack | undefined;
  packState: FindingsPackState;
}) {
  const mastery = pack?.findings.find((f) => f.key === "mastery_premium");
  const nums = mastery ? (mastery.statement.match(PERCENT) ?? []) : [];
  const delta =
    mastery && mastery.value != null && mastery.unit
      ? `${mastery.value >= 0 ? "+" : ""}${mastery.value}${mastery.unit}`
      : null;
  const hasResult = mastery != null && nums.length >= 2;
  const unavailable =
    packState === "loading"
      ? "Loading… Findings Pack mastery cohort result."
      : packState === "error"
        ? "Unavailable: Findings Pack mastery cohort result could not be loaded."
        : packState === "missing" || !hasResult
          ? "Unavailable: Findings Pack mastery cohort result is missing."
          : null;

  return (
    <div className="card3" data-testid="card-mastery" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionHead label="MASTERY · FINDINGS PACK COHORT" color="var(--color-info)" />
      {/* Findings Pack population cohort number: blue, never teal. */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono-n" style={{ font: "700 22px var(--font-mono)", color: "var(--color-info)" }}>
          {nums[0] ?? "—"}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>cohort result vs</span>
        <span className="mono-n" style={{ font: "700 16px var(--font-mono)", color: "var(--color-dim)" }}>
          {nums[1] ?? "—"}
        </span>
      </div>
      <p role="status" style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "var(--color-soft-text)" }}>
        {unavailable ??
          `Findings Pack cohort result: ${nums[0]} vs ${nums[1]}${delta ? ` (${delta})` : ""}.`}
      </p>
    </div>
  );
}
