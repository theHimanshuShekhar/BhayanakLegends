import type { TierEntry } from "../../api/types";
import { formatCount, formatInitials, formatRate } from "../format";

export function titleCase(role: string): string {
  return role.charAt(0).toUpperCase() + role.slice(1).toLowerCase();
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        padding: 8,
        borderRadius: 12,
        background: "rgba(10,11,22,.5)",
        textAlign: "center",
      }}
    >
      {/* Findings Pack population rate: blue, never teal. */}
      <div
        className="mono-n"
        style={{
          font: "700 15px var(--font-mono)",
          color: "var(--color-info)",
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 8, letterSpacing: ".06em", color: "var(--color-dimmer)" }}>
        {label}
      </div>
    </div>
  );
}

export function ChampionHeader({
  entry,
  banRate,
}: {
  entry: TierEntry;
  banRate?: number | null;
}) {
  return (
    <div
      className="card3b"
      data-testid="champion-header"
      style={{
        padding: 15,
        background: "linear-gradient(165deg,#2b2650,var(--color-surface-2) 65%)",
        boxShadow: "var(--shadow-z2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
        <div
          style={{
            width: 60,
            height: 60,
            borderRadius: 19,
            background: "linear-gradient(150deg,var(--color-accent),#4b4180)",
            display: "grid",
            placeItems: "center",
            font: "700 17px var(--font-mono)",
            color: "var(--color-bg)",
            boxShadow: "0 5px 0 rgba(0,0,0,.5),0 16px 28px -10px rgba(145,132,217,.55)",
            flex: "none",
          }}
        >
          {formatInitials(entry.champion)}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ font: "700 21px var(--font-mono)", letterSpacing: "-.02em" }}>
              {entry.champion}
            </span>
            <span className="pill" style={{ background: "var(--color-info)", color: "var(--color-bg)" }}>
              {entry.tier} tier
            </span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--color-dim)", marginTop: 2 }}>
            {titleCase(entry.role)} · {formatCount(entry.games, "games")} logged
          </div>
        </div>
      </div>
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <StatCell label="PICK" value={formatRate(entry.pick_rate)} />
        <StatCell label="BAN" value={formatRate(banRate ?? null, "ban rate unavailable")} />
        <StatCell label="WIN" value={formatRate(entry.win_rate)} />
      </div>
    </div>
  );
}
