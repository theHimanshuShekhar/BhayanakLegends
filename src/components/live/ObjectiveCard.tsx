import { Stat, Tag } from "../ui";

export interface ObjectiveStat {
  label: string;
  value: string;
}

export function ObjectiveCard({
  objective,
  headline,
  stats,
  takeaway,
  actionable = false,
}: {
  objective: string;
  headline: string;
  stats: ObjectiveStat[];
  takeaway: string;
  /** Only findings tagged advice may instruct (ADR-0003); takeaways stay descriptive otherwise. */
  actionable?: boolean;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4" data-testid={`objective-${objective.toLowerCase()}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-dimmer">{objective}</div>
          <div className="mt-0.5 text-sm font-medium">{headline}</div>
        </div>
        {actionable && <Tag verdict="advice">advice</Tag>}
      </div>
      <div className="mt-3 flex gap-5">
        {stats.map((s) => (
          <Stat key={s.label} label={s.label} value={s.value} />
        ))}
      </div>
      {takeaway && (
        <p className="mt-3 text-xs leading-relaxed text-dim">{takeaway}</p>
      )}
    </div>
  );
}
