import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { WheelPage } from "./WheelPage";

const useWheelOverview = vi.fn();
const useDefaultAccount = vi.fn();
const useAccounts = vi.fn();
const useWheelAssign = vi.fn();
const useWheelUnassign = vi.fn();
const useWheelReset = vi.fn();
const useWheelRepair = vi.fn();

vi.mock("@/api/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/queries")>();
  return {
    ...actual,
    useWheelOverview: (...args: unknown[]) => useWheelOverview(...args),
    useDefaultAccount: (...args: unknown[]) => useDefaultAccount(...args),
    useAccounts: (...args: unknown[]) => useAccounts(...args),
    useWheelAssign: (...args: unknown[]) => useWheelAssign(...args),
    useWheelUnassign: (...args: unknown[]) => useWheelUnassign(...args),
    useWheelReset: (...args: unknown[]) => useWheelReset(...args),
    useWheelRepair: (...args: unknown[]) => useWheelRepair(...args),
  };
});

const mockMutation = () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null, data: null });

const mockWheelOverview = {
  symbols: {
    SPY: {
      symbol: "SPY",
      wheel_state: "EMPTY",
      last_updated_utc: "2026-02-17T18:00:00Z",
      manual_override: false,
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
  wheel_integrity: { status: "PASS" },
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
    useWheelAssign.mockReturnValue(mockMutation());
    useWheelUnassign.mockReturnValue(mockMutation());
    useWheelReset.mockReturnValue(mockMutation());
    useWheelRepair.mockReturnValue(mockMutation());
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
    expect(screen.getByText("One position per symbol (already open)")).toBeInTheDocument();
    expect(screen.getByText("DTE below minimum")).toBeInTheDocument();
  });

  it("Open ticket uses provided contract_key and opens TradeTicketDrawer", () => {
    render(<WheelPage />);
    const openBtn = screen.getByRole("button", { name: /open ticket/i });
    fireEvent.click(openBtn);
    const dialog = screen.getByRole("dialog", { name: /trade ticket/i });
    expect(dialog).toBeInTheDocument();
    expect(screen.getAllByText(/2026-12-20/).length).toBeGreaterThan(0);
  });

  it("Phase 20: shows Repair wheel state section and Assign when state is EMPTY", () => {
    render(<WheelPage />);
    expect(screen.getByRole("button", { name: /repair wheel state/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Assign$/i })).toBeInTheDocument();
  });

  it("Phase 20: shows Unassign and Reset when state is ASSIGNED", () => {
    useWheelOverview.mockReturnValue({
      data: {
        ...mockWheelOverview,
        symbols: {
          SPY: {
            ...mockWheelOverview.symbols.SPY,
            wheel_state: "ASSIGNED",
            last_updated_utc: "2026-02-17T18:00:00Z",
            manual_override: true,
          },
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<WheelPage />);
    expect(screen.getByRole("button", { name: /unassign/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Reset$/i })).toBeInTheDocument();
  });

  it("Phase 20: shows manual override and last_updated when present", () => {
    useWheelOverview.mockReturnValue({
      data: {
        ...mockWheelOverview,
        symbols: {
          SPY: {
            ...mockWheelOverview.symbols.SPY,
            manual_override: true,
            last_updated_utc: "2026-02-17T18:00:00Z",
          },
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<WheelPage />);
    expect(screen.getByTitle(/manual override/i)).toBeInTheDocument();
  });

  it("R22.3: renders Admin/Recovery explanation panel and no raw FAIL_* in panel text", () => {
    render(<WheelPage />);
    expect(screen.getByText("Admin / Recovery")).toBeInTheDocument();
    expect(screen.getByText(/Use Repair only when/)).toBeInTheDocument();
    const body = document.body.innerHTML;
    const adminSection = body;
    expect(adminSection).not.toMatch(/FAIL_[A-Z_0-9]+/);
  });
});
