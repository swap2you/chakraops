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
};

const mockHistory = {
  runs: [
    {
      timestamp_utc: "2026-01-01T12:00:00Z",
      overall_status: "PASS",
      checks: [{ check: "orats", status: "PASS", details: {} }],
    },
  ],
};

const mockUseLatestSnapshot = vi.fn(() => ({ data: null, isError: true }));
const mockUseUiSystemHealth = vi.fn(() => ({ data: mockHealth, isLoading: false, isError: false }));
vi.mock("@/api/queries", () => ({
  useUiSystemHealth: (...args: unknown[]) => mockUseUiSystemHealth(...args),
  useDiagnosticsHistory: () => ({ data: mockHistory }),
  useRunDiagnostics: () => ({
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
});
