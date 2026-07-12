// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R36.1 — ExplanationPanel component tests.

import { describe, it, expect } from "vitest";
import { render, screen } from "@/test/test-utils";
import { ExplanationPanel } from "./ExplanationPanel";
import type { RecommendationExplanation } from "@/api/types";

function makeExplanation(overrides: Partial<RecommendationExplanation> = {}): RecommendationExplanation {
  return {
    symbol: "AAPL",
    strategy: "CSP",
    profile: "balanced",
    decision_status: "WATCH",
    manual_only: true,
    trade_execution: false,
    primary_reason: {
      code: "BELOW_RETURN_THRESHOLD",
      category: "RETURN",
      severity: "SOFT",
      klass: "TEMPORARY",
      title: "Below return threshold",
      explanation: "The estimated return is below the profile's minimum.",
      unit: "pct",
      measured_field: "expected_return_pct",
      threshold_field: "profile.min_return_pct",
    },
    supporting_reasons: [
      {
        code: "DELTA_IN_RANGE",
        category: "DELTA",
        severity: "INFO",
        klass: "INFORMATIONAL",
        title: "Delta in target range",
        explanation: "The contract's delta is within the profile band.",
      },
    ],
    passed_gates: ["DELTA_IN_RANGE"],
    failed_gates: ["BELOW_RETURN_THRESHOLD"],
    measured_values: [
      { code: "BELOW_RETURN_THRESHOLD", name: "Below return threshold", measured: 1.8, threshold: 2.0, unit: "pct", comparator: ">=", within: false },
      { code: "DELTA_IN_RANGE", name: "Delta in target range", measured: 0.3, threshold: [0.2, 0.4], unit: "delta", comparator: "in_range", within: true },
    ],
    near_miss: { is_near_miss: true, gate: "BELOW_RETURN_THRESHOLD", measured: 1.8, threshold: 2.0, unit: "pct", distance: 0.2, epsilon: 0.25, note: "Missed BELOW_RETURN_THRESHOLD by 0.2 pct (<= 0.25)." },
    calculation_trace: [
      { input: "Below return threshold", value: 1.8, unit: "pct", source: "computed", timestamp: "2026-07-11T20:00:00+00:00", formula: "return_pct = premium / collateral * 100", threshold: 2.0, comparator: ">=", output: false, rounding: "2dp" },
    ],
    data_sources: [{ name: "PRICE", as_of_utc: "2026-07-11T20:00:00+00:00", status: "FRESH" }],
    timestamps: { price_as_of: "2026-07-11T20:00:00+00:00", chain_as_of: "2026-07-11T20:00:00+00:00" },
    event_risk: { earnings_days: 30, blackout_days: 3 },
    portfolio_impact: { capital_required: 10000, contracts: 1, shares: 0, expected_return_pct: 1.8, expected_return_dollars: 180 },
    temporary_reasons: ["BELOW_RETURN_THRESHOLD"],
    safety_critical_reasons: [],
    ...overrides,
  };
}

describe("ExplanationPanel", () => {
  it("renders nothing when explanation is missing", () => {
    const { container } = render(<ExplanationPanel explanation={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the primary reason title and explanation", () => {
    render(<ExplanationPanel explanation={makeExplanation()} />);
    const primary = screen.getByTestId("explanation-primary");
    expect(primary).toBeInTheDocument();
    expect(primary).toHaveTextContent("Below return threshold");
    expect(primary).toHaveTextContent(/estimated return is below/i);
  });

  it("renders supporting reasons", () => {
    render(<ExplanationPanel explanation={makeExplanation()} />);
    expect(screen.getByTestId("explanation-supporting")).toHaveTextContent("Delta in target range");
  });

  it("renders measured-vs-threshold chips", () => {
    render(<ExplanationPanel explanation={makeExplanation()} />);
    const chip = screen.getByTestId("measured-BELOW_RETURN_THRESHOLD");
    expect(chip).toHaveTextContent("1.80 pct");
    expect(chip).toHaveTextContent("2 pct");
  });

  it("renders a near-miss badge and note", () => {
    render(<ExplanationPanel explanation={makeExplanation()} />);
    const nm = screen.getByTestId("explanation-near-miss");
    expect(nm).toHaveTextContent(/near miss/i);
    expect(nm).toHaveTextContent(/Missed BELOW_RETURN_THRESHOLD/);
  });

  it("does not render near-miss when not a near miss", () => {
    render(<ExplanationPanel explanation={makeExplanation({ near_miss: { is_near_miss: false } })} />);
    expect(screen.queryByTestId("explanation-near-miss")).toBeNull();
  });

  it("shows the safety-critical badge when present", () => {
    render(<ExplanationPanel explanation={makeExplanation({ safety_critical_reasons: ["WIDE_SPREAD"] })} />);
    expect(screen.getByTestId("explanation-safety-critical")).toHaveTextContent("Safety-critical: 1");
  });

  it("renders an expandable calculation trace", () => {
    render(<ExplanationPanel explanation={makeExplanation()} />);
    const trace = screen.getByTestId("explanation-calc-trace");
    expect(trace).toHaveTextContent("Calculation trace");
    expect(trace).toHaveTextContent("return_pct = premium / collateral * 100");
  });

  it("never renders raw FAIL_/WARN_ codes", () => {
    const { container } = render(<ExplanationPanel explanation={makeExplanation()} />);
    expect(container.textContent).not.toMatch(/FAIL_|WARN_/);
  });
});
