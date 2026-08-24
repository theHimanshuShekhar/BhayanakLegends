import { usePostgameLatest } from "../api/hooks";
import "../components/journal/kicker.css";
import { PageHeader } from "../components/Layout";
import { CaveatFooter } from "../components/journal/CaveatFooter";
import { fmtClock, fmtDuration, signed } from "../components/journal/format";
import { Card, EmptyState, Stat, Tag } from "../components/ui";
import type { HabitOutcome } from "../api/types";

function CheckpointCard({ label, gold }: { label: string; gold: number | null }) {
  const tone = gold == null ? "text-dim" : gold >= 0 ? "text-teal" : "text-danger";
  return (
    <Card kicker="Diagnostic" className="flex-1">
      <Stat label={label} value={<span className={tone}>{signed(gold)}</span>} />
    </Card>
  );
}

function HabitRow({ habit }: { habit: HabitOutcome }) {
  const tag =
    habit.verdict === "good" ? (
      <Tag verdict="good">good</Tag>
    ) : habit.verdict === "bad" ? (
      <Tag verdict="bad">bad</Tag>
    ) : habit.verdict === "n/a" ? (
      <Tag verdict="neutral">n/a</Tag>
    ) : (
      <Tag verdict="neutral">neutral</Tag>
    );
  return (
    <li className="flex items-center justify-between gap-3 border-b border-line py-2 last:border-b-0">
      <span className="text-xs">{habit.label}</span>
      <span className="ml-auto font-mono text-xs text-dim">{habit.value}</span>
      {tag}
    </li>
  );
}

export function PostGamePage() {
  const query = usePostgameLatest();

  return (
    <div>
      <PageHeader kicker="Improvement Journal" title="Post-game digest" />
      {query.isLoading && <div className="text-xs text-dim">loading…</div>}
      {query.isError && (
        <div className="text-xs text-danger">
          The sidecar isn't reachable — open the app again or check the connection dot.
        </div>
      )}
      {query.data === null && (
        <EmptyState
          title="No games analyzed yet"
          body="Play a game with the app running, or import your history from the History tab."
        />
      )}
      {query.data && (
        <div className="max-w-3xl space-y-4">
          <Card>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <h2 className="text-base font-medium">{query.data.champion}</h2>
              <span className="text-[10px] uppercase tracking-widest text-dim">
                {query.data.role}
              </span>
              {query.data.win ? <Tag verdict="good">WIN</Tag> : <Tag verdict="bad">LOSS</Tag>}
              <span className="ml-auto font-mono text-xs text-dim" data-testid="digest-duration">
                {fmtDuration(query.data.duration_s)}
              </span>
              <span className="font-mono text-[10px] text-dimmer">
                {fmtClock(query.data.played_at)}
              </span>
            </div>

            <blockquote className="mt-3 border-l-2 border-accent pl-3 text-sm" data-testid="digest-headline">
              {query.data.headline}
            </blockquote>
          </Card>

          <Card kicker="Checkpoints" title="Gold difference at 10 / 15 / 20 minutes">
            <p className="mb-3 text-[10px] uppercase tracking-widest text-dimmer">
              Diagnostic · describes what happened
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <CheckpointCard label="Gold @10" gold={query.data.checkpoints.gold_diff_10} />
              <CheckpointCard label="Gold @15" gold={query.data.checkpoints.gold_diff_15} />
              <CheckpointCard label="Gold @20" gold={query.data.checkpoints.gold_diff_20} />
            </div>
          </Card>

          <Card kicker="Habits" title="How the game lined up with the pack's habits">
            <ul data-testid="habit-outcomes">
              {query.data.habits.map((h) => (
                <HabitRow key={h.key} habit={h} />
              ))}
            </ul>
          </Card>

          <p className="text-xs text-dim">
            Older games arrive through Backfill — start it from the History tab.
          </p>

          <CaveatFooter />
        </div>
      )}
    </div>
  );
}
