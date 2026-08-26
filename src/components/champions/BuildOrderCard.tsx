import { SectionHead } from "../ui";

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
      <SectionHead label="BUILD ORDER · BETA-BINOMIAL SHRUNK" />
      <p style={{ margin: 0, fontSize: 10, lineHeight: 1.5, color: "var(--color-dim)" }}>
        Unavailable: the Findings Pack carries no item-sequence features.
      </p>
    </div>
  );
}
