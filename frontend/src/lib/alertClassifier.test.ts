import { describe, it, expect } from "vitest";
import { isActionable, severityFromLevel, severityBorderClass, dedupeForDashboard, alertsForDashboard } from "./alertClassifier";
import type { AlertsView } from "@/types/views";

describe("alertClassifier", () => {
  it("NO_TRADE alerts are not actionable", () => {
    const item: AlertsView["items"][0] = { code: "NO_TRADE", message: "No READY trade today" };
    expect(isActionable(item)).toBe(false);
  });

  it("alerts with position_id are actionable", () => {
    const item: AlertsView["items"][0] = { code: "TARGET_1_HIT", position_id: "pos-1", message: "Near T1" };
    expect(isActionable(item)).toBe(true);
  });

  it("dedupeForDashboard excludes NO_TRADE", () => {
    const items: AlertsView["items"] = [
      { code: "NO_TRADE", message: "No trade" },
      { code: "TARGET_1_HIT", message: "Near T1", position_id: "pos-1" },
    ];
    const deduped = dedupeForDashboard(items);
    expect(deduped).toHaveLength(1);
    expect(deduped[0].code).toBe("TARGET_1_HIT");
  });

  it("alertsForDashboard returns only actionable after dedupe", () => {
    const items: AlertsView["items"] = [
      { code: "NO_TRADE", message: "No trade" },
      { code: "TARGET_1_HIT", message: "Near T1", position_id: "pos-1" },
    ];
    const forDash = alertsForDashboard(items);
    expect(forDash).toHaveLength(1);
  });

  it("severityFromLevel handles missing level", () => {
    expect(severityFromLevel(undefined)).toBe("info");
    expect(severityFromLevel("warning")).toBe("warning");
  });

  it("severityBorderClass does not break under missing level", () => {
    const c = severityBorderClass(undefined);
    expect(typeof c).toBe("string");
    expect(c.length).toBeGreaterThan(0);
  });

  describe("Phase 8.7: HOLD + TARGET_HIT and dashboard", () => {
    it("dashboard shows only actionable when NO_TRADE and TARGET_HIT both present", () => {
      const items: AlertsView["items"] = [
        { code: "NO_TRADE", message: "No trade today" },
        { code: "TARGET_1_HIT", message: "Near T1", position_id: "pos-1", symbol: "SPY" },
      ];
      const forDash = alertsForDashboard(items);
      expect(forDash).toHaveLength(1);
      expect(forDash[0].code).toBe("TARGET_1_HIT");
    });

    it("dedupe keeps dashboard list short on spam day", () => {
      const items: AlertsView["items"] = [
        { code: "NO_TRADE", message: "No trade" },
        ...Array.from({ length: 5 }, (_, i) => ({ code: "TARGET_1_HIT", message: `T1 ${i}`, position_id: `pos-${i}` })),
      ];
      const deduped = dedupeForDashboard(items);
      expect(deduped.every((x) => x.code !== "NO_TRADE")).toBe(true);
      const forDash = alertsForDashboard(items);
      expect(forDash.length).toBeLessThanOrEqual(5);
    });

    it("notifications can show full list (NO_TRADE included) while dashboard is deduped", () => {
      const items: AlertsView["items"] = [
        { code: "NO_TRADE", message: "No trade" },
        { code: "TARGET_1_HIT", message: "T1", position_id: "pos-1" },
      ];
      expect(alertsForDashboard(items)).toHaveLength(1);
      expect(items).toHaveLength(2);
    });
  });

  describe("Phase 8.7: malformed alert", () => {
    it("missing level defaults to info", () => {
      expect(severityFromLevel(undefined)).toBe("info");
      expect(severityFromLevel("")).toBe("info");
    });

    it("missing code or message does not crash; non-actionable when no position_id", () => {
      const item = { level: "warning" } as AlertsView["items"][0];
      expect(isActionable(item)).toBe(false);
      const items = [item];
      const forDash = alertsForDashboard(items);
      expect(forDash).toHaveLength(0);
    });
  });
});
