import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { SystemDiagnosticsPage } from "./SystemDiagnosticsPage";

const mockHealth = {
  api: { status: "OK", latency_ms: 10 },
  decision_store: { status: "OK" },
  orats: { status: "OK", last_success_at: "2026-01-01T12:00:00Z" },
  market: { phase: "OPEN", is_open: true },
  scheduler: { interval_minutes: 15, last_run_at: null, next_run_at: null },
  eod_freeze: { enabled: true, scheduled_time_et: "15:58", last_run_at_utc: null, last_snapshot_dir: null },
  mark_refresh: { last_run_at_utc: null, last_result: null, updated_count: null, skipped_count: null, error_count: null, errors_sample: [] },
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
const mockIntegrityData = {
  stores: {
    notifications: { path: "/out/notifications.jsonl", exists: true, total_lines: 10, invalid_lines: 0, last_valid_line: 10, last_valid_offset: 0 },
    diagnostics_history: { path: "/out/diagnostics_history.jsonl", exists: true, total_lines: 5, invalid_lines: 0, last_valid_line: 5, last_valid_offset: 0 },
    positions_events: { path: "/out/positions/positions_events.jsonl", exists: true, total_lines: 0, invalid_lines: 0, last_valid_line: 0, last_valid_offset: 0 },
  },
};

vi.mock("@/api/queries", () => ({
  useUiSystemHealth: (...args: unknown[]) => mockUseUiSystemHealth(...args),
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

  it("shows Mark Refresh card (Phase 16.0)", () => {
    mockUseUiSystemHealth.mockReturnValueOnce({
      data: {
        ...mockHealth,
        mark_refresh: {
          last_run_at_utc: "2026-01-01T14:00:00Z",
          last_result: "PASS",
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
