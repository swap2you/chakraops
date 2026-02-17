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
};
const mockUniverse = { symbols: [], updated_at: "2026-01-01T12:00:00Z", source: "ARTIFACT_V2" };
const mockHealth = { api: { status: "OK" }, market: { phase: "OPEN" }, orats: { status: "OK" } };
const mockFiles = { files: [{ name: "decision_latest.json" }] };
const mockPositions = { positions: [] };

vi.mock("@/api/queries", () => ({
  useArtifactList: () => ({ data: mockFiles }),
  useDecision: () => ({ data: mockDecision }),
  useUniverse: () => ({ data: mockUniverse }),
  useUiSystemHealth: () => ({ data: mockHealth }),
  useUiTrackedPositions: () => ({ data: mockPositions }),
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
});
