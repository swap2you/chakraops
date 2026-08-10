// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0: Backtest results must carry an explicit, unmissable simulation label.
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@/test/test-utils";
import { BacktestPage } from "./BacktestPage";

const mockRunResponse = {
  status: "OK",
  run_id: "run-sim-1",
  created_ts: "2026-02-27T12:00:00Z",
  mode: "live",
  paths: { summary_json: "/p/summary.json", trades_csv: "/p/trades.csv" },
  metrics: {
    start_date: "2026-02-20", end_date: "2026-02-27", mode: "live",
    total_realized_pl: 500, total_fees: 10, trade_count: 5,
    win_count: 3, loss_count: 2, win_rate: 60, by_strategy: {}, max_drawdown_proxy: 50,
  },
  trades: [],
};

vi.mock("@/api/queries", () => ({
  useBacktestRuns: () => ({ data: { runs: [] }, isLoading: false }),
  useBacktestRun: () => ({
    mutate: (_payload: unknown, opts?: { onSuccess?: (d: unknown) => void }) => {
      opts?.onSuccess?.(mockRunResponse);
    },
    mutateAsync: vi.fn().mockResolvedValue(mockRunResponse),
    isPending: false,
  }),
  useR40LastRun: () => ({
    data: { status: "OK", simulation: true, manual_only: true, present: false },
    isLoading: false,
  }),
  downloadBacktestFile: vi.fn(),
}));

describe("BacktestPage simulation label", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows 'SIMULATION — NOT A LIVE RECOMMENDATION' once results render", async () => {
    render(<BacktestPage />);
    expect(screen.queryByTestId("backtest-simulation-label")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("backtest-run-btn"));
    const label = screen.getByTestId("backtest-simulation-label");
    expect(label).toBeInTheDocument();
    expect(label).toHaveTextContent(/SIMULATION — NOT A LIVE RECOMMENDATION/i);
  });
});
