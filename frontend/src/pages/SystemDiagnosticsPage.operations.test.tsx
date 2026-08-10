import { render, screen } from "@/test/test-utils";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SystemDiagnosticsPage } from "./SystemDiagnosticsPage";

const mockUseUiSystemHealth = vi.fn();
const mockUseOperationsStatus = vi.fn();

vi.mock("@/api/queries", () => ({
  useUiSystemHealth: () => mockUseUiSystemHealth(),
  useOperationsStatus: () => mockUseOperationsStatus(),
  useEarningsDebug: () => ({ data: null }),
  useDiagnosticsHistory: () => ({ data: { runs: [] } }),
  useRunDiagnostics: () => ({ mutate: vi.fn(), isPending: false }),
  useRunEval: () => ({ mutate: vi.fn(), isPending: false }),
  useLatestSnapshot: () => ({ data: null, isError: false }),
  useRunFreezeSnapshot: () => ({ mutate: vi.fn(), isPending: false, data: null }),
  useStoresIntegrity: () => ({ data: null }),
  useRepairStore: () => ({ mutate: vi.fn(), isPending: false }),
  useAdminSlackTest: () => ({ mutate: vi.fn(), isPending: false }),
  useAdminEvaluationForce: () => ({ mutate: vi.fn(), isPending: false }),
  usePositionsUnifiedRebuild: () => ({ mutate: vi.fn(), isPending: false }),
  usePositionsUnifiedIntegrityCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useReconcileDiff: () => ({ data: null, isLoading: false }),
}));

describe("SystemDiagnosticsPage operations panel", () => {
  beforeEach(() => {
    mockUseUiSystemHealth.mockReturnValue({
      data: { api: { status: "OK" }, scheduler: {}, market: {} },
      isLoading: false,
      isError: false,
    });
    mockUseOperationsStatus.mockReturnValue({
      data: {
        scheduler: {
          master_enabled: false,
          legacy_schedulers_enabled: false,
          jobs: [{ job_id: "backup", enabled: false, schedule: "Daily" }],
        },
        orats_token_present: true,
        backup: { latest: { backup_id: "backup_test" }, count: 1 },
      },
    });
  });

  it("renders R35 operations panel", () => {
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("operations-panel-r35")).toBeInTheDocument();
    expect(screen.getByText(/Scheduler master/i)).toBeInTheDocument();
    expect(screen.getByTestId("scheduler-master-status")).toHaveTextContent(/Disabled \(false\)/i);
  });

  it("R46: shows legacy schedulers false, Slack CODE_READY/UNCONFIGURED, Copilot unconfigured", () => {
    mockUseUiSystemHealth.mockReturnValue({
      data: {
        api: { status: "OK" },
        scheduler: {},
        market: {},
        slack: { implementation_status: "CODE_READY", config_status: "UNCONFIGURED", configured: false },
        copilot: { key_present: false, key_source: "NONE" },
      },
      isLoading: false,
      isError: false,
    });
    render(<SystemDiagnosticsPage />);
    expect(screen.getByTestId("scheduler-legacy-status")).toHaveTextContent(/Disabled \(false\)/i);
    expect(screen.getByTestId("slack-implementation-status")).toHaveTextContent("CODE_READY");
    expect(screen.getByTestId("slack-config-status")).toHaveTextContent("UNCONFIGURED");
    expect(screen.getByTestId("copilot-config-status")).toHaveTextContent("UNCONFIGURED");
  });
});
