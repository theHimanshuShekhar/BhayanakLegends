import type { FindingsPack } from "../../api/types";
import { formatClock, formatUnavailable } from "../format";
import { SectionHead } from "../ui";

/**
 * The shipped Findings Pack does not contain the complete live probability
 * contract: an exact live gold observation, compatible quartile boundaries,
 * and model inputs. Keep this state explicit instead of deriving a number
 * from a clock-only checkpoint lookup.
 */
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
  const signal = "var(--color-dimmer)";
  return (
    <section
      className="card3b"
      data-testid="wp-band"
      style={{ padding: 14, display: "flex", flexDirection: "column" }}
    >
      <SectionHead
        color="var(--color-info)"
        label={`WIN PROBABILITY · FINDINGS PACK${packVersion ? ` ${packVersion}` : ""}`}
        right={
          <span
            className="mono-n"
            data-testid="wp-value"
            style={{ font: "700 20px var(--font-mono)", color: signal }}
          >
            {formatUnavailable("compatible live inputs unavailable")}
          </span>
        }
      />
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
        <line x1="0" y1="54" x2="640" y2="54" stroke="rgba(233,233,237,.16)" strokeWidth="1" />
        <line
          x1="0"
          y1="54"
          x2="640"
          y2="54"
          stroke="rgba(233,233,237,.28)"
          strokeWidth="2"
          strokeDasharray="4 5"
          strokeLinecap="round"
        />
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
        <span className="mono-n">{formatClock(clockS)}</span>
      </div>
      <p style={{ margin: "8px 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
        The current Findings Pack lacks the compatible live input, quartile boundaries, and model inputs needed to
        map this game. Personal History remains separate from live inference.
      </p>
    </section>
  );
}
