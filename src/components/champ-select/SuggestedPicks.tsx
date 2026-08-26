import type { AssignedRole, FindingsPack, TierEntry } from "../../api/types";
import { formatCount, formatInitials, formatRate, formatUnavailable } from "../format";
import { SectionHead } from "../ui";
import { CS_ROLES } from "./shared";

function StatBlock({ value, label }: { value: string; label: string }) {
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
      {/* Findings Pack population stat: blue, never teal. */}
      <div className="mono-n" style={{ font: "700 17px var(--font-mono)", color: "var(--color-info)" }}>
        {value}
      </div>
      <div style={{ fontSize: 8.5, letterSpacing: ".1em", color: "var(--color-dimmer)" }}>{label}</div>
    </div>
  );
}

function HeroCard({ hero, role }: { hero: TierEntry; role: AssignedRole }) {
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
          color: "var(--color-bg)",
          boxShadow: "0 5px 0 rgba(0,0,0,.5),0 18px 30px -10px rgba(145,132,217,.6)",
        }}
      >
        {formatInitials(hero.champion)}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ font: "700 20px var(--font-mono)", letterSpacing: "-.02em" }}>{hero.champion}</span>
          <span className="pill" style={{ background: "var(--color-accent)", color: "var(--color-bg)" }}>
            Best pick
          </span>
          <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-soft-blue)" }}>
            {hero.tier} tier · {role}
          </span>
        </div>
        <p style={{ margin: "5px 0 0", fontSize: 11, lineHeight: 1.5, color: "var(--color-soft-lavender)", maxWidth: 420 }}>
          {formatCount(hero.games, "games")} from the Findings Pack at {formatRate(hero.win_rate)} — population data,
          not your history.
        </p>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <StatBlock value={formatRate(hero.win_rate)} label="VS FIELD" />
        <StatBlock value={formatRate(hero.pick_rate)} label="PICK RATE" />
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
            color: "var(--color-soft-text)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          {formatInitials(entry.champion)}
        </div>
        <div>
          <div style={{ font: "600 13px var(--font-mono)" }}>{entry.champion}</div>
          <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>
            {formatCount(entry.games, "games")} · {entry.tier}
          </div>
        </div>
      </div>
      {/* Both pills are Findings Pack population data: blue, regardless of framing. */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <span className="pill" style={{ background: "var(--color-info-low)", color: "var(--color-info)" }}>
          {formatRate(entry.win_rate)} field
        </span>
        <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-info)" }}>
          {formatRate(entry.pick_rate)} pick rate
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Tier {entry.tier} in the current pack.
      </p>
    </div>
  );
}

export function SuggestedPicks({
  pack,
  role,
  locked = false,
}: {
  pack: FindingsPack | undefined;
  role: AssignedRole | null;
  locked?: boolean;
}) {
  if (locked) return null;

  const validRole = role && CS_ROLES.includes(role) ? role : null;
  const sorted =
    validRole && pack
      ? pack.tier_list.filter((t) => t.role === validRole).sort((a, b) => b.win_rate - a.win_rate)
      : [];
  const hero = sorted.find((t) => t.tier === "S" || t.tier === "A");
  const minis = sorted.filter((t) => t !== hero).slice(0, 3);
  const muted = minis.length ? minis[minis.length - 1].champion : null;
  const patch = pack?.dataset.patches[pack.dataset.patches.length - 1];
  const unavailable = !validRole
    ? formatUnavailable("assigned role unavailable; suggestions are withheld")
    : !pack
      ? formatUnavailable(`Findings Pack unavailable for ${validRole}; suggestions are withheld`)
      : sorted.length === 0
        ? formatUnavailable(`Findings Pack has no rows for ${validRole}`)
        : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }} data-testid="card-suggested-picks">
      <SectionHead
        label="SUGGESTED PICKS"
        color="var(--color-dimmer)"
        right={
          <>
            {validRole && (
              <span
                className="pill"
                data-testid="suggested-role"
                style={{ background: "var(--color-accent-low)", color: "var(--color-accent)" }}
              >
                {validRole}
              </span>
            )}
            <span className="mono-n" style={{ fontSize: 10, color: "var(--color-dimmer)" }}>
              {patch ? `patch ${patch}` : formatUnavailable("Findings Pack patch")}
            </span>
          </>
        }
      />
      <p
        data-testid="honesty-caption"
        style={{ margin: "-6px 0 0", fontSize: 10, lineHeight: 1.5, color: "var(--color-dimmer)" }}
      >
        {unavailable ?? `Pre-lock guidance for ${validRole}: Findings Pack population data only — not your history.`}
      </p>

      {unavailable ? (
        <div className="card3" data-testid="suggestions-unavailable" style={{ padding: 15, fontSize: 11, color: "var(--color-dim)" }}>
          {unavailable}
        </div>
      ) : hero ? (
        <HeroCard hero={hero} role={validRole!} />
      ) : null}

      {!unavailable && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          {minis.map((m) => (
            <MiniCard key={m.champion} entry={m} muted={m.champion === muted} />
          ))}
        </div>
      )}
    </div>
  );
}
