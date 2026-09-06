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
