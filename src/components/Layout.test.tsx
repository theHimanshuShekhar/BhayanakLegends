import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { Layout } from "./Layout";

const routerState = vi.hoisted(() => ({ pathname: "/progress" }));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useRouterState: () => routerState.pathname,
}));

vi.mock("../api/sse", () => ({
  useEvents: () => false,
}));

function renderWithProviders(ui: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>,
  );
}

describe("Layout accessibility", () => {
  it("exposes landmarks, current navigation, and the offline connection state", () => {
    renderWithProviders(
      <Layout>
        <p>Route content</p>
      </Layout>,
    );

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveTextContent("Route content");
    expect(screen.getByRole("link", { name: "Progress" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText(/sidecar · offline/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("sidecar · offline");
  });

  it("moves focus to a destination heading and resets the route scroll position", async () => {
    const { rerender } = renderWithProviders(
      <Layout>
        <h1 tabIndex={-1}>Progress</h1>
      </Layout>,
    );

    expect(document.activeElement).not.toBe(screen.getByRole("heading", { level: 1 }));

    const screenRegion = screen.getByRole("main");
    Object.defineProperty(screenRegion, "scrollTop", { configurable: true, value: 144, writable: true });

    routerState.pathname = "/history";
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <Layout>
          <h1 tabIndex={-1}>Improvement Journal</h1>
        </Layout>,
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveFocus());
    expect(screenRegion.scrollTop).toBe(0);
    expect(screen.getByRole("heading", { level: 1 })).toHaveAttribute("tabindex", "-1");
  });
  it("keeps the six route links and shell statuses in stable keyboard order", () => {
    renderWithProviders(
      <Layout>
        <h1 tabIndex={-1}>Trajectory</h1>
      </Layout>,
    );

    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Live match",
      "Champ select",
      "Post-game",
      "Progress",
      "Champions",
      "History",
    ]);
    expect(screen.getByRole("navigation", { name: "Primary" })).toHaveClass("rc-navbar");
    expect(screen.getByTestId("connection-status")).toBeVisible();
    expect(screen.getByText("Findings Pack · 26k games")).toBeVisible();
  });

});
