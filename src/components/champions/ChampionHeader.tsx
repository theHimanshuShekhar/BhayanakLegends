import type { TierEntry } from "../../api/types";
import { pct } from "../ui";

export function titleCase(role: string): string {
  return role.charAt(0).toUpperCase() + role.slice(1).toLowerCase();
}

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase();
}

function StatCell({
  label,
  value,
  teal,
}: {
  label: string;
  value: string;
  teal?: boolean;
}) {
  return (
    <div
      style={{
        padding: 8,
        borderRadius: 12,
        background: "rgba(10,11,22,.5)",
        textAlign: "center",
      }}
    >
      <div
        className="mono-n"
        style={{
          font: "700 15px var(--font-mono)",
          color: teal ? "var(--color-teal)" : undefined,
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
            color: "#0e1020",
            boxShadow: "0 5px 0 rgba(0,0,0,.5),0 16px 28px -10px rgba(145,132,217,.55)",
            flex: "none",
          }}
        >
          {initials(entry.champion)}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ font: "700 21px var(--font-mono)", letterSpacing: "-.02em" }}>
              {entry.champion}
            </span>
            <span className="pill" style={{ background: "var(--color-teal)", color: "#0e1020" }}>
              {entry.tier} tier
            </span>
          </div>
          <div style={{ fontSize: 10.5, color: "var(--color-dim)", marginTop: 2 }}>
            {titleCase(entry.role)} · {entry.games.toLocaleString()} games logged
          </div>
        </div>
      </div>
      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        <StatCell label="PICK" value={pct(entry.pick_rate)} />
        <StatCell label="BAN" value={banRate != null ? pct(banRate) : "—"} />
        <StatCell label="WIN" value={pct(entry.win_rate)} teal />
      </div>
    </div>
  );
}
