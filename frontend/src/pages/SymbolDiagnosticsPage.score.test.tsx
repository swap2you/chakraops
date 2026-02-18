/**
 * Score UX and liquidity_evaluated tests.
 * - Tooltip includes raw + final + cap when cap applies.
 * - liquidity_evaluated=false shows "Not evaluated", not "failed".
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { SymbolDiagnosticsPage } from "./SymbolDiagnosticsPage";

const mockDiagnosticsWithCap = {
  symbol: "SPY",
  verdict: "HOLD",
  primary_reason: "test",
  composite_score: 65,
  raw_score: 89,
  final_score: 65,
  pre_cap_score: 89,
  score_caps: {
    regime_cap: 65,
    applied_caps: [
      {
        type: "regime_cap",
        cap_value: 65,
        before: 89,
        after: 65,
        reason: "Regime NEUTRAL caps score to 65",
      },
    ],
  },
  confidence_band: "B",
  liquidity: {
    stock_liquidity_ok: null,
    option_liquidity_ok: null,
    reason: null,
    liquidity_evaluated: false,
  },
  provider_status: "OK",
  gates: [],
  stock: { price: 450 },
  exit_plan: {},
  explanation: {},
  symbol_eligibility: {},
  computed: {},
};

const useSymbolDiagnosticsMock = vi.fn();
vi.mock("@/api/queries", () => ({
  useSymbolDiagnostics: (...args: unknown[]) => useSymbolDiagnosticsMock(...args),
  useRecomputeSymbolDiagnostics: () => ({ mutate: vi.fn(), isPending: false }),
  useDefaultAccount: () => ({ data: null }),
  useUiSystemHealth: () => ({ data: { market: { phase: "OPEN" } } }),
}));

describe("SymbolDiagnosticsPage score UX", () => {
  beforeEach(() => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockDiagnosticsWithCap,
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=SPY");
  });

  it("shows Final score with cap indicator when score_caps applies", async () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText(/Final score 65/)).toBeInTheDocument();
    expect(screen.getByText(/capped from 89/)).toBeInTheDocument();
  });

  it("shows Not evaluated for liquidity when liquidity_evaluated=false", async () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getAllByText("Not evaluated").length).toBeGreaterThanOrEqual(1);
  });
});

describe("SymbolDiagnosticsPage run_id fetch (Phase 11.2)", () => {
  it("does not show exact run warning when exact_run is true", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...mockDiagnosticsWithCap, exact_run: true, run_id: "run-123" },
      isLoading: false,
      isError: false,
    });
    window.history.pushState(
      {},
      "",
      "/symbol-diagnostics?symbol=SPY&run_id=run-123"
    );
    render(<SymbolDiagnosticsPage />);
    expect(screen.queryByText(/Exact run not available/)).not.toBeInTheDocument();
  });

  it("shows exact run warning when run_id in URL and exact_run is false", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...mockDiagnosticsWithCap, exact_run: false },
      isLoading: false,
      isError: false,
    });
    window.history.pushState(
      {},
      "",
      "/symbol-diagnostics?symbol=SPY&run_id=missing-run-uuid"
    );
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText(/Exact run not available/)).toBeInTheDocument();
    expect(screen.getByText(/was not found in history/)).toBeInTheDocument();
  });
});
