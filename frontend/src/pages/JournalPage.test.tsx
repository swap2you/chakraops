/**
 * R25.5: Journal page — list, mocked API; no FAIL/WARN in document.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { JournalPage } from "./JournalPage";

const mockEntries = [
  {
    id: "e1",
    created_ts: "2026-02-20T12:00:00Z",
    trade_date: "2026-02-20",
    symbol: "SPY",
    strategy: "SHARES",
    action: "BUY",
    qty: 100,
    price: 450.0,
    premium: null,
    fees: null,
    notes: "test",
    tags: "tag1",
    realized_pl: null,
  },
];

vi.mock("@/api/queries", () => ({
  useJournal: () => ({
    data: { entries: mockEntries },
    isLoading: false,
    isError: false,
    error: null,
  }),
  useJournalCreate: () => ({ mutateAsync: vi.fn(), isPending: false, reset: vi.fn() }),
  useJournalUpdate: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useJournalExport: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("JournalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders journal list using mocked hook", () => {
    render(<JournalPage />);
    expect(screen.getByRole("heading", { name: /Journal/i })).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(screen.getAllByText(/SHARES/).length).toBeGreaterThanOrEqual(1);
  });

  it("document text does not contain FAIL or WARN (R25.5 safety)", () => {
    const { container } = render(<JournalPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("shows Export CSV and Add entry actions", () => {
    render(<JournalPage />);
    expect(screen.getByRole("button", { name: /Export CSV/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add entry/i })).toBeInTheDocument();
  });
});
