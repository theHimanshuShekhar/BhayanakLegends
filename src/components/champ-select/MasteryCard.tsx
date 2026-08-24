import type { FindingsPack } from "../../api/types";

const PERCENT = /\d+(?:\.\d+)?%/g;

// ADR-0003 phrasing discipline: mastery_premium is actionable in the shipped
// packs, so the imperative caption is allowed; a diagnostic variant would fall
// back to the verbatim statement. Numbers are parsed from the pack, never
// hardcoded.
export function MasteryCard({ pack }: { pack: FindingsPack | undefined }) {
  const mastery = pack?.findings.find((f) => f.key === "mastery_premium");
  const nums = mastery ? (mastery.statement.match(PERCENT) ?? []) : [];
  const delta =
    mastery && mastery.value != null && mastery.unit
      ? `${mastery.value >= 0 ? "+" : ""}${mastery.value}${mastery.unit}`
      : null;
  const gamesK = pack ? Math.round(pack.dataset.matches / 1000) : null;
  const actionable = mastery != null && mastery.tier !== "diagnostic";

  const caption = !mastery
    ? "Mastery finding arrives with the next Findings Pack."
    : actionable
      ? `When the pick is close, take the pocket pick — the premium is ${delta ?? "real"}${
          gamesK ? ` at ${gamesK}k games` : ""
        }.`
      : mastery.statement;

  return (
    <div className="card3" data-testid="card-mastery" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-info)" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          MASTERY · POCKET PICKS PAY
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="mono-n" style={{ font: "700 22px var(--font-mono)", color: "var(--color-teal)" }}>
          {nums[0] ?? "—"}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>on your top 3 vs</span>
        <span className="mono-n" style={{ font: "700 16px var(--font-mono)", color: "var(--color-dim)" }}>
          {nums[1] ?? "—"}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>on the rest</span>
      </div>
      <p style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5, color: "#cfd3e5" }}>{caption}</p>
    </div>
  );
}
