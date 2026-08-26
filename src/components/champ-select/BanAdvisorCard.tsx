import type { BanAdvice, FindingsPack } from "../../api/types";
import { formatInitials, formatRate, formatUnavailable } from "../format";
import { SectionHead } from "../ui";

function Row({ advice }: { advice: BanAdvice }) {
  const featured = advice.recommendation === "real-threat";
  const skip = advice.recommendation === "skip";
  return (
    <div
      data-testid={`ban-advisor-row-${advice.champion}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        padding: "9px 10px",
        borderRadius: 13,
        ...(featured
          ? {
              background: "linear-gradient(140deg,#2b1e46,var(--color-surface-2) 78%)",
              boxShadow: "0 3px 0 rgba(0,0,0,.5),0 0 0 1.5px rgba(123,176,239,.5)",
            }
          : {
              background: "var(--color-surface-3)",
              boxShadow: "var(--shadow-z1)",
              opacity: skip ? 0.6 : undefined,
            }),
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          flex: "none",
          borderRadius: 9,
          background: "linear-gradient(150deg,#5a3644,#2b1a22)",
          display: "grid",
          placeItems: "center",
          font: "700 9px var(--font-mono)",
          color: "#e5a8b8",
        }}
      >
        {formatInitials(advice.champion)}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: "600 11.5px var(--font-mono)" }}>{advice.champion}</div>
        {/* Findings Pack population rates render in the population blue. */}
        <div style={{ fontSize: 9, color: "var(--color-info)" }}>
          {formatRate(advice.win_rate)} WR at {formatRate(advice.ban_rate)} ban rate
        </div>
      </div>
      {featured ? (
        <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-soft-blue)" }}>
          Recommend ban
        </span>
      ) : advice.recommendation === "fear-ban" ? (
        <span className="pill" style={{ background: "var(--color-amber-low)", color: "var(--color-amber)" }}>
          Fear ban
        </span>
      ) : (
        <span className="pill" style={{ background: "var(--color-surface-2)", color: "var(--color-dim)" }}>
          skip
        </span>
      )}
    </div>
  );
}

export function BanAdvisorCard({ pack }: { pack: FindingsPack | undefined }) {
  const rows = [...(pack?.ban_advisor ?? [])].sort((a, b) => b.win_rate - a.win_rate).slice(0, 1);
  const waste = pack?.findings.find((f) => f.key === "ban_waste_correlation");
  const traps = (pack?.trap_picks ?? []).slice(0, 3);

  // ADR-0003: ban_waste_correlation is actionable in the shipped packs, so the
  // imperative "spend them" phrasing is allowed; a diagnostic variant would
  // render its verbatim statement instead.
  const paragraph = !waste
    ? "Fear-bans only pay off in snowball-prone lobbies — target the strong, unbanned champions above."
    : waste.tier === "diagnostic"
      ? waste.statement
      : `Most bans don't correlate with strength (r=${waste.value}) — spend them on the strong, unbanned champions above instead of fear-bans.`;

  return (
    <div className="card3" data-testid="card-ban-advisor" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <SectionHead label="BAN ADVISOR · FINDINGS PACK" color="var(--color-info)" />

      {rows.length === 0 ? (
        <p style={{ margin: 0, fontSize: 10, color: "var(--color-dim)" }}>
          {formatUnavailable("Findings Pack ban advisor has no rows")}
        </p>
      ) : (
        rows.map((r) => <Row key={r.champion} advice={r} />)
      )}

      {rows.length > 0 && (
        <p style={{ margin: 0, fontSize: 10, lineHeight: 1.55, color: "var(--color-dim)" }}>{paragraph}</p>
      )}

      {traps.length > 0 && (
        <div
          style={{
            marginTop: 2,
            paddingTop: 9,
            borderTop: "1px solid var(--color-line)",
            fontSize: 9.5,
            lineHeight: 1.6,
            color: "var(--color-dimmer)",
          }}
        >
          Trap picks this patch — priority far outstrips winrate:{" "}
          <b style={{ color: "var(--color-dim)" }}>
            {traps[0].champion} <span style={{ color: "var(--color-info)" }}>{formatRate(traps[0].win_rate)}</span>
          </b>
          {traps.slice(1).map((t) => (
            <span key={t.champion}>
              {" · "}
              {t.champion} <span style={{ color: "var(--color-info)" }}>{formatRate(t.win_rate)}</span>
            </span>
          ))}
          .
        </div>
      )}
    </div>
  );
}
