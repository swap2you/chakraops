import { describe, it, expect } from "vitest";
import { formatTimestampEt, formatTimestampEtFull } from "./formatTimestamp";

describe("formatTimestampEt", () => {
  it("parses ISO UTC and renders in America/New_York with ET marker", () => {
    const result = formatTimestampEt("2026-02-17T20:58:29Z");
    expect(result).toContain("ET");
    // 20:58 UTC = 3:58 PM ET (Feb is EST)
    expect(result).toMatch(/3:58|15:58|3:58 PM|15:58/);
  });

  it("handles null/undefined", () => {
    expect(formatTimestampEt(null)).toBe("—");
    expect(formatTimestampEt(undefined)).toBe("—");
  });

  it("handles invalid input gracefully", () => {
    const result = formatTimestampEt("not-a-date");
    // Invalid Date produces "Invalid Date" + " ET"
    expect(result).toContain("Invalid Date");
    expect(result).toContain("ET");
  });
});

describe("formatTimestampEtFull", () => {
  it("includes seconds in output", () => {
    const result = formatTimestampEtFull("2026-02-17T20:58:29Z");
    expect(result).toContain("ET");
    expect(result).toMatch(/\d{1,2}:\d{2}:\d{2}/);
  });
});
