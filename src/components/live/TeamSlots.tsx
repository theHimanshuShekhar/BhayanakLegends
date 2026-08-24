// COMPLIANCE (Riot policy, long-standing): ranked enemy summoner names and tags
// must NEVER be rendered in champ select. Enemy slots are deliberately given no
// name-capable prop at all: LiveStatus carries no roster, so there is no data
// path for an enemy summoner name to reach these slots. Ally names are also
// unavailable at v1, so ally slots show role labels plus the session phase.
export type TeamSide = "ally" | "enemy";

const ROLES = ["TOP", "JGL", "MID", "BOT", "SUP"] as const;

function phaseChip(phase: string | null): { label: string; className: string } {
  if (!phase) return { label: "waiting", className: "bg-surface-3 text-dim" };
  const p = phase.toLowerCase();
  if (/lock|final|confirm/.test(p)) return { label: "locked", className: "bg-teal-low text-teal" };
  if (/hover|pick|plan|ban/.test(p)) return { label: "hover", className: "bg-accent-low text-accent" };
  return { label: p, className: "bg-surface-3 text-dim" };
}

export function TeamSlots({ side, phase }: { side: TeamSide; phase: string | null }) {
  const chip = phaseChip(phase);
  return (
    <div className="flex gap-2" data-testid={`team-slots-${side}`}>
      {ROLES.map((role) => (
        <div
          key={role}
          data-testid={`${side}-slot-${role}`}
          className={`flex flex-1 items-center justify-between gap-2 rounded-md border px-3 py-2 ${
            side === "enemy" ? "border-dashed border-line bg-deep" : "border-line bg-surface"
          }`}
        >
          <span className="text-[10px] uppercase tracking-widest text-dimmer">{role}</span>
          {side === "enemy" ? (
            <span className="font-mono text-xs text-dimmer">???</span>
          ) : (
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${chip.className}`}>
              {chip.label}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
