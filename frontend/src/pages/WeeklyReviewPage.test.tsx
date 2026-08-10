import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, renderWithRoute } from "@/test/test-utils";
import { WeeklyReviewPage } from "./WeeklyReviewPage";

const mockChecklist = { row: { status: "OPEN", key: "2026-09" } };
const mockSummary = {
  week: "2026-09",
  from_date: "2026-02-23",
  to_date: "2026-03-01",
  realized_pl_total: 100,
  trade_count: 5,
  winners: [{ symbol: "SPY", realized_pl: 50 }],
  losers: [{ symbol: "QQQ", realized_pl: -20 }],
  guardrails: {},
};
const mockMarkDone = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));

vi.mock("@/api/queries", () => ({
  useOpsChecklist: vi.fn(() => ({ data: mockChecklist })),
  useOpsWeeklySummary: vi.fn(() => ({ data: mockSummary })),
  useOpsChecklistMarkDone: () => mockMarkDone(),
}));

describe("WeeklyReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders weekly summary and mark done button", () => {
    renderWithRoute(<WeeklyReviewPage />, "/weekly");
    expect(screen.getByTestId("weekly-summary-card")).toBeInTheDocument();
    expect(screen.getByTestId("weekly-mark-done")).toBeInTheDocument();
    expect(screen.getByText(/Week \d{4}-\d{2}/)).toBeInTheDocument();
    expect(screen.getByText(/100\.00/)).toBeInTheDocument();
  });

  it("R45: shows sample-size caveat without unsupported performance claims", () => {
    renderWithRoute(<WeeklyReviewPage />, "/weekly");
    const caveat = screen.getByTestId("weekly-sample-caveat");
    expect(caveat).toHaveTextContent(/sample sizes/i);
    expect(caveat).toHaveTextContent(/not treat short-window/i);
    expect(caveat.textContent || "").not.toMatch(/guaranteed|alpha|beat the market/i);
  });

  it("mark done calls mutation with WEEKLY kind", async () => {
    const mutateMock = vi.fn();
    mockMarkDone.mockReturnValue({ mutate: mutateMock, isPending: false });
    renderWithRoute(<WeeklyReviewPage />, "/weekly");
    await userEvent.click(screen.getByTestId("weekly-mark-done"));
    expect(mutateMock).toHaveBeenCalledWith(expect.objectContaining({ kind: "WEEKLY" }));
  });

  it("shows pending banner when status OPEN", () => {
    renderWithRoute(<WeeklyReviewPage />, "/weekly");
    expect(screen.getByTestId("weekly-pending-banner")).toBeInTheDocument();
  });

  it("no FAIL or WARN in DOM", () => {
    renderWithRoute(<WeeklyReviewPage />, "/weekly");
    expect(document.body.textContent).not.toMatch(/\bFAIL\b/);
    expect(document.body.textContent).not.toMatch(/\bWARN\b/);
  });
});
