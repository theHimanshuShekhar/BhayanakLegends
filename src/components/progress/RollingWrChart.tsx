import type { CSSProperties } from "react";
import type { PatchAggregate } from "../../api/types";

export type WrPoint = PatchAggregate;

function chartPath(points: WrPoint[]): { line: string; area: string; poly: string; single: { x: number; y: number } | null } {
  if (points.length === 0) return { line: "", area: "", poly: "", single: null };
  const n = points.length;
  const x = (i: number) => (n === 1 ? 310 : Math.round((i / (n - 1)) * 620));
  const y = (wr: number) => Math.round(96 - Math.max(0, Math.min(1, wr)) * 88);
  const coords = points.map((p, i) => `${x(i)},${y(p.win_rate)}`);
  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c}`).join(" ");
  const area = `${line} L620,100 L0,100 Z`;
  return {
    line,
    area,
    poly: coords.join(" "),
    single: n === 1 ? { x: x(0), y: y(points[0].win_rate) } : null,
  };
}

function direction(points: WrPoint[]): { label: string; style: CSSProperties } | null {
  if (points.length < 2) return null;
  const first = points[0].win_rate;
  const last = points[points.length - 1].win_rate;
  if (last > first + 0.005)
    return { label: "Climbing", style: { background: "var(--color-teal-low)", color: "var(--color-teal)" } };
  if (last < first - 0.005)
    return { label: "Sliding", style: { background: "var(--color-danger-low)", color: "#f4c3ce" } };
  return { label: "Flat", style: { background: "var(--color-surface-3)", color: "var(--color-dim)" } };
}

export function RollingWrChart({ points }: { points: WrPoint[] }) {
  const { area, poly, single } = chartPath(points);
  const dir = direction(points);
  const totalGames = points.reduce((acc, p) => acc + p.games, 0);

  return (
    <div
      className="card3b"
      data-testid="rolling-wr-chart"
      style={{ padding: 15, display: "flex", flexDirection: "column" }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span
          style={{
            font: "700 9.5px var(--font-mono)",
            letterSpacing: ".14em",
            color: "var(--color-dim)",
          }}
        >
          PATCH WIN RATE · PERSONAL HISTORY
        </span>
        {dir && <span className="pill" style={dir.style}>{dir.label}</span>}
      </div>

      {points.length === 0 ? (
        <div data-testid="empty-state" style={{ padding: "26px 4px", textAlign: "center" }}>
          <div style={{ fontSize: 12, fontWeight: 500 }}>No tracked games yet</div>
          <p style={{ margin: "4px auto 0", maxWidth: 420, fontSize: 10.5, color: "var(--color-dim)" }}>
            Once Backfill downloads matches from the History tab, your true patch win rates show
            up here.
          </p>
        </div>
      ) : (
        <>
          <svg
            viewBox="0 0 620 100"
            style={{ width: "100%", height: 88, marginTop: 6 }}
            preserveAspectRatio="none"
            data-testid="rolling-wr-svg"
          >
            <defs>
              <linearGradient id="bl-wr-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#9184d9" stopOpacity=".45" />
                <stop offset="1" stopColor="#9184d9" stopOpacity="0" />
              </linearGradient>
            </defs>
            {single ? (
              <circle cx={single.x} cy={single.y} r="5" fill="#9184d9" />
            ) : (
              <>
                <path d={area} fill="url(#bl-wr-fill)" />
                <polyline
                  points={poly}
                  fill="none"
                  stroke="#9184d9"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              </>
            )}
          </svg>
          <div
            className="mono-n"
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 9,
              color: "var(--color-dimmer)",
            }}
          >
            {points.map((p) => (
              <span key={p.patch}>{p.patch}</span>
            ))}
          </div>
          <p
            style={{
              margin: "6px 0 0",
              fontSize: 9,
              lineHeight: 1.5,
              color: "var(--color-dimmer)",
            }}
          >
            True games in the patch/role-known Personal History subset: {totalGames.toLocaleString()}
            — never summed from overlapping Trajectory windows.
          </p>
        </>
      )}
    </div>
  );
}
