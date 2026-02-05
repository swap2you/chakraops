import { describe, it, expect } from "vitest";
import { SCENARIO_KEYS, getScenarioBundle, SCENARIO_LABELS } from "./index";
import { validateScenarioBundle } from "../validator";

describe("Scenario registry", () => {
  it("has at least 18 scenario keys", () => {
    expect(SCENARIO_KEYS.length).toBeGreaterThanOrEqual(18);
  });

  it("each scenario key has a bundle and label", () => {
    for (const key of SCENARIO_KEYS) {
      const bundle = getScenarioBundle(key);
      expect(bundle).toBeDefined();
      expect(bundle.dailyOverview !== undefined || bundle.decisionHistory?.length).toBe(true);
      expect(SCENARIO_LABELS[key]).toBeDefined();
    }
  });

  it("S18 stress scenario has 250+ history and 50+ positions", () => {
    const bundle = getScenarioBundle("S18_STRESS_250_50");
    expect(bundle.decisionHistory.length).toBeGreaterThanOrEqual(250);
    expect(bundle.positions.length).toBeGreaterThanOrEqual(50);
  });

  it("validator returns warnings array (no throw)", () => {
    for (const key of SCENARIO_KEYS) {
      const bundle = getScenarioBundle(key);
      const warnings = validateScenarioBundle(bundle, key);
      expect(Array.isArray(warnings)).toBe(true);
      warnings.forEach((w) => {
        expect(w.code).toBeDefined();
        expect(w.message).toBeDefined();
      });
    }
  });
});
