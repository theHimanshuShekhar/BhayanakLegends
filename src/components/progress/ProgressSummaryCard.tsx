import type { HistorySummary } from "../../api/types";
import { pct } from "../ui";

export function ProgressSummaryCard({ summary }: { summary: HistorySummary }) {
  const patches = summary.patches;
  const range =
    patches.length > 0 ? `${patches[0]} → ${patches[patches.length - 1]}` : "—";
  return (
    <div
      data-testid="progress-summary"
      style={{
        padding: 15,
        borderRadius: 22,
        background: "linear-gradient(158deg,#2b2650,var(--color-surface-2) 72%)",
        boxShadow: "var(--shadow-z2)",
      }}
    >
      <div
        style={{
          font: "700 9.5px var(--font-mono)",
          letterSpacing: ".14em",
          color: "rgba(210,206,253,.6)",
        }}
      >
        PERSONAL HISTORY
      </div>
      <div style={{ marginTop: 9, display: "flex", alignItems: "center", gap: 12 }}>
        <div
          style={{
            width: 50,
            height: 50,
            borderRadius: 16,
            background: "linear-gradient(150deg,var(--color-accent),#4b4180)",
            display: "grid",
            placeItems: "center",
            font: "700 13px var(--font-mono)",
            color: "#0e1020",
            boxShadow: "0 4px 0 rgba(0,0,0,.5),0 14px 26px -8px rgba(145,132,217,.45)",
            flex: "none",
          }}
        >
          YOU
        </div>
        <div>
          <div
            className="mono-n"
            style={{ font: "700 20px/1 var(--font-mono)" }}
            data-testid="summary-matches-progress"
          >
            {summary.matches.toLocaleString()}
          </div>
          <div
            className="mono-n"
            style={{ marginTop: 4, fontSize: 10.5, color: "var(--color-dim)" }}
          >
            {pct(summary.win_rate)} win rate · {range}
          </div>
        </div>
      </div>
      <div
        style={{
          marginTop: 12,
          height: 7,
          borderRadius: 999,
          background: "var(--color-deep)",
          boxShadow: "inset 0 2px 5px rgba(0,0,0,.8)",
          overflow: "hidden",
        }}
      >
        <div
          className="bl-width"
          style={{
            width: `${Math.round(summary.win_rate * 100)}%`,
            height: "100%",
            borderRadius: 999,
            background: "linear-gradient(90deg,var(--color-teal),#8ce8d1)",
          }}
        />
      </div>
    </div>
  );
}
