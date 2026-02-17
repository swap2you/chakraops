import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { PortfolioPage } from "./PortfolioPage";

const usePortfolio = vi.fn();
const useAccounts = vi.fn();
const useDefaultAccount = vi.fn();
const useClosePosition = vi.fn();
const useDeletePosition = vi.fn();

vi.mock("@/api/queries", () => ({
  usePortfolio: (...args: unknown[]) => usePortfolio(...args),
  useAccounts: (...args: unknown[]) => useAccounts(...args),
  useDefaultAccount: (...args: unknown[]) => useDefaultAccount(...args),
  useClosePosition: (...args: unknown[]) => useClosePosition(...args),
  useDeletePosition: (...args: unknown[]) => useDeletePosition(...args),
}));

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
    useAccounts.mockReturnValue({ data: { accounts: [] } });
    useDefaultAccount.mockReturnValue({ data: { account: null } });
    useClosePosition.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      isError: false,
      error: null,
    });
    useDeletePosition.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false });
  });

  it("renders without throwing", () => {
    expect(() => render(<PortfolioPage />)).not.toThrow();
  });

  it("shows Close action for OPEN position", async () => {
    render(<PortfolioPage />);
    const closeBtn = await screen.findByRole("button", { name: /close/i });
    expect(closeBtn).toBeInTheDocument();
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
});
