import type { ReactNode } from "react";

export function Dot({ color, glow = false }: { color: string; glow?: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={{
        width: 6,
        height: 6,
        borderRadius: "var(--radius-pill)",
        background: color,
        flex: "none",
        boxShadow: glow ? `0 0 8px ${color}` : undefined,
      }}
    />
  );
}

export function SectionHead({
  color = "var(--color-info)",
  label,
  right,
  level = 2,
  glow = false,
  dot = true,
}: {
  color?: string;
  label: ReactNode;
  right?: ReactNode;
  level?: 2 | 3;
  glow?: boolean;
  dot?: boolean;
}) {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
      {dot && <Dot color={color} glow={glow} />}
      <Heading
        style={{
          margin: 0,
          font: level === 3 ? "600 10.5px var(--font-mono)" : "var(--type-label)",
          letterSpacing: level === 3 ? undefined : "var(--tracking-label)",
          color: "var(--color-dim)",
          textTransform: level === 3 ? undefined : "uppercase",
        }}
      >
        {label}
      </Heading>
      {right != null && (
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
          {right}
        </div>
      )}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div
      data-testid="empty-state"
      className="rounded-lg border border-dashed border-line bg-deep p-8 text-center"
    >
      <div className="text-sm font-medium">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs text-dim">{body}</p>
    </div>
  );
}

export function Unavailable({ reason, testId }: { reason: string; testId?: string }) {
  return (
    <span data-testid={testId} role="status" className="inline-flex items-center gap-1">
      <Dot color="var(--color-dimmer)" />
      <span>{`Unavailable: ${reason}`}</span>
    </span>
  );
}
