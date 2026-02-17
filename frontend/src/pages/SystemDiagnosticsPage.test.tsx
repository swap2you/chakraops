import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { SystemDiagnosticsPage } from "./SystemDiagnosticsPage";

const mockHealth = {
  api: { status: "OK", latency_ms: 10 },
  decision_store: { status: "OK" },
  orats: { status: "OK", last_success_at: "2026-01-01T12:00:00Z" },
  market: { phase: "OPEN", is_open: true },
  scheduler: { interval_minutes: 15, last_run_at: null, next_run_at: null },
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

vi.mock("@/api/queries", () => ({
  useUiSystemHealth: () => ({ data: mockHealth, isLoading: false, isError: false }),
  useDiagnosticsHistory: () => ({ data: mockHistory }),
  useRunDiagnostics: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

describe("SystemDiagnosticsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
