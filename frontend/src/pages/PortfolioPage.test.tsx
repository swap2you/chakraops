import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { PortfolioPage } from "./PortfolioPage";

const usePortfolio = vi.fn();
const usePortfolioMetrics = vi.fn();
const useAccounts = vi.fn();
const useDefaultAccount = vi.fn();
const useClosePosition = vi.fn();
const useDeletePosition = vi.fn();
const usePositionEvents = vi.fn();
const usePortfolioRisk = vi.fn();
const useRefreshMarks = vi.fn();
const useAccountSummary = vi.fn();
const useAccountHoldings = vi.fn();
const useSetBalances = vi.fn();
const useUpsertHolding = vi.fn();
const useDeleteHolding = vi.fn();

vi.mock("@/api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/queries")>();
  return {
    ...actual,
    usePortfolio: (...args: unknown[]) => usePortfolio(...args),
    usePortfolioMetrics: (...args: unknown[]) => usePortfolioMetrics(...args),
    useAccounts: (...args: unknown[]) => useAccounts(...args),
    useDefaultAccount: (...args: unknown[]) => useDefaultAccount(...args),
    useClosePosition: (...args: unknown[]) => useClosePosition(...args),
    useDeletePosition: (...args: unknown[]) => useDeletePosition(...args),
    usePositionEvents: (...args: unknown[]) => usePositionEvents(...args),
    usePortfolioRisk: (...args: unknown[]) => usePortfolioRisk(...args),
    useRefreshMarks: (...args: unknown[]) => useRefreshMarks(...args),
    useAccountSummary: (...args: unknown[]) => useAccountSummary(...args),
    useAccountHoldings: (...args: unknown[]) => useAccountHoldings(...args),
    useSetBalances: (...args: unknown[]) => useSetBalances(...args),
    useUpsertHolding: (...args: unknown[]) => useUpsertHolding(...args),
    useDeleteHolding: (...args: unknown[]) => useDeleteHolding(...args),
  };
});

const mockMetrics = {
  open_positions_count: 1,
  capital_deployed: 45000,
  realized_pnl_total: 120,
  win_rate: 0.75,
  avg_pnl: 40,
  avg_credit: 250,
  avg_dte_at_entry: 32,
};

const mockPortfolioOpen = {
  positions: [
    {
      position_id: "pos_1",
      id: "pos_1",
      symbol: "SPY",
      strategy: "CSP",
      status: "OPEN",
      is_test: false,
      entry_credit: 2.5,
      mark: 1.2,
      premium_captured_pct: 52,
      dte: 45,
      alert_flags: [],
    },
  ],
  capital_deployed: 45000,
  open_positions_count: 1,
  shares_positions: [] as Array<{
    symbol: string;
    quantity: number;
    avg_cost?: number | null;
    mark_value?: number | null;
    mark_source?: string | null;
    mark_age_sec?: number | null;
    unrealized_pl?: number | null;
    market_value?: number | null;
    unrealized_pnl?: number | null;
  }>,
};

const mockPortfolioClosed = {
  positions: [
    {
      position_id: "pos_2",
      id: "pos_2",
      symbol: "QQQ",
      strategy: "CC",
      status: "CLOSED",
      is_test: false,
      entry_credit: 3.0,
      realized_pnl: 120,
      alert_flags: [],
    },
  ],
  capital_deployed: 0,
  open_positions_count: 0,
};

const mockPortfolioWithTest = {
  positions: [
    {
      position_id: "pos_3",
      id: "pos_3",
      symbol: "DIAG_TEST_AAPL",
      strategy: "CSP",
      status: "OPEN",
      is_test: true,
      alert_flags: [],
    },
  ],
  capital_deployed: 0,
  open_positions_count: 0,
};

