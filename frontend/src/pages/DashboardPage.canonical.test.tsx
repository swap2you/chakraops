// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0 (H-5 cutover): Dashboard renders the canonical authoritative block as the
// operator-facing PRIMARY recommendation; legacy lists are demoted to a collapsed
// diagnostics section and never act as a primary recommendation.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { DashboardPage } from "./DashboardPage";

const mockDecision = {
  artifact: { artifact_version: "v2", metadata: { pipeline_timestamp: "2026-01-01T12:00:00Z" }, symbols: [], selected_candidates: [] },
  artifact_version: "v2", evaluation_timestamp_utc: "2026-01-01T12:00:00Z", decision_store_mtime_utc: "2026-01-01T12:00:00Z",
};
const mockHealth = { api: { status: "OK" }, market: { phase: "OPEN" }, orats: { status: "OK" } };

function item(symbol: string, status = "ACTIONABLE", action = "ENTRY", extra: Record<string, unknown> = {}) {
  return {
    symbol, strategy: "CSP", next_action_code: action, decision_status: status,
    capital_required: 10000, expected_return_pct: 2.5, score: 90,
    reason_codes: [], risk_flags: [], event_risk: { earnings_days: 30 },
    manual_only: true, authoritative: true, recommended_by: "canonical_decision_engine", ...extra,
  };
}

function payload(over: Record<string, unknown> = {}) {
  return {
    top_options: [{ symbol: "LEGACY1", next_action_code: "ENTRY", rationale_lines: [] }],
    top_shares: [],
    recently_changed: [],
    decision_source: "canonical_decision_engine",
    active_profile: "balanced",
    manual_only: true,
    legacy_lists_role: "diagnostic_non_authoritative",
    authoritative_recommendations: {
      decision_source: "canonical_decision_engine", manual_only: true, active_profile: "balanced",
      as_of_utc: "2026-06-21T16:00:00Z",
      actionable: [item("AAPL")], watch: [], blocked: [], stay_in_cash: null, counts: { actionable: 1 },
    },
    capital_safety: {
      per_suggestion_not_additive: true, note_code: "X", total_capital_required_displayed: 10000,
      available_cash: 50000, cash_known: true, cash_buffer_pct: 20, cash_buffer_amount: 10000,
      deployable_capital: 40000, exceeds_deployable_capital: false, flags: [], assumes_leverage_or_margin: false,
    },
    ...over,
  };
}

const mockUseActionNeeded = vi.fn(() => ({ data: payload(), isLoading: false, isError: false }));
vi.mock("@/api/queries", () => ({
  useArtifactList: () => ({ data: { files: [{ name: "decision_latest.json" }] } }),
  useDecision: () => ({ data: mockDecision }),
  useUniverse: () => ({ data: { symbols: [], updated_at: "2026-01-01T12:00:00Z", source: "ARTIFACT_V2" } }),
  useUiSystemHealth: () => ({ data: mockHealth }),
  useUnifiedPositionsFromDb: () => ({ data: { count: 0, items: [] } }),
  useLivePositionLenses: () => ({
    data: {
      live_open_count: 0,
      live_equity_count: 0,
      live_option_count: 0,
      live_authority: "broker_snapshot",
      live_state: "FRESH",
    },
  }),
  usePortfolio: () => ({ data: { capital_deployed: 0, positions: [] } }),
  useDefaultAccount: () => ({ data: { account: { account_id: "acct_1" } } }),
  usePortfolioMtm: () => ({ data: null }),
  useSharesCandidates: () => ({ data: null }),
  useActionNeeded: (...a: unknown[]) => mockUseActionNeeded(...a),
  useNotifications: () => ({ data: { notifications: [] } }),
  useRunEval: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isSuccess: false, isError: false, error: null }),
}));

describe("DashboardPage canonical cutover", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseActionNeeded.mockReturnValue({ data: payload(), isLoading: false, isError: false });
  });

  it("renders the canonical primary card from authoritative output", async () => {
    render(<DashboardPage />);
    expect(await screen.findByTestId("canonical-primary")).toBeInTheDocument();
    expect(screen.getByTestId("canonical-rec-AAPL")).toBeInTheDocument();
  });

  it("shows manual-only wording, active profile, and capital safety", async () => {
    render(<DashboardPage />);
    expect(await screen.findByTestId("canonical-manual-only")).toHaveTextContent(/manual execution only/i);
    expect(screen.getByText(/Profile: balanced/i)).toBeInTheDocument();
    expect(screen.getByTestId("canonical-capital-safety")).toHaveTextContent(/deployable cash/i);
  });

  it("demotes legacy lists to a collapsed diagnostics section", async () => {
    render(<DashboardPage />);
    const legacy = await screen.findByTestId("legacy-diagnostics");
    expect(legacy.tagName.toLowerCase()).toBe("details");
    expect(legacy).not.toHaveAttribute("open");
  });

  it("caps actionable primary cards to the profile top 5-7", async () => {
    const many = Array.from({ length: 10 }, (_, i) => item(`SYM${i}`));
    mockUseActionNeeded.mockReturnValue({
      data: payload({ authoritative_recommendations: { decision_source: "canonical_decision_engine", manual_only: true, active_profile: "balanced", as_of_utc: "2026-06-21T16:00:00Z", actionable: many, watch: [], blocked: [], stay_in_cash: null } }),
      isLoading: false, isError: false,
    });
    render(<DashboardPage />);
    const cards = await screen.findAllByTestId(/^canonical-rec-/);
    expect(cards.length).toBeLessThanOrEqual(7);
    expect(cards.length).toBeGreaterThanOrEqual(5);
  });

  it("never renders an actionable primary when canonical is unavailable", async () => {
    mockUseActionNeeded.mockReturnValue({
      data: payload({
        authoritative_recommendations: { decision_source: "canonical_decision_engine_unavailable", status: "UNAVAILABLE", manual_only: true, active_profile: "balanced", actionable: [], watch: [], blocked: [], reason_codes: ["CANONICAL_ARTIFACT_MISSING"] },
        capital_safety: null,
      }),
      isLoading: false, isError: false,
    });
    render(<DashboardPage />);
    expect(await screen.findByTestId("canonical-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("canonical-rec-AAPL")).not.toBeInTheDocument();
  });

  it("shows stay-in-cash (no actionable primary) when stale data blocks everything", async () => {
    mockUseActionNeeded.mockReturnValue({
      data: payload({
        authoritative_recommendations: { decision_source: "canonical_decision_engine", manual_only: true, active_profile: "balanced", as_of_utc: "2026-06-21T16:00:00Z", actionable: [], watch: [], blocked: [item("ZZZZ", "BLOCKED", "BLOCKED", { reason_codes: ["STALE_PRICE"] })], stay_in_cash: null },
      }),
      isLoading: false, isError: false,
    });
    render(<DashboardPage />);
    expect(await screen.findByTestId("canonical-stay-in-cash")).toBeInTheDocument();
    expect(screen.queryByTestId("canonical-rec-AAPL")).not.toBeInTheDocument();
  });
});
