import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { TradeTicketDrawer } from "./TradeTicketDrawer";

const mockCandidate = {
  strategy: "CSP",
  strike: 450,
  expiry: "2026-03-21",
  delta: 0.25,
  credit_estimate: 2.5,
  max_loss: 1000,
  contract_key: "450-2026-03-21-PUT",
};

const mockAccount = {
  account_id: "acct_1",
  total_capital: 100000,
  max_collateral_per_trade: 50000,
  max_total_collateral: 100000,
  max_positions_open: 10,
};

const mockSaveMutate = vi.fn();
vi.mock("@/api/queries", () => ({
  useDefaultAccount: () => ({ data: { account: mockAccount } }),
  useUiTrackedPositions: () => ({
    data: { capital_deployed: 20000, open_positions_count: 2 },
  }),
  useManualExecute: () => ({ mutate: vi.fn(), isPending: false }),
  useSavePaperPosition: () => ({ mutate: mockSaveMutate, isPending: false }),
}));

describe("TradeTicketDrawer", () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders contract details (strike, expiry, type, contracts)", () => {
    render(
      <TradeTicketDrawer
        symbol="SPY"
        candidate={mockCandidate}
        onClose={onClose}
      />
    );
    expect(screen.getByText(/SPY · CSP 450 2026-03-21 · 1 contract/)).toBeInTheDocument();
  });

  it("shows sizing section when account has limits", () => {
    render(
      <TradeTicketDrawer
        symbol="SPY"
        candidate={mockCandidate}
        onClose={onClose}
      />
    );
    expect(screen.getByText(/Sizing/i)).toBeInTheDocument();
    expect(screen.getByText(/Max per trade/)).toBeInTheDocument();
    expect(screen.getByText(/Remaining capacity/)).toBeInTheDocument();
    expect(screen.getByText(/Open positions/)).toBeInTheDocument();
  });

  it("Save disabled when options strategy missing contract identity (Phase 12.0)", () => {
    const candidateNoContract = { ...mockCandidate, contract_key: undefined, option_symbol: undefined };
    render(
      <TradeTicketDrawer symbol="SPY" candidate={candidateNoContract} onClose={onClose} />
    );
    const saveBtn = screen.getByRole("button", { name: /Save Position/i });
    expect(saveBtn).toBeDisabled();
    expect(screen.getByText(/contract_key or option_symbol.*required/)).toBeInTheDocument();
  });

  it("save payload includes decision_ref and contract_key (Phase 11)", () => {
    const decisionRef = {
      evaluation_timestamp_utc: "2026-02-17T20:00:00Z",
      artifact_source: "LIVE",
    };

    render(
      <TradeTicketDrawer
        symbol="SPY"
        candidate={mockCandidate}
        onClose={onClose}
        decisionRef={decisionRef}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Save Position/i }));

    expect(mockSaveMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: "SPY",
        strategy: "CSP",
        contracts: 1,
        strike: 450,
        expiration: "2026-03-21",
        decision_ref: decisionRef,
        contract_key: expect.any(String),
      }),
      expect.any(Object)
    );
  });
});
