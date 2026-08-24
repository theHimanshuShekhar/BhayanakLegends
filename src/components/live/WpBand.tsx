import type { FindingsPack } from "../../api/types";
import { pct, Tag } from "../ui";

function nearestBucket(pack: FindingsPack | undefined, clockS: number) {
  const rows = pack?.checkpoints ?? [];
  if (rows.length === 0) return null;
  let best = rows[0];
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const row of rows) {
    const minute = /@(\d+)m/.exec(row.gold_diff_bucket)?.[1];
    if (minute == null) continue;
    const distance = Math.abs(Number(minute) * 60 - clockS);
    // strict `<` keeps the earlier checkpoint on ties
    if (distance < bestDistance) {
      best = row;
      bestDistance = distance;
    }
  }
  return best;
}

export function WpBand({ pack, clockS }: { pack: FindingsPack | undefined; clockS: number }) {
  const bucket = nearestBucket(pack, clockS);
  return (
    <section className="rounded-lg border border-line bg-surface p-4 shadow-z1" data-testid="wp-band">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-accent">Win probability</div>
          <div className="mt-0.5 text-sm font-medium">Where this game stands</div>
        </div>
        <Tag verdict="info">Checkpoint estimate</Tag>
      </div>

      {bucket == null ? (
        <p className="mt-3 text-xs text-dim">Checkpoint table arrives with the next Findings Pack.</p>
      ) : (
        <>
          <div className="mt-3 font-mono text-2xl">{pct(bucket.win_rate)}</div>
          {/* Diagnostic, not advice (ADR-0003): a static checkpoint lookup describes
              population odds at similar states; it does not tell you what to do.
              The calibrated live model ships as a pack model artifact later. */}
          <div className="mt-1 text-[10px] uppercase tracking-widest text-dimmer">Diagnostic</div>
          <div className="mt-1 text-xs text-dim">Nearest checkpoint: {bucket.gold_diff_bucket}</div>
        </>
      )}
      <p className="mt-3 border-t border-line pt-3 text-[10px] leading-relaxed text-dimmer">
        Calibrated live model arrives with pack model artifacts. Until then this is the nearest
        population checkpoint, not your game's odds.
      </p>
    </section>
  );
}
