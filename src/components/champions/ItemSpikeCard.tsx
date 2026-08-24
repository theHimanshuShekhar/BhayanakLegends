import { useMemo } from "react";
import type { TrajectoryPoint } from "../../api/types";
import { patchOrder } from "../journal/format";
import { KickerRow } from "./bits";

interface PatchWr {
  patch: string;
  wr: number;
}

function perPatchWr(points: TrajectoryPoint[]): PatchWr[] {
  const latestByPatch = new Map<string, TrajectoryPoint>();
  for (const point of points) {
    const latest = latestByPatch.get(point.patch);
    if (!latest || point.index > latest.index) latestByPatch.set(point.patch, point);
  }
  return [...latestByPatch.values()]
    .sort((a, b) => patchOrder(a.patch) - patchOrder(b.patch))
    .map((point) => ({ patch: point.patch, wr: point.rolling_wr }));
}

function polylinePoints(rows: PatchWr[]): string {
  if (rows.length === 0) return "";
  const n = rows.length;
  const y = (wr: number) => Math.round(66 - Math.max(0, Math.min(1, wr)) * 60);
  if (n === 1) return `0,${y(rows[0].wr)} 300,${y(rows[0].wr)}`;
  return rows
    .map((p, i) => `${Math.round((i / (n - 1)) * 300)},${y(p.wr)}`)
    .join(" ");
}

export function ItemSpikeCard({ points }: { points: TrajectoryPoint[] }) {
  const rows = useMemo(() => perPatchWr(points), [points]);
  const labels = useMemo(() => {
    if (rows.length <= 4) return rows.map((r) => r.patch);
    const idx = [0, 1, 2, rows.length - 1].map((i) =>
      Math.min(rows.length - 1, Math.round((i / 3) * (rows.length - 1))),
    );
    return [...new Set(idx)].map((i) => rows[i].patch);
  }, [rows]);

  return (
    <div
      className="card3b"
      data-testid="item-spike-card"
      style={{ padding: 13, display: "flex", flexDirection: "column", gap: 8 }}
    >
      <KickerRow label="ITEM SPIKE TIMING" />
      {rows.length === 0 ? (
        <p
          style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}
          data-testid="item-spike-empty"
        >
          Item-completion timing lands with the Data-Dragon item refresh — until then this chart
          carries the rolling win rate per patch from your Personal History.
        </p>
      ) : (
        <>
          <svg
            viewBox="0 0 300 70"
            style={{ width: "100%", height: 64 }}
            preserveAspectRatio="none"
            data-testid="item-spike-svg"
          >
            <polyline
              points={polylinePoints(rows)}
              fill="none"
              stroke="#57cfb4"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
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
            {labels.map((patch) => (
              <span key={patch}>{patch}</span>
            ))}
          </div>
          <p style={{ margin: 0, fontSize: 9.5, lineHeight: 1.5, color: "var(--color-dim)" }}>
            <span style={{ color: "var(--color-teal)" }}>Solid</span> rolling win rate per patch
            from your Personal History · the controlled-for-team-gold line lands with the
            model-bearing pack.
          </p>
        </>
      )}
    </div>
  );
}
