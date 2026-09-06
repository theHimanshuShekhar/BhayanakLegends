import { SectionHead } from "../ui";

export function LeakPanel() {
  return (
    <div
      data-testid="deaths-panel"
      style={{
        padding: 15,
        borderRadius: 22,
        background: "linear-gradient(160deg,#2d1c28,var(--color-surface) 68%)",
        boxShadow: "var(--shadow-z2)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 0,
      }}
    >
      <SectionHead
        level={3}
        label="DEATHS BY GAME MINUTE"
        color="var(--color-dimmer)"
        dot={false}
        right={
          <span className="pill" style={{ background: "var(--color-surface-3)", color: "var(--color-dim)" }}>
            Idle
          </span>
        }
      />
      <p
        style={{
          margin: "auto 0 0",
          fontSize: 10.5,
          lineHeight: 1.55,
          color: "var(--color-dim)",
        }}
        data-testid="deaths-idle-caption"
      >
        Unavailable: timeline features are not in the Findings Pack — sync games from the History
        tab to populate this panel.
      </p>
    </div>
  );
}
