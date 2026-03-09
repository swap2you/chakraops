/**
 * R27.9/R28.0/R28.9: Positions page — unified list; source=recompute (default) or source=db; no FAIL/WARN/PASS in document.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, renderWithRoute, screen } from "@/test/test-utils";
import { PositionsPage } from "./PositionsPage";

const mockPositions = [
  {
    id: "live_shares_1",
    symbol: "AAPL",
    instrument_type: "SHARES",
    is_paper: 0,
    qty: 100,
    avg_price: 150.5,
    strike: null,
    expiry: null,
    right: null,
    opened_ts: "2026-02-20T12:00:00",
    link_id: "1",
    notes: null,
    tags: null,
  },
  {
    id: "paper_2",
    symbol: "SPY",
    instrument_type: "CSP",
    is_paper: 1,
    qty: 2,
    avg_price: 3.5,
    strike: 450,
    expiry: "2026-03-21",
    right: "PUT",
    opened_ts: "2026-02-15T10:00:00",
    link_id: "2",
    notes: null,
    tags: null,
    mark_value: 4.25,
    unrealized_pl: 150,
  },
];

const mockUseUnifiedPositions = vi.fn(() => ({
  data: { positions: mockPositions, state: "open", include_paper: true },
  isLoading: false,
  isError: false,
}));

const mockUseUnifiedPositionsFromDb = vi.fn(() => ({
  data: { items: mockPositions, count: mockPositions.length, status: "OK", status_label: "OK" },
  isLoading: false,
  isError: false,
}));

vi.mock("@/api/queries", () => ({
  useUnifiedPositions: (params: Record<string, unknown>) => mockUseUnifiedPositions(params),
  useUnifiedPositionsFromDb: (params: Record<string, unknown>) => mockUseUnifiedPositionsFromDb(params),
}));

describe("PositionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUnifiedPositions.mockReturnValue({
      data: { positions: mockPositions, state: "open", include_paper: true },
      isLoading: false,
      isError: false,
    });
  });

  it("renders Positions header and filters", () => {
    render(<PositionsPage />);
    expect(screen.getByRole("heading", { name: /^Positions$/i })).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-state")).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-paper")).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-type")).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-symbol")).toBeInTheDocument();
  });

  it("renders positions table with Symbol, Source, Type, Qty, Opened, Mark, Ticket, Journal, Paper", () => {
    render(<PositionsPage />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Mark / Unrealized")).toBeInTheDocument();
    expect(screen.getAllByText("LIVE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("PAPER").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByTestId("positions-row").length).toBe(2);
    expect(screen.getAllByTestId("positions-link-ticket").length).toBe(2);
    expect(screen.getAllByTestId("positions-link-journal").length).toBe(2);
    expect(screen.getAllByTestId("positions-link-paper").length).toBeGreaterThanOrEqual(1);
  });

  it("shows Mark/Unrealized for paper row when API provides mark_value and unrealized_pl", () => {
    const { container } = render(<PositionsPage />);
    expect(container.textContent).toMatch(/4\.25/);
    expect(container.textContent).toMatch(/150/);
  });

  it("calls useUnifiedPositions with state and include_paper", () => {
    render(<PositionsPage />);
    expect(mockUseUnifiedPositions).toHaveBeenCalledWith(
      expect.objectContaining({ state: "open", include_paper: true })
    );
  });

  it("document textContent has no FAIL or WARN (R27.9/R28.0)", () => {
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R28.9: when source=db shows Source: Stored and uses db endpoint", () => {
    renderWithRoute(<PositionsPage />, "/positions?source=db");
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Stored");
    expect(mockUseUnifiedPositionsFromDb).toHaveBeenCalled();
  });

  it("R28.9: when source absent shows Source: Computed", () => {
    render(<PositionsPage />);
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Computed");
  });

  it("R28.9: document has no FAIL/WARN/PASS tokens", () => {
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
  });

  it("filter state change triggers new request", async () => {
    render(<PositionsPage />);
    const stateSelect = screen.getByTestId("positions-filter-state");
    await userEvent.selectOptions(stateSelect, "closed");
    expect(mockUseUnifiedPositions).toHaveBeenLastCalledWith(
      expect.objectContaining({ state: "closed" })
    );
  });
});
