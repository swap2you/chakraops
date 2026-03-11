import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, within } from "@/test/test-utils";
import { SystemDiagnosticsPage } from "./SystemDiagnosticsPage";

const mockHealth = {
  api: { status: "OK", latency_ms: 10 },
  decision_store: { status: "OK" },
  orats: { status: "OK", last_success_at: "2026-01-01T12:00:00Z" },
  market: { phase: "OPEN", is_open: true },
  scheduler: {
    interval_minutes: 15,
    last_run_at: null,
    next_run_at: null,
    last_skip_reason: "market_closed",
    last_duration_ms: 12.5,
    last_run_ok: null,
    last_run_error: null,
    run_count_today: 0,
  },
  slack: {
    last_send_at: null,
    last_send_ok: null,
    last_error: null,
    last_channel: null,
    last_payload_type: null,
    channels: {
      signals: { last_send_at: null, last_send_ok: null, last_error: null, last_payload_type: null },
      daily: { last_send_at: null, last_send_ok: null, last_error: null, last_payload_type: null },
      data_health: { last_send_at: null, last_send_ok: null, last_error: null, last_payload_type: null },
      critical: { last_send_at: null, last_send_ok: null, last_error: null, last_payload_type: null },
    },
  },
  eod_freeze: { enabled: true, scheduled_time_et: "15:58", last_run_at_utc: null, last_snapshot_dir: null },
  mark_refresh: { last_run_at_utc: null, status: null, status_label: null, updated_count: null, skipped_count: null, error_count: null, errors_sample: [] },
  cadence: { mode: "EOD_BIASED", eligibility_as_of: "2026-02-27T18:00:00Z" },
  earnings_probe_symbol: "SPY",
  positions_unified_reconcile: {
    status: "OK",
    paper_open_count: 0,
    paper_closed_count: 0,
    unified_open_paper_count: 0,
    unified_closed_paper_count: 0,
  },
  positions_unified_rebuild: {
    status: "OK",
    status_label: "OK",
    last_rebuild_at_utc: "2026-02-27T14:00:00Z",
    last_rebuild_open_count: 2,
    last_rebuild_closed_count: 1,
    last_include_paper: true,
  },
  positions_unified_integrity_check: {
    last_checked_at_utc: "2026-02-27T15:00:00Z",
    last_status: "OK",
    last_status_label: "OK",
    last_reconcile_missing_count: 0,
    last_reconcile_extra_count: 0,
    last_reconcile_mismatched_count: 0,
    last_sample_items: [
      {
        kind: "missing",
        id: "p1",
        symbol: "AAPL",
        instrument_type: "SHARES",
        link_positions_url: "/positions?source=db&symbol=AAPL&include_paper=true",
        link_diagnostics_url: "/system",
      },
    ],
  },
  guardrails: {
    status: "OK",
    metrics: { cash_reserve_pct: 40, open_options_count: 1, open_shares_count: 0, symbols_exposure_count: 2, max_symbol_notional_pct: 10 },
    limits: { MAX_OPEN_OPTIONS_POSITIONS: 6, MAX_OPEN_SHARES_POSITIONS: 10, MAX_SYMBOLS_EXPOSURE: 12, MAX_NOTIONAL_PER_SYMBOL_PCT: 15, MIN_CASH_RESERVE_PCT: 25 },
  },
};

const mockHistory = {
  runs: [
    {
      timestamp_utc: "2026-01-01T12:00:00Z",
      overall_status: "PASS",
      checks: [{ check: "orats", status: "PASS", details: {}, recommended_action: null }],
    },
  ],
};

const mockUseLatestSnapshot = vi.fn(() => ({ data: null, isError: true }));
const mockUseUiSystemHealth = vi.fn(() => ({ data: mockHealth, isLoading: false, isError: false }));
const mockRebuildMutate = vi.fn();
const mockDownloadIntegrityBundle = vi.hoisted(() => vi.fn());
const mockIntegrityData = {
  stores: {
    notifications: { path: "/out/notifications.jsonl", exists: true, total_lines: 10, invalid_lines: 0, last_valid_line: 10, last_valid_offset: 0 },
    diagnostics_history: { path: "/out/diagnostics_history.jsonl", exists: true, total_lines: 5, invalid_lines: 0, last_valid_line: 5, last_valid_offset: 0 },
    positions_events: { path: "/out/positions/positions_events.jsonl", exists: true, total_lines: 0, invalid_lines: 0, last_valid_line: 0, last_valid_offset: 0 },
  },
};

