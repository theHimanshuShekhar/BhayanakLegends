import { describe, expect, it } from "vitest";
import {
  formatClock,
  formatCount,
  formatDuration,
  formatGold,
  formatInitials,
  formatItemQuantity,
  formatPercentagePoints,
  formatRate,
  formatUnavailable,
} from "./format";

describe("canonical presentation formatters", () => {
  it("formats rates to one decimal percent", () => {
    expect(formatRate(0.814)).toBe("81.4%");
    expect(formatRate(0)).toBe("0.0%");
  });

  it("formats signed percentage points with a sign and separated unit", () => {
    expect(formatPercentagePoints(29.5)).toBe("+29.5 pp");
    expect(formatPercentagePoints(-1.25)).toBe("-1.3 pp");
  });

  it("formats signed grouped gold", () => {
    expect(formatGold(-1200)).toBe("-1,200g");
    expect(formatGold(26000)).toBe("+26,000g");
    expect(formatGold(0)).toBe("+0g");
  });

  it("formats grouped counts with nouns and item quantities", () => {
    expect(formatCount(26000, "games")).toBe("26,000 games");
    expect(formatCount(1, "game")).toBe("1 game");
    expect(formatItemQuantity(2)).toBe("×2");
    expect(formatItemQuantity(0)).toBe("×0");
  });

  it("formats duration rollover and clamps the live clock", () => {
    expect(formatDuration(59)).toBe("0:59");
    expect(formatDuration(60)).toBe("1:00");
    expect(formatDuration(3600)).toBe("1:00:00");
    expect(formatClock(-12)).toBe("0:00");
    expect(formatClock(3661.9)).toBe("1:01:01");
  });

  it("formats initials after punctuation", () => {
    expect(formatInitials("Cho'Gath")).toBe("CH");
    expect(formatInitials("Dr. Mundo")).toBe("DR");
  });

  it("uses a named unavailable reason instead of a dash", () => {
    expect(formatUnavailable("live input is not reported")).toBe("Unavailable: live input is not reported");
    expect(formatRate(null, "rate is not reported")).toBe("Unavailable: rate is not reported");
    expect(formatGold(undefined, "gold checkpoint is missing")).toBe("Unavailable: gold checkpoint is missing");
  });
});
