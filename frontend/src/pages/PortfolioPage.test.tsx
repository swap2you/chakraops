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

  it("shows capital deployed in header", async () => {
    render(<PortfolioPage />);
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
});
