// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0 (H-5 cutover): Symbol Diagnostics renders the canonical decision as the
// primary authority, treats legacy diagnostics as explanatory, and shows an
// understandable NOT-EVALUATED state with Recompute for absent symbols (never a
// generic "Failed to load"). Raw FAIL_/WARN_/PASS codes are never rendered.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithRoute, screen, clearTestQueryCache } from "@/test/test-utils";
import { SymbolDiagnosticsPage } from "./SymbolDiagnosticsPage";
import { ApiError } from "@/api/client";

const useSymbolDiagnosticsMock = vi.fn();
vi.mock("@/api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/queries")>();
  return {
    ...actual,
    useSymbolDiagnostics: (...args: unknown[]) => useSymbolDiagnosticsMock(...args),
    useRecomputeSymbolDiagnostics: () => ({ mutate: vi.fn(), isPending: false }),
    useDefaultAccount: () => ({ data: { account: { account_id: "default" } } }),
    useUiSystemHealth: () => ({ data: { market: { phase: "OPEN" } } }),
    useActionNeeded: () => ({ data: { top_options: [], top_shares: [] } }),
    useUpsertSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useCloseSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useClosedSharePositions: () => ({ data: { positions: [] } }),
    useSetDeltaOverride: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteDeltaOverride: () => ({ mutate: vi.fn(), isPending: false }),
    useJournalRecordClose: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

const canonicalOk = {
  symbol: "AAPL",
  verdict: "HOLD",
  primary_reason: null,
  provider_status: "OK",
  gates: [],
  stock: { price: 100 },
  exit_plan: {},
  explanation: {},
  symbol_eligibility: {},
  computed: {},
  canonical_status: "OK",
  active_profile: "balanced",
  decision_source: "canonical_decision_engine",
  canonical_decision: {
    symbol: "AAPL", strategy: "CSP", next_action_code: "ENTRY", decision_status: "ACTIONABLE",
    capital_required: 10000, expected_return_pct: 2.5, score: 90,
    reason_codes: ["LIQUIDITY_VALIDATED_UPSTREAM"], risk_flags: ["FAIL_SOMETHING"],
    manual_only: true, authoritative: true, recommended_by: "canonical_decision_engine",
  },
};

describe("SymbolDiagnosticsPage canonical primary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearTestQueryCache();
  });

  it("renders the canonical decision as the primary authority", () => {
    useSymbolDiagnosticsMock.mockReturnValue({ data: canonicalOk, isLoading: false, isError: false });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=AAPL");
    expect(screen.getByTestId("symbol-canonical-decision")).toBeInTheDocument();
  });

  it("never renders raw FAIL_/WARN_/PASS codes in the canonical reasons", () => {
    useSymbolDiagnosticsMock.mockReturnValue({ data: canonicalOk, isLoading: false, isError: false });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=AAPL");
    const reasons = screen.getByTestId("symbol-canonical-reasons");
    expect(reasons.textContent || "").not.toMatch(/FAIL_|WARN_|PASS_/);
  });

  it("shows a NOT-EVALUATED state with Recompute for an absent (404) symbol", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: undefined, isLoading: false, isError: true, error: new ApiError("API 404", 404),
    });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=ZZZZ");
    expect(screen.getByTestId("symbol-unavailable")).toHaveTextContent(/not evaluated/i);
    expect(screen.getByTestId("symbol-unavailable-recompute")).toBeInTheDocument();
    expect(screen.queryByText(/failed to load/i)).not.toBeInTheDocument();
  });

  it("shows canonical-unavailable when the engine has no decision for the symbol", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...canonicalOk, canonical_status: "UNAVAILABLE", canonical_decision: null }, isLoading: false, isError: false,
    });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=AAPL");
    expect(screen.getByTestId("symbol-canonical-unavailable")).toBeInTheDocument();
  });
});