describe("PortfolioPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePortfolio.mockReturnValue({ data: mockPortfolioOpen, isLoading: false, isError: false });
    usePortfolioMetrics.mockReturnValue({ data: mockMetrics });
    useAccounts.mockReturnValue({ data: { accounts: [] } });
    useDefaultAccount.mockReturnValue({ data: { account: null } });
    useClosePosition.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    useDeletePosition.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false });
    usePositionEvents.mockReturnValue({ data: { position_id: "pos_1", events: [] }, isLoading: false });
    usePortfolioRisk.mockReturnValue({ data: { status: "PASS", metrics: {}, breaches: [] } });
    useRefreshMarks.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false });
    useAccountSummary.mockReturnValue({
      data: { account_id: "default", name: "Default", cash: 0, buying_power: 0, holdings_count: 0, base_currency: "USD" },
    });
    useAccountHoldings.mockReturnValue({ data: { holdings: [] } });
    useSetBalances.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useUpsertHolding.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useDeleteHolding.mockReturnValue({ mutate: vi.fn(), isPending: false });
  });

  it("renders without throwing", () => {
    expect(() => render(<PortfolioPage />)).not.toThrow();
  });

  it("shows Close action for OPEN position", async () => {
    render(<PortfolioPage />);
    const closeBtn = await screen.findByRole("button", { name: /close/i });
    expect(closeBtn).toBeInTheDocument();
  });

  it("shows Portfolio Metrics card (Phase 12.0)", async () => {
    render(<PortfolioPage />);
    expect(screen.getByText(/Portfolio Metrics/)).toBeInTheDocument();
    expect(screen.getByText(/Realized PnL total/)).toBeInTheDocument();
    expect(screen.getByText(/\$120\.00/)).toBeInTheDocument();
  });

  it("shows Account & Portfolio title and capital deployed in header", async () => {
    render(<PortfolioPage />);
    expect(screen.getByText(/Account & Portfolio/i)).toBeInTheDocument();
    expect(screen.getByText(/\$45,000\.00 deployed/i)).toBeInTheDocument();
  });

  it("totals exclude is_test: capital_deployed 0 when only test position", () => {
    usePortfolio.mockReturnValue({
      data: mockPortfolioWithTest,
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    expect(screen.getByText(/\$0\.00 deployed/i)).toBeInTheDocument();
  });

  it("shows Delete action for CLOSED position", () => {
    usePortfolio.mockReturnValue({
      data: mockPortfolioClosed,
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    const deleteBtn = screen.getByRole("button", { name: /delete/i });
    expect(deleteBtn).toBeInTheDocument();
  });

  it("shows View decision link with run_id when position has decision_ref.run_id", () => {
    usePortfolio.mockReturnValue({
      data: {
        positions: [
          {
            ...mockPortfolioOpen.positions[0],
            decision_ref: { run_id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890" },
          },
        ],
        capital_deployed: 45000,
        open_positions_count: 1,
      },
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    const link = screen.getByRole("link", { name: /decision \(run a1b2c3d4/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute(
      "href",
      "/symbol-diagnostics?symbol=SPY&run_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    );
  });

  it("shows View button and opens detail drawer with Details and Timeline tabs (Phase 13.0)", () => {
    render(<PortfolioPage />);
    const viewBtn = screen.getByRole("button", { name: /view/i });
    expect(viewBtn).toBeInTheDocument();
    fireEvent.click(viewBtn);
    expect(screen.getByRole("button", { name: /^details$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^timeline/i })).toBeInTheDocument();
  });

  it("shows Roll position button for open CSP position (Phase 13.0)", () => {
    render(<PortfolioPage />);
    fireEvent.click(screen.getByRole("button", { name: /view/i }));
    const rollBtn = screen.getByRole("button", { name: /roll position/i });
    expect(rollBtn).toBeInTheDocument();
  });

  it("shows Balances (manual) and Holdings sections (Phase 21.1)", () => {
    render(<PortfolioPage />);
    expect(screen.getByText(/Balances \(manual\)/)).toBeInTheDocument();
    expect(screen.getByText(/Holdings/)).toBeInTheDocument();
    expect(screen.getByText(/Add holding/)).toBeInTheDocument();
  });

  it("R44: distinguishes cash vs total capital vs buying power", () => {
    useDefaultAccount.mockReturnValue({
      data: { account: { account_id: "default", total_capital: 100000, max_capital_per_trade_pct: 5 } },
    });
    useAccounts.mockReturnValue({
      data: { accounts: [{ account_id: "default", total_capital: 100000 }] },
    });
    useAccountSummary.mockReturnValue({
      data: { account_id: "default", name: "Default", cash: 0, buying_power: 25000, holdings_count: 0, base_currency: "USD" },
    });
    render(<PortfolioPage />);
    expect(screen.getByTestId("portfolio-cash")).toHaveTextContent(/Cash \(available\)/i);
    expect(screen.getByTestId("portfolio-cash")).toHaveTextContent(/\$0\.00/);
    expect(screen.getByTestId("portfolio-total-capital")).toHaveTextContent(/Total capital/i);
    expect(screen.getByTestId("portfolio-total-capital")).toHaveTextContent(/\$100,000\.00/);
    expect(screen.getByTestId("portfolio-buying-power")).toHaveTextContent(/Buying power/i);
    expect(screen.getByTestId("portfolio-buying-power")).toHaveTextContent(/\$25,000\.00/);
    expect(screen.getByTestId("portfolio-balance-labels").textContent || "").toMatch(/≠ cash|Not total capital/i);
  });

  it("R37: shows manual portfolio snapshot provenance (not broker-synced)", () => {
    render(<PortfolioPage />);
    expect(screen.getByTestId("portfolio-provenance")).toHaveTextContent(/Manual portfolio snapshot/i);
    expect(screen.getByTestId("portfolio-provenance")).toHaveTextContent(/not broker-synced/i);
    expect(screen.getByText(/user-entered, not broker-synced/i)).toBeInTheDocument();
  });

  it("shows Decision (latest) with no run badge when position has no run_id", () => {
    usePortfolio.mockReturnValue({
      data: mockPortfolioOpen,
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    const link = screen.getByRole("link", { name: /decision \(latest\)/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/symbol-diagnostics?symbol=SPY");
    expect(screen.getByText("no run")).toBeInTheDocument();
  });

  it("R27.4: renders Shares Positions with Mark and Unrealized P/L columns; em dash when missing", () => {
    usePortfolio.mockReturnValue({
      data: {
        ...mockPortfolioOpen,
        shares_positions: [
          { symbol: "SPY", quantity: 100, avg_cost: 100, mark_value: 105, mark_source: "LAST", mark_age_sec: 30, unrealized_pl: 500, market_value: 10500 },
          { symbol: "QQQ", quantity: 50, avg_cost: null, market_value: null, unrealized_pl: null },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    expect(screen.getByText("Shares Positions")).toBeInTheDocument();
    expect(screen.getAllByText("Mark").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Unrealized P/L")).toBeInTheDocument();
    expect(screen.getByText(/LAST/)).toBeInTheDocument();
    expect(screen.getByText(/\$500\.00/)).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });

  it("R27.4: document textContent has no FAIL or WARN", () => {
    render(<PortfolioPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R27.7: shows CC eligible badge and Open CC ticket link when cc_eligible is true", () => {
    usePortfolio.mockReturnValue({
      data: {
        ...mockPortfolioOpen,
        shares_positions: [
          {
            symbol: "SPY",
            quantity: 100,
            avg_cost: 100,
            mark_value: 105,
            mark_source: "LAST",
            mark_age_sec: 30,
            unrealized_pl: 500,
            pct_return: 5,
            cc_eligible: true,
            cc_eligible_reason: "Standard lot (100+ shares)",
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    expect(screen.getByText("Eligible")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open cc ticket/i })).toBeInTheDocument();
    expect(screen.getByText("CC eligible")).toBeInTheDocument();
  });

  it("R27.7: document has no raw FAIL or WARN in portfolio shares section", () => {
    usePortfolio.mockReturnValue({
      data: {
        ...mockPortfolioOpen,
        shares_positions: [
          { symbol: "SPY", quantity: 50, cc_eligible: false, cc_eligible_reason: "Fewer than 100 shares" },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R27.8: shows Options Positions table with mark, DTE, recommend, reason and Open Ticket / Open Symbol links", () => {
    usePortfolio.mockReturnValue({
      data: {
        ...mockPortfolioOpen,
        options_positions: [
          {
            position_id: "pos-opt-1",
            symbol: "SPY",
            strategy: "CSP",
            strike: 400,
            expiration: "2026-04-18",
            contracts: 1,
            mark_value: 1.2,
            mark_source: "LAST",
            mark_age_sec: 30,
            unrealized_pnl: 130,
            dte: 45,
            pct_max_profit: 52,
            lifecycle_recommend: "Hold",
            lifecycle_reason: "Hold",
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    expect(screen.getByText("Options Positions")).toBeInTheDocument();
    expect(screen.getByText("Max profit %")).toBeInTheDocument();
    expect(screen.getByText("Recommend")).toBeInTheDocument();
    expect(screen.getByText("Reason")).toBeInTheDocument();
    expect(screen.getAllByText("Hold").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("link", { name: /open ticket/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("link", { name: /open symbol/i }).length).toBeGreaterThanOrEqual(1);
  });

  it("R27.8: document has no FAIL or WARN when options_positions present", () => {
    usePortfolio.mockReturnValue({
      data: {
        ...mockPortfolioOpen,
        options_positions: [
          {
            position_id: "pos-1",
            symbol: "SPY",
            strategy: "CSP",
            lifecycle_recommend: "Hold",
            lifecycle_reason: "Hold",
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    render(<PortfolioPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });
});
