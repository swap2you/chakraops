// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0 (H-5 cutover): Today renders the canonical authoritative block as the
// operator-facing PRIMARY recommendation; the legacy list is demoted to a
// collapsed diagnostics section.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithRoute, screen } from "@/test/test-utils";
import { TodayPage } from "./TodayPage";

const mockSummary = {
  latest_run_ts: "2026-02-27T17:00:00Z", as_of_et: "2026-02-27 12:00 ET",
  cadence: { mode: "EOD_BIASED", eligibility_as_of: "2026-02-27T17:00:00Z" },
  orats_status: "OK", orats_freshness_state_label: "OK", guardrails: { status: "OK" },
  notifications_health: {}, notifications_new_count: 0, earnings_probe: { status: "OK" }, action_needed_count: null,
};

function item(symbol: string) {
  return {
    symbol, strategy: "CSP", next_action_code: "ENTRY", decision_status: "ACTIONABLE",
    capital_required: 10000, expected_return_pct: 2.5, score: 90, reason_codes: [], risk_flags: [],
    event_risk: { earnings_days: 30 }, manual_only: true, authoritative: true, recommended_by: "canonical_decision_engine",
  };
}

const canonicalPayload = {
  top_options: [{ symbol: "LEGACY1", strategy: "CSP", next_action_code: "ENTRY" }],
  top_shares: [], recently_changed: [],
  decision_source: "canonical_decision_engine", active_profile: "balanced", manual_only: true,
  legacy_lists_role: "diagnostic_non_authoritative",
  authoritative_recommendations: {
    decision_source: "canonical_decision_engine", manual_only: true, active_profile: "balanced",
    as_of_utc: "2026-06-21T16:00:00Z", actionable: [item("AAPL")], watch: [], blocked: [], stay_in_cash: null,
  },
  capital_safety: {
    per_suggestion_not_additive: true, note_code: "X", total_capital_required_displayed: 10000,
    available_cash: 50000, cash_known: true, cash_buffer_pct: 20, cash_buffer_amount: 10000,
    deployable_capital: 40000, exceeds_deployable_capital: false, flags: [], assumes_leverage_or_margin: false,
  },
};

vi.mock("@/api/queries", () => ({
  useTodaySummary: vi.fn(() => ({ data: mockSummary, isLoading: false, refetch: vi.fn() })),
  useActionNeeded: vi.fn(() => ({ data: canonicalPayload, isLoading: false, isError: false, refetch: vi.fn() })),
  useRunEval: () => ({ mutate: vi.fn(), isPending: false }),
  useJournal: vi.fn(() => ({ data: { entries: [] } })),
  useNotifications: vi.fn(() => ({ data: { notifications: [] }, refetch: vi.fn() })),
  useAckNotification: () => ({ mutate: vi.fn(), isPending: false }),
  useArchiveNotification: () => ({ mutate: vi.fn(), isPending: false }),
  useAckBulkNotifications: () => ({ mutate: vi.fn(), isPending: false }),
  useArchiveBulkNotifications: () => ({ mutate: vi.fn(), isPending: false }),
  useOpsChecklist: vi.fn(() => ({ data: { row: { status: "OPEN", key: "2026-02-27" } } })),
  useOpsEodSummary: vi.fn(() => ({ data: { date: "2026-02-27" } })),
  useOpsChecklistMarkDone: () => ({ mutate: vi.fn(), isPending: false }),
  useExecutionLogPost: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

describe("TodayPage canonical cutover", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders canonical primary cards from authoritative output", () => {
    renderWithRoute(<TodayPage />, "/today");
    expect(screen.getByTestId("canonical-primary")).toBeInTheDocument();
    expect(screen.getByTestId("canonical-rec-AAPL")).toBeInTheDocument();
  });

  it("shows manual-only wording and capital safety", () => {
    renderWithRoute(<TodayPage />, "/today");
    expect(screen.getByTestId("canonical-manual-only")).toHaveTextContent(/manual execution only/i);
    expect(screen.getByTestId("canonical-capital-safety")).toBeInTheDocument();
  });

  it("demotes the legacy list to collapsed diagnostics", () => {
    renderWithRoute(<TodayPage />, "/today");
    const legacy = screen.getByTestId("today-legacy-diagnostics");
    expect(legacy.tagName.toLowerCase()).toBe("details");
    expect(legacy).not.toHaveAttribute("open");
  });
});