const mockEarningsDebug = { status: "OK", next_date: "2026-03-15", days: 14, implied_move_pct: 5.2, as_of: "2026-02-27T12:00:00Z" };
const mockUseEarningsDebug = vi.fn(() => ({ data: mockEarningsDebug }));

vi.mock("@/api/queries", () => ({
  useUiSystemHealth: (...args: unknown[]) => mockUseUiSystemHealth(...args),
  useEarningsDebug: (symbol: string) => mockUseEarningsDebug(symbol),
  useDiagnosticsHistory: () => ({ data: mockHistory }),
  useRunDiagnostics: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useRunEval: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
  useLatestSnapshot: (...args: unknown[]) => mockUseLatestSnapshot(...args),
  useRunFreezeSnapshot: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    data: null,
  }),
  useStoresIntegrity: () => ({ data: mockIntegrityData }),
  useRepairStore: () => ({ mutate: vi.fn(), isPending: false }),
  useAdminSlackTest: () => ({ mutate: vi.fn(), isPending: false, data: null }),
  useAdminEvaluationForce: () => ({ mutate: vi.fn(), isPending: false, data: null }),
  usePositionsUnifiedRebuild: () => ({ mutate: mockRebuildMutate, isPending: false }),
  usePositionsUnifiedIntegrityCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useReconcileDiff: () => ({ data: { missing_count: 0, extra_count: 0, mismatched_count: 0, items: [] }, isLoading: false }),
  downloadIntegrityBundle: mockDownloadIntegrityBundle,
}));

