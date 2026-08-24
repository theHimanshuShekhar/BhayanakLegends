import { pct } from "../ui";

export interface TrendPoint {
  label: string;
  value: number; // 0..1
}

const W = 560;
const H = 160;
const PAD = { top: 12, right: 14, bottom: 24, left: 34 };

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) =>
    points.length <= 1 ? PAD.left + innerW / 2 : PAD.left + (i * innerW) / (points.length - 1);
  const y = (v: number) => PAD.top + (1 - Math.min(1, Math.max(0, v))) * innerH;

  const grid = [0, 0.5, 1];
  const path = points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-40 w-full"
      role="img"
      aria-label="rolling win rate per patch"
      data-testid="trend-chart"
    >
      {grid.map((g) => (
        <g key={g}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(g)}
            y2={y(g)}
            stroke="currentColor"
            className="text-line"
            strokeWidth="1"
          />
          <text x={PAD.left - 6} y={y(g) + 3} textAnchor="end" className="fill-dimmer font-mono text-[9px]">
            {Math.round(g * 100)}%
          </text>
        </g>
      ))}
      {points.length > 1 && (
        <polyline
          points={path}
          fill="none"
          stroke="currentColor"
          className="text-accent"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}
      {points.map((p, i) => (
        <circle
          key={`${p.label}-${i}`}
          data-testid={`trend-dot-${i}`}
          cx={x(i)}
          cy={y(p.value)}
          r="4"
          fill="currentColor"
          className="text-accent"
        >
          <title>{`${p.label} — ${pct(p.value)}`}</title>
        </circle>
      ))}
      {points.map((p, i) => (
        <text
          key={`label-${p.label}-${i}`}
          x={x(i)}
          y={H - 6}
          textAnchor="middle"
          className="fill-dim font-mono text-[9px]"
        >
          {p.label}
        </text>
      ))}
    </svg>
  );
}
