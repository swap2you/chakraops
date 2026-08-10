/**
 * R27.0: Paper page — summary and positions with mocked hooks; tab switch; no FAIL/WARN.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@/test/test-utils";
import { PaperPage } from "./PaperPage";

const mockOpenPositions = [
  {
    id: "p1",
    symbol: "SPY",
    strategy: "SHARES",
    qty: 100,
    open_price: 450,
    open_ts: "2026-02-20T12:00:00Z",
    realized_pl: null,
    close_ts: null,
    mark_value: 455,
    mark_source: "LAST",
    mark_age_sec: 10,
    quote_ts: "2026-02-27T12:00:00Z",
    unrealized_pl_usd: 500,
  },
];
const mockClosedPositions = [
  {
    id: "p2",
    symbol: "QQQ",
    strategy: "CSP",
    qty: 2,
    open_price: 3.5,
    open_ts: "2026-02-01T10:00:00Z",
    realized_pl: 120.5,
    close_ts: "2026-02-15T14:00:00Z",
  },
];
const mockSummary = {
  month: "2026-02",
  realized_pl: 120.5,
  trade_count: 3,
  win_rate: 66,
  fees_total: 5,
};

const mockUsePaperPositions = vi.fn((params: { status?: string }) => {
  const positions = params?.status === "CLOSED" ? mockClosedPositions : mockOpenPositions;
  return { data: { positions }, isLoading: false, isError: false, refetch: vi.fn() };
});
const mockUsePaperSummary = vi.fn(() => ({ data: mockSummary, isLoading: false }));
const mockUsePaperClose = vi.fn(() => ({
  mutateAsync: vi.fn().mockResolvedValue(undefined),
  isPending: false,
}));

vi.mock("@/api/queries", () => ({
  usePaperPositions: (params: { status?: string }) => mockUsePaperPositions(params),
  usePaperSummary: (month: string) => mockUsePaperSummary(month),
  usePaperClose: () => mockUsePaperClose(),
}));

describe("PaperPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUsePaperPositions.mockImplementation((params: { status?: string }) => {
      const positions = params?.status === "CLOSED" ? mockClosedPositions : mockOpenPositions;
      return { data: { positions }, isLoading: false, isError: false, refetch: vi.fn() };
    });
    mockUsePaperSummary.mockReturnValue({ data: mockSummary, isLoading: false });
  });

  it("renders Paper Portfolio header and summary card", () => {
    render(<PaperPage />);
    expect(screen.getByRole("heading", { name: /Paper Portfolio/i })).toBeInTheDocument();
    expect(screen.getByTestId("paper-summary-card")).toBeInTheDocument();
    expect(screen.getByText(/Realized P\/L:/)).toBeInTheDocument();
  });

  it("R45: labels SIMULATION and isolation from live portfolio", () => {
    render(<PaperPage />);
    expect(screen.getByTestId("paper-simulation-banner")).toHaveTextContent(/SIMULATION/i);
    expect(screen.getByTestId("paper-simulation-banner")).toHaveTextContent(/not live account/i);
    expect(screen.getByText(/isolated from the live portfolio/i)).toBeInTheDocument();
  });

  it("renders Open and Closed tabs and positions card", () => {
    render(<PaperPage />);
    expect(screen.getByTestId("paper-tab-open")).toBeInTheDocument();
    expect(screen.getByTestId("paper-tab-closed")).toBeInTheDocument();
    expect(screen.getByTestId("paper-positions-card")).toBeInTheDocument();
  });

  it("shows open positions by default and closed after tab switch", async () => {
    render(<PaperPage />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getAllByTestId("paper-position-row").length).toBe(1);
    await userEvent.click(screen.getByTestId("paper-tab-closed"));
    expect(screen.getByText("QQQ")).toBeInTheDocument();
    expect(screen.getAllByTestId("paper-position-row").length).toBe(1);
  });

  it("document text does not contain FAIL or WARN (R27.0)", () => {
    const { container } = render(<PaperPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("Open tab shows Mark and Unrealized P/L columns (R27.1)", () => {
    render(<PaperPage />);
    expect(screen.getByTestId("paper-th-mark")).toBeInTheDocument();
    expect(screen.getByTestId("paper-th-unrealized")).toBeInTheDocument();
    expect(screen.getByTestId("paper-cell-mark")).toBeInTheDocument();
    expect(screen.getByTestId("paper-cell-unrealized")).toBeInTheDocument();
    expect(screen.getByTestId("paper-cell-unrealized")).toHaveTextContent("500.00");
  });

  it("Close button opens modal; modal has submit (R27.2)", async () => {
    render(<PaperPage />);
    await userEvent.click(screen.getByTestId("paper-close-btn"));
    expect(screen.getByTestId("paper-close-modal")).toBeInTheDocument();
    expect(screen.getByTestId("paper-close-submit")).toBeInTheDocument();
    expect(screen.getByTestId("paper-close-price-input")).toBeInTheDocument();
  });
});
