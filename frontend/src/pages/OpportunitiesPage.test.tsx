// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
/** R39: Opportunities page — strategy buckets + near miss / blocked. */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { OpportunitiesPage } from "./OpportunitiesPage";

function item(symbol: string, strategy: string, action = "ENTRY", extra: Record<string, unknown> = {}) {
  return {
    symbol,
    strategy,
    next_action_code: action,
    decision_status: action === "BLOCKED" ? "BLOCKED" : "ACTIONABLE",
    capital_required: 10000,
    expected_return_pct: 2.5,
    score: 90,
    reason_codes: [],
    risk_flags: [],
    event_risk: { earnings_days: 30 },
    manual_only: true,
    authoritative: true,
    recommended_by: "canonical_decision_engine",
    ...extra,
  };
}

const payload = {
  top_options: [],
  top_shares: [],
  recently_changed: [],
  decision_source: "canonical_decision_engine",
  active_profile: "balanced",
  manual_only: true,
  authoritative_recommendations: {
    decision_source: "canonical_decision_engine",
    manual_only: true,
    active_profile: "balanced",
    as_of_utc: "2026-06-21T16:00:00Z",
    actionable: [item("AAPL", "CSP"), item("MSFT", "CC"), item("WMT", "SHARES")],
    watch: [item("TSLA", "CSP", "WATCH")],
    blocked: [item("ZZZZ", "CSP", "BLOCKED", { reason_codes: ["STALE_PRICE"] })],
    stay_in_cash: null,
  },
};

const mockUseActionNeeded = vi.fn(() => ({ data: payload, isLoading: false, isError: false }));
const mockNearMisses = vi.fn(() => ({
  data: { near_misses: [{ symbol: "NEAR1", reason: "BELOW_RETURN_THRESHOLD" }] },
  isLoading: false,
  isError: false,
}));

vi.mock("@/api/queries", () => ({
  useActionNeeded: (...a: unknown[]) => mockUseActionNeeded(...a),
  useUiSystemHealth: () => ({ data: { orats: { status: "OK" } } }),
  useUniverseV2NearMisses: (...a: unknown[]) => mockNearMisses(...a),
}));

describe("OpportunitiesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseActionNeeded.mockReturnValue({ data: payload, isLoading: false, isError: false });
  });

  it("renders page and strategy sections", () => {
    render(<OpportunitiesPage />);
    expect(screen.getByTestId("opportunities-page")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /opportunities/i })).toBeInTheDocument();
    expect(screen.getByTestId("opp-section-csp")).toBeInTheDocument();
    expect(screen.getByTestId("opp-section-cc")).toBeInTheDocument();
    expect(screen.getByTestId("opp-section-shares")).toBeInTheDocument();
    expect(screen.getByTestId("opp-section-watch")).toBeInTheDocument();
    expect(screen.getByTestId("opp-section-near-miss")).toBeInTheDocument();
    expect(screen.getByTestId("opp-section-blocked")).toBeInTheDocument();
  });

  it("lists CSP / CC / Shares / Watch / Blocked symbols", () => {
    render(<OpportunitiesPage />);
    expect(screen.getByTestId("opp-csp-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("opp-cc-MSFT")).toBeInTheDocument();
    expect(screen.getByTestId("opp-shares-WMT")).toBeInTheDocument();
    expect(screen.getByTestId("opp-watch-TSLA")).toBeInTheDocument();
    expect(screen.getByTestId("opp-blocked-ZZZZ")).toBeInTheDocument();
  });

  it("shows universe near-miss symbols", () => {
    render(<OpportunitiesPage />);
    expect(screen.getByTestId("opp-near-miss-uv2-NEAR1")).toBeInTheDocument();
  });
});
