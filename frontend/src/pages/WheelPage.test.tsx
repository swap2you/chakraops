import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { WheelPage } from "./WheelPage";

const useWheelOverview = vi.fn();
const useDefaultAccount = vi.fn();
const useAccounts = vi.fn();

vi.mock("@/api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/queries")>();
  return {
    ...actual,
    useWheelOverview: (...args: unknown[]) => useWheelOverview(...args),
    useDefaultAccount: (...args: unknown[]) => useDefaultAccount(...args),
    useAccounts: (...args: unknown[]) => useAccounts(...args),
  };
});

const mockWheelOverview = {
  symbols: {
    SPY: {
      symbol: "SPY",
      wheel_state: "EMPTY",
      next_action: {
        action_type: "OPEN_TICKET",
        suggested_contract_key: "100-2026-12-20-PUT",
        reasons: ["Symbol eligible in decision"],
        blocked_by: [],
      },
      suggested_candidate: {
        strategy: "CSP",
        strike: 100,
        expiry: "2026-12-20",
        contract_key: "100-2026-12-20-PUT",
        credit_estimate: 1.5,
        max_loss: 10000,
      },
      risk_status: "PASS",
      last_decision_score: 75,
      last_decision_band: "B",
      links: { run_id: "run-abc" },
      open_position: null,
    },
  },
  risk_status: "PASS",
  run_id: "run-abc",
};

describe("WheelPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWheelOverview.mockReturnValue({
      data: mockWheelOverview,
      isLoading: false,
      isError: false,
    });
    useDefaultAccount.mockReturnValue({ data: { account: { account_id: "paper" } } });
    useAccounts.mockReturnValue({ data: { accounts: [{ account_id: "paper" }] } });
  });

  it("renders wheel table with symbol rows", () => {
    render(<WheelPage />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("EMPTY")).toBeInTheDocument();
    expect(screen.getByText("OPEN_TICKET")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("75")).toBeInTheDocument();
  });

  it("shows blocked_by list when next_action has blocked_by", () => {
    useWheelOverview.mockReturnValue({
      data: {
        symbols: {
          SPY: {
            symbol: "SPY",
            wheel_state: "EMPTY",
            next_action: {
              action_type: "BLOCKED",
              suggested_contract_key: null,
              reasons: ["Wheel policy"],
              blocked_by: ["wheel_one_position_per_symbol", "wheel_min_dte(14<21)"],
            },
            risk_status: "PASS",
            last_decision_score: 70,
            links: {},
            open_position: null,
          },
        },
        risk_status: "PASS",
      },
      isLoading: false,
      isError: false,
    });
    render(<WheelPage />);
    expect(screen.getByText("wheel_one_position_per_symbol")).toBeInTheDocument();
    expect(screen.getByText("wheel_min_dte(14<21)")).toBeInTheDocument();
  });

  it("Open ticket uses provided contract_key and opens TradeTicketDrawer", () => {
    render(<WheelPage />);
    const openBtn = screen.getByRole("button", { name: /open ticket/i });
    fireEvent.click(openBtn);
    const dialog = screen.getByRole("dialog", { name: /trade ticket/i });
    expect(dialog).toBeInTheDocument();
    expect(screen.getAllByText(/2026-12-20/).length).toBeGreaterThan(0);
  });
});
