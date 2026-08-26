import { ReactNode } from "react";

export function Card({
  kicker,
  title,
  children,
  className = "",
}: {
  kicker?: string;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-line bg-surface p-4 shadow-z1 ${className}`}
      data-testid={title ? `card-${slug(title)}` : undefined}
    >
      {kicker && <div className="kicker">{kicker}</div>}
      {title && <h2 className="mt-0.5 text-sm font-medium">{title}</h2>}
      {children}
    </section>
  );
}

export function Tag({
  verdict,
  children,
}: {
  verdict: "good" | "bad" | "neutral" | "advice" | "info";
  children: ReactNode;
}) {
  const styles = {
    good: "bg-teal-low text-teal",
    bad: "bg-danger-low text-danger",
    neutral: "bg-surface-3 text-dim",
    advice: "bg-accent-low text-accent",
    info: "bg-info-low text-info",
  }[verdict];
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${styles}`}>
      {children}
    </span>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-dimmer">{label}</div>
      <div className="font-mono text-sm">{value}</div>
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

export function Unavailable({ testId }: { testId?: string }) {
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1">
      <span
        aria-hidden="true"
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: "var(--color-dimmer)",
          display: "inline-block",
        }}
      />
      <span>Unavailable</span>
    </span>
  );
}

export function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
