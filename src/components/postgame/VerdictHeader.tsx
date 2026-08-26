import type { PostGameDigest } from "../../api/types";
import { formatDuration, formatInitials } from "../format";

/**
 * Verdict header tile: teal gradient for a win, red for a loss, dim chrome
 * when no digest exists yet. Sub line binds champion · role · duration — the
 * design's KDA/tier/patch tail has no digest fields, so it stays out.
 */
export function VerdictHeader({ digest }: { digest: PostGameDigest | null }) {
  const idle = digest == null;
  const win = digest?.win ?? false;
  const titleColor = idle ? "var(--color-dim)" : win ? "#b8ecd9" : "#f4c3ce";
  const subColor = idle
    ? "var(--color-dimmer)"
    : win
      ? "rgba(184,236,217,.75)"
      : "rgba(244,195,206,.7)";
  return (
    <section
      className="card3b"
      data-testid="verdict-header"
      aria-labelledby="postgame-verdict-heading"
      style={{
        flex: "none",
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: "12px 16px",
        background: idle
          ? "var(--color-surface-2)"
          : win
            ? "linear-gradient(150deg,#1b463f,var(--color-surface-2) 82%)"
            : "linear-gradient(150deg,#4d2436,var(--color-surface-2) 82%)",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 44,
          height: 44,
          borderRadius: 14,
          background: idle
            ? "var(--color-surface-3)"
            : "linear-gradient(150deg,var(--color-accent),var(--color-accent-low))",
          display: "grid",
          placeItems: "center",
          font: "700 12px var(--font-mono)",
          color: idle ? "var(--color-dimmer)" : "#0e1020",
        }}
      >
        {formatInitials(digest?.champion, "champion unavailable")}
      </div>
      <div>
        <h2
          id="postgame-verdict-heading"
          style={{
            margin: "0 0 4px",
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".11em",
            color: "var(--color-dim)",
            textTransform: "uppercase",
          }}
        >
          Verdict
        </h2>
        <h3
          data-testid="verdict"
          style={{ margin: 0, font: "700 17px var(--font-mono)", color: titleColor }}
        >
          {idle ? "No game analyzed" : win ? "Victory" : "Defeat"}
        </h3>
        <div className="mono-n" data-testid="verdict-sub" style={{ fontSize: 10, color: subColor }}>
          {digest
            ? `${digest.champion} · ${digest.role} · ${formatDuration(digest.duration_s)}`
            : "play a game with the app running, or Backfill from History"}
        </div>
      </div>
    </section>
  );
}
