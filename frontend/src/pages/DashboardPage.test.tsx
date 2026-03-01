import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { DashboardPage } from "./DashboardPage";

const mockDecision = {
  artifact: {
    artifact_version: "v2",
    metadata: { pipeline_timestamp: "2026-01-01T12:00:00Z" },
    symbols: [],
    selected_candidates: [],
  },
  artifact_version: "v2",
  evaluation_timestamp_utc: "2026-01-01T12:00:00Z",
  decision_store_mtime_utc: "2026-01-01T12:00:00Z",
};
const mockUniverse = { symbols: [], updated_at: "2026-01-01T12:00:00Z", evaluation_timestamp_utc: "2026-01-01T12:00:00Z", source: "ARTIFACT_V2" };
const mockHealth = { api: { status: "OK" }, market: { phase: "OPEN" }, orats: { status: "OK" } };
const mockFiles = { files: [{ name: "decision_latest.json" }] };
const mockPositions = { positions: [] };

const mockUseUiSystemHealth = vi.fn(() => ({ data: mockHealth }));
const mockUsePortfolioMtm = vi.fn(() => ({ data: null }));
const mockUseActionNeeded = vi.fn(() => ({ data: { top_options: [], top_shares: [], recently_changed: [] } }));
vi.mock("@/api/queries", () => ({
  useArtifactList: () => ({ data: mockFiles }),
  useDecision: () => ({ data: mockDecision }),
  useUniverse: () => ({ data: mockUniverse }),
  useUiSystemHealth: (...args: unknown[]) => mockUseUiSystemHealth(...args),
  useUiTrackedPositions: () => ({ data: mockPositions }),
  useDefaultAccount: () => ({ data: { account: { account_id: "acct_1" } } }),
  usePortfolioMtm: (...args: unknown[]) => mockUsePortfolioMtm(...args),
  useSharesCandidates: () => ({ data: null }),
  useActionNeeded: (...args: unknown[]) => mockUseActionNeeded(...args),
  useRunEval: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    error: null,
  }),
}));

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders without throwing", () => {
    expect(() => render(<DashboardPage />)).not.toThrow();
  });

  it("shows decision region", async () => {
    render(<DashboardPage />);
    const region = await screen.findByRole("region", { name: /decision/i });
    expect(region).toBeInTheDocument();
  });

  it("shows trade plan region", async () => {
    render(<DashboardPage />);
    const region = await screen.findByRole("region", { name: /trade plan/i });
    expect(region).toBeInTheDocument();
  });

  it("shows daily overview region", async () => {
    render(<DashboardPage />);
    const region = await screen.findByRole("region", { name: /daily overview/i });
    expect(region).toBeInTheDocument();
  });

  it("shows Manage positions CTA linking to Portfolio", async () => {
    render(<DashboardPage />);
    const links = screen.getAllByRole("link", { name: /Manage positions/i });
    expect(links.length).toBeGreaterThanOrEqual(1);
    expect(links[0]).toHaveAttribute("href", "/portfolio");
  });

  it("shows Net PnL card when MTM data available (Phase 15.0)", async () => {
    mockUsePortfolioMtm.mockReturnValue({
      data: { realized_total: 100, unrealized_total: -50, positions: [] },
    });
    render(<DashboardPage />);
    expect(await screen.findByRole("region", { name: /trade plan/i })).toBeInTheDocument();
    expect(screen.getByText(/Net PnL/i)).toBeInTheDocument();
    expect(screen.getByText("Realized")).toBeInTheDocument();
    expect(screen.getByText("Unrealized")).toBeInTheDocument();
    mockUsePortfolioMtm.mockReturnValue({ data: null });
  });

  it("Run Evaluation button disabled when market closed (Phase 9)", async () => {
    mockUseUiSystemHealth.mockReturnValue({
      data: { ...mockHealth, market: { ...mockHealth.market, phase: "POST" } },
    });
    render(<DashboardPage />);
    const btn = await screen.findByRole("button", { name: /run evaluation/i });
    expect(btn).toBeDisabled();
    mockUseUiSystemHealth.mockReturnValue({ data: mockHealth });
  });

  it("R24.1: Action Needed card renders options and shares rows from API", async () => {
    mockUseActionNeeded.mockReturnValue({
      data: {
        top_options: [
          { symbol: "AAPL", next_action_code: "ENTRY", rationale_lines: ["Near support."], key_number: "delta 0.28", tab: "Options", accordion: "Trade", accordion_id: "trade" },
        ],
        top_shares: [
          { symbol: "WMT", next_action_code: "HOLD", rationale_lines: ["In position."], key_number: "spot 165", tab: "Shares", accordion: "Trade Plan", accordion_id: "trade-plan" },
        ],
        recently_changed: [],
      },
    });
    render(<DashboardPage />);
    const card = await screen.findByTestId("action-needed-card");
    expect(card).toBeInTheDocument();
    expect(screen.getByTestId("action-needed-options-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("action-needed-shares-row-WMT")).toBeInTheDocument();
    const optLink = screen.getByTestId("action-needed-options-row-AAPL");
    expect(optLink).toHaveAttribute("href", expect.stringContaining("symbol=AAPL"));
    expect(optLink).toHaveAttribute("href", expect.stringContaining("tab=Options"));
    expect(optLink).toHaveAttribute("href", expect.stringContaining("accordion=trade"));
    const shrLink = screen.getByTestId("action-needed-shares-row-WMT");
    expect(shrLink).toHaveAttribute("href", expect.stringContaining("symbol=WMT"));
    expect(shrLink).toHaveAttribute("href", expect.stringContaining("tab=Shares"));
    expect(shrLink).toHaveAttribute("href", expect.stringContaining("accordion=trade-plan"));
  });

  it("R24.2: Action Needed shows severity when present and never raw FAIL_/WARN_", async () => {
    mockUseActionNeeded.mockReturnValue({
      data: {
        top_options: [
          { symbol: "NVDA", next_action_code: "CLOSE", rationale_lines: ["Target reached."], key_number: "spot 150", tab: "Options", accordion: "Trade", accordion_id: "trade", severity: "high", dte: 10, strike: 145 },
        ],
        top_shares: [],
        recently_changed: [],
      },
    });
    render(<DashboardPage />);
    await screen.findByTestId("action-needed-card");
    expect(screen.getByTestId("action-needed-severity-NVDA")).toHaveTextContent("high");
    expect(document.body.textContent).not.toMatch(/FAIL_|WARN_/);
  });

  it("R25.9: Guardrails card renders when system health includes guardrails", async () => {
    mockUseUiSystemHealth.mockReturnValue({
      data: {
        ...mockHealth,
        guardrails: {
          status: "OK",
          metrics: { cash_reserve_pct: 35, open_options_count: 2, open_shares_count: 1, symbols_exposure_count: 3, max_symbol_notional_pct: 8 },
          limits: { MAX_OPEN_OPTIONS_POSITIONS: 6, MAX_OPEN_SHARES_POSITIONS: 10, MAX_SYMBOLS_EXPOSURE: 12, MAX_NOTIONAL_PER_SYMBOL_PCT: 15, MIN_CASH_RESERVE_PCT: 25 },
        },
      },
    });
    render(<DashboardPage />);
    const card = await screen.findByTestId("guardrails-card");
    expect(card).toBeInTheDocument();
    expect(screen.getByText("Guardrails")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bFAIL\b/);
    expect(document.body.textContent).not.toMatch(/\bWARN\b/);
    mockUseUiSystemHealth.mockReturnValue({ data: mockHealth });
  });

  it("R24.4: Action Needed shows mark provenance, Recommend, and roll reason (safe labels only)", async () => {
    mockUseActionNeeded.mockReturnValue({
      data: {
        top_options: [
          {
            symbol: "AAPL",
            next_action_code: "ROLL",
            rationale_lines: [],
            key_number: null,
            tab: "Options",
            accordion: "Trade",
            accordion_id: "trade",
            severity: "medium",
            dte: 12,
            strike: 150,
            mark_value: 1.23,
            mark_source: "MID",
            mark_age_sec: 18,
            pct_max_profit: 52,
            recommended_action_code: "ROLL",
            roll_reason_codes: ["DTE_WINDOW"],
          },
        ],
        top_shares: [],
        recently_changed: [],
      },
    });
    render(<DashboardPage />);
    await screen.findByTestId("action-needed-card");
    expect(screen.getByTestId("action-needed-mark-AAPL")).toHaveTextContent(/Mark: 1.23/);
    expect(screen.getByTestId("action-needed-mark-AAPL")).toHaveTextContent(/MID/);
    expect(screen.getByTestId("action-needed-mark-AAPL")).toHaveTextContent(/18s old/);
    expect(screen.getByTestId("action-needed-pct-profit-AAPL")).toHaveTextContent("52%");
    expect(screen.getByTestId("action-needed-roll-reason-AAPL")).toHaveTextContent("Reason: DTE window");
    expect(document.body.textContent).not.toMatch(/FAIL_|WARN_/);
  });

  it("R26.0: Action Needed shows size, notional, and constraints for ENTRY with r260 sizing", async () => {
    mockUseActionNeeded.mockReturnValue({
      data: {
        top_options: [
          {
            symbol: "SPY",
            next_action_code: "ENTRY",
            rationale_lines: ["Eligible."],
            key_number: null,
            tab: "Options",
            accordion: "trade",
            accordion_id: "trade",
            sizing_recommended_by: "r260",
            recommended_contracts: 2,
            recommended_notional_usd: 20000,
            sizing_constraints_hit: ["CASH_RESERVE"],
          },
        ],
        top_shares: [
          {
            symbol: "QQQ",
            next_action_code: "ENTRY",
            rationale_lines: ["Support."],
            key_number: null,
            tab: "Shares",
            accordion: "trade-plan",
            accordion_id: "trade-plan",
            sizing_recommended_by: "r260",
            recommended_qty: 50,
            recommended_notional_usd: 25000,
            sizing_constraints_hit: [],
          },
        ],
        recently_changed: [],
      },
    });
    render(<DashboardPage />);
    await screen.findByTestId("action-needed-card");
    const optSizing = screen.getByTestId("action-needed-sizing-SPY");
    expect(optSizing).toHaveTextContent(/Size: 2 contracts/);
    expect(optSizing).toHaveTextContent(/Notional: \$20,000/);
    expect(optSizing).toHaveTextContent(/Constraints: Cash reserve/);
    const shrSizing = screen.getByTestId("action-needed-sizing-QQQ");
    expect(shrSizing).toHaveTextContent(/Size: 50 shares/);
    expect(shrSizing).toHaveTextContent(/Notional: \$25,000/);
    expect(document.body.textContent).not.toMatch(/FAIL_|WARN_/);
  });

  it("R26.0: No FAIL or WARN in DOM when guardrails include available_budget_usd", async () => {
    mockUseUiSystemHealth.mockReturnValue({
      data: {
        ...mockHealth,
        guardrails: {
          status: "OK",
          metrics: {
            cash_reserve_pct: 30,
            open_options_count: 1,
            open_shares_count: 0,
            symbols_exposure_count: 2,
            max_symbol_notional_pct: 10,
            available_budget_usd: 45000,
          },
          limits: { MAX_OPEN_OPTIONS_POSITIONS: 6, MAX_OPEN_SHARES_POSITIONS: 10, MAX_SYMBOLS_EXPOSURE: 12 },
        },
      },
    });
    render(<DashboardPage />);
    await screen.findByTestId("guardrails-card");
    expect(screen.getByTestId("guardrails-available-budget")).toHaveTextContent("$45,000");
    expect(document.body.textContent).not.toMatch(/FAIL_|WARN_/);
    mockUseUiSystemHealth.mockReturnValue({ data: mockHealth });
  });
});
