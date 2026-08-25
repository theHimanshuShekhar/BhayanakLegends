import { render } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import documentArtifact from "../../.impeccable/design.json";
import { assertDesignArtifactMatches } from "../design-system.contract";
import "../styles.css";


const expectedColors = {
  "soft-text": "#cfd3e5",
  "soft-lavender": "#e0ddf5",
  "soft-blue": "#cfe3f9",
  "soft-rose": "#f4c3ce",
  "chip-text": "#e7e5fe",
} as const;

const expectedRadii = {
  sm: "6px",
  md: "10px",
  lg: "16px",
  xl: "20px",
  pill: "999px",
} as const;

const expectedSpacing = {
  xs: "6px",
  sm: "8px",
  md: "12px",
  lg: "16px",
} as const;

const expectedTypography = {
  headline: {
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif",
    fontSize: "18px",
    fontWeight: 500,
    lineHeight: 1.25,
  },
  title: {
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace",
    fontSize: "13px",
    fontWeight: 600,
    lineHeight: 1.3,
  },
  body: {
    fontFamily: "Inter Variable, Inter, system-ui, sans-serif",
    fontSize: "10.5px",
    fontWeight: 400,
    lineHeight: 1.5,
  },
  label: {
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace",
    fontSize: "9.5px",
    fontWeight: 700,
    lineHeight: 1.2,
    letterSpacing: "0.11em",
  },
} as const;

type ContractExtensions = {
  colorMeta: Record<string, { canonical: string }>;
  radiusMeta: Record<string, string>;
  spacingMeta: Record<string, string>;
  typographyMeta: Record<string, Record<string, string | number>>;
  namedRules: Array<Record<string, string>>;
  motion: Array<Record<string, string>>;
};
describe("design system contract", () => {
  test("contains authored soft colors, shape, spacing, and composite typography metadata", () => {
    const extensions = documentArtifact.extensions as ContractExtensions;
    for (const [name, value] of Object.entries(expectedColors)) {
      expect(extensions.colorMeta[name].canonical).toBe(value);
    }
    expect(extensions.radiusMeta).toEqual(expectedRadii);
    expect(extensions.spacingMeta).toEqual(expectedSpacing);
    for (const [name, value] of Object.entries(expectedTypography)) {
      expect(extensions.typographyMeta[name]).toMatchObject(value);
    }
    expect(extensions.typographyMeta.label.letterSpacing).toBe("0.11em");
  });

  test("records the named data-worlds rule and urgent-dot-only motion contract", () => {
    const extensions = documentArtifact.extensions as ContractExtensions;
    expect(extensions.namedRules).toContainEqual({
      name: "The Two-Data-Worlds Rule",
      body: expect.stringContaining("Teal describes the player's Personal History"),
    });
    expect(extensions.motion).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "route-enter", value: "180ms ease-out" }),
        expect.objectContaining({ name: "live-dot-pulse", value: "2.4s opacity breath" }),
        expect.objectContaining({ name: "bar-easing", value: "450ms exponential ease-out" }),
        expect.objectContaining({ name: "urgent-timer", value: "≤30s amber live-dot pulse" }),
      ]),
    );
    expect(extensions.motion).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ name: "state-transition" })]),
    );
  });

  test("fails on a real token mismatch but ignores generatedAt-only changes", () => {
    const contract = {
      colors: expectedColors,
      radii: expectedRadii,
      spacing: expectedSpacing,
      typography: expectedTypography,
      motion: documentArtifact.extensions.motion,
      namedRules: documentArtifact.extensions.namedRules,
    };
    const generatedAtOnly = { ...documentArtifact, generatedAt: "2099-01-01T00:00:00Z" };
    expect(() => assertDesignArtifactMatches(generatedAtOnly, contract)).not.toThrow();

    const mismatched = structuredClone(documentArtifact);
    mismatched.extensions.colorMeta["soft-blue"].canonical = "#000000";
    expect(() => assertDesignArtifactMatches(mismatched, contract)).toThrow(/soft-blue/);
  });

  test("resolves canonical runtime tokens on a minimal rc surface", () => {
    const { container } = render(<div className="rc contract-surface" />);
    const computed = getComputedStyle(container.firstElementChild as HTMLElement);
    for (const [name, value] of Object.entries(expectedColors)) {
      expect(computed.getPropertyValue(`--color-${name}`).trim()).toBe(value);
    }
    for (const [name, value] of Object.entries(expectedRadii)) {
      expect(computed.getPropertyValue(`--radius-${name}`).trim()).toBe(value);
    }

    for (const [name, value] of Object.entries(expectedTypography)) {
      const composite = `${value.fontWeight} ${value.fontSize}/${value.lineHeight} ${value.fontFamily}`.replace(/, /gu, ",");
      expect(computed.getPropertyValue(`--type-${name}`).trim()).toBe(composite);
    }
    expect(computed.getPropertyValue("--tracking-label").trim()).toBe("0.11em");
    for (const [name, value] of Object.entries(expectedSpacing)) {
      expect(computed.getPropertyValue(`--space-${name}`).trim()).toBe(value);
    }
  });
});
