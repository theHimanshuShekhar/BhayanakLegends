import type { CSSProperties, ReactNode } from "react";

export function KickerRow({
  label,
  dot = "var(--color-info)",
  right,
}: {
  label: string;
  dot?: string;
  right?: ReactNode;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: 999,
          background: dot,
          flex: "none",
        }}
      />
      <span className="kicker" style={{ fontSize: 9.5 }}>
        {label}
      </span>
      {right != null && <span style={{ marginLeft: "auto" }}>{right}</span>}
    </div>
  );
}

export function RailHeader({ label, right }: { label: string; right?: ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
      }}
    >
      <span
        style={{
          font: "700 9.5px var(--font-mono)",
          letterSpacing: ".14em",
          color: "var(--color-dim)",
        }}
      >
        {label}
      </span>
      {right}
    </div>
  );
}

export function captionStyle(marginTop = 0): CSSProperties {
  return {
    margin: `${marginTop} 0 0`,
    fontSize: 9,
    lineHeight: 1.5,
    color: "var(--color-dimmer)",
  };
}
