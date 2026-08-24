import type { PackFinding } from "../../api/types";
import { Stat, Tag } from "../ui";

const PERCENT = /\d+(?:\.\d+)?%/g;

/**
 * Explains the lanes-ahead curve from the Findings Pack (diagnostic finding
 * `lanes_ahead`): winning probability at 0 lanes ahead vs 5. Numbers are read
 * verbatim from the pack statement — nothing is invented here. Diagnostic
 * phrasing only: the caption describes, it never instructs.
 */
export function LanesAheadMeter({ finding }: { finding: PackFinding | undefined }) {
  if (!finding) return null;
  const points = finding.statement.match(PERCENT) ?? [];
  if (points.length < 2) return null;
  return (
    <div data-testid="lanes-ahead">
      <p className="text-xs leading-relaxed text-dim">{finding.statement}</p>
      <div className="mt-3 flex items-center gap-4">
        <Stat label="0 ahead" value={points[0]} />
        <div
          aria-hidden
          className="h-1 flex-1 rounded-full bg-linear-to-r from-accent-low to-teal"
        />
        <Stat label="5 ahead" value={points[points.length - 1]} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-2">
        <span className="text-[10px] uppercase tracking-widest text-dimmer">spread beats stacked</span>
        <Tag verdict="info">diagnostic</Tag>
      </div>
    </div>
  );
}
