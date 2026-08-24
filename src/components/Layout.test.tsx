import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { Layout } from "./Layout";


vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useRouterState: () => "/progress",
}));

vi.mock("../api/sse", () => ({
  useEvents: () => false,
}));

describe("Layout accessibility", () => {
  it("exposes landmarks, current navigation, and the offline connection state", () => {
    render(
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
});
