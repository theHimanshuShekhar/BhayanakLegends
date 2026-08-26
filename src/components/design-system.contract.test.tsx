import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import documentArtifact from "../../.impeccable/design.json";
import { assertDesignArtifactMatches } from "../design-system.contract";
import { formatEffectPerSd } from "./format";
import { BanStrip } from "./champ-select/BanStrip";
import type { ChampSelectSnapshot } from "../api/types";
import "../styles.css";

/**
 * Mechanical design-system detector (#99, parent #37).
 *
 * Beyond the artifact/token assertions below, the tests scan runtime sources
 * (via Vite raw globs, no node builtins) and fail on: exact palette literals
 * outside the generated token block, duplicate/dead primitive or formatter
 * exports, forbidden navigation/pending phrases, percent/pp presentations of
 * `effect_per_sd`, and `.bl-pulse` attached to anything but an aria-hidden
 * connection/urgent dot. Test files are excluded from the scans because they
 * intentionally pin canonical values to detect drift.
 */

const RAW_SOURCES = import.meta.glob("/src/**/*.{ts,tsx,css}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const GENERATED_TOKEN_BLOCK =
  /\/\* BEGIN GENERATED DESIGN TOKENS[\s\S]*?\/\* END GENERATED DESIGN TOKENS \*\//;
const TEST_FILE = /\/[^/]*\.test\.[jt]sx?$/;
const HEX_6 = /#[0-9a-fA-F]{6}\b/g;

type SourceFile = { path: string; source: string };

/** Runtime sources under scan: everything except the detector's own peers. */
function runtimeSources(): SourceFile[] {
  return Object.entries(RAW_SOURCES)
    .map(([path, source]) => ({ path, source }))
    .filter(({ path }) => !TEST_FILE.test(path));
}

/** Remove comments so prose in comments never trips copy/pattern detectors. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, "$1 ");
}

/** String-literal contents plus JSX text: the user-visible copy surface. */
function visibleCopyCorpus(source: string): string {
  const bare = stripComments(source);
  const strings = Array.from(
    bare.matchAll(/(["'`])((?:\\.|(?!\1)[^\\])*)\1/g),
    (match) => match[2],
  ).join("\n");
  const jsxText = Array.from(
    bare.matchAll(/>([^<>{}]+)</g),
    (match) => match[1],
  ).join("\n");
  return `${strings}\n${jsxText}`;
}

/** Exact palette values declared by the generated token block (lowercase). */
function declaredTokenHexes(): string[] {
  const block = RAW_SOURCES["/src/styles.css"]?.match(GENERATED_TOKEN_BLOCK)?.[0] ?? "";
  return Array.from(block.matchAll(HEX_6), (match) => match[0].toLowerCase());
}

/** Files + lines where an exact palette literal escapes the allowlist. */
function paletteViolations(): string[] {
  const tokens = declaredTokenHexes();
  const offenders: string[] = [];
  for (const { path, source } of runtimeSources()) {
    // styles.css is allowlisted only inside its generated token block.
    const scanned =
      path === "/src/styles.css" ? source.replace(GENERATED_TOKEN_BLOCK, " ") : source;
    for (const match of scanned.matchAll(HEX_6)) {
      if (tokens.includes(match[0].toLowerCase())) {
        const line = scanned.slice(0, match.index).split("\n").length;
        offenders.push(`${path}:${line} repeats palette value ${match[0]}`);
      }
    }
  }
  return offenders;
}

function exportedNames(source: string): string[] {
  return Array.from(
    source.matchAll(/\bexport\s+(?:async\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)/g),
    (match) => match[1],
  );
}

const PRIMITIVE_SEAM = ["Dot", "EmptyState", "SectionHead", "Unavailable"] as const;
const FORMATTER_SEAM = [
  "formatClock",
  "formatCount",
  "formatDuration",
  "formatEffectPerSd",
  "formatGold",
  "formatInitials",
  "formatItemQuantity",
  "formatPercentagePoints",
  "formatRate",
  "formatUnavailable",
] as const;

/** Formatter/primitive names that may never be defined outside the two seams. */
const DUPLICATE_NAME =
  /^(?:Dot|SectionHead|EmptyState|Unavailable|CardHead|KickerRow|pct|pp|signed|fmtClock|fmtDuration)$/u;

function duplicateSeamDefinitions(): string[] {
  const offenders: string[] = [];
  for (const { path, source } of runtimeSources()) {
    if (path === "/src/components/ui.tsx" || path === "/src/components/format.ts") continue;
    for (const match of source.matchAll(
      /\bexport\s+(?:async\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)/g,
    )) {
      if (DUPLICATE_NAME.test(match[1]) || /^format[A-Z]/u.test(match[1])) {
        offenders.push(`${path} exports duplicate seam member ${match[1]}`);
      }
    }
  }
  return offenders;
}

const FORBIDDEN_COPY: ReadonlyArray<[RegExp, string]> = [
  [/\b(?:lands?|arrives?|ships?)\b/iu, "speculative pending vocabulary"],
  [/\bpending\b/iu, "generic pending vocabulary"],
  [/["'>](?:Live match|Progress|History)["'<]/u, "avoided navigation label"],
];

function forbiddenCopyHits(): string[] {
  const offenders: string[] = [];
  for (const { path, source } of runtimeSources()) {
    if (!path.endsWith(".tsx") && !path.endsWith(".ts")) continue;
    const corpus = visibleCopyCorpus(source);
    for (const [pattern, why] of FORBIDDEN_COPY) {
      if (pattern.test(corpus)) offenders.push(`${path}: ${why}`);
    }
  }
  return offenders;
}

function snapshotFixture(overrides: Partial<ChampSelectSnapshot> = {}): ChampSelectSnapshot {
  return {
    active: true,
    phase: "GameStart",
    timer_sec: 23,
    local_assigned_role: "MIDDLE",
    bans_ally: [],
    bans_enemy: [],
    ally: [],
    enemy: [],
    ...overrides,
  };
}

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

  test("no exact palette literal exists outside token declarations or generated metadata", () => {
    // Named pre-cutover failure: soft-blue leaked as a raw literal in runtime code.
    const runtimeSource = runtimeSources()
      .map(({ path, source }) =>
        path === "/src/styles.css" ? source.replace(GENERATED_TOKEN_BLOCK, " ") : source,
      )
      .join("\n");
    expect(runtimeSource).not.toMatch(/#cfe3f9/i);

    expect(paletteViolations(), "exact palette duplicates outside the token allowlist").toEqual(
      [],
    );
  });

  test("one shared primitive and one shared formatter seam serve every caller", () => {
    expect(exportedNames(RAW_SOURCES["/src/components/ui.tsx"]).sort()).toEqual(
      [...PRIMITIVE_SEAM].sort(),
    );
    expect(exportedNames(RAW_SOURCES["/src/components/format.ts"]).sort()).toEqual(
      [...FORMATTER_SEAM].sort(),
    );
    expect(duplicateSeamDefinitions(), "duplicate/dead seam members outside the seams").toEqual(
      [],
    );
  });

  test("navigation and pending vocabulary stay canonical in visible copy", () => {
    expect(forbiddenCopyHits(), "forbidden navigation/pending phrases in visible copy").toEqual(
      [],
    );
  });

  test("effect_per_sd keeps multiplier semantics everywhere", () => {
    // Named pre-cutover divergence: multiplier copy pinned against percent/pp drift.
    expect(formatEffectPerSd(2.24)).toBe("×2.24 effect per SD");
    expect(formatEffectPerSd(0.83)).toBe("×0.83 effect per SD");
    expect(formatEffectPerSd(null)).toBe("Unavailable: effect per SD unavailable");

    const percentPresentations: string[] = [];
    const fieldFiles: string[] = [];
    for (const { path, source } of runtimeSources()) {
      const bare = stripComments(source);
      if (
        /(effect[_ ]per[_ ]sd[^\n]{0,80}%)/iu.test(bare) ||
        (/%\s*(?:WR|win rate)/iu.test(bare) && /per\s*SD/iu.test(bare)) ||
        /\+\s*\d+(?:\.\d+)?\s*pp\b[^\n]{0,30}per\s*SD/iu.test(bare)
      ) {
        percentPresentations.push(path);
      }
      if (path !== "/src/api/types.ts" && /effect_per_sd/u.test(stripComments(source))) {
        fieldFiles.push(path);
      }
    }
    expect(percentPresentations, "percent/pp presentation of effect_per_sd").toEqual([]);
    for (const path of fieldFiles) {
      expect(
        RAW_SOURCES[path],
        `${path} renders effect_per_sd without the shared formatter`,
      ).toContain("formatEffectPerSd");
    }
  });

  test(".bl-pulse attaches only to aria-hidden urgent/connection dots", () => {
    const offenders: string[] = [];
    for (const { path, source } of runtimeSources()) {
      if (!path.endsWith(".tsx")) continue;
      for (const match of source.matchAll(/bl-pulse/g)) {
        const open = source.lastIndexOf("<", match.index ?? 0);
        const close = source.indexOf(">", match.index ?? 0);
        const tag = source.slice(Math.max(0, open), close === -1 ? undefined : close + 1);
        // Only aria-hidden or dot-marked non-interactive elements may carry
        // the pulse; anything else (e.g. the whole timer pill) is a violation.
        const allowed = /aria-hidden/u.test(tag) || /dot/iu.test(tag);
        if (!allowed || /<(?:button|a)\b/iu.test(tag)) {
          const line = source.slice(0, match.index).split("\n").length;
          offenders.push(`${path}:${line} attaches bl-pulse to a non-dot element`);
        }
      }
    }
    expect(offenders, ".bl-pulse outside aria-hidden dot elements").toEqual([]);
  });

  test("urgent timer renders a pulsing aria-hidden dot while the amber pill stays static", () => {
    const { unmount } = render(
      <BanStrip
        snapshot={snapshotFixture()}
        timerLabel="00:23"
        timerUrgent={true}
        lastError={null}
      />,
    );
    const pill = screen.getByTestId("cs-timer-pill");
    // The pill itself never carries the pulse class...
    expect(pill.classList.contains("bl-pulse")).toBe(false);
    // ...and inside it, exactly one pulsing element exists: the aria-hidden dot.
    const pulsing = Array.from(pill.querySelectorAll(".bl-pulse"));
    expect(pulsing).toEqual([screen.getByTestId("cs-timer-dot")]);
    expect(pulsing.map((el) => el.getAttribute("aria-hidden"))).toEqual(["true"]);
    expect(pill.style.background).toContain("--color-amber");

    const dot = screen.getByTestId("cs-timer-dot");
    expect(dot.getAttribute("aria-hidden")).toBe("true");
    expect(dot.classList.contains("bl-pulse")).toBe(true);
    unmount();

    const calm = render(
      <BanStrip
        snapshot={snapshotFixture({ timer_sec: 42 })}
        timerLabel="00:42"
        timerUrgent={false}
        lastError={null}
      />,
    );
    const calmPill = screen.getByTestId("cs-timer-pill");
    expect(calmPill.classList.contains("bl-pulse")).toBe(false);
    expect(calmPill.style.background).toContain("--color-accent");
    expect(screen.queryByTestId("cs-timer-dot")).toBeNull();
    calm.unmount();
  });

  test("motion stays gated behind prefers-reduced-motion", () => {
    const styles = RAW_SOURCES["/src/styles.css"];
    const noPreference = styles.indexOf("@media (prefers-reduced-motion: no-preference)");
    const reduce = styles.indexOf("@media (prefers-reduced-motion: reduce)");
    expect(noPreference, "styles.css must gate authored motion").toBeGreaterThanOrEqual(0);
    expect(reduce, "styles.css must declare its reduce block after the motion block").toBeGreaterThan(
      noPreference,
    );
    const gated = styles.slice(noPreference, reduce);
    for (const hook of [".rc-route", ".bl-pulse", ".bl-width"]) {
      expect(gated).toContain(hook);
    }
    // Authored declarations must not leak outside the no-preference gate.
    expect(styles.slice(reduce)).not.toMatch(/\.bl-pulse|\.bl-width/);

    // Global kill switch: reduced motion disables both pulse and transitions.
    const designSystem = RAW_SOURCES["/src/design-system.css"];
    expect(designSystem).toMatch(
      /@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?animation:\s*none\s*!important;[\s\S]*?transition:\s*none\s*!important;/,
    );
  });
});
