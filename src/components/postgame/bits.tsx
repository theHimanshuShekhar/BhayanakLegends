import type { ReactNode } from "react";

export function Dot({ color }: { color: string }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 999,
        background: color,
        flex: "none",
      }}
    />
  );
}

export function CardHead({ color, label, right }: { color: string; label: string; right?: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Dot color={color} />
      <span
        style={{ font: "700 9.5px var(--font-mono)", letterSpacing: ".11em", color: "var(--color-dim)" }}
      >
        {label}
      </span>
      {right != null && (
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>{right}</div>
      )}
    </div>
  );
}

export function pp(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}pp`;
}
