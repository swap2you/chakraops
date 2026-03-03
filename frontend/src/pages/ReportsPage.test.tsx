/**
 * R25.5: Reports page — monthly summary with mocked hook; no FAIL/WARN in document.
 * R26.5: Monthly close panel — Generate triggers mutation; no FAIL/WARN in DOM.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen } from "@/test/test-utils";
import { ReportsPage } from "./ReportsPage";

const mockReport = {
  month: "2026-02",
  total_realized_pl: 500.5,
  by_strategy: { SHARES: 200, CSP: 200.5, CC: 100 },
  trade_count: 5,
  win_count: 3,
  loss_count: 2,
  win_rate: 60,
  avg_hold_days: null,
  top_winners: [
    { symbol: "SPY", realized_pl: 150, strategy: "SHARES" },
    { symbol: "QQQ", realized_pl: 100, strategy: "CSP" },
  ],
  top_losers: [
    { symbol: "IWM", realized_pl: -50, strategy: "CC" },
  ],
  fees_total: 10.0,
  included_paper: false,
  mode: "LIVE_ONLY" as const,
};

const mockCloseFiles = {
  month: "2026-02",
  files: [{ name: "monthly_report.json", size: 100 }, { name: "summary.txt", size: 50 }],
  generated_ts: "2026-02-27T12:00:00Z",
  paths: ["monthly_report.json", "monthly_report.csv", "journal_export.csv", "summary.txt"],
};

const mockMutate = vi.fn();

vi.mock("@/api/queries", () => ({
  useReportsMonthly: () => ({
    data: mockReport,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useMonthlyCloseFiles: () => ({
    data: mockCloseFiles,
    isLoading: false,
  }),
  useMonthlyCloseGenerate: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
  downloadMonthlyCloseFile: vi.fn(),
}));

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders monthly report summary using mocked data", () => {
    render(<ReportsPage />);
    expect(screen.getByRole("heading", { name: /Monthly report/i })).toBeInTheDocument();
    expect(screen.getByText(/Total realized P\/L/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Top winners/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Top losers/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("IWM")).toBeInTheDocument();
  });

  it("renders Monthly Close panel with Generate live/paper buttons and download links (R26.5, R27.1)", () => {
    render(<ReportsPage />);
    expect(screen.getByTestId("monthly-close-panel")).toBeInTheDocument();
    expect(screen.getByTestId("monthly-close-generate-live")).toHaveTextContent("Generate live pack");
    expect(screen.getByTestId("monthly-close-generate-paper")).toHaveTextContent("Generate paper pack");
    expect(screen.getByTestId("monthly-close-download-live-monthly_report-json")).toBeInTheDocument();
    expect(screen.getByTestId("monthly-close-download-live-summary-txt")).toBeInTheDocument();
  });

  it("Generate live pack triggers mutation with month and include_paper false (R26.5, R27.1)", async () => {
    render(<ReportsPage />);
    await userEvent.click(screen.getByTestId("monthly-close-generate-live"));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate).toHaveBeenCalledWith(expect.objectContaining({ month: expect.stringMatching(/^\d{4}-\d{2}$/), include_paper: false }));
  });

  it("Generate paper pack calls API with include_paper true (R27.1)", async () => {
    render(<ReportsPage />);
    await userEvent.click(screen.getByTestId("monthly-close-generate-paper"));
    expect(mockMutate).toHaveBeenCalledWith(expect.objectContaining({ include_paper: true }));
  });

  it("shows Mode label from report (R27.1)", () => {
    render(<ReportsPage />);
    expect(screen.getByTestId("reports-mode-label")).toHaveTextContent("Mode: Live only");
  });

  it("document text does not contain FAIL or WARN (R25.5 safety)", () => {
    const { container } = render(<ReportsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("shows Include paper toggle (R27.0)", () => {
    render(<ReportsPage />);
    expect(screen.getByTestId("reports-include-paper")).toBeInTheDocument();
    expect(screen.getByText(/Include paper/)).toBeInTheDocument();
  });
});
