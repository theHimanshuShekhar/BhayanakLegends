import { describe, expect, it } from "vitest";
import { patchOrder, sortPatches } from "./format";

describe("patch ordering", () => {
  it("sorts minor versions numerically", () => {
    expect(sortPatches(["16.10", "16.9"])).toEqual(["16.9", "16.10"]);
    expect(patchOrder("16.9")).toBeLessThan(patchOrder("16.10"));
  });

  it("puts malformed patches after valid values and missing values last", () => {
    expect(sortPatches(["bad", null, "16.10", "16.x", "16.9", undefined])).toEqual([
      "16.9",
      "16.10",
      "16.x",
      "bad",
      null,
      undefined,
    ]);
  });
});
