import type { AssignedRole, CellState } from "../../api/types";

export type FindingsPackState = "loading" | "available" | "missing" | "error";

export interface ChampSelectAllyView {
  cell_id: number;
  champion: string | null;
  name: string | null;
  is_local: boolean;
  state: CellState;
}

export interface ChampSelectSessionView {
  active: boolean;
  assignedRole: AssignedRole | null;
  allies: ChampSelectAllyView[];
  localCell: ChampSelectAllyView | null;
  localChampion: string | null;
  locked: boolean;
  knownAlliedPicks: ChampSelectAllyView[];
  pickedCount: number;
}

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
