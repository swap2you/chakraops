import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@/test/test-utils";
import { UniversePage } from "./UniversePage";

const mockUniverse = {
  symbols: [
    {
      symbol: "SPY",
      verdict: "ELIGIBLE",
      final_verdict: "ELIGIBLE",
      strategy: "CSP",
      strike: 450,
      expiration: "2026-03-20",
      selected_contract_key: "450-2026-03-20-PUT",
      option_symbol: "SPY  260320P00450000",
      capital_required: 45000,
      band: "B",
      score: 65,
    },
  ],
  updated_at: "2026-02-17T20:00:00Z",
  evaluation_timestamp_utc: "2026-02-17T20:00:00Z",
  run_id: "run-123",
  source: "ARTIFACT_V2",
};

const mockSaveMutate = vi.fn();
const mockAddSymbol = vi.fn();
const mockRemoveSymbol = vi.fn();
vi.mock("@/api/queries", () => ({
  useUniverse: () => ({ data: mockUniverse }),
  useUniverseSymbols: () => ({
    data: {
      symbols: ["SPY"],
      base_count: 1,
      overlay_added_count: 0,
      overlay_removed_count: 0,
    },
  }),
  useUniverseAddSymbol: () => ({ mutate: mockAddSymbol, isPending: false }),
  useUniverseRemoveSymbol: () => ({ mutate: mockRemoveSymbol, isPending: false }),
  useRunEval: () => ({ mutate: vi.fn(), isPending: false }),
  useUiSystemHealth: () => ({ data: { market: { phase: "OPEN" } } }),
  useSavePaperPosition: () => ({ mutate: mockSaveMutate, isPending: false }),
  useDefaultAccount: () => ({ data: { account: { account_id: "acct_1" } } }),
  useUiTrackedPositions: () => ({ data: { capital_deployed: 0, open_positions_count: 0 } }),
  useManualExecute: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("UniversePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Add symbol form (Phase 21.3)", async () => {
    render(<UniversePage />);
    expect(screen.getByPlaceholderText(/Add symbol/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Add$/i })).toBeInTheDocument();
  });

  it("Add symbol triggers useUniverseAddSymbol with uppercase symbol (Phase 21.3)", async () => {
    render(<UniversePage />);
    const input = screen.getByPlaceholderText(/Add symbol/i);
    fireEvent.change(input, { target: { value: "nvda" } });
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));
    expect(mockAddSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: "NVDA" }), expect.any(Object));
  });

  it("Remove triggers useUniverseRemoveSymbol (Phase 21.3)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<UniversePage />);
    const removeBtns = screen.getAllByRole("button", { name: /Remove/i });
    const rowRemove = removeBtns.find((b) => b.getAttribute("title") === "Remove from universe") ?? removeBtns[0];
    fireEvent.click(rowRemove);
    expect(mockRemoveSymbol).toHaveBeenCalledWith("SPY");
    confirmSpy.mockRestore();
  });

  it("invalid add symbol shows validation message (Phase 21.3)", async () => {
    render(<UniversePage />);
    const input = screen.getByPlaceholderText(/Add symbol/i);
    fireEvent.change(input, { target: { value: "!!" } });
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));
    expect(screen.getByText(/Only letters, numbers/i)).toBeInTheDocument();
  });

  it("Open Ticket passes contract_key and decision_ref to save payload", async () => {
    render(<UniversePage />);
    const table = await screen.findByRole("table");
    const buttons = within(table).getAllByRole("button", { name: /Open Ticket/i });
    const openTicketBtn = buttons.find((b) => b.tagName === "BUTTON") ?? buttons[0];
    fireEvent.click(openTicketBtn);

    const saveBtn = screen.getByRole("button", { name: /Save Position/i });
    fireEvent.click(saveBtn);

    expect(mockSaveMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: "SPY",
        strategy: "CSP",
        contracts: 1,
        strike: 450,
        expiration: "2026-03-20",
        contract_key: "450-2026-03-20-PUT",
        decision_ref: expect.objectContaining({
          run_id: "run-123",
          evaluation_timestamp_utc: "2026-02-17T20:00:00Z",
          selected_contract_key: "450-2026-03-20-PUT",
        }),
      }),
      expect.any(Object)
    );
  });
});
