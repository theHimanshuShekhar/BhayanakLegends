import { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { useEvents } from "../api/sse";

const NAV = [
  { to: "/live", label: "Live match" },
  { to: "/champ-select", label: "Champ select" },
  { to: "/postgame", label: "Post-game" },
  { to: "/progress", label: "Progress" },
  { to: "/champions", label: "Champions" },
  { to: "/history", label: "History" },
];

export function ConnectionStatus({ connected }: { connected: boolean }) {
  return (
    <div
      className="pill"
      data-testid="connection-status"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      style={{
        background: connected ? "var(--color-accent-low)" : "var(--color-surface-2)",
        color: connected ? "#e7e5fe" : "var(--color-dim)",
        boxShadow: "var(--shadow-z1)",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6,
          height: 6,
          borderRadius: 999,
          background: connected ? "var(--color-accent)" : "var(--color-dimmer)",
          boxShadow: connected ? "0 0 8px var(--color-accent)" : "none",
        }}
      />
      sidecar · {connected ? "connected" : "offline"}
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const connected = useEvents();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="rc">
      <header className="rc-topbar">
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: 5,
            background: "linear-gradient(140deg,var(--color-accent),var(--color-accent-low))",
            boxShadow: "0 2px 6px rgba(145,132,217,.5)",
          }}
        />
        <span style={{ font: "700 11.5px var(--font-mono)", letterSpacing: ".06em" }}>
          BHAYANAK LEGENDS
        </span>
        <span style={{ fontSize: 10.5, color: "var(--color-dimmer)" }}>
          friends-first · 26k games
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <span
            data-testid="sidecar-dot"
            title={connected ? "sidecar connected" : "sidecar offline"}
            style={{
              width: 10,
              height: 10,
              borderRadius: 999,
              background: connected ? "var(--color-teal)" : "var(--color-danger)",
              boxShadow: connected ? "0 0 8px var(--color-teal)" : "none",
            }}
          />
          <span style={{ width: 10, height: 10, borderRadius: 999, background: "#3a3f56" }} />
          <span style={{ width: 10, height: 10, borderRadius: 999, background: "#4a3040" }} />
        </div>
      </header>

      <nav className="rc-navbar" aria-label="Primary">
        {NAV.map((item) => {
          const active = pathname === item.to || (item.to === "/live" && pathname === "/");
          return (
            <Link
              key={item.to}
              to={item.to}
              data-testid={`nav-${item.to.slice(1)}`}
              className="pill"
              aria-current={active ? "page" : undefined}
              style={
                active
                  ? {
                      background: "var(--color-accent)",
                      color: "#0e1020",
                      boxShadow:
                        "0 3px 0 var(--color-accent-low),0 8px 16px -6px rgba(145,132,217,.6)",
                    }
                  : {
                      background: "var(--color-surface-2)",
                      color: "var(--color-dim)",
                      boxShadow: "var(--shadow-z1)",
                    }
              }
            >
              {item.label}
            </Link>
          );
        })}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 7 }}>
          <ConnectionStatus connected={connected} />
          <div
            className="pill"
            style={{
              background: "var(--color-info-low)",
              color: "#cfe3f9",
              boxShadow: "var(--shadow-z1)",
            }}
          >
            <span
              aria-hidden="true"
              style={{ width: 6, height: 6, borderRadius: 999, background: "var(--color-info)" }}
            />
            Findings Pack · 26k games
          </div>
        </div>
      </nav>

      <main className="rc-screen">{children}</main>
    </div>
  );
}

export function PageHeader({ kicker, title }: { kicker?: string; title: string }) {
  return (
    <header className="mb-5">
      {kicker && <div className="kicker">{kicker}</div>}
      <h1 className="mt-1 text-lg font-medium">{title}</h1>
    </header>
  );
}
