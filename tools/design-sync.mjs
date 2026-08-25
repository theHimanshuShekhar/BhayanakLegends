#!/usr/bin/env node
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const designPath = resolve(root, "DESIGN.md");
const artifactPath = resolve(root, ".impeccable/design.json");
const stylesPath = resolve(root, "src/styles.css");

const colors = {
  deep: "Deep Midnight",
  bg: "Midnight Canvas",
  surface: "Instrument Surface",
  "surface-2": "Raised Surface",
  "surface-3": "Inset Surface",
  line: "Hairline",
  text: "Bright Text",
  dim: "Quiet Text",
  dimmer: "Quiet Text Dim",
  accent: "Instrument Lavender",
  "accent-low": "Lavender Low",
  danger: "Danger Rose",
  "danger-low": "Danger Rose Low",
  teal: "Signal Teal",
  "teal-low": "Signal Teal Low",
  amber: "Caution Amber",
  "amber-low": "Caution Amber Low",
  info: "Field Blue",
  "info-low": "Field Blue Low",
  "soft-text": "Soft Annotation Text",
  "soft-lavender": "Soft Annotation Lavender",
  "soft-blue": "Soft Annotation Blue",
  "soft-rose": "Soft Annotation Rose",
  "chip-text": "Chip Text",
};

