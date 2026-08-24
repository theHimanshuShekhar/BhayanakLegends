import { CS_ROLES, phaseChip } from "./shared";

// Teammate champions + mastery badges are live-session data the sidecar does
// not expose at v1, so the roster renders champion-level placeholders (active:
// role rows with the session phase; idle: waiting rows). No summoner names
// ever render here.
export function YourSideCard({ active, phase }: { active: boolean; phase: string | null }) {
  const chip = phaseChip(phase);
  const rows: string[] = active ? [...CS_ROLES] : ["?", "?", "?"];
  return (
    <div className="card3" data-testid="cs-your-side" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-amber)" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          YOUR SIDE · RANKED
        </span>
      </div>
      {rows.map((r, i) => (
        <div
          key={`${r}-${i}`}
          data-testid={active ? `cs-side-slot-${r}` : undefined}
          style={{ display: "flex", alignItems: "center", gap: 9, opacity: active ? undefined : 0.6 }}
        >
          <div
            style={{
              width: 24,
              height: 24,
              borderRadius: 8,
              background: "linear-gradient(150deg,#454a66,#22263a)",
              display: "grid",
              placeItems: "center",
              font: "700 8px var(--font-mono)",
              color: "#b2b6ca",
            }}
          >
            ?
          </div>
          <div style={{ flex: 1, fontSize: 10, minWidth: 0 }}>{active ? r : "—"}</div>
          {active ? (
            <span className="pill" style={{ background: chip.bg, color: chip.color }}>
              {chip.label}
            </span>
          ) : (
            <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
              —
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
