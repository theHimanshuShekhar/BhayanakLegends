import type { MatchupEvidenceRow } from "../populationEvidence";
import { EvidenceMeta } from "../populationEvidence";
import { formatCount, formatInterval, formatRate } from "../format";
import { SectionHead } from "../ui";

function MatchupRow({ m }: { m: MatchupEvidenceRow }) {
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
        <div
          data-testid={`matchup-bar-${m.champion}-${m.opponent}`}
          className="bl-width"
          style={{
            width: `${Math.round(m.estimate * 100)}%`,
            height: "100%",
            background: "var(--color-info)",
          }}
        />
      </div>
      <span
        className="mono-n"
        style={{
          width: 156,
          textAlign: "right",
          fontSize: 9.5,
          color: "var(--color-dim)",
          flex: "none",
          whiteSpace: "nowrap",
        }}
      >
        {formatRate(m.estimate)} · {formatInterval(m.interval)} · {formatCount(m.games, "games")}
      </span>
      <EvidenceMeta metadata={m.metadata} />
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
  matchups: MatchupEvidenceRow[];
}) {
  const higher = matchups.filter((m) => m.estimate >= 0.5).sort((a, b) => b.estimate - a.estimate);
  const lower = matchups.filter((m) => m.estimate < 0.5).sort((a, b) => a.estimate - b.estimate);
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
          <div style={{ fontSize: 9.5, color: "var(--color-dim)", letterSpacing: ".08em" }}>
            HIGHER OBSERVED ESTIMATES FOR {champion.toUpperCase()}
          </div>
          <div data-testid="favorable-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {higher.map((m) => (
              <MatchupRow key={`${m.champion}-${m.opponent}-${m.role}`} m={m} />
            ))}
            {higher.length === 0 && <EmptyLine text={empty} />}
          </div>
          <div
            style={{
              fontSize: 9.5,
              color: "var(--color-dim)",
              letterSpacing: ".08em",
              marginTop: 4,
            }}
          >
            LOWER OBSERVED ESTIMATES FOR {champion.toUpperCase()}
          </div>
          <div data-testid="difficult-list" style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {lower.map((m) => (
              <MatchupRow key={`${m.champion}-${m.opponent}-${m.role}`} m={m} />
            ))}
            {lower.length === 0 && <EmptyLine text={empty} />}
          </div>
          <p
            style={{
              margin: "auto 0 0",
              fontSize: 9.5,
              lineHeight: 1.5,
              color: "var(--color-dimmer)",
            }}
          >
            Source: Findings Pack · matchup_examples · directional estimate with interval
          </p>
        </>
      )}
    </div>
  );
}
