// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R43 — Why no trade / first hard blocker + stock/options freshness sections.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithRoute, screen, clearTestQueryCache } from "@/test/test-utils";
import { SymbolDiagnosticsPage, deriveWhyNoTrade } from "./SymbolDiagnosticsPage";

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
    useUniverseV2Record: () => ({ data: null }),
  };
});

const blockedDiag = {
  symbol: "AAPL",
  verdict: "BLOCKED",
  primary_reason: "Price data is stale",
  provider_status: "OK",
  gates: [{ name: "Freshness", status: "FAIL", pass: false, reason: "Quote older than threshold" }],
  blockers: [],
  stock: { price: 100, quote_as_of: "2026-08-10T14:00:00Z", field_sources: { price: "ORATS" } },
  exit_plan: {},
  explanation: {},
  symbol_eligibility: {},
  computed: {},
  candidates: [],
  as_of_inputs: { orats_as_of: "2026-08-10T14:05:00Z", quote_as_of: "2026-08-10T14:00:00Z" },
  canonical_status: "OK",
  active_profile: "balanced",
  decision_source: "canonical_decision_engine",
  canonical_decision: {
    symbol: "AAPL",
    strategy: "CSP",
    next_action_code: "BLOCKED",
    decision_status: "BLOCKED",
    reason_codes: ["STALE_PRICE"],
    risk_flags: [],
    manual_only: true,
    authoritative: true,
    recommended_by: "canonical_decision_engine",
  },
};

describe("SymbolDiagnosticsPage R43", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearTestQueryCache();
  });

  it("deriveWhyNoTrade prefers first failed gate", () => {
    const why = deriveWhyNoTrade(blockedDiag as never);
    expect(why?.source).toBe("gate");
    expect(why?.summary).toMatch(/Quote older/i);
  });

  it("shows why-no-trade card with first hard blocker", () => {
    useSymbolDiagnosticsMock.mockReturnValue({ data: blockedDiag, isLoading: false, isError: false });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=AAPL");
    expect(screen.getByTestId("why-no-trade-card")).toBeInTheDocument();
    expect(screen.getByTestId("first-hard-blocker-badge")).toHaveTextContent(/First hard blocker/i);
    expect(screen.getByTestId("why-no-trade-summary")).toHaveTextContent(/Quote older/i);
  });

  it("renders stock and options data freshness sections on Options tab", () => {
    useSymbolDiagnosticsMock.mockReturnValue({ data: blockedDiag, isLoading: false, isError: false });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=AAPL");
    expect(screen.getByTestId("stock-data-section")).toHaveTextContent(/as of/i);
    expect(screen.getByTestId("options-data-section")).toHaveTextContent(/ORATS as of/i);
  });

  it("renders stock data section on Shares tab", () => {
    useSymbolDiagnosticsMock.mockReturnValue({ data: blockedDiag, isLoading: false, isError: false });
    renderWithRoute(
      <SymbolDiagnosticsPage initialTabForTest="Shares" />,
      "/symbol-diagnostics?symbol=AAPL&tab=Shares"
    );
    expect(screen.getByTestId("shares-stock-data-section")).toHaveTextContent(/100/);
  });
});
