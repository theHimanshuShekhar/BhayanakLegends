import { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { useEvents } from "../api/sse";

const NAV = [
  {
    group: "Live Companion",
    items: [
      { to: "/champ-select", label: "Champ Select" },
      { to: "/live", label: "Live Match" },
    ],
  },
  {
    group: "Improvement Journal",
    items: [
      { to: "/postgame", label: "Post-game" },
      { to: "/progress", label: "Progress" },
      { to: "/champions", label: "Champions" },
      { to: "/history", label: "History" },
    ],
  },
];

export function Layout({ children }: { children: ReactNode }) {
  const connected = useEvents();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="flex h-full">
      <nav className="flex w-52 shrink-0 flex-col border-r border-line bg-deep px-3 py-4">
        <div className="mb-6 px-2">
          <div className="text-sm font-medium tracking-wide">Bhayanak Legends</div>
          <div className="mt-0.5 text-[10px] text-dim">friends-first research, applied</div>
        </div>
        {NAV.map((section) => (
          <div key={section.group} className="mb-4">
            <div className="mb-1 px-2 text-[10px] uppercase tracking-widest text-dimmer">
              {section.group}
            </div>
            {section.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                data-testid={`nav-${item.to.slice(1)}`}
                className={`block rounded-md px-2 py-1.5 text-xs ${
                  pathname === item.to
                    ? "bg-surface-2 text-text"
                    : "text-dim hover:bg-surface hover:text-text"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        ))}
        <div className="mt-auto flex items-center gap-1.5 px-2 text-[10px] text-dim">
          <span
            data-testid="sidecar-dot"
            className={`inline-block size-1.5 rounded-full ${connected ? "bg-teal" : "bg-danger"}`}
          />
          {connected ? "sidecar connected" : "sidecar offline"}
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}

export function PageHeader({ kicker, title }: { kicker?: string; title: string }) {
  return (
    <header className="mb-5">
      {kicker && (
        <div className="text-[10px] uppercase tracking-widest text-accent">{kicker}</div>
      )}
      <h1 className="mt-1 text-lg font-medium">{title}</h1>
    </header>
  );
}
