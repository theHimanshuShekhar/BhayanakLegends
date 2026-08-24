import type { HabitDef } from "../../api/types";
import { Tag } from "../ui";

function effectLabel(effectPerSd: number): string {
  return `×${effectPerSd.toFixed(2)} per SD`;
}

export function HabitNudges({ habits }: { habits: HabitDef[] }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-4 shadow-z1" data-testid="habit-nudges">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[10px] uppercase tracking-widest text-accent">Habit nudges</div>
        <span className="text-[10px] uppercase tracking-widest text-dimmer">actionable</span>
      </div>
      {habits.length === 0 ? (
        <p className="mt-3 text-xs text-dim">Habit effects arrive with the next Findings Pack.</p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {habits.map((h) => (
            <li
              key={h.key}
              data-testid={`habit-nudge-${h.key}`}
              className="flex items-center justify-between gap-3"
            >
              <div>
                <div className="text-xs font-medium">{h.label}</div>
                <div className="font-mono text-[11px] text-teal">{effectLabel(h.effect_per_sd)}</div>
              </div>
              {/* These four habits are the pack's actionable tier: they may instruct. */}
              <Tag verdict="advice">advice</Tag>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
