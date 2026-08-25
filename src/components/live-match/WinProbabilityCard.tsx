import type { FindingsPack } from "../../api/types";
import { pct } from "../ui";
import { clockLabel, Dot } from "./bits";

function nearestBucket(pack: FindingsPack | undefined, clockS: number) {
  const rows = pack?.checkpoints ?? [];
  let best: (typeof rows)[number] | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const row of rows) {
    const minute = /@(\d+)m/.exec(row.gold_diff_bucket)?.[1];
    if (minute == null) continue;
    const distance = Math.abs(Number(minute) * 60 - clockS);
    // strict `<` keeps the earlier checkpoint on ties
    if (distance < bestDistance) {
      best = row;
      bestDistance = distance;
    }
  }
  return best;
}

/** Bucket keys arrive in pack-specific shapes; give the quartile form a readable label. */
function bucketLabel(bucket: string): string {
  const quartile = /^(bottom|top)_quartile_@?(\d+)m$/.exec(bucket);
  return quartile ? `${quartile[1]} quartile @${quartile[2]}m` : bucket;
}

/**
 * Win probability, honest edition (ADR-0003): the number is a nearest-bucket
 * lookup in pack.checkpoints, labeled Checkpoint estimate · Diagnostic. The
 * calibrated live model ships with the next pack as a model artifact.
 */
export function WinProbabilityCard({
  pack,
  clockS,
  active,
  packVersion,
}: {
  pack: FindingsPack | undefined;
  clockS: number;
  active: boolean;
  packVersion: string | null;
}) {
  const bucket = nearestBucket(pack, clockS);
  const wr = active && bucket ? bucket.win_rate : null;
  const y = wr == null ? 54 : Math.round(106 - wr * 100);
  // Semantic signal: teal when the estimate is favorable, rose when behind.
  const signal = wr == null ? "var(--color-dimmer)" : wr >= 0.5 ? "var(--color-teal)" : "var(--color-danger)";
  return (
    <section
      className="card3b"
      data-testid="wp-band"
      style={{ padding: 14, display: "flex", flexDirection: "column" }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <Dot color="var(--color-info)" />
        <span
          style={{
            font: "700 10px var(--font-mono)",
            letterSpacing: ".12em",
            color: "var(--color-dim)",
          }}
        >
          WIN PROBABILITY · FINDINGS PACK{packVersion ? ` ${packVersion}` : ""}
        </span>
        <span
          className="mono-n"
          data-testid="wp-value"
          style={{
            marginLeft: "auto",
            font: "700 20px var(--font-mono)",
            color: signal,
          }}
        >
          {wr == null ? "—" : pct(wr)}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 5 }}>
        <span
          className="pill"
          style={{
            background: "var(--color-info-low)",
            color: "#cfe3f9",
            fontSize: 8,
            padding: "2px 7px",
          }}
        >
          Checkpoint estimate
        </span>
        <span
          style={{ font: "700 8px var(--font-mono)", letterSpacing: ".1em", color: "var(--color-dimmer)" }}
        >
          Diagnostic
        </span>
        {bucket && (
          <span className="mono-n" style={{ marginLeft: "auto", fontSize: 9, color: "var(--color-dimmer)" }}>
            {bucketLabel(bucket.gold_diff_bucket)}
          </span>
        )}
      </div>
      <svg
        viewBox="0 0 640 108"
        style={{ width: "100%", height: 100, marginTop: 6 }}
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="wp-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#57cfb4" stopOpacity=".4" />
            <stop offset="1" stopColor="#57cfb4" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="wp-fill-behind" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#e5738f" stopOpacity=".35" />
            <stop offset="1" stopColor="#e5738f" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" y1="54" x2="640" y2="54" stroke="rgba(233,233,237,.16)" strokeWidth="1" />
        {wr == null ? (
          <line
            x1="0"
            y1={y}
            x2="640"
            y2={y}
            stroke="rgba(233,233,237,.28)"
            strokeWidth="2"
            strokeDasharray="4 5"
            strokeLinecap="round"
          />
        ) : (
          <>
            <path
              d={`M0,${y} L640,${y} L640,108 L0,108 Z`}
              fill={wr >= 0.5 ? "url(#wp-fill)" : "url(#wp-fill-behind)"}
            />
            <polyline
              points={`0,${y} 640,${y}`}
              fill="none"
              stroke={signal}
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <circle cx="640" cy={y} r="5" fill={signal} />
            <circle cx="640" cy={y} r="9" fill={signal} opacity=".25" />
          </>
        )}
      </svg>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 8,
          fontSize: 9,
          color: "var(--color-dimmer)",
          marginTop: 1,
        }}
      >
        <span className="mono-n">0:00</span>
        <span>checkpoint timeline lands with the LCU bridge</span>
        <span className="mono-n">{clockLabel(clockS)}</span>
      </div>
      <p style={{ margin: "8px 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        Nearest population checkpoint, not your game's odds — the calibrated model ships with the
        next pack.
      </p>
    </section>
  );
}
