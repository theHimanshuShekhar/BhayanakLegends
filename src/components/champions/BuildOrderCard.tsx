import { KickerRow } from "./bits";

export function BuildOrderCard() {
  return (
    <div
      className="card3"
      data-testid="build-order-card"
      style={{
        padding: 13,
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <KickerRow label="BUILD ORDER · BETA-BINOMIAL SHRUNK" />
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Build analytics land after the Data-Dragon item refresh — the pack carries no item
        sequences yet.
      </p>
      <p
        style={{
          margin: "auto 0 0",
          fontSize: 9,
          lineHeight: 1.5,
          color: "var(--color-dimmer)",
        }}
      >
        Pending Data Dragon item-id refresh — treat as approximate v1.
      </p>
    </div>
  );
}
