import type { MatchupExample } from "../../api/types";
import { formatCount, formatPercentagePoints, formatRate } from "../format";
import { SectionHead } from "../ui";

function MatchupRow({ m }: { m: MatchupExample }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          flex: 1,
          fontSize: 10.5,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={`${m.champion} vs ${m.opponent}`}
      >
        {m.champion} vs {m.opponent}
      </span>
      <div
        style={{
          width: 76,
          height: 7,
          borderRadius: 999,
          background: "var(--color-deep)",
          overflow: "hidden",
          flex: "none",
        }}
      >
        {/* Findings Pack population evidence: blue in both directions. */}
        <div
          data-testid={`matchup-bar-${m.champion}-${m.opponent}`}
          className="bl-width"
          style={{
            width: `${Math.round(m.wr * 100)}%`,
            height: "100%",
            background: "var(--color-info)",
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
        {formatRate(m.wr)} ±{formatPercentagePoints(Math.abs(m.ci)).slice(1)} · {formatCount(m.games, "games")}
      </span>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <div style={{ fontSize: 9.5, color: "var(--color-dimmer)" }}>{text}</div>;
}

export function MatchupsCard({
  champion,
  matchups,
}: {
  champion: string | null;
  matchups: MatchupExample[];
}) {
  const favorable = matchups.filter((m) => m.wr >= 0.5).sort((a, b) => b.wr - a.wr);
  const difficult = matchups.filter((m) => m.wr < 0.5).sort((a, b) => a.wr - b.wr);
  const empty = `The current Findings Pack has no directional example for ${champion ?? "this champion"}.`;

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
      <SectionHead label="MATCHUPS · FINDINGS PACK" />
      {!champion ? (
        <EmptyLine text="Select a champion to see directional examples." />
      ) : (
        <>
          {/* Favorable/difficult framing is carried by the words, not by
              recoloring the population evidence itself (blue throughout). */}
          <div style={{ fontSize: 9.5, color: "var(--color-dim)", letterSpacing: ".08em" }}>
            FAVORABLE EXAMPLES FOR {champion.toUpperCase()}
          </div>
          <div data-testid="favorable-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {favorable.map((m) => (
              <MatchupRow key={`${m.champion}-${m.opponent}`} m={m} />
            ))}
            {favorable.length === 0 && <EmptyLine text={empty} />}
          </div>
          <div
            style={{
              fontSize: 9.5,
              color: "var(--color-dim)",
              letterSpacing: ".08em",
              marginTop: 4,
            }}
          >
            DIFFICULT EXAMPLES FOR {champion.toUpperCase()}
          </div>
          <div data-testid="difficult-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {difficult.map((m) => (
              <MatchupRow key={`${m.champion}-${m.opponent}`} m={m} />
            ))}
            {difficult.length === 0 && <EmptyLine text={empty} />}
          </div>
          <p
            style={{
              margin: "auto 0 0",
              fontSize: 9.5,
              lineHeight: 1.5,
              color: "var(--color-dimmer)",
            }}
          >
            Source: Findings Pack · matchup_examples
          </p>
        </>
      )}
    </div>
  );
}
