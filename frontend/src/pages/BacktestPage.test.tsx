/**
 * R27.5: Backtest page — controls, run mutation, results from mocked response, download buttons; no FAIL/WARN in DOM.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@/test/test-utils";
import { BacktestPage } from "./BacktestPage";

const mockRunResponse = {
  status: "OK",
  run_id: "run-123",
  created_ts: "2026-02-27T12:00:00Z",
  mode: "live",
  paths: { summary_json: "/path/summary.json", trades_csv: "/path/trades.csv" },
  metrics: {
    start_date: "2026-02-20",
    end_date: "2026-02-27",
    mode: "live",
    total_realized_pl: 500,
    total_fees: 10,
    trade_count: 5,
    win_count: 3,
    loss_count: 2,
    win_rate: 60,
    by_strategy: { SHARES: { realized_pl: 300, trades: 2, wins: 1, losses: 1 }, CSP: { realized_pl: 200, trades: 3, wins: 2, losses: 1 } },
    max_drawdown_proxy: 50,
  },
  trades: [
    { trade_date: "2026-02-21", symbol: "SPY", strategy: "SHARES", action: "SELL", qty: 100, realized_pl: 200 },
    { trade_date: "2026-02-22", symbol: "QQQ", strategy: "CSP", action: "CLOSE_CSP", realized_pl: 150 },
  ],
};

const mockMutate = vi.fn();

vi.mock("@/api/queries", () => ({
  useBacktestRuns: () => ({
    data: { runs: [{ id: "run-123", start_date: "2026-02-20", end_date: "2026-02-27", mode: "live", created_ts: "2026-02-27T12:00:00Z", path_json: "{}" }] },
    isLoading: false,
  }),
  useBacktestRun: () => ({
    mutate: mockMutate,
    mutateAsync: vi.fn().mockResolvedValue(mockRunResponse),
    isPending: false,
  }),
  useR40LastRun: () => ({
    data: { status: "OK", simulation: true, manual_only: true, present: false },
    isLoading: false,
  }),
  downloadBacktestFile: vi.fn(),
}));

describe("BacktestPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders controls (date range, include paper, paper only, run button)", () => {
    render(<BacktestPage />);
    expect(screen.getByText("Backtest")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-start-date")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-end-date")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-include-paper")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-paper-only")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-run-btn")).toBeInTheDocument();
  });

  it("run mutation called with expected payload when Run is clicked", async () => {
    render(<BacktestPage />);
    await userEvent.click(screen.getByTestId("backtest-run-btn"));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        start_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        end_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        include_paper: false,
        paper_only: false,
      }),
      expect.any(Object)
    );
  });

  it("renders Run backtest card with date inputs and Run button", () => {
    render(<BacktestPage />);
    expect(screen.getByText("Run backtest")).toBeInTheDocument();
    expect(screen.getByTestId("backtest-run-btn")).toHaveTextContent(/Run/i);
  });

  it("document text does not contain FAIL or WARN (R27.5 safety)", () => {
    const { container } = render(<BacktestPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });
});
