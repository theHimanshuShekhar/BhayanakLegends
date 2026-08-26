import { useMemo } from "react";
import type { PatchAggregate, TrajectoryPoint } from "../../api/types";
import { formatRate as pct } from "../format";
import { KickerRow } from "./bits";

function chronological(points: TrajectoryPoint[]): TrajectoryPoint[] {
  return [...points].sort(
    (a, b) => a.played_at.localeCompare(b.played_at) || a.index - b.index,
  );
}

function polylinePoints(points: TrajectoryPoint[]): {
  points: string;
  single: { x: number; y: number } | null;
} {
  if (points.length === 0) return { points: "", single: null };
  const n = points.length;
  const y = (wr: number) => Math.round(66 - Math.max(0, Math.min(1, wr)) * 60);
  const x = (index: number) => (n === 1 ? 150 : Math.round((index / (n - 1)) * 300));
  const coords = points.map((point, index) => `${x(index)},${y(point.rolling_wr)}`);
  return {
    points: coords.join(" "),
    single: n === 1 ? { x: x(0), y: y(points[0].rolling_wr) } : null,
  };
}

function ErrorLine({ source, message }: { source: string; message: string }) {
  return (
    <p style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-danger)" }}>
      {source}: {message}
    </p>
  );
}

export function TrajectoryCard({
  champion,
  points,
  aggregates,
  trajectoryError,
  aggregateError,
  trajectoryLoading = false,
}: {
  champion: string | null;
  points: TrajectoryPoint[];
  aggregates: PatchAggregate[];
  trajectoryError?: string | null;
  aggregateError?: string | null;
  trajectoryLoading?: boolean;
}) {
  const rows = useMemo(() => chronological(points), [points]);
  const { points: poly, single } = useMemo(() => polylinePoints(rows), [rows]);
  const labelIndices = useMemo(() => {
    if (rows.length <= 4) return rows.map((_, index) => index);
    return [0, 1, 2, 3].map((index) =>
      Math.round((index / 3) * (rows.length - 1)),
    );
  }, [rows]);

  return (
    <div
      className="card3b"
      data-testid="trajectory-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <KickerRow label="TRAJECTORY · PERSONAL HISTORY" />
      {!champion ? (
        <p
          style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}
          data-testid="trajectory-selection-guidance"
        >
          Select a champion from the role tier list to view Personal History.
        </p>
      ) : trajectoryLoading ? (
        <p
          style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}
          data-testid="trajectory-loading"
        >
          Loading Personal History…
        </p>
      ) : trajectoryError ? (
        <ErrorLine source="Trajectory" message={trajectoryError} />
      ) : rows.length === 0 ? (
        <p
          style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}
          data-testid="trajectory-empty"
        >
          Backfill has no Personal History for {champion} yet.
        </p>
      ) : (
        <>
          <svg
            viewBox="0 0 300 70"
            style={{ width: "100%", height: 64 }}
            preserveAspectRatio="none"
            data-testid="trajectory-svg"
          >
            {single ? (
              <circle cx={single.x} cy={single.y} r="4.5" fill="#57cfb4" />
            ) : (
              <polyline
                points={poly}
                fill="none"
                stroke="#57cfb4"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}
          </svg>
          <div
            className="mono-n"
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 8.5,
              color: "var(--color-dimmer)",
            }}
          >
            {labelIndices.map((index) => (
              <span key={`${rows[index].played_at}-${rows[index].index}-${index}`}>
                {rows[index].patch}
              </span>
            ))}
          </div>
        </>
      )}

      {champion && aggregateError && <ErrorLine source="Patch aggregates" message={aggregateError} />}
      {champion && !aggregateError && aggregates.length > 0 && (
        <div
          data-testid="trajectory-aggregates"
          style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 2 }}
        >
          <div style={{ fontSize: 9.5, letterSpacing: ".08em", color: "var(--color-dim)" }}>
            PATCH SUMMARIES · PERSONAL HISTORY
          </div>
          {aggregates.map((aggregate) => (
            <div
              key={aggregate.patch}
              style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5 }}
            >
              <span className="mono-n">{aggregate.patch}</span>
              <span className="mono-n" style={{ color: "var(--color-dim)" }}>
                {aggregate.wins} wins · {aggregate.games} games · {pct(aggregate.win_rate)}
              </span>
            </div>
          ))}
        </div>
      )}
      {champion && (
        <p style={{ margin: "auto 0 0", fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dimmer)" }}>
          Both surfaces are Personal History; patch summaries are sourced from true aggregates.
        </p>
      )}
    </div>
  );
}
