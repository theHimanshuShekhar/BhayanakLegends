// No champion-specific source exists yet: this card is read-only and does not
// display a recommendation or pretend to write to the live client.
export function LoadoutCard() {
  return (
    <div className="card3" data-testid="card-loadout" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-accent)" }} />
        <span style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}>
          LOADOUT · READ-ONLY
        </span>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <div style={{ flex: 1, padding: "7px 9px", borderRadius: 11, background: "var(--color-surface-2)", boxShadow: "var(--shadow-z1)" }}>
          <div style={{ fontSize: 8.5, letterSpacing: ".1em", color: "var(--color-dimmer)" }}>KEYSTONE</div>
          <div style={{ font: "600 11px var(--font-mono)" }}>—</div>
        </div>
        <div style={{ flex: 1, padding: "7px 9px", borderRadius: 11, background: "var(--color-surface-2)", boxShadow: "var(--shadow-z1)" }}>
          <div style={{ fontSize: 8.5, letterSpacing: ".1em", color: "var(--color-dimmer)" }}>SUMMS</div>
          <div style={{ font: "600 11px var(--font-mono)" }}>—</div>
        </div>
      </div>
      <p
        style={{ margin: 0, fontSize: 8.5, lineHeight: 1.4, color: "var(--color-dimmer)" }}
        data-testid="cs-loadout-unavailable"
      >
        Unavailable: no champion-specific loadout source exists.
      </p>
      <div style={{ marginTop: "auto", display: "flex", gap: 7 }}>
        <button
          type="button"
          disabled
          data-testid="cs-apply-loadout"
          style={{
            flex: 1,
            padding: 9,
            borderRadius: 999,
            border: "none",
            background: "var(--color-accent)",
            color: "#0e1020",
            font: "700 11px var(--font-mono)",
            textAlign: "center",
            boxShadow: "0 3px 0 var(--color-accent-low),0 12px 20px -8px rgba(145,132,217,.55)",
            opacity: 0.55,
            cursor: "not-allowed",
          }}
        >
          Loadout unavailable
        </button>
      </div>
    </div>
  );
}
