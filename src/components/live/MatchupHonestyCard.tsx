import type { FindingsPack, FindingTier, PackFinding } from "../../api/types";
import { Stat, Tag } from "../ui";

const PERCENT = /\d+(?:\.\d+)?%/g;

function percents(s: string): string[] {
  return s.match(PERCENT) ?? [];
}

function tierTag(tier: FindingTier) {
  // ADR-0003 phrasing discipline: actionable/a-lite findings may instruct;
  // diagnostic findings only describe. Statements render verbatim from the
  // pack so the tier-appropriate wording is never rewritten here.
  return tier === "diagnostic" ? (
    <Tag verdict="info">diagnostic</Tag>
  ) : (
    <Tag verdict="advice">{tier}</Tag>
  );
}

function ppDelta(f: PackFinding): string | null {
  if (f.value == null || !f.unit) return null;
  const sign = f.value >= 0 ? "+" : "";
  return `${sign}${f.value}${f.unit}`;
}

export function MatchupHonestyCard({ pack }: { pack: FindingsPack | undefined }) {
  const counterpick = pack?.findings.find((f) => f.key === "counterpick_spread");
  const mastery = pack?.findings.find((f) => f.key === "mastery_premium");
  const masteryPair = mastery ? percents(mastery.statement) : [];
  const delta = mastery ? ppDelta(mastery) : null;

  return (
    <section
      className="rounded-lg border border-line bg-surface p-4 shadow-z1"
      data-testid="card-matchup-honesty"
    >
      <div className="text-[10px] uppercase tracking-widest text-accent">Matchup honesty</div>
      <h2 className="mt-0.5 text-sm font-medium">What counter-picking is worth</h2>

      {counterpick && (
        <div className="mt-3">
          <div className="flex items-start justify-between gap-2">
            <div className="text-xs font-medium">{counterpick.title}</div>
            {tierTag(counterpick.tier)}
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-dim">{counterpick.statement}</p>
          {counterpick.value != null && counterpick.unit && (
            <div className="mt-2">
              <Stat label="Total spread" value={`±${Math.abs(counterpick.value)}${counterpick.unit}`} />
            </div>
          )}
        </div>
      )}

      {mastery && (
        <div className="mt-4 border-t border-line pt-3">
          <div className="flex items-start justify-between gap-2">
            <div className="text-xs font-medium">{mastery.title}</div>
            {tierTag(mastery.tier)}
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-dim">{mastery.statement}</p>
          {masteryPair.length >= 2 && (
            <div className="mt-3 flex gap-5">
              <Stat label="Pocket pick win rate" value={masteryPair[0]} />
              <Stat label="Rest win rate" value={masteryPair[1]} />
              {delta && <Stat label="Premium" value={delta} />}
            </div>
          )}
        </div>
      )}

      {!counterpick && !mastery && (
        <p className="mt-3 text-xs text-dim">Matchup findings arrive with the next Findings Pack.</p>
      )}
    </section>
  );
}
