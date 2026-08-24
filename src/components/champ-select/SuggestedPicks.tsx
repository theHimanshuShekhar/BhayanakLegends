import type { FindingsPack, TierEntry } from "../../api/types";
import { initials, pct0 } from "./shared";

const ROLE = "MIDDLE";

function StatBlock({ value, label, teal }: { value: string; label: string; teal?: boolean }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "8px 11px",
        borderRadius: 14,
        background: "rgba(10,11,22,.55)",
        boxShadow: "inset 0 2px 6px rgba(0,0,0,.6)",
      }}
    >
      <div className="mono-n" style={{ font: "700 17px var(--font-mono)", color: teal ? "var(--color-teal)" : undefined }}>
        {value}
      </div>
      <div style={{ fontSize: 8.5, letterSpacing: ".1em", color: "var(--color-dimmer)" }}>{label}</div>
    </div>
  );
}

function HeroCard({ hero }: { hero: TierEntry }) {
  return (
    <div
      data-testid="cs-hero-pick"
      style={{
        borderRadius: 20,
        padding: 15,
        background: "linear-gradient(160deg,#2b2650,var(--color-surface-2) 70%)",
        boxShadow:
          "0 5px 0 rgba(0,0,0,.55),0 30px 52px -18px rgba(0,0,0,.95),0 0 0 1.5px rgba(145,132,217,.55),inset 0 1px 0 rgba(255,255,255,.1)",
        display: "flex",
        gap: 14,
        alignItems: "center",
      }}
    >
      <div
        style={{
          width: 66,
          height: 66,
          flex: "none",
          borderRadius: 20,
          background: "linear-gradient(150deg,var(--color-accent),#4b4180)",
          display: "grid",
          placeItems: "center",
          font: "700 19px var(--font-mono)",
          color: "#0e1020",
          boxShadow: "0 5px 0 rgba(0,0,0,.5),0 18px 30px -10px rgba(145,132,217,.6)",
        }}
      >
        {initials(hero.champion)}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ font: "700 20px var(--font-mono)", letterSpacing: "-.02em" }}>{hero.champion}</span>
          <span className="pill" style={{ background: "var(--color-accent)", color: "#0e1020" }}>
            Best pick
          </span>
          <span className="pill" style={{ background: "var(--color-info-low)", color: "#cfe3f9" }}>
            {hero.tier} tier
          </span>
        </div>
        <p style={{ margin: "5px 0 0", fontSize: 11, lineHeight: 1.5, color: "#e0ddf5", maxWidth: 420 }}>
          {hero.games.toLocaleString()} pack games at {pct0(hero.win_rate)} — population data, not your history.
        </p>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <StatBlock value={pct0(hero.win_rate)} label="VS FIELD" teal />
        <StatBlock value={pct0(hero.pick_rate)} label="PICK RATE" />
      </div>
    </div>
  );
}

function MiniCard({ entry, muted }: { entry: TierEntry; muted: boolean }) {
  return (
    <div
      className="card3"
      data-testid={`cs-mini-${entry.champion}`}
      style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8, opacity: muted ? 0.74 : undefined }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 12,
            background: "linear-gradient(150deg,#4a5570,#232a3d)",
            display: "grid",
            placeItems: "center",
            font: "700 10px var(--font-mono)",
            color: "#cfd3e5",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          {initials(entry.champion)}
        </div>
        <div>
          <div style={{ font: "600 13px var(--font-mono)" }}>{entry.champion}</div>
          <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
            {entry.games} games · {entry.tier}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span
          className="pill"
          style={
            entry.win_rate >= 0.5
              ? { background: "var(--color-teal-low)", color: "var(--color-teal)" }
              : { background: "var(--color-danger-low)", color: "#f4c3ce" }
          }
        >
          {pct0(entry.win_rate)} field
        </span>
        <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
          {pct0(entry.pick_rate)} pick rate
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Tier {entry.tier} in the current pack.
      </p>
    </div>
  );
}

export function SuggestedPicks({ pack }: { pack: FindingsPack | undefined }) {
  const sorted = (pack?.tier_list ?? []).filter((t) => t.role === ROLE).sort((a, b) => b.win_rate - a.win_rate);
  const hero = sorted.find((t) => t.tier === "S" || t.tier === "A");
  const minis = sorted.filter((t) => t !== hero).slice(0, 3);
  const muted = minis.length ? minis[minis.length - 1].champion : null;
  const patch = pack?.dataset.patches[pack.dataset.patches.length - 1];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }} data-testid="card-suggested-picks">
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "#7a8098" }} />
        <span style={{ font: "700 11px var(--font-mono)", letterSpacing: ".12em", color: "var(--color-dim)" }}>
          SUGGESTED PICKS
        </span>
        <span
          className="pill"
          style={{ background: "var(--color-surface-2)", color: "var(--color-dim)", boxShadow: "var(--shadow-z1)" }}
        >
          Your pool
        </span>
        <span className="mono-n" style={{ marginLeft: "auto", fontSize: 10, color: "var(--color-dimmer)" }}>
          {patch ? `patch ${patch}` : "pack pending"}
        </span>
      </div>
      <p
        data-testid="honesty-caption"
        style={{ margin: "-6px 0 0", fontSize: 10, lineHeight: 1.5, color: "var(--color-dimmer)" }}
      >
        Counter-pick spread across every matchup ≈ ±2.5pp, empirical-Bayes shrunk — the smallest lever in the game.
        Read these as a nudge, not a verdict.
      </p>

      {hero ? (
        <HeroCard hero={hero} />
      ) : (
        <div className="card3" style={{ padding: 15, fontSize: 11, color: "var(--color-dim)" }}>
          No tier-list rows for {ROLE} yet.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        {minis.map((m) => (
          <MiniCard key={m.champion} entry={m} muted={m.champion === muted} />
        ))}
      </div>
    </div>
  );
}
