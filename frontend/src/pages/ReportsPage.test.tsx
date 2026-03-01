/**
 * R25.5: Reports page — monthly summary with mocked hook; no FAIL/WARN in document.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { ReportsPage } from "./ReportsPage";

const mockReport = {
  month: "2026-02",
  total_realized_pl: 500.5,
  by_strategy: { SHARES: 200, CSP: 200.5, CC: 100 },
  trade_count: 5,
  win_count: 3,
  loss_count: 2,
  win_rate: 60,
  avg_hold_days: null,
  top_winners: [
    { symbol: "SPY", realized_pl: 150, strategy: "SHARES" },
    { symbol: "QQQ", realized_pl: 100, strategy: "CSP" },
  ],
  top_losers: [
    { symbol: "IWM", realized_pl: -50, strategy: "CC" },
  ],
  fees_total: 10.0,
};

vi.mock("@/api/queries", () => ({
  useReportsMonthly: () => ({
    data: mockReport,
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders monthly report summary using mocked data", () => {
    render(<ReportsPage />);
    expect(screen.getByRole("heading", { name: /Monthly report/i })).toBeInTheDocument();
    expect(screen.getByText(/Total realized P\/L/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Top winners/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Top losers/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("IWM")).toBeInTheDocument();
  });

  it("document text does not contain FAIL or WARN (R25.5 safety)", () => {
    const { container } = render(<ReportsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });
});
