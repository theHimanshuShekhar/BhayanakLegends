import type { RoleBenchmark } from "../../api/types";

function deltaLabel(delta: number): string {
  return delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1);
}

export function BenchmarkCards({ rows }: { rows: RoleBenchmark[] }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        gap: 12,
      }}
      data-testid="benchmark-cards"
    >
      {rows.map((r) => {
        const personal = r.personal.cs10;
        const median = r.population.cs10_median;
        const delta = personal != null && median != null ? personal - median : null;
        const good = (delta ?? 0) >= 0;
        const scale =
          personal != null && median != null && Math.max(personal, median) > 0
            ? Math.max(personal, median)
            : null;
        const fill =
          scale != null && personal != null
            ? `${Math.round((personal / scale) * 1000) / 10}%`
            : "0%";
        const tick =
          scale != null && median != null
            ? `${Math.round((median / scale) * 1000) / 10}%`
            : null;
        return (
          <div className="card3" style={{ padding: 11 }} key={r.role} data-testid={`benchmark-${r.role}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ fontSize: 9, letterSpacing: ".08em", color: "var(--color-dimmer)" }}>
                CS@10 · {r.role}
              </span>
              {delta != null && (
                <span
                  className="pill"
                  style={{
                    background: good ? "var(--color-teal-low)" : "var(--color-danger-low)",
                    color: good ? "var(--color-teal)" : "#f4c3ce",
                    padding: "2px 7px",
                  }}
                >
                  {deltaLabel(delta)}
                </span>
              )}
            </div>
            <div
              className="mono-n"
              style={{
                font: "700 25px/1.1 var(--font-mono)",
                marginTop: 6,
                color:
                  personal == null
                    ? "var(--color-dim)"
                    : good
                      ? undefined
                      : "var(--color-danger)",
              }}
            >
              {personal != null ? personal.toFixed(1) : "—"}
            </div>
            <div
              data-testid={`benchmark-bar-${r.role}`}
              style={{
                position: "relative",
                marginTop: 8,
                height: 6,
                borderRadius: 999,
                background: "var(--color-deep)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: fill,
                  height: "100%",
                  background: good ? "var(--color-teal)" : "var(--color-danger)",
                }}
              />
              {tick != null && (
                <div
                  title={`population median ${median}`}
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: tick,
                    width: 2,
                    background: "var(--color-dimmer)",
                  }}
                />
              )}
            </div>
            <div style={{ marginTop: 6, fontSize: 9, color: "var(--color-dimmer)" }}>
              pop median {median ?? "—"} · {Math.round(r.population.sample / 1000)}k games
            </div>
          </div>
        );
      })}
    </div>
  );
}
