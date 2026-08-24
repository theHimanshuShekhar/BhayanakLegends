import type { BanAdvice, FindingsPack } from "../../api/types";
import { pct, Tag } from "../ui";

function adviceTag(rec: BanAdvice["recommendation"]) {
  if (rec === "real-threat") return <Tag verdict="advice">Recommend ban</Tag>;
  if (rec === "fear-ban") return <Tag verdict="advice">Fear ban</Tag>;
  return <Tag verdict="neutral">skip</Tag>;
}

export function BanAdvisorCard({ pack }: { pack: FindingsPack | undefined }) {
  const rows = [...(pack?.ban_advisor ?? [])].sort((a, b) => b.win_rate - a.win_rate);
  const traps = pack?.trap_picks ?? [];
  return (
    <section
      className="rounded-lg border border-line bg-surface p-4 shadow-z1"
      data-testid="card-ban-advisor"
    >
      <div className="text-[10px] uppercase tracking-widest text-accent">Ban advisor</div>
      <h2 className="mt-0.5 text-sm font-medium">Real threats by population win rate</h2>
      {rows.length === 0 ? (
        <p className="mt-3 text-xs text-dim">Ban advisor arrives with the next Findings Pack.</p>
      ) : (
        <table className="mt-3 w-full text-left">
          <thead>
            <tr className="text-[10px] uppercase tracking-widest text-dimmer">
              <th className="pb-1 font-normal">Champion</th>
              <th className="pb-1 text-right font-normal">WR</th>
              <th className="pb-1 text-right font-normal">BR</th>
              <th className="pb-1" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.champion} data-testid={`ban-advisor-row-${r.champion}`} className="border-t border-line">
                <td className="py-1.5 text-xs font-medium">{r.champion}</td>
                <td className="py-1.5 text-right font-mono text-xs">{pct(r.win_rate)}</td>
                <td className="py-1.5 text-right font-mono text-xs text-dim">{pct(r.ban_rate)}</td>
                <td className="py-1.5 pl-3 text-right">{adviceTag(r.recommendation)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="mt-4 rounded-md border border-dashed border-line bg-deep p-3">
        <div className="text-[10px] uppercase tracking-widest text-dimmer">Trap picks</div>
        {traps.length === 0 ? (
          <p className="mt-2 text-xs text-dim">No trap-pick table in this pack.</p>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {traps.map((t) => (
              <li key={t.champion} className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium">{t.champion}</span>
                <span className="flex items-center gap-3">
                  <span className="font-mono text-xs text-danger">{pct(t.win_rate)}</span>
                  <Tag verdict="neutral">trap</Tag>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
