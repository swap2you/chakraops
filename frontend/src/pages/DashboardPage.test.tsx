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
vi.mock("@/api/queries", () => ({
  useArtifactList: () => ({ data: mockFiles }),
  useDecision: () => ({ data: mockDecision }),
  useUniverse: () => ({ data: mockUniverse }),
  useUiSystemHealth: (...args: unknown[]) => mockUseUiSystemHealth(...args),
  useUiTrackedPositions: () => ({ data: mockPositions }),
  useDefaultAccount: () => ({ data: { account: { account_id: "acct_1" } } }),
  usePortfolioMtm: (...args: unknown[]) => mockUsePortfolioMtm(...args),
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
});