describe("SystemDiagnosticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUiSystemHealth.mockReturnValue({ data: mockHealth, isLoading: false, isError: false });
  });

  it("renders without throwing", () => {
    expect(() => render(<SystemDiagnosticsPage />)).not.toThrow();
  });

  it("shows System Status", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/System Status/i)).toBeInTheDocument();
  });

  it("R25.8: shows cadence banner when EOD_BIASED", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("cadence-banner")).toBeInTheDocument();
    expect(screen.getByText(/Cadence: eod-biased/i)).toBeInTheDocument();
  });

  it("R25.8: shows Earnings probe card with safe labels", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("earnings-probe-card")).toBeInTheDocument();
    expect(screen.getByText(/Earnings probe/i)).toBeInTheDocument();
    expect(screen.getByText(/Probe symbol SPY/i)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R28.1: Unified Positions Reconcile card renders when present; no FAIL/WARN in document", () => {
    render(<SystemDiagnosticsPage />);
    const reconcileCard = screen.getByTestId("positions-unified-reconcile-card");
    expect(reconcileCard).toBeInTheDocument();
    expect(within(reconcileCard).getByText("Unified Positions Reconcile")).toBeInTheDocument();
    expect(screen.getByText(/Paper open/i)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R29.4: Unified Positions Integrity Check card renders when positions_unified_integrity_check present", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("positions-unified-integrity-check-card")).toBeInTheDocument();
    expect(screen.getByTestId("integrity-check-view-details-btn")).toHaveTextContent("View details");
  });

  it("R29.6: integrity sample items show Open positions link with correct href; no forbidden tokens", async () => {
    const user = userEvent.setup();
    const { container } = render(<SystemDiagnosticsPage />);
    await user.click(screen.getByTestId("integrity-check-view-details-btn"));
    const openPosLinks = screen.getAllByTestId("integrity-sample-open-positions");
    expect(openPosLinks.length).toBeGreaterThanOrEqual(1);
    expect(openPosLinks[0]).toHaveAttribute("href", "/positions?source=db&symbol=AAPL&include_paper=true");
    const openDiagLinks = screen.getAllByTestId("integrity-sample-open-diagnostics");
    expect(openDiagLinks.length).toBeGreaterThanOrEqual(1);
    expect(openDiagLinks[0]).toHaveAttribute("href", "/system");
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R29.7: Download integrity bundle button only when Review; clicking calls download with include_paper true", async () => {
    const healthReview = {
      ...mockHealth,
      positions_unified_integrity_check: {
        ...mockHealth.positions_unified_integrity_check,
        last_status: "Review",
        last_status_label: "Differences found",
      },
    };
    mockUseUiSystemHealth.mockReturnValue({ data: healthReview, isLoading: false, isError: false });
    const user = userEvent.setup();
    render(<SystemDiagnosticsPage />);
    const downloadBtn = screen.getByTestId("integrity-check-download-bundle-btn");
    expect(downloadBtn).toHaveTextContent("Download integrity bundle");
    await user.click(downloadBtn);
    expect(mockDownloadIntegrityBundle).toHaveBeenCalledWith(true);
  });

  it("R29.7: when integrity status OK, Download integrity bundle button is not present", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.queryByTestId("integrity-check-download-bundle-btn")).not.toBeInTheDocument();
  });

  it("R29.4: document has no FAIL/WARN/PASS or FAIL_/WARN_ tokens", () => {
    render(<SystemDiagnosticsPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R29.5: when integrity status Review, remediation guidance shows bullets and links", () => {
    const healthReview = {
      ...mockHealth,
      positions_unified_integrity_check: {
        ...mockHealth.positions_unified_integrity_check,
        last_status: "Review",
        last_status_label: "Differences found",
      },
    };
    mockUseUiSystemHealth.mockReturnValue({ data: healthReview, isLoading: false, isError: false });
    render(<SystemDiagnosticsPage />);
    const guidance = screen.getByTestId("integrity-check-remediation-guidance");
    expect(guidance).toBeInTheDocument();
    expect(guidance).not.toHaveTextContent("No action needed.");
    expect(guidance).toHaveTextContent("View diff details");
    expect(guidance).toHaveTextContent("Run integrity check");
    expect(guidance).toHaveTextContent("Rebuild unified positions");
  });

  it("R29.5: document has no forbidden tokens", () => {
    render(<SystemDiagnosticsPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R28.7: Unified Positions Rebuild card renders when positions_unified_rebuild present", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("positions-unified-rebuild-card")).toBeInTheDocument();
    expect(screen.getByText(/Unified Positions Rebuild/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rebuild unified positions/i })).toBeInTheDocument();
  });

  it("R28.7: Rebuild button click with confirm triggers mutation with include_paper true", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<SystemDiagnosticsPage />);
    await user.click(screen.getByTestId("positions-unified-rebuild-btn"));
    expect(mockRebuildMutate).toHaveBeenCalledWith({ include_paper: true });
    vi.mocked(window.confirm).mockRestore();
  });

  it("R28.7: Document has no raw FAIL/WARN/PASS tokens", () => {
    render(<SystemDiagnosticsPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
  });

  it("R28.8: Reconcile Diff card renders when positions_unified_reconcile present", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("positions-unified-reconcile-diff-card")).toBeInTheDocument();
    expect(screen.getByText(/Unified Positions Reconcile Diff/i)).toBeInTheDocument();
  });

  it("R28.8: View details button exists when reconcile is Review and toggles expand", async () => {
    const user = userEvent.setup();
    mockUseUiSystemHealth.mockReturnValue({
      data: { ...mockHealth, positions_unified_reconcile: { ...mockHealth.positions_unified_reconcile, status: "Review" } },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    const btn = screen.getByTestId("reconcile-diff-view-details-btn");
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(screen.getByText(/Hide details/i)).toBeInTheDocument();
  });

  it("R28.8: Document has no FAIL/WARN/PASS in reconcile diff area", () => {
    render(<SystemDiagnosticsPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
  });

  it("R28.9: Rebuild now button renders only when reconcile status is Review", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.queryByTestId("reconcile-diff-rebuild-now-btn")).not.toBeInTheDocument();
    mockUseUiSystemHealth.mockReturnValue({
      data: { ...mockHealth, positions_unified_reconcile: { ...mockHealth.positions_unified_reconcile, status: "Review" } },
      isLoading: false,
      isError: false,
    });
    const { unmount } = render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("reconcile-diff-rebuild-now-btn")).toBeInTheDocument();
    unmount();
  });

  it("R28.9: Clicking Rebuild now triggers mutation with include_paper true", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockUseUiSystemHealth.mockReturnValue({
      data: { ...mockHealth, positions_unified_reconcile: { ...mockHealth.positions_unified_reconcile, status: "Review" } },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    await user.click(screen.getByTestId("reconcile-diff-rebuild-now-btn"));
    expect(mockRebuildMutate).toHaveBeenCalledWith({ include_paper: true }, expect.any(Object));
    vi.mocked(window.confirm).mockRestore();
  });

  it("R28.9: Document has no FAIL/WARN/PASS tokens", () => {
    render(<SystemDiagnosticsPage />);
    expect(document.body.textContent ?? "").not.toMatch(/\b(FAIL|WARN|PASS)\b/);
  });

  it("R25.9: Guardrails card renders with safe labels; no FAIL/WARN in DOM", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("guardrails-card")).toBeInTheDocument();
    expect(screen.getByText(/^Guardrails$/)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("shows Sanity Checks section", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Sanity Checks/i)).toBeInTheDocument();
  });

  it("shows Run All button", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByRole("button", { name: /Run All/i })).toBeInTheDocument();
  });

  it("shows Freeze Snapshot section (PR2)", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Freeze Snapshot/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Archive Now \(no eval\)/i })).toBeInTheDocument();
  });

  it("shows Run Scheduler now button in Scheduler card", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByRole("button", { name: /Run Scheduler now/i })).toBeInTheDocument();
  });

  it("shows last_skip_reason in Scheduler card (Phase 21.5); R22.2 uses friendly label", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Market closed/i)).toBeInTheDocument();
  });

  it("R22.2: shows friendly scheduler skip reason when market_closed (set-and-forget, not error)", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Market closed — scheduler skips until open/)).toBeInTheDocument();
  });

  it("R22.2: ORATS card shows Freshness and Threshold when present", () => {
    mockUseUiSystemHealth.mockReturnValueOnce({
      data: {
        ...mockHealth,
        orats: {
          ...mockHealth.orats,
          orats_freshness_state: "OK",
          orats_freshness_state_label: "OK",
          orats_as_of: "2026-01-01T12:00:00Z",
          orats_threshold_triggered: "ok_minutes",
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText("ORATS")).toBeInTheDocument();
    expect(screen.getByText("Threshold")).toBeInTheDocument();
    expect(screen.getByText("Within OK window")).toBeInTheDocument();
  });

  it("R22.2: System Status has no raw FAIL_* reason codes in UI", () => {
    render(<SystemDiagnosticsPage />);
    expect(document.body.innerHTML).not.toMatch(/FAIL_[A-Z_0-9]+/);
  });

  it("shows Slack card and 4 channel test buttons (R21.5.1)", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/^Slack$/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Test signals/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Test daily/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Test data health/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Test critical/i })).toBeInTheDocument();
  });

  it("shows Force evaluation now button (Phase 21.5)", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByRole("button", { name: /Force evaluation now/i })).toBeInTheDocument();
  });

  it("shows Select All and Clear buttons in Sanity Checks", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByRole("button", { name: /Select All/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Clear/i })).toBeInTheDocument();
  });

  it("Run EOD Freeze button disabled when market closed (PR2)", () => {
    mockUseUiSystemHealth.mockReturnValueOnce({
      data: { ...mockHealth, market: { ...mockHealth.market, phase: "POST", is_open: false } },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    const btn = screen.getByRole("button", { name: /Run EOD Freeze \(eval \+ archive\)/i });
    expect(btn).toBeDisabled();
  });

  it("shows Mark Refresh card (Phase 16.0); R28.2 uses safe status only", () => {
    mockUseUiSystemHealth.mockReturnValueOnce({
      data: {
        ...mockHealth,
        mark_refresh: {
          last_run_at_utc: "2026-01-01T14:00:00Z",
          status: "OK",
          status_label: "OK",
          updated_count: 2,
          skipped_count: 0,
          error_count: 0,
          errors_sample: [],
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Mark Refresh/i)).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
    expect(text).not.toMatch(/\bPASS\b/);
  });

  it("R28.2: Mark refresh and portfolio risk notifier render safe labels only; no FAIL/WARN/PASS in document", () => {
    mockUseUiSystemHealth.mockReturnValueOnce({
      data: {
        ...mockHealth,
        mark_refresh: {
          last_run_at_utc: "2026-01-01T14:00:00Z",
          status: "Blocked",
          status_label: "No update",
          updated_count: 0,
          skipped_count: 0,
          error_count: 1,
          errors_sample: ["err1"],
        },
        portfolio_risk_notifier: { status: "Degraded", label: "Advisory" },
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Mark Refresh/i)).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("No update")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
    expect(text).not.toMatch(/\bPASS\b/);
  });

  it("shows eod_freeze last_error when present (Phase 11.3)", () => {
    mockUseUiSystemHealth.mockReturnValueOnce({
      data: {
        ...mockHealth,
        eod_freeze: {
          ...mockHealth.eod_freeze,
          last_error: "Connection refused",
          last_result: "FAIL",
        },
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    expect(screen.getByText(/Connection refused/)).toBeInTheDocument();
  });
});
