const PATCH_RE = /^(\d+)\.(\d+)$/;

function parsedPatch(patch: string | null | undefined): [number, number] | null {
  if (patch == null) return null;
  const match = PATCH_RE.exec(patch);
  return match ? [Number(match[1]), Number(match[2])] : null;
}

export function patchOrder(patch: string | null | undefined): number {
  const parsed = parsedPatch(patch);
  // Keep legacy numeric consumers deterministic: malformed/missing values sort after valid patches.
  return parsed ? parsed[0] * 1_000_000 + parsed[1] : Number.MAX_SAFE_INTEGER;
}

export function sortPatches<T extends string | null | undefined>(
  patches: readonly T[],
): T[] {
  return [...patches].sort((a, b) => {
    const left = parsedPatch(a);
    const right = parsedPatch(b);
    if (left && right) return left[0] - right[0] || left[1] - right[1];
    if (left) return -1;
    if (right) return 1;
    if (a == null) return b == null ? 0 : 1;
    if (b == null) return -1;
    return a.localeCompare(b);
  });
}

