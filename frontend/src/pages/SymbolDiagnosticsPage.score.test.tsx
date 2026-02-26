/**
 * Score UX and liquidity_evaluated tests.
 * - Tooltip includes raw + final + cap when cap applies.
 * - liquidity_evaluated=false shows "Not evaluated", not "failed".
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, renderWithFreshClient, renderWithRoute, screen, fireEvent, waitFor, within, clearTestQueryCache } from "@/test/test-utils";
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
    useDefaultAccount: () => ({ data: { account: { account_id: "default" } } }),
    useUiSystemHealth: () => ({ data: { market: { phase: "OPEN" } } }),
    useUpsertSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useCloseSharePosition: () => ({ mutate: vi.fn(), isPending: false }),
    useClosedSharePositions: () => ({ data: { positions: [] } }),
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
    expect(screen.getByText(/Final [Ss]core 65/)).toBeInTheDocument();
    expect(screen.getByTestId("score-used-line")).toHaveTextContent(/capped/);
  });

  it("R23.4.4: Score breakdown shows Capped by when applied_caps present", () => {
    render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    expect(screen.getByText("Capped by")).toBeInTheDocument();
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
  });

  it("R23.4.7 Case A: applied_caps present — Capped by summary line with reason_code (cap=cap_value): before→after", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        score_caps: {
          regime_cap: 65,
          applied_caps: [
            { type: "regime_cap", reason_code: "REGIME_CAP", cap_value: 65, before: 89, after: 65, reason: "Regime NEUTRAL caps score to 65" },
          ],
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    expect(screen.getByTestId("capped-by-summary")).toHaveTextContent(/REGIME_CAP \(cap=65\): 89→65/);
    expect(screen.getByText("Capped by")).toBeInTheDocument();
  });

  it("R23.4.7 Case B: applied_caps empty — No caps applied", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        score_breakdown: { composite_score: 70, raw_score: 70, final_score: 70 },
        score_caps: { applied_caps: [] },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    expect(screen.getByTestId("no-caps-applied")).toHaveTextContent("No caps applied.");
  });

  it("R23.4.7 Hold-time: formula and compact line when hold_time_atr and hold_time_distance_to_t1 present", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        targets: { t1: 460, t2: null, t3: null },
        hold_time_estimate: {
          sessions: 4,
          basis_key: "atr_sessions_to_target",
          hold_time_basis: "ATR-based",
          hold_time_atr: 2.5,
          hold_time_distance_to_t1: 10,
          hold_time_sessions: 4,
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByTestId("hold-time-formula")).toHaveTextContent("Sessions to T1 = ceil(|T1-Spot| / ATR)");
    expect(screen.getByTestId("hold-time-block")).toHaveTextContent("ATR");
    expect(screen.getByTestId("hold-time-block")).toHaveTextContent("Distance");
  });

  it("R24.5: earnings advisory pill when earnings_data_status OK and earnings_next_date", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        earnings: {
          earnings_days: 1,
          earnings_block: false,
          note: null,
          earnings_next_date: "2026-02-26",
          earnings_annc_tod: "AMC",
          implied_earnings_move_pct: 6.5,
          earnings_data_status: "OK",
          earnings_as_of: "2026-02-25T21:00:00Z",
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText(/Earnings: 1d \(AMC\)/)).toBeInTheDocument();
  });

  it("R24.5: no FAIL_ or WARN_ in risk flags / earnings UI text", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        earnings: {
          earnings_days: null,
          earnings_block: false,
          note: "Unavailable",
          earnings_next_date: null,
          earnings_annc_tod: "Unknown",
          implied_earnings_move_pct: null,
          earnings_data_status: "Unavailable",
          earnings_as_of: null,
        },
      },
      isLoading: false,
      isError: false,
    });
    const { container } = render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R24.5.1: no hero pill when earnings_data_status is Unavailable", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        earnings: {
          earnings_days: null,
          earnings_block: false,
          note: "Unavailable",
          earnings_next_date: "2026-02-26",
          earnings_annc_tod: "Unknown",
          implied_earnings_move_pct: null,
          earnings_data_status: "Unavailable",
          earnings_as_of: null,
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.queryByText(/Earnings: 1d/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Earnings: Today/)).not.toBeInTheDocument();
  });

  it("R24.5.1: no 0000-00-00 appears in UI", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        earnings: {
          earnings_days: null,
          earnings_block: false,
          note: "Unavailable",
          earnings_next_date: "0000-00-00",
          earnings_annc_tod: "Unknown",
          implied_earnings_move_pct: null,
          earnings_data_status: "Unavailable",
          earnings_as_of: null,
        },
      },
      isLoading: false,
      isError: false,
    });
    const { container } = render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    const text = container.textContent ?? "";
    expect(text).not.toContain("0000-00-00");
  });

  it("R23.4.8: when applied_caps present shows Score used: Final score (capped)", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        score_caps: {
          regime_cap: 65,
          applied_caps: [
            { type: "regime_cap", reason_code: "REGIME_CAP", cap_value: 65, before: 89, after: 65 },
          ],
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    expect(screen.getByTestId("score-used-line")).toHaveTextContent("Score used: Final score (capped)");
  });

  it("R23.4.8: when applied_caps empty shows Score used: Raw score (uncapped)", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        score_breakdown: { composite_score: 70, raw_score: 70, final_score: 70 },
        score_caps: { applied_caps: [] },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByText("Risk & Details"));
    expect(screen.getByTestId("score-used-line")).toHaveTextContent("Score used: Raw score (uncapped)");
  });

  it("R23.4.8: Hold-time block and help include session = one trading day and plain-English estimate", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        hold_time_estimate: {
          sessions: 5,
          basis_key: "atr_sessions_to_target",
          hold_time_atr: 2,
          hold_time_distance_to_t1: 8,
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    const plainEl = screen.getByTestId("hold-time-plain-english");
    expect(plainEl).toHaveTextContent(/one trading day/i);
    expect(plainEl).toHaveTextContent(/not a promise/i);
    const holdTimeBlock = screen.getByTestId("hold-time-block");
    const helpButton = holdTimeBlock.querySelector("button");
    expect(helpButton).toBeTruthy();
    fireEvent.click(helpButton!);
    expect(screen.getAllByText(/one trading day/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows Not evaluated for liquidity when liquidity_evaluated=false", async () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getAllByText("Not evaluated").length).toBeGreaterThanOrEqual(1);
  });

  it("R23.1: Symbol header shows price when present", () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("$450.00")).toBeInTheDocument();
  });

  it("R23.1: Symbol header shows Not available or — when price absent", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...mockDiagnosticsWithCap, stock: {} },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.queryByText("$450.00")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Not available|—/).length).toBeGreaterThanOrEqual(1);
  });

  it("displays price from underlying_price when price key missing", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: { ...mockDiagnosticsWithCap, stock: { underlying_price: 123.45 } },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("$123.45")).toBeInTheDocument();
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
    expect(screen.getAllByText(/abs\(delta\) 0\.55.*outside target range/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/abs\(delta\)/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/0\.55/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/outside target range/).length).toBeGreaterThanOrEqual(1);
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

  it("R24.6: Gate Summary shows Blocked not FAIL when gate status is FAIL", () => {
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
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=WMT");
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.queryByText(/\bFAIL\b/)).not.toBeInTheDocument();
  });

  it("R24.6: document textContent has no word-boundary FAIL or WARN", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        gates: [
          { name: "Stage1", status: "PASS", reason: null, pass: true },
          { name: "Stage2", status: "FAIL", reason: "rejected_due_to_delta", pass: false },
        ],
        symbol_eligibility: { status: "FAIL", required_data_missing: [], required_data_stale: [] },
      },
      isLoading: false,
      isError: false,
    });
    const { container } = render(<SymbolDiagnosticsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
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
    // Parser maps rejected_due_to_delta=5 to "Rejected due to delta band (rejected_count=5)." (may appear in reasons list)
    expect(screen.getAllByText(/Rejected due to delta band \(rejected_count=5\)/).length).toBeGreaterThanOrEqual(1);
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

  it("renders Targets & hold-time when targets and hold_time_estimate present", () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("Targets & hold-time")).toBeInTheDocument();
    expect(screen.getByText("108")).toBeInTheDocument();
    expect(screen.getByText(/5 sessions/)).toBeInTheDocument();
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

describe("SymbolDiagnosticsPage R23.3 Shares plan", () => {
  const mockWithSharesPlan = {
    ...mockDiagnosticsWithCap,
    shares_plan: {
      eligible: true,
      reason_codes: ["SHARES_ELIGIBLE"],
      spot: 100,
      entry_zone: { low: 98, high: 102, basis: "DAILY_SUPPORT" },
      stop: { price: 96, basis: "WEEKLY_SUPPORT_MINUS_ATR" },
      targets: { t1: 104, t2: 108, basis: "WEEKLY_RESISTANCE" },
      hold_time: { sessions_to_t1: 5, sessions_to_t2: null, method: "ATR_DISTANCE" },
      sizing: { suggested_shares: 40, suggested_cost: 4000, max_loss: 160, risk_pct_used: 0.008, basis: "ACCOUNT_RISK" },
    },
  };

  beforeEach(() => {
    clearTestQueryCache();
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockWithSharesPlan,
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=WMT");
  });

  it("Options tab does not show Shares/Trade Plan content when shares_plan is present", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: mockWithSharesPlan,
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByRole("button", { name: "Options" })).toBeInTheDocument();
    expect(screen.queryByTestId("shares-trade-plan-card")).not.toBeInTheDocument();
    expect(screen.queryByText(/98 – 102/)).not.toBeInTheDocument();
  });

  it("Shares tab shows eligibility and reason codes as safe labels", async () => {
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=WMT");
    renderWithFreshClient(<SymbolDiagnosticsPage initialTabForTest="Shares" />);
    await waitFor(() => expect(screen.getByTestId("shares-tab-content")).toBeInTheDocument(), { timeout: 5000 });
    expect(screen.getByText("Why eligible")).toBeInTheDocument();
    expect(screen.getByText("Meets all shares eligibility rules")).toBeInTheDocument();
  });

  it("Shares tab shows Trade Plan (spot, entry zone, stop, targets, sizing) when eligible", async () => {
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=WMT&tab=Shares");
    const tabContent = await screen.findByTestId("shares-tab-content", {}, { timeout: 10000 });
    const card = within(tabContent).getByTestId("shares-trade-plan-card");
    const withinCard = within(card);
    expect(withinCard.getByText("Trade Plan")).toBeInTheDocument();
    expect(withinCard.getByText("100")).toBeInTheDocument();
    expect(withinCard.getByText(/98 – 102/)).toBeInTheDocument();
    expect(withinCard.getByText("96")).toBeInTheDocument();
    expect(withinCard.getByText("40")).toBeInTheDocument();
  }, 15000);

  it("Shares tab shows insufficient data when sizing basis is INSUFFICIENT_DATA", async () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockWithSharesPlan,
        shares_plan: {
          ...mockWithSharesPlan.shares_plan,
          sizing: { suggested_shares: null, suggested_cost: null, max_loss: null, risk_pct_used: null, basis: "INSUFFICIENT_DATA" },
        },
      },
      isLoading: false,
      isError: false,
    });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=WMT&tab=Shares");
    const tabContent = await screen.findByTestId("shares-tab-content", {}, { timeout: 10000 });
    const card = within(tabContent).getByTestId("shares-trade-plan-card");
    expect(within(card).getByText(/Insufficient data/)).toBeInTheDocument();
  }, 15000);
});

describe("SymbolDiagnosticsPage R23.5.0 Shares Trade Plan and lifecycle", () => {
  beforeEach(() => {
    clearTestQueryCache();
  });

  it("Shares tab renders Trade Plan accordion with entry zone, stop, targets when present", async () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        shares_plan: {
          eligible: false,
          reason_codes: ["NOT_NEAR_SUPPORT"],
          spot: 50,
          entry_zone: { low: 48, high: 52 },
          stop: 45,
          targets: { t1: 55, t2: 58, t3: 60 },
          hold_time: { sessions_to_t1: 4, method: "ATR_DISTANCE" },
          sizing: { basis: "ACCOUNT_RISK", suggested_shares: 20 },
        },
      },
      isLoading: false,
      isError: false,
    });
    renderWithRoute(<SymbolDiagnosticsPage />, "/symbol-diagnostics?symbol=SPY&tab=Shares");
    await screen.findByTestId("shares-tab-content", {}, { timeout: 10000 });
    const card = await screen.findByTestId("shares-trade-plan-card", {}, { timeout: 5000 });
    const withinCard = within(card);
    expect(withinCard.getByText(/48 – 52/)).toBeInTheDocument();
    expect(withinCard.getByText("45")).toBeInTheDocument();
    expect(withinCard.getByText("55")).toBeInTheDocument();
    expect(withinCard.getByTestId("shares-why-checklist")).toBeInTheDocument();
  }, 15000);

  it("Shares tab shows hold-time plain-English when hold_time_estimate has ATR/distance", async () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        shares_plan: {
          eligible: true,
          reason_codes: ["SHARES_ELIGIBLE"],
          spot: 100,
          entry_zone: { low: 98, high: 102 },
          stop: 96,
          targets: { t1: 104 },
          hold_time_estimate: { sessions: 4, hold_time_atr: 2, hold_time_distance_to_t1: 8 },
          sizing: { basis: "ACCOUNT_RISK", suggested_shares: 40 },
        },
      },
      isLoading: false,
      isError: false,
    });
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=SPY");
    renderWithFreshClient(<SymbolDiagnosticsPage initialTabForTest="Shares" />);
    await waitFor(() => expect(screen.getByTestId("shares-hold-time-block")).toBeInTheDocument(), { timeout: 5000 });
    const holdBlock = screen.getByTestId("shares-hold-time-block");
    expect(holdBlock).toHaveTextContent(/one trading day/i);
    expect(holdBlock).toHaveTextContent(/not a promise/i);
  });

  it("Close position modal appears when position exists and Close position is clicked", async () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        shares_plan: { eligible: true, reason_codes: ["SHARES_ELIGIBLE"], spot: 100 },
        shares_position: { id: "pos-1", account_id: "default", symbol: "SPY", quantity: 50, avg_cost: 99, opened_at: null, notes: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
      },
      isLoading: false,
      isError: false,
    });
    renderWithRoute(<SymbolDiagnosticsPage initialTabForTest="Shares" />, "/symbol-diagnostics?symbol=SPY&tab=Shares");
    await screen.findByTestId("shares-tab-content", {}, { timeout: 10000 });
    const closeBtn = await screen.findByTestId("close-position-open-btn", {}, { timeout: 5000 });
    await userEvent.click(closeBtn);
    const modal = await waitFor(() => screen.getByTestId("close-position-modal"), { timeout: 10000 });
    expect(within(modal).getByText("Exit price (required)")).toBeInTheDocument();
    expect(within(modal).getByText("Exit date (default today)")).toBeInTheDocument();
  }, 15000);
});

describe("SymbolDiagnosticsPage R23.4.6 UX and Copilot drawer", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/symbol-diagnostics?symbol=WMT");
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        targets: { t1: 108, t2: 110, t3: 112, target_basis: "SR_LEVEL", level_source_timeframe: "daily", targets_already_exceeded: false },
        hold_time_estimate: { sessions: 5, basis_key: "atr_sessions_to_target" },
      },
      isLoading: false,
      isError: false,
    });
  });

  it("Options tab does not show Copilot panel by default (no right column)", () => {
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByText("Copilot")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /Copilot/i })).not.toBeInTheDocument();
  });

  it("Copilot button opens drawer; drawer can be closed", () => {
    render(<SymbolDiagnosticsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Copilot/i }));
    expect(screen.getByRole("dialog", { name: /Copilot/i })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Close Copilot"));
    expect(screen.queryByRole("dialog", { name: /Copilot/i })).not.toBeInTheDocument();
  });

  it("Tooltip for bar_count or target basis is present when MTF or targets exist", () => {
    render(<SymbolDiagnosticsPage />);
    const barCountHeader = screen.queryByText("bar_count");
    const basisLabel = screen.queryByTestId("target-basis-label");
    expect(barCountHeader != null || basisLabel != null).toBe(true);
  });

  it("shows targets_already_exceeded badge and guidance when flagged", () => {
    useSymbolDiagnosticsMock.mockReturnValue({
      data: {
        ...mockDiagnosticsWithCap,
        stock: { price: 200, underlying_price: 200 },
        targets: { t1: 108, t2: 110, t3: 112, targets_already_exceeded: true },
        hold_time_estimate: { sessions: 5, basis_key: "atr_sessions_to_target" },
      },
      isLoading: false,
      isError: false,
    });
    render(<SymbolDiagnosticsPage />);
    expect(screen.getByTestId("target-already-exceeded-badge")).toBeInTheDocument();
    expect(screen.getByText(/Targets already exceeded at snapshot; recompute for updated levels/)).toBeInTheDocument();
  });
});
