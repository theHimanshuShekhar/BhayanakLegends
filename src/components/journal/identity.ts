export function isValidRiotId(value: string): boolean {
  const [gameName, tagLine, ...extra] = value.trim().split("#");
  return Boolean(gameName?.trim() && tagLine?.trim() && extra.length === 0);
}
