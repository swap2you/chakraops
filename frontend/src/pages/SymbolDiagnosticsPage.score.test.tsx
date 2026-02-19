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

describe("SymbolDiagnosticsPage Gate Summary", () => {
  it("renders sample-driven delta message when reasons_explained has delta sample", () => {
    const sampleDrivenMessage =
      "abs(delta) 0.55 (55%) outside target range 0.20–0.40.";
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        primary_reason: "No contract passed (rejected_due_to_delta=5)",
        reasons_explained: [
          {
            code: "rejected_due_to_delta",
            severity: "blocker",
            title: "Delta band",
            message: sampleDrivenMessage,
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=HD");
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText(/Gate Summary/)).toBeInTheDocument();
    expect(screen.getByText(sampleDrivenMessage)).toBeInTheDocument();
    expect(screen.getByText(/abs\(delta\)/)).toBeInTheDocument();
    expect(screen.getByText(/0\.55/)).toBeInTheDocument();
    expect(screen.getByText(/outside target range/)).toBeInTheDocument();
  });

  it("gate table shows formatted reason, never raw rejected_due_to_delta=N as delta", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        gates: [
          { name: "Stage2", status: "FAIL", reason: "rejected_due_to_delta=32", pass: false },
        ],
      },
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=HD");
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText(/Rejected due to delta band \(rejected_count=32\)/)).toBeInTheDocument();
    expect(screen.queryByText(/delta=32/)).not.toBeInTheDocument();
  });

  it("shows parsed English when reasons_explained is empty (rejected_due_to_delta=N → rejected_count)", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        primary_reason: "No contract passed (rejected_due_to_delta=5)",
        reasons_explained: [],
      },
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=HD");
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText(/Gate Summary/)).toBeInTheDocument();
    // Parser maps rejected_due_to_delta=5 to "Rejected due to delta band (rejected_count=5)."
    expect(screen.getByText(/Rejected due to delta band \(rejected_count=5\)/)).toBeInTheDocument();
    expect(screen.queryByText(/delta=5/)).not.toBeInTheDocument();
  });
});

describe("SymbolDiagnosticsPage R21.4 Technical details panel", () => {
  const mockWithComputedValues = {
    ...mockDiagnosticsWithCap,
    computed_values: {
      rsi: 54.1,
      rsi_range: [40, 60] as [number, number],
      atr: 2.5,
      atr_pct: 0.02,
      support_level: 100,
      resistance_level: 110,
      regime: "UP",
      delta_band: [0.25, 0.35] as [number, number],
      rejected_count: 3,
    },
  };

  beforeEach(() => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockWithComputedValues,
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=NVDA");
  });

  it("renders Technical details panel with expected fields and safe labels", () => {
    render(<SymbolDiagnosticsPage />);
    const panel = screen.getByTestId("technical-details-panel");
    expect(panel).toBeInTheDocument();
    expect(panel).toHaveTextContent("Technical details");
    // Safe labels (no FAIL_* codes)
    expect(panel).toHaveTextContent("RSI");
    expect(panel).toHaveTextContent("RSI range");
    expect(panel).toHaveTextContent("Delta band");
    expect(panel).toHaveTextContent("Rejected count");
    expect(panel).toHaveTextContent("54.1");
    expect(panel).toHaveTextContent("40 – 60");
    expect(panel).toHaveTextContent("0.25 – 0.35");
    expect(panel).toHaveTextContent("3");
    expect(panel).toHaveTextContent("UP");
  });

  it("does not show raw FAIL_* codes in the technical details panel", () => {
    render(<SymbolDiagnosticsPage />);
    const panel = screen.getByTestId("technical-details-panel");
    expect(panel).toBeInTheDocument();
    expect(panel).not.toHaveTextContent("FAIL_");
  });
});
