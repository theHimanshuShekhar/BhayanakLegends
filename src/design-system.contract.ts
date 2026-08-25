type DesignContract = {
  colors: Readonly<Record<string, string>>;
  radii: Readonly<Record<string, string>>;
  spacing: Readonly<Record<string, string>>;
  typography: Readonly<Record<string, Readonly<Record<string, string | number>>>>;
  motion: readonly Readonly<Record<string, string>>[];
  namedRules: readonly Readonly<Record<string, string>>[];
};

type Artifact = {
  extensions?: {
    colorMeta?: Record<string, { canonical?: string }>;
    radiusMeta?: unknown;
    spacingMeta?: unknown;
    typographyMeta?: Record<string, unknown>;
    motion?: unknown;
    namedRules?: unknown;
  };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function same(actual: unknown, expected: unknown) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}


export function assertDesignArtifactMatches(artifact: Artifact, contract: DesignContract) {
  for (const [name, value] of Object.entries(contract.colors)) {
    if (artifact.extensions?.colorMeta?.[name]?.canonical !== value) {
      throw new Error(`Design contract drift at soft color ${name}`);
    }
  }
  if (!same(artifact.extensions?.radiusMeta, contract.radii)) throw new Error("Design contract drift at radii");
  if (!same(artifact.extensions?.spacingMeta, contract.spacing)) throw new Error("Design contract drift at spacing");
  for (const [name, value] of Object.entries(contract.typography)) {
    const actual = artifact.extensions?.typographyMeta?.[name];
    if (!isRecord(actual)) throw new Error(`Design contract drift at typography ${name}`);
    for (const [property, expected] of Object.entries(value)) {
      if (actual[property] !== expected) {
        throw new Error(`Design contract drift at typography ${name}.${property}`);
      }
    }
  }
  if (!same(artifact.extensions?.motion, contract.motion)) throw new Error("Design contract drift at motion");
  if (!same(artifact.extensions?.namedRules, contract.namedRules)) throw new Error("Design contract drift at named rules");
}
