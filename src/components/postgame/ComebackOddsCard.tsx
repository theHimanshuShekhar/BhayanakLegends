import type { FindingsPack, PostGameDigest } from "../../api/types";
import { pct } from "../ui";
import { CardHead } from "./bits";
import { fmtK } from "./format";

function nearestDeficit(
  odds: { gold_deficit_at_15: number; win_rate: number }[],
  gold15: number,
) {
  let best: (typeof odds)[number] | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const row of odds) {
    const distance = Math.abs(row.gold_deficit_at_15 - gold15);
    if (distance < bestDistance) {
      best = row;
      bestDistance = distance;
    }
  }
  return best;
}

/**
 * Comeback odds read the digest's own gold@15 against the pack's checkpoint
 * table. Diagnostic phrasing — it describes what teams at this state do, it
 * never tells you to surrender or play on.
 */
export function ComebackOddsCard({
  digest,
  pack,
}: {
  digest: PostGameDigest | null;
  pack: FindingsPack | undefined;
}) {
  const gold15 = digest?.checkpoints.gold_diff_15 ?? null;
  const row = gold15 == null ? null : nearestDeficit(pack?.comeback_odds ?? [], gold15);
  return (
    <section
      className="card3b"
      data-testid="comeback-odds"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <CardHead color="var(--color-info)" label="COMEBACK ODDS" />
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span
          className="mono-n"
          data-testid="comeback-value"
          style={{
            font: "700 22px var(--font-mono)",
            color:
              row && gold15 != null && gold15 < 0 ? "var(--color-danger)" : "var(--color-dimmer)",
          }}
        >
          {row ? pct(row.win_rate) : "—"}
        </span>
        <span style={{ fontSize: 10, color: "var(--color-dimmer)" }}>
          {row && gold15 != null
            ? `win rate down ${fmtK(Math.abs(gold15))} gold at 15`
            : "gold down at 15 → win chance"}
        </span>
      </div>
      <p data-testid="comeback-note" style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "#cfd3e5" }}>
        {row && gold15 != null
          ? `You were down ${Math.abs(gold15).toLocaleString("en-US")}g at 15. Teams here still win about 1 in ${Math.max(2, Math.round(1 / row.win_rate))} — no single play explains it away.`
          : "The checkpoint table arrives with the next Findings Pack."}
      </p>
    </section>
  );
}
