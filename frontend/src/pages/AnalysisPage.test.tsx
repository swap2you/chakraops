/**
 * Phase 10: Symbol Diagnostics page — gates, blockers, recommendation.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { AnalysisPage } from "./AnalysisPage";
import { DataModeProvider } from "@/context/DataModeContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { BrowserRouter } from "react-router-dom";
import * as apiClient from "@/data/apiClient";

vi.mock("@/data/apiClient", () => ({
  apiGet: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public bodySnippet?: string
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

const mockDiagnostics = {
  symbol: "NVDA",
  in_universe: true,
  universe_reason: "In universe",
  snapshot_time: "2026-02-01T14:00:00Z",
  market: { regime: "NORMAL", risk_posture: "CONSERVATIVE" },
  gates: [
    { name: "no_exclusion", pass: true, detail: "Symbol not in exclusions", code: null },
    { name: "liquidity", pass: false, detail: "Spread too wide", code: "SPREAD" },
  ],
  blockers: [{ code: "SPREAD", message: "Spread too wide", severity: "high" }],
  liquidity: { spread_pct: 0.05 },
  earnings: { next_date: null, days_to_earnings: null, blocked: false },
  options: { has_options: true, chain_ok: true, expirations_count: 5, contracts_count: 100 },
  eligibility: { verdict: "UNKNOWN" as const, primary_reason: "Eligibility not determined" },
  notes: [],
};

function LiveWrapper({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <DataModeProvider initialMode="LIVE">
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</BrowserRouter>
      </DataModeProvider>
    </ThemeProvider>
  );
}

describe("AnalysisPage", () => {
  it("renders LIVE only message in MOCK mode", () => {
    render(<AnalysisPage />);
    expect(screen.getByText(/LIVE only/i)).toBeInTheDocument();
  });

  it("in LIVE shows symbol input and Analyze button", () => {
    vi.mocked(apiClient.apiGet).mockResolvedValue(mockDiagnostics);
    render(<AnalysisPage />, { wrapper: LiveWrapper });
    expect(screen.getByPlaceholderText(/e.g. NVDA/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze/i })).toBeInTheDocument();
  });

  it("renders gate list and blockers after successful fetch", async () => {
    vi.mocked(apiClient.apiGet).mockResolvedValue(mockDiagnostics);
    render(<AnalysisPage />, { wrapper: LiveWrapper });
    const input = screen.getByPlaceholderText(/e.g. NVDA/i);
    fireEvent.change(input, { target: { value: "NVDA" } });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));
    expect(await screen.findByText("Gates")).toBeInTheDocument();
    expect(screen.getByText(/no_exclusion/i)).toBeInTheDocument();
    expect(screen.getByText("Blockers")).toBeInTheDocument();
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("Eligibility not determined")).toBeInTheDocument();
    expect(screen.getByText("SPREAD")).toBeInTheDocument();
  });

  it("renders UNKNOWN status and Eligibility not determined when symbol not in universe", async () => {
    const outOfScope = {
      ...mockDiagnostics,
      symbol: "NVDA",
      in_universe: false,
      status: "OUT_OF_SCOPE",
      eligibility: { verdict: "UNKNOWN" as const, primary_reason: "Eligibility not determined" },
      fetched_at: "2026-02-01T15:00:00Z",
      blockers: [{ code: "NOT_IN_UNIVERSE", message: "Symbol not in evaluation universe", severity: "info" }],
    };
    vi.mocked(apiClient.apiGet).mockResolvedValue(outOfScope);
    render(<AnalysisPage />, { wrapper: LiveWrapper });
    fireEvent.change(screen.getByPlaceholderText(/e.g. NVDA/i), { target: { value: "NVDA" } });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));
    expect(await screen.findByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("Eligibility not determined")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
  });
});
