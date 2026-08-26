import type { AssignedRole, FindingsPack, TierEntry } from "../../api/types";
export const CS_ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] as const;

export function initials(name: string): string {
  return name.replace(/[^a-zA-Z]/g, "").slice(0, 2).toUpperCase();
}

export function pct0(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

export function pct1(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export function pickHero(pack: FindingsPack | undefined, role: AssignedRole | null): TierEntry | undefined {
  if (!role) return undefined;
  return (pack?.tier_list ?? [])
    .filter((t) => t.role === role)
    .sort((a, b) => b.win_rate - a.win_rate)
    .find((t) => t.tier === "S" || t.tier === "A");
}

export interface PhaseChip {
  label: string;
  bg: string;
  color: string;
}

export function phaseChip(phase: string | null): PhaseChip {
  if (!phase) return { label: "waiting", bg: "var(--color-surface-3)", color: "var(--color-dim)" };
  const p = phase.toLowerCase();
  if (/lock|final|confirm/.test(p))
    return { label: "locked", bg: "var(--color-teal-low)", color: "var(--color-teal)" };
  if (/hover|pick|plan|ban/.test(p))
    return { label: "hover", bg: "var(--color-accent-low)", color: "var(--color-accent)" };
  return { label: p, bg: "var(--color-surface-3)", color: "var(--color-dim)" };
}
