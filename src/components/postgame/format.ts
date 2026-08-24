export function fmtDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export function signed(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : "-"}${Math.abs(v).toLocaleString("en-US")}`;
}

export function initials(champion: string): string {
  return champion.slice(0, 2).toUpperCase();
}

export function fmtK(g: number): string {
  return g >= 1000 ? `${(g / 1000).toFixed(g % 1000 === 0 ? 0 : 1)}k` : `${g}`;
}
