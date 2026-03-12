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
    link_target: null as { kind: string; id: string } | null,
    has_readiness_pack: true,
  },
  {
    id: "e2",
    created_ts: "2026-02-21T10:00:00Z",
    trade_date: "2026-02-21",
    symbol: "SPY",
    strategy: "SHARES",
    action: "SELL",
    qty: 100,
    price: 455.0,
    premium: null,
    fees: null,
    notes: "close",
    tags: "",
    realized_pl: 500,
    link_target: { kind: "shares", id: "SPY:pos-abc" } as { kind: string; id: string },
    has_readiness_pack: false,
  },
];

const mockDownloadJournalReadinessPack = vi.fn();

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
  downloadJournalReadinessPack: (...args: unknown[]) => mockDownloadJournalReadinessPack(...args),
}));

describe("JournalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders journal list using mocked hook", () => {
    render(<JournalPage />);
    expect(screen.getByRole("heading", { name: /Journal/i })).toBeInTheDocument();
    expect(screen.getAllByText("SPY").length).toBeGreaterThanOrEqual(1);
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

  it("shows Include paper toggle (R27.0)", () => {
    render(<JournalPage />);
    expect(screen.getByTestId("journal-include-paper")).toBeInTheDocument();
    expect(screen.getByText(/Include paper/)).toBeInTheDocument();
  });

  it("shows Paper only filter (R27.2)", () => {
    render(<JournalPage />);
    expect(screen.getByTestId("journal-paper-only")).toBeInTheDocument();
    expect(screen.getByText(/Paper only/)).toBeInTheDocument();
  });

  it("R27.4: Open link renders when entry has link_target", () => {
    render(<JournalPage />);
    const openLinks = screen.getAllByTestId("journal-open-link");
    expect(openLinks.length).toBe(1);
    expect(openLinks[0]).toHaveTextContent("Open");
    expect(openLinks[0]).toHaveAttribute("href", "/symbol-diagnostics?symbol=SPY");
  });

  it("R27.4: no FAIL or WARN in DOM", () => {
    const { container } = render(<JournalPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R30.3: when entry has has_readiness_pack, Download readiness pack button appears and click calls download", async () => {
    const user = (await import("@testing-library/user-event")).default;
    render(<JournalPage />);
    const packBtn = screen.getByTestId("journal-download-readiness-pack");
    expect(packBtn).toBeInTheDocument();
    expect(packBtn).toHaveTextContent("Download readiness pack");
    await user.click(packBtn);
    expect(mockDownloadJournalReadinessPack).toHaveBeenCalledWith("e1", "SPY");
  });

  it("R30.3: no forbidden tokens in document when Download readiness pack shown", () => {
    render(<JournalPage />);
    expect(screen.getByTestId("journal-download-readiness-pack")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_|WARN_/);
  });
});
