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
const mockPaperMutate = vi.fn();

const mockReadiness = {
  status: "OK" as const,
  status_label: "All checks OK",
  as_of_utc: "2026-02-27T12:00:00Z",
  checks: [
    { code: "INTEGRITY", status: "OK" as const, label: "OK", detail: "", action_label: "Open integrity", action_href: "/positions?source=db&symbol=SPY" },
    { code: "MARK_FRESHNESS", status: "OK" as const, label: "OK", detail: "", action_label: "Open system diagnostics", action_href: "/system" },
    { code: "CASH_SECURED_RESERVE", status: "OK" as const, label: "OK", detail: "", action_label: "Open portfolio", action_href: "/portfolio" },
    { code: "SIZING_CONSTRAINTS", status: "OK" as const, label: "No constraints hit", detail: "", action_label: "Open guardrails", action_href: "/system" },
    { code: "EARNINGS_ADVISORY", status: "OK" as const, label: "OK", detail: "", action_label: "Open symbol", action_href: "/symbol-diagnostics?symbol=SPY" },
    { code: "ACCOUNT_PRESENT", status: "OK" as const, label: "Default account set", detail: "", action_label: "Open settings", action_href: "/system" },
  ],
  order_stub: { title: "Order stub: SPY CSP OPEN", lines: ["Symbol: SPY", "Strategy: CSP", "Action: OPEN", "Qty: 2"] },
};
const mockUseTradeTicketReadiness = vi.fn(() => ({ data: mockReadiness, isLoading: false, isError: false }));

vi.mock("@/api/queries", () => ({
  useTradeTicket: (...args: unknown[]) => mockUseTradeTicket(...args),
  useTradeTicketReadiness: (...args: unknown[]) => mockUseTradeTicketReadiness(...args),
  useJournalFromTicket: () => mockUseJournalFromTicket(),
  usePaperExecute: () => ({ mutate: mockPaperMutate, isPending: false }),
}));

const ticketUrl = "/ticket?symbol=SPY&strategy=CSP&action=OPEN";

describe("TradeTicketPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseTradeTicket.mockReturnValue({ data: mockTicket, isLoading: false, isError: false });
    mockUseTradeTicketReadiness.mockReturnValue({ data: mockReadiness, isLoading: false, isError: false });
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
    expect(mockMutate).toHaveBeenCalledWith(mockTicket.journal_draft, expect.any(Object));
  });

  it("no FAIL or WARN in DOM", () => {
    render(<TradeTicketPage />);
    expect(document.body.textContent).not.toMatch(/FAIL_|WARN_/);
  });

  it("shows no symbol message when symbol is missing", () => {
    renderWithRoute(<TradeTicketPage />, "/ticket");
    expect(screen.getByText(/No symbol/)).toBeInTheDocument();
  });

  it("shows paper section with toggle (R27.0)", () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    expect(screen.getByTestId("ticket-paper-section")).toBeInTheDocument();
    expect(screen.getByTestId("ticket-paper-toggle")).toBeInTheDocument();
  });

  it("Simulate Fill calls paper execute mutation when paper mode on and price set (R27.0)", async () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    await userEvent.click(screen.getByText("Paper execute"));
    await userEvent.click(screen.getByTestId("ticket-paper-toggle"));
    await userEvent.type(screen.getByTestId("ticket-paper-price"), "2.50");
    await userEvent.click(screen.getByTestId("ticket-paper-simulate"));
    expect(mockPaperMutate).toHaveBeenCalled();
    const payload = mockPaperMutate.mock.calls[0][0];
    expect(payload).toMatchObject({ mode: "PAPER", action: expect.any(String), symbol: "SPY", strategy: "CSP", qty: 2 });
  });

  it("R30.0: Execution readiness card renders; Copy order stub copies order_stub.lines", async () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    expect(screen.getByTestId("trade-ticket-readiness-card")).toBeInTheDocument();
    expect(screen.getByText("Execution readiness")).toBeInTheDocument();
    const copyStubBtn = screen.getByTestId("ticket-copy-order-stub");
    expect(copyStubBtn).toHaveTextContent(/Copy order stub/);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await userEvent.click(copyStubBtn);
    expect(writeText).toHaveBeenCalledWith("Symbol: SPY\nStrategy: CSP\nAction: OPEN\nQty: 2");
  });

  it("R30.0: document has no forbidden tokens (FAIL/WARN/PASS or FAIL_/WARN_)", () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_|WARN_/);
  });

  it("R30.1: renders Fix links for checks with action_href and href matches expected paths", () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    const fixIntegrity = screen.getByTestId("readiness-fix-integrity");
    expect(fixIntegrity).toBeInTheDocument();
    expect(fixIntegrity).toHaveAttribute("href", "/positions?source=db&symbol=SPY");
    const fixMarkFreshness = screen.getByTestId("readiness-fix-mark_freshness");
    expect(fixMarkFreshness).toHaveAttribute("href", "/system");
    const fixEarnings = screen.getByTestId("readiness-fix-earnings_advisory");
    expect(fixEarnings).toHaveAttribute("href", "/symbol-diagnostics?symbol=SPY");
  });

  it("R30.1: shows Ready to execute: Review and guidance when readiness.status is Review", () => {
    mockUseTradeTicketReadiness.mockReturnValue({
      data: { ...mockReadiness, status: "Review" as const, status_label: "Review required" },
      isLoading: false,
      isError: false,
    });
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    expect(screen.getByTestId("readiness-ready-banner")).toHaveTextContent("Ready to execute: Review");
    expect(screen.getByTestId("readiness-review-guidance")).toHaveTextContent("Resolve the items below before executing.");
  });

  it("R30.1: no forbidden tokens in document.textContent and no FAIL_/WARN_ substrings", () => {
    renderWithRoute(<TradeTicketPage />, ticketUrl);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_|WARN_/);
  });
});
