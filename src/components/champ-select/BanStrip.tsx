import { CS_ROLES, phaseChip } from "./shared";

function SlashTile({ plain = false }: { plain?: boolean }) {
  return (
    <div
      style={{
        width: 26,
        height: 26,
        borderRadius: 9,
        background: plain ? "#2b2f45" : "#22263a",
        boxShadow: "inset 0 2px 5px rgba(0,0,0,.6)",
        position: "relative",
      }}
    >
      {!plain && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: 9,
            background:
              "linear-gradient(45deg,transparent 46%,var(--color-danger) 46%,var(--color-danger) 54%,transparent 54%)",
            opacity: 0.45,
          }}
        />
      )}
    </div>
  );
}

function Divider() {
  return (
    <div
      style={{ flex: 1, height: 1, background: "linear-gradient(90deg,transparent,var(--color-line),transparent)" }}
    />
  );
}

function AllySlot({ role, chipLabel }: { role: string; chipLabel: string }) {
  return (
    <div
      data-testid={`ally-slot-${role}`}
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 14,
        background: "var(--color-surface-3)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          flex: "none",
          borderRadius: 10,
          background: "linear-gradient(150deg,#454a66,#22263a)",
          display: "grid",
          placeItems: "center",
          font: "700 12px var(--font-mono)",
          color: "#6a6f88",
        }}
      >
        ?
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ font: "600 11px var(--font-mono)" }}>{role}</div>
        <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>{chipLabel}</div>
      </div>
    </div>
  );
}

// COMPLIANCE (Riot policy): ranked enemy summoner names must never render in
// champ select. Enemy slots carry role labels only — LiveStatus exposes no
// roster, so no enemy name has a data path into this tree.
function EnemySlot({ role }: { role: string }) {
  return (
    <div
      data-testid={`enemy-slot-${role}`}
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px 6px 6px",
        borderRadius: 14,
        background: "var(--color-surface-3)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <div
        style={{
          width: 30,
          height: 30,
          flex: "none",
          borderRadius: 10,
          background: "linear-gradient(150deg,#5a3644,#2b1a22)",
          display: "grid",
          placeItems: "center",
          font: "700 12px var(--font-mono)",
          color: "#6a6f88",
        }}
      >
        ?
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ font: "600 11px var(--font-mono)" }}>{role}</div>
        <div style={{ fontSize: 9, color: "var(--color-dimmer)" }}>not revealed</div>
      </div>
    </div>
  );
}

function IdleBanner({ lastError }: { lastError: string | null }) {
  return (
    <div
      data-testid="cs-idle-banner"
      style={{
        flex: "none",
        borderRadius: 18,
        padding: "16px 14px",
        background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))",
        boxShadow: "var(--shadow-z2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-amber)", flex: "none" }}
        />
        <span style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          Ranked draft hides enemy summoner names — the app shows champion-level intel only.
        </span>
        <div
          className="pill"
          style={{
            marginLeft: "auto",
            background: "var(--color-surface-3)",
            color: "var(--color-dim)",
            boxShadow: "var(--shadow-z1)",
          }}
        >
          waiting for client
        </div>
      </div>
      {lastError && (
        <div
          data-testid="detection-status"
          style={{
            marginTop: 6,
            font: "600 9px var(--font-mono)",
            letterSpacing: ".06em",
            color: "var(--color-amber)",
          }}
        >
          client detection: {lastError}
        </div>
      )}
    </div>
  );
}

export function BanStrip({
  active,
  phase,
  lastError,
}: {
  active: boolean;
  phase: string | null;
  lastError: string | null;
}) {
  if (!active) return <IdleBanner lastError={lastError} />;
  const chip = phaseChip(phase);
  return (
    <div
      data-testid="cs-ban-strip"
      style={{
        flex: "none",
        borderRadius: 18,
        padding: "11px 14px 12px",
        background: "linear-gradient(180deg,var(--color-surface-2),var(--color-surface))",
        boxShadow: "var(--shadow-z2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 10 }}>
        <span className="kicker">BANS</span>
        <div style={{ display: "flex", gap: 5 }}>
          <SlashTile />
          <SlashTile />
          <SlashTile />
          <SlashTile />
          <SlashTile />
        </div>
        <Divider />
        <div className="pill mono-n" style={{ background: "var(--color-accent)", color: "#0e1020" }}>
          Champ select · {chip.label}
        </div>
        <Divider />
        <div style={{ display: "flex", gap: 5 }}>
          <SlashTile />
          <SlashTile />
          <SlashTile />
          <SlashTile />
          <SlashTile plain />
        </div>
        <span className="kicker">BANS</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1px 1fr", gap: 14, alignItems: "stretch" }}>
        <div style={{ display: "flex", gap: 7 }} data-testid="cs-ally-row">
          {CS_ROLES.map((role) => (
            <AllySlot key={role} role={role} chipLabel={chip.label} />
          ))}
        </div>
        <div style={{ background: "linear-gradient(180deg,transparent,var(--color-line),transparent)" }} />
        <div style={{ display: "flex", gap: 7 }} data-testid="cs-enemy-row">
          {CS_ROLES.map((role) => (
            <EnemySlot key={role} role={role} />
          ))}
        </div>
      </div>

      <div
        style={{
          marginTop: 9,
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "7px 11px",
          borderRadius: 999,
          background: "rgba(10,11,22,.5)",
          boxShadow: "inset 0 2px 5px rgba(0,0,0,.5)",
        }}
      >
        <span
          style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-amber)", flex: "none" }}
        />
        <span style={{ fontSize: 10, lineHeight: 1.4, color: "var(--color-dim)" }}>
          Ranked draft hides enemy summoner names until the loading screen — everything on the right is
          champion-level only.
        </span>
      </div>
    </div>
  );
}
