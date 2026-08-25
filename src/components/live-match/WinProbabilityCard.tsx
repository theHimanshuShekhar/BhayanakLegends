import type { FindingsPack } from "../../api/types";
import { clockLabel, Dot } from "./bits";

/**
 * The shipped Findings Pack does not contain the complete live probability
 * contract: an exact live gold observation, compatible quartile boundaries,
 * and model inputs. Keep this state explicit instead of deriving a number
 * from a clock-only checkpoint lookup.
 */
const LIVE_PROBABILITY: number | null = null;

export function WinProbabilityCard({
  pack: _pack,
  clockS,
  active: _active,
  packVersion,
}: {
  pack: FindingsPack | undefined;
  clockS: number;
  active: boolean;
  packVersion: string | null;
}) {
  void clockS;
  const wr = LIVE_PROBABILITY;
  const y = 54;
  const signal = "var(--color-dimmer)";
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
          —
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
          Unavailable
        </span>
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
        <span>live inputs unavailable</span>
        <span className="mono-n">{clockLabel(clockS)}</span>
      </div>
      <p style={{ margin: "8px 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        The current Findings Pack lacks the compatible live input, quartile boundaries, and model inputs needed to
        map this game. Personal History remains separate from live inference.
      </p>
    </section>
  );
}
