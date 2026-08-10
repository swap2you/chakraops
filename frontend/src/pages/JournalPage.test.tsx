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
    link_target: { kind: "shares", id: "SPY:pos-abc" } as { kind: string; id: string },
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
    link_target: null as { kind: string; id: string } | null,
    has_readiness_pack: false,
  },
];

const mockDownloadJournalReadinessPack = vi.fn();
const mockDownloadJournalReadinessPacksJsonl = vi.fn();

const mockReadinessPackBundle = {
  readiness: {
    status: "OK",
    status_label: "All checks OK",
    as_of_utc: "2026-02-20T12:00:00Z",
    checks: [
      { code: "INTEGRITY", status: "OK", label: "OK", detail: "Last check: 2026-02-20", action_href: "/positions?source=db&symbol=SPY" },
      { code: "MARK_FRESHNESS", status: "OK", label: "OK", detail: "", action_href: "/system" },
    ],
    order_stub: { title: "Order stub: SPY CSP OPEN", lines: ["Symbol: SPY", "Strategy: CSP", "Action: OPEN", "Qty: 2"] },
  },
};

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
  downloadJournalReadinessPacksJsonl: (...args: unknown[]) => mockDownloadJournalReadinessPacksJsonl(...args),
  useJournalEntryReadinessPack: () => ({ data: mockReadinessPackBundle, isLoading: false, isError: false }),
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

  it("R45: states Journal is the canonical fill record", () => {
    render(<JournalPage />);
    expect(screen.getByTestId("journal-canonical-banner")).toHaveTextContent(/canonical fill record/i);
    expect(screen.getAllByText(/canonical fill record/i).length).toBeGreaterThanOrEqual(1);
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

  it("R30.4: when has_readiness_pack=true, View readiness pack button appears", () => {
    render(<JournalPage />);
    const viewBtn = screen.getByTestId("journal-view-readiness-pack");
    expect(viewBtn).toBeInTheDocument();
    expect(viewBtn).toHaveTextContent("View readiness pack");
  });

  it("R30.4: clicking View readiness pack opens modal with summary, checks, order stub", async () => {
    const user = (await import("@testing-library/user-event")).default;
    render(<JournalPage />);
    await user.click(screen.getByTestId("journal-view-readiness-pack"));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("Readiness pack")).toBeInTheDocument();
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Checks")).toBeInTheDocument();
    expect(screen.getByText("Order stub")).toBeInTheDocument();
    expect(screen.getByText(/OK — All checks OK/)).toBeInTheDocument();
    expect(screen.getByText("INTEGRITY")).toBeInTheDocument();
    expect(dialog.textContent).toContain("Symbol: SPY");
  });

  it("R30.4: when has_readiness_pack=false, row has no View readiness pack button (only one row has pack)", () => {
    render(<JournalPage />);
    const viewButtons = screen.getAllByTestId("journal-view-readiness-pack");
    expect(viewButtons.length).toBe(1);
  });

  it("R30.4: document has no forbidden tokens (FAIL/WARN/PASS or FAIL_/WARN_)", () => {
    render(<JournalPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_|WARN_/);
  });

  it("R30.4: Fix links render when action_href present and are internal", async () => {
    const user = (await import("@testing-library/user-event")).default;
    render(<JournalPage />);
    await user.click(screen.getByTestId("journal-view-readiness-pack"));
    const fixLinks = screen.getAllByRole("link", { name: "Fix" });
    expect(fixLinks.length).toBeGreaterThanOrEqual(1);
    expect(fixLinks[0]).toHaveAttribute("href", "/positions?source=db&symbol=SPY");
  });

  it("R30.5: Has readiness pack filter toggle is present and default On", () => {
    render(<JournalPage />);
    expect(screen.getByTestId("journal-filter-has-pack")).toBeInTheDocument();
    expect(screen.getByText(/Has readiness pack/)).toBeInTheDocument();
    const checkbox = screen.getByRole("checkbox", { name: /Has readiness pack/ });
    expect(checkbox).toBeChecked();
  });

  it("R30.5: when filter On, only entries with pack are shown; when Off, all entries shown", async () => {
    const user = (await import("@testing-library/user-event")).default;
    render(<JournalPage />);
    expect(screen.getAllByTestId("journal-view-readiness-pack")).toHaveLength(1);
    const checkbox = screen.getByRole("checkbox", { name: /Has readiness pack/ });
    await user.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(screen.getByText("SELL")).toBeInTheDocument();
    expect(screen.getAllByTestId("journal-view-readiness-pack")).toHaveLength(1);
  });

  it("R30.5: Download readiness packs (JSONL) button calls download with correct params", async () => {
    const user = (await import("@testing-library/user-event")).default;
    render(<JournalPage />);
    const btn = screen.getByTestId("journal-download-readiness-packs");
    expect(btn).toHaveTextContent("Download readiness packs (JSONL)");
    await user.click(btn);
    expect(mockDownloadJournalReadinessPacksJsonl).toHaveBeenCalledTimes(1);
    const call = mockDownloadJournalReadinessPacksJsonl.mock.calls[0][0];
    expect(call.has_pack).toBe(true);
    expect(call.from_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(call.to_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(call.limit).toBe(200);
  });

  it("R30.5: document has no forbidden tokens", () => {
    render(<JournalPage />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_|WARN_/);
  });
});
