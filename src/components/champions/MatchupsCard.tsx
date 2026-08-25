import type { MatchupExample } from "../../api/types";
import { pct } from "../ui";
import { KickerRow } from "./bits";

function MatchupRow({ m, color }: { m: MatchupExample; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          width: 52,
          fontSize: 10.5,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          flex: "none",
        }}
        title={`${m.champion} vs ${m.opponent}`}
      >
        {m.opponent}
      </span>
      <div
        style={{
          flex: 1,
          height: 7,
          borderRadius: 999,
          background: "var(--color-deep)",
          overflow: "hidden",
        }}
      >
        <div
          className="bl-width"
          style={{
            width: `${Math.round(m.wr * 100)}%`,
            height: "100%",
            background: color,
          }}
        />
      </div>
      <span
        className="mono-n"
        style={{
          width: 112,
          textAlign: "right",
          fontSize: 9.5,
          color: "var(--color-dim)",
          flex: "none",
          whiteSpace: "nowrap",
        }}
      >
        {pct(m.wr)} ±{m.ci.toFixed(1)} · {m.games}g
      </span>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <div style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>{text}</div>;
}

export function MatchupsCard({ matchups }: { matchups: MatchupExample[] }) {
  const youCounter = matchups.filter((m) => m.wr >= 0.5).sort((a, b) => b.wr - a.wr);
  const countersYou = matchups.filter((m) => m.wr < 0.5).sort((a, b) => a.wr - b.wr);

  return (
    <div
      className="card3"
      data-testid="matchups-card"
      style={{
        padding: 13,
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 9,
      }}
    >
      <KickerRow label="MATCHUPS · EB-SHRUNK" />
      <div style={{ fontSize: 9.5, color: "var(--color-teal)", letterSpacing: ".08em" }}>
        YOU COUNTER
      </div>
      <div data-testid="you-counter-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {youCounter.map((m) => (
          <MatchupRow key={`${m.champion}-${m.opponent}`} m={m} color="var(--color-teal)" />
        ))}
        {youCounter.length === 0 && <EmptyLine text="no clear edges in the pack" />}
      </div>
      <div
        style={{
          fontSize: 9.5,
          color: "#f4c3ce",
          letterSpacing: ".08em",
          marginTop: 4,
        }}
      >
        COUNTERS YOU
      </div>
      <div data-testid="counters-you-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {countersYou.map((m) => (
          <MatchupRow key={`${m.champion}-${m.opponent}`} m={m} color="var(--color-danger)" />
        ))}
        {countersYou.length === 0 && <EmptyLine text="no rough spots in the pack" />}
      </div>
      <p
        style={{
          margin: "auto 0 0",
          fontSize: 9.5,
          lineHeight: 1.5,
          color: "var(--color-dimmer)",
        }}
      >
        Total spread across every matchup ≈ ±2.5pp — the smallest lever in the game, not a
        verdict.
      </p>
    </div>
  );
}
