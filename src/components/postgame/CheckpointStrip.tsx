import type { PostGameDigest } from "../../api/types";
import { CardHead } from "./bits";
import { signed } from "./format";

/**
 * Checkpoint strip: signed gold deltas at 10/15/20, green when ahead, red
 * when behind. Diagnostic — describes what happened, never instructs.
 */
export function CheckpointStrip({ digest }: { digest: PostGameDigest | null }) {
  const c = digest?.checkpoints;
  const cells = [
    { key: "10", label: "GOLD @10", value: c?.gold_diff_10 },
    { key: "15", label: "GOLD @15", value: c?.gold_diff_15 },
    { key: "20", label: "GOLD @20", value: c?.gold_diff_20 },
  ];
  return (
    <section
      className="card3b"
      data-testid="checkpoint-strip"
      style={{ flex: "none", marginTop: 12, padding: 14 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
        <CardHead
          color="var(--color-info)"
          label="CHECKPOINTS · GOLD DIFFERENCE"
          right={
            <span style={{ font: "700 8px var(--font-mono)", letterSpacing: ".1em", color: "var(--color-dimmer)" }}>
              Diagnostic
            </span>
          }
        />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
        {cells.map((cell) => (
          <div
            key={cell.key}
            data-testid={`checkpoint-${cell.key}`}
            style={{
              padding: "8px 9px",
              borderRadius: 12,
              background: "var(--color-surface-2)",
              boxShadow: "var(--shadow-z1)",
            }}
          >
            <div style={{ fontSize: 8, letterSpacing: ".08em", color: "var(--color-dimmer)" }}>{cell.label}</div>
            <div
              className="mono-n"
              style={{
                font: "700 14px var(--font-mono)",
                color:
                  cell.value == null
                    ? "var(--color-dimmer)"
                    : cell.value >= 0
                      ? "var(--color-teal)"
                      : "var(--color-danger)",
              }}
            >
              {signed(cell.value == null ? null : Math.round(cell.value))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
