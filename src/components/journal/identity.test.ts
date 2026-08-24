import { describe, expect, it } from "vitest";
import { isValidRiotId } from "./identity";

describe("isValidRiotId", () => {
  it("accepts an explicit GameName#TAG identity", () => {
    expect(isValidRiotId("Game Name#TAG")).toBe(true);
  });

  it("rejects missing, incomplete, or ambiguous identities", () => {
    expect(isValidRiotId("")).toBe(false);
    expect(isValidRiotId("Game Name")).toBe(false);
    expect(isValidRiotId("#TAG")).toBe(false);
    expect(isValidRiotId("Game Name#")).toBe(false);
    expect(isValidRiotId("Game#Name#TAG")).toBe(false);
  });
});
