import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, renderWithRoute } from "@/test/test-utils";
import { TradeTicketPage } from "./TradeTicketPage";

const mockTicket = {
  symbol: "SPY",
  strategy: "CSP",
  action: "OPEN",
  snapshot_header: { symbol: "SPY", strategy: "CSP", action: "OPEN", cadence_mode: "LIVE", as_of_et: "2026-02-27 12:00", recommended_action: "Entry" },
  sizing: { recommended_contracts: 2, recommended_notional_usd: 24000, sizing_constraints_hit: [], cash_secured_available_usd: 50000, csp_risk_proxy_move_pct: 7 },
  contract_details: { expiry: "2026-03-21", strike: 600, right: "PUT", dte: 23 },
  execution_steps: ["1. Open options order ticket.", "2. Order type: Limit."],
  journal_draft: { trade_date: "2026-02-27", symbol: "SPY", strategy: "CSP", action: "BUY", qty: 2, contract_key: "SPY250321P00600000" },
  guardrails: {},
  earnings_advisory: {},
};

const mockUseTradeTicket = vi.fn(() => ({ data: mockTicket, isLoading: false, isError: false }));
const mockMutate = vi.fn();
const mockUseJournalFromTicket = vi.fn(() => ({ mutate: mockMutate, isPending: false }));

vi.mock("@/api/queries", () => ({
  useTradeTicket: (...args: unknown[]) => mockUseTradeTicket(...args),
  useJournalFromTicket: () => mockUseJournalFromTicket(),
}));

const ticketUrl = "/ticket?symbol=SPY&strategy=CSP&action=OPEN";

describe("TradeTicketPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseTradeTicket.mockReturnValue({ data: mockTicket, isLoading: false, isError: false });
  });

  it("renders ticket with snapshot, sizing, steps, journal sections", async () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    expect(screen.getByTestId("trade-ticket-page")).toBeInTheDocument();
    expect(screen.getByText(/Snapshot/)).toBeInTheDocument();
    expect(screen.getByText(/Sizing/)).toBeInTheDocument();
    expect(screen.getByText(/Execution steps/)).toBeInTheDocument();
    expect(screen.getByText(/Journal draft/)).toBeInTheDocument();
  });

  it("shows copy steps and save to journal buttons", () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    expect(screen.getByTestId("ticket-copy-steps")).toBeInTheDocument();
    expect(screen.getByTestId("ticket-save-journal")).toBeInTheDocument();
    expect(screen.getByTestId("ticket-copy-json")).toBeInTheDocument();
    expect(screen.getByTestId("ticket-copy-csv")).toBeInTheDocument();
  });

  it("Save to Journal calls mutation with journal_draft", async () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    const saveBtn = screen.getByTestId("ticket-save-journal");
    await userEvent.click(saveBtn);
    expect(mockMutate).toHaveBeenCalledWith(mockTicket.journal_draft);
  });

  it("no FAIL or WARN in DOM", () => {
    render(<TradeTicketPage />);
    expect(document.body.textContent).not.toMatch(/FAIL_|WARN_/);
  });

  it("shows no symbol message when symbol is missing", () => {
    renderWithRoute(<TradeTicketPage />, "/ticket");
    expect(screen.getByText(/No symbol/)).toBeInTheDocument();
  });
});
