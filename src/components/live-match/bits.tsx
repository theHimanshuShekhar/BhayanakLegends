import type { ReactNode } from "react";

export function Dot({ color, glow = false }: { color: string; glow?: boolean }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: 999,
        background: color,
        flex: "none",
        boxShadow: glow ? `0 0 8px ${color}` : undefined,
      }}
    />
  );
}

export function CardHead({
  color,
  label,
  right,
  spacing = ".11em",
  size = "700 9.5px var(--font-mono)",
}: {
  color: string;
  label: string;
  right?: ReactNode;
  spacing?: string;
  size?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Dot color={color} />
      <span style={{ font: size, letterSpacing: spacing, color: "var(--color-dim)" }}>{label}</span>
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

export function clockLabel(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
