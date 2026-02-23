/**
 * Score UX and liquidity_evaluated tests.
 * - Tooltip includes raw + final + cap when cap applies.
 * - liquidity_evaluated=false shows "Not evaluated", not "failed".
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
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
vi.mock("@/api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/queries")>();
  return {
    ...actual,
    useSymbolDiagnostics: (...args: unknown[]) => useSymbolDiagnosticsMock(...args),
    useRecomputeSymbolDiagnostics: () => ({ mutate: vi.fn(), isPending: false }),
    useDefaultAccount: () => ({ data: null }),
    useUiSystemHealth: () => ({ data: { market: { phase: "OPEN" } } }),
    useUpsertSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
  };
});

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

  it("R23.1: Symbol header shows price when present", () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("$450.00")).toBeInTheDocument();
  });

  it("R23.1: Symbol header shows — when price absent", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...mockDiagnosticsWithCap, stock: {} },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.queryByText("$450.00")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });
});

describe("SymbolDiagnosticsPage R23.1 Shares opened date", () => {
  beforeEach(() => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...mockDiagnosticsWithCap, shares_plan: {}, shares_position: null },
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=SPY");
  });

  it("Shares opened date input has type=date", () => {
    render(<SymbolDiagnosticsPage />);
    const sharesTab = screen.getByRole("button", { name: /Shares/i });
    fireEvent.click(sharesTab);
    const addBtn = screen.getByRole("button", { name: /Add Shares Position/i });
    fireEvent.click(addBtn);
    const dateInput = document.querySelector('input[type="date"]');
    expect(dateInput).toBeInTheDocument();
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

describe("SymbolDiagnosticsPage R22.4 MTF levels and hold-time", () => {
  const mockWithMtf = {
    ...mockDiagnosticsWithCap,
    mtf_levels: {
      monthly: { support: 100, resistance: 110, as_of: "2026-02-17T18:00:00Z", method: "pivot" },
      weekly: { support: 100, resistance: 110, as_of: "2026-02-17T18:00:00Z", method: "pivot" },
      daily: { support: 100, resistance: 110, as_of: "2026-02-17T18:00:00Z", method: "pivot" },
      "4h": null,
    },
    methodology: { candles_source: "diagnostics", window: "20", clustering_tolerance_pct: 1.0, active_criteria: "nearest_to_spot" },
    targets: { t1: 108, t2: 112, t3: 115 },
    invalidation: 98,
    hold_time_estimate: { sessions: 5, basis_key: "atr_sessions_to_target" },
  };

  beforeEach(() => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockWithMtf,
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=SPY");
  });

  it("renders Multi-timeframe levels section when mtf_levels present", async () => {
    render(<SymbolDiagnosticsPage />);
    const mtfHeading = await screen.findByText("Multi-timeframe levels");
    expect(mtfHeading).toBeInTheDocument();
    expect(screen.getByText("monthly")).toBeInTheDocument();
    expect(screen.getByText("daily")).toBeInTheDocument();
  });

  it("does not show raw FAIL_* in MTF or hold-time user-facing text", async () => {
    render(<SymbolDiagnosticsPage />);
    await screen.findByText("Multi-timeframe levels");
    expect(document.body.innerHTML).not.toMatch(/FAIL_[A-Z_0-9]+/);
  });
});

describe("SymbolDiagnosticsPage R23.2 Delta diagnostics and override", () => {
  const mockWithDeltaDiagnostics = {
    ...mockDiagnosticsWithCap,
    delta_diagnostics: {
      band_min: 0.2,
      band_max: 0.4,
      best_delta: 0.18,
      miss: 0.02,
      direction: "BELOW_BAND" as const,
      best_candidate: { strike: 165, expiry: "2026-04-18", bid: 1.8, ask: 2 },
    },
  };

  beforeEach(() => {
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=WMT");
  });

  it("renders Delta band (rejected) card with best_delta, miss, and direction when delta_diagnostics present", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockWithDeltaDiagnostics,
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("Delta band (rejected)")).toBeInTheDocument();
    expect(screen.getByText(/Best available delta/)).toBeInTheDocument();
    expect(screen.getByText("0.18")).toBeInTheDocument();
    expect(screen.getByText(/Distance to band/)).toBeInTheDocument();
    expect(screen.getByText("0.02")).toBeInTheDocument();
    expect(screen.getByText(/below band/)).toBeInTheDocument();
    expect(screen.getByText(/Target band/)).toBeInTheDocument();
    expect(screen.getByText(/0.2 – 0.4/)).toBeInTheDocument();
    expect(screen.getAllByText(/Closest contract/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Strike 165/)).toBeInTheDocument();
  });

  it("shows Override active badge when delta_override is present", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockWithDeltaDiagnostics,
        delta_override: { delta_lo: 0.2, delta_hi: 0.42, updated_at_utc: "2026-02-17T20:00:00Z" },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("Override active")).toBeInTheDocument();
    expect(screen.getByText(/Band: 0.2 – 0.42/)).toBeInTheDocument();
  });

  it("shows Adjust delta band (Advanced) only after Show Advanced is clicked", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockWithDeltaDiagnostics,
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.queryByText("Adjust delta band (Advanced)")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Show Advanced"));
    expect(screen.getByText("Adjust delta band (Advanced)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Hide Advanced"));
    expect(screen.queryByText("Adjust delta band (Advanced)")).not.toBeInTheDocument();
  });
});