function unquote(value) {
  const trimmed = value.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

function parseDesign(source) {
  const frontMatter = source.match(/^---\n([\s\S]*?)\n---/u)?.[1];
  if (!frontMatter) throw new Error("DESIGN.md is missing front matter");
  const result = { colors: {}, typography: {}, rounded: {}, spacing: {}, motion: {}, interactionStates: {}, namedRules: {} };
  let section = "";
  let nested = "";
  for (const line of frontMatter.split("\n")) {
    if (!line.trim() || line.trim().startsWith("#")) continue;
    const top = line.match(/^([A-Za-z][\w-]*):\s*$/u);
    if (top) {
      section = top[1];
      nested = "";
      continue;
    }
    const nestedTop = line.match(/^  ([A-Za-z][\w-]*):\s*$/u);
    if (nestedTop) {
      nested = nestedTop[1];
      continue;
    }
    const property = line.match(/^ {2,4}([A-Za-z][\w-]*):\s*(.+)$/u);
    if (!property || !(section in result)) continue;
    const [, key, raw] = property;
    if (section === "typography" && nested) result.typography[nested] ??= {}, result.typography[nested][key] = unquote(raw);
    else result[section][key] = unquote(raw);
  }
  return result;
}

function expectedArtifact(design, current) {
  const currentColors = current.extensions?.colorMeta ?? {};
  const colorMeta = Object.fromEntries(Object.entries(design.colors).map(([name, canonical]) => [name, {
    ...(currentColors[name] ?? {}),
    role: currentColors[name]?.role ?? (name.startsWith("soft-") || name === "chip-text" ? "neutral" : "neutral"),
    displayName: colors[name] ?? name,
    canonical,
  }]));
  const typographyMeta = Object.fromEntries(Object.entries(design.typography).map(([name, value]) => [name, {
    ...(current.extensions?.typographyMeta?.[name] ?? {}),
    ...value,
  }]));
  return {
    ...current,
    extensions: {
      ...current.extensions,
      colorMeta,
      radiusMeta: design.rounded,
      spacingMeta: design.spacing,
      typographyMeta,
      namedRules: Object.entries(design.namedRules).map(([name, body]) => ({
        name: {
          "two-data-worlds": "The Two-Data-Worlds Rule",
          "readout-hierarchy": "The Readout Hierarchy Rule",
          "layer-before-shadow": "The Layer-Before-Shadow Rule",
        }[name] ?? name,
        body,
      })),
      interactionStates: design.interactionStates,
      motion: Object.entries(design.motion).map(([name, value]) => ({ name, value })),
    },
  };
}

function runtimeTokenCss(design) {
  const colorLines = Object.entries(design.colors).map(([name, value]) => `  --color-${name}: ${value};`);
  const radiusLines = Object.entries(design.rounded).map(([name, value]) => `  --radius-${name}: ${value};`);
  const spacingLines = Object.entries(design.spacing).map(([name, value]) => `  --space-${name}: ${value};`);
  const typeLines = Object.entries(design.typography).map(([name, value]) => {
    const family = value.fontFamily;
    const composite = `${value.fontWeight} ${value.fontSize}/${value.lineHeight} ${family}`;
    return `  --type-${name}: ${composite};`;
  });
  const labelTracking = design.typography.label?.letterSpacing ? `  --tracking-label: ${design.typography.label.letterSpacing};` : "";
  return `/* BEGIN GENERATED DESIGN TOKENS: do not edit; run pnpm design:sync */
:root {
${[...colorLines, ...radiusLines, ...spacingLines, ...typeLines, labelTracking].filter(Boolean).join("\n")}
}

@theme inline {
${[...Object.keys(design.colors).map((name) => `  --color-${name}: var(--color-${name});`), Object.keys(design.rounded).map((name) => `  --radius-${name}: var(--radius-${name});`), Object.keys(design.spacing).map((name) => `  --spacing-${name}: var(--space-${name});`)].flat().join("\n")}
}
/* END GENERATED DESIGN TOKENS */`;
}

function syncStyles(design) {
  const source = readFileSync(stylesPath, "utf8");
  const block = runtimeTokenCss(design);
  const marker = /\/\* BEGIN GENERATED DESIGN TOKENS[\s\S]*?\/\* END GENERATED DESIGN TOKENS \*\//u;
  if (marker.test(source)) {
    writeFileSync(stylesPath, source.replace(marker, block));
    return;
  }
  const imports = /(@import[^;]+;\n@import[^;]+;)/u;
  if (!imports.test(source)) throw new Error("styles.css must keep its imports before generated tokens");
  writeFileSync(stylesPath, source.replace(imports, `$1\n\n${block}`));
}

function assertEqual(actual, expected, path) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Design contract drift at ${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

function checkStyles(design) {
  const source = readFileSync(stylesPath, "utf8");
  for (const [name, value] of Object.entries(design.colors)) assertEqual(source.match(new RegExp(`--color-${name}:\\s*([^;]+);`))?.[1]?.trim(), value, `runtime color ${name}`);
  for (const [name, value] of Object.entries(design.rounded)) assertEqual(source.match(new RegExp(`--radius-${name}:\\s*([^;]+);`))?.[1]?.trim(), value, `runtime radius ${name}`);
  for (const [name, value] of Object.entries(design.spacing)) assertEqual(source.match(new RegExp(`--space-${name}:\\s*([^;]+);`))?.[1]?.trim(), value, `runtime spacing ${name}`);
  for (const [name, value] of Object.entries(design.typography)) {
    const expected = `${value.fontWeight} ${value.fontSize}/${value.lineHeight} ${value.fontFamily}`;
    assertEqual(source.match(new RegExp(`--type-${name}:\\s*([^;]+);`))?.[1]?.trim(), expected, `runtime typography ${name}`);
  }
}

function checkArtifact(design, artifact) {
  const expected = expectedArtifact(design, artifact);
  for (const [name, value] of Object.entries(design.colors)) assertEqual(artifact.extensions?.colorMeta?.[name]?.canonical, value, `artifact color ${name}`);
  assertEqual(artifact.extensions?.radiusMeta, expected.extensions.radiusMeta, "artifact radii");
  assertEqual(artifact.extensions?.spacingMeta, expected.extensions.spacingMeta, "artifact spacing");
  assertEqual(artifact.extensions?.interactionStates, expected.extensions.interactionStates, "artifact interaction states");
  assertEqual(artifact.extensions?.motion, expected.extensions.motion, "artifact motion");
  assertEqual(artifact.extensions?.namedRules, expected.extensions.namedRules, "artifact named rules");
  for (const [name, value] of Object.entries(design.typography)) assertEqual(artifact.extensions?.typographyMeta?.[name], expected.extensions.typographyMeta[name], `artifact typography ${name}`);
}

function sync() {
  const design = parseDesign(readFileSync(designPath, "utf8"));
  const current = JSON.parse(readFileSync(artifactPath, "utf8"));
  const artifact = expectedArtifact(design, current);
  artifact.generatedAt = new Date().toISOString();
  writeFileSync(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`);
  syncStyles(design);
}

function check(path = artifactPath) {
  const design = parseDesign(readFileSync(designPath, "utf8"));
  checkStyles(design);
  checkArtifact(design, JSON.parse(readFileSync(resolve(path), "utf8")));
}

if (process.argv[2] === "--check") check(process.argv[3]);
else sync();

export { check, parseDesign, sync };
