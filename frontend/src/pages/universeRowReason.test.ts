// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R36.2 — universeRowReason: hard-over-soft ordering, no empty cells, no raw code leak.

import { describe, it, expect } from "vitest";
import { universeRowReason } from "./UniversePage";

describe("universeRowReason", () => {
  it("orders hard (FAIL) reasons ahead of soft (WARN) reasons", () => {
    // Legacy /api/ui/universe emits severity FAIL/WARN (not HARD/SOFT).
    const { text, tooltip } = universeRowReason({
      reasons_explained: [
        { code: "WARN_RSI_RANGE", severity: "WARN", title: "RSI outside preferred range" },
        { code: "FAIL_REGIME", severity: "FAIL", title: "Regime conflict" },
      ],
    });
    expect(text).toBe("Regime conflict");
    // Tooltip lists hard first too.
    expect(tooltip.indexOf("Regime conflict")).toBeLessThan(tooltip.indexOf("RSI outside preferred range"));
  });

  it("orders registry HARD ahead of SOFT", () => {
    const { text } = universeRowReason({
      reasons_explained: [
        { code: "DELTA_OUT_OF_RANGE", severity: "SOFT", title: "Delta out of range" },
        { code: "STALE_PRICE", severity: "HARD", title: "Price data is stale" },
      ],
    });
    expect(text).toBe("Price data is stale");
  });

  it("never leaves an empty reason cell for an eligible row", () => {
    const { text } = universeRowReason({ verdict: "ELIGIBLE", final_verdict: "ELIGIBLE" });
    expect(text).toBe("Passed all checks");
  });

  it("shows Not evaluated when there is no verdict", () => {
    const { text } = universeRowReason({});
    expect(text).toBe("Not evaluated");
  });

  it("never leaks a raw FAIL_/WARN_ code from primary_reason fallback", () => {
    const { text, tooltip } = universeRowReason({ verdict: "BLOCKED", primary_reason: "FAIL_STALE_PRICE" });
    expect(text).not.toMatch(/FAIL_|WARN_/);
    expect(tooltip).not.toMatch(/FAIL_|WARN_/);
    expect(text).toBe("STALE PRICE");
  });
});
