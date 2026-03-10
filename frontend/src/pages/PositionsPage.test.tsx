/**
 * R27.9/R28.0/R28.9/R29.0: Positions page — default Stored (source=db), staleness banner, no FAIL/WARN/PASS.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, renderWithRoute, screen, within } from "@/test/test-utils";
import { PositionsPage } from "./PositionsPage";

const mockPositions = [
  {
    id: "live_shares_1",
    symbol: "AAPL",
    instrument_type: "SHARES",
    is_paper: 0,
    qty: 100,
    avg_price: 150.5,
    strike: null,
    expiry: null,
    right: null,
    opened_ts: "2026-02-20T12:00:00",
    link_id: "1",
    notes: null,
    tags: null,
  },
  {
    id: "paper_2",
    symbol: "SPY",
    instrument_type: "CSP",
    is_paper: 1,
    qty: 2,
    avg_price: 3.5,
    strike: 450,
    expiry: "2026-03-21",
    right: "PUT",
    opened_ts: "2026-02-15T10:00:00",
    link_id: "2",
    notes: null,
    tags: null,
    mark_value: 4.25,
    unrealized_pl: 150,
  },
];

const mockUseUnifiedPositions = vi.fn(() => ({
  data: { positions: mockPositions, state: "open", include_paper: true },
  isLoading: false,
  isError: false,
}));

const mockUseUnifiedPositionsFromDb = vi.fn(() => ({
  data: { items: mockPositions, count: mockPositions.length, status: "OK", status_label: "OK" },
  isLoading: false,
  isError: false,
}));

/** R29.0: Not stale when finished_at_utc is recent (future). */
const healthNotStale = {
  positions_unified_rebuild: { finished_at_utc: "2099-06-01T12:00:00Z", last_include_paper: true },
  positions_unified_reconcile: { status: "OK" as const },
};
/** R29.4: Integrity check block with last run + sample items for View details. */
const healthWithIntegrityDetails = {
  ...healthNotStale,
  positions_unified_integrity_check: {
    last_checked_at_utc: "2026-02-27T15:00:00Z",
    last_status: "OK" as const,
    last_status_label: "OK",
    last_reconcile_missing_count: 0,
    last_reconcile_extra_count: 0,
    last_reconcile_mismatched_count: 0,
    last_sample_items: [{ kind: "missing", id: "p1", symbol: "AAPL", instrument_type: "SHARES" }],
  },
};
/** R29.0: Stale when block missing or finished_at_utc old/missing. */
const healthStale = { positions_unified_rebuild: undefined, positions_unified_reconcile: { status: "OK" as const } };
/** R29.1: Reconcile status Review for Integrity strip diff tests. */
const healthReconcileReview = {
  ...healthNotStale,
  positions_unified_reconcile: { status: "Review" as const },
};

const mockReconcileDiffPayload = {
  missing_count: 1,
  extra_count: 0,
  mismatched_count: 1,
  items: [
    { id: "diff-1", kind: "missing" as const, symbol: "AAPL", instrument_type: "SHARES", fields_diff: ["qty"] },
  ],
};
const mockUseReconcileDiff = vi.fn(() => ({
  data: mockReconcileDiffPayload,
  isLoading: false,
}));

const mockUseUiSystemHealth = vi.fn(() => ({ data: healthNotStale }));
const mockMutate = vi.fn();
const mockMutateIntegrity = vi.fn();
const mockUsePositionsUnifiedRebuild = vi.fn(() => ({
  mutate: mockMutate,
  isPending: false,
  data: undefined,
}));
const mockUsePositionsUnifiedIntegrityCheck = vi.fn(() => ({
  mutate: mockMutateIntegrity,
  isPending: false,
  data: undefined,
}));

vi.mock("@/api/queries", () => ({
  useUnifiedPositions: (params: Record<string, unknown>) => mockUseUnifiedPositions(params),
  useUnifiedPositionsFromDb: (params: Record<string, unknown>) => mockUseUnifiedPositionsFromDb(params),
  useUiSystemHealth: () => mockUseUiSystemHealth(),
  usePositionsUnifiedRebuild: () => mockUsePositionsUnifiedRebuild(),
  usePositionsUnifiedIntegrityCheck: () => mockUsePositionsUnifiedIntegrityCheck(),
  useReconcileDiff: (params: Record<string, unknown>) => mockUseReconcileDiff(params),
}));

describe("PositionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseUnifiedPositions.mockReturnValue({
      data: { positions: mockPositions, state: "open", include_paper: true },
      isLoading: false,
      isError: false,
    });
    mockUseUnifiedPositionsFromDb.mockReturnValue({
      data: { items: mockPositions, count: mockPositions.length, status: "OK", status_label: "OK" },
      isLoading: false,
      isError: false,
    });
    mockUseUiSystemHealth.mockReturnValue({ data: healthNotStale });
    mockUsePositionsUnifiedRebuild.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      data: undefined,
    });
    mockUsePositionsUnifiedIntegrityCheck.mockReturnValue({
      mutate: mockMutateIntegrity,
      isPending: false,
      data: undefined,
    });
    mockUseReconcileDiff.mockReturnValue({ data: mockReconcileDiffPayload, isLoading: false });
  });

  it("renders Positions header and filters", () => {
    render(<PositionsPage />);
    expect(screen.getByRole("heading", { name: /^Positions$/i })).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-state")).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-paper")).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-type")).toBeInTheDocument();
    expect(screen.getByTestId("positions-filter-symbol")).toBeInTheDocument();
  });

  it("renders positions table with Symbol, Source, Type, Qty, Opened, Mark, Ticket, Journal, Paper", () => {
    render(<PositionsPage />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Mark / Unrealized")).toBeInTheDocument();
    expect(screen.getAllByText("LIVE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("PAPER").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByTestId("positions-row").length).toBe(2);
    expect(screen.getAllByTestId("positions-link-ticket").length).toBe(2);
    expect(screen.getAllByTestId("positions-link-journal").length).toBe(2);
    expect(screen.getAllByTestId("positions-link-paper").length).toBeGreaterThanOrEqual(1);
  });

  it("shows Mark/Unrealized for paper row when API provides mark_value and unrealized_pl", () => {
    const { container } = render(<PositionsPage />);
    expect(container.textContent).toMatch(/4\.25/);
    expect(container.textContent).toMatch(/150/);
  });

  it("calls useUnifiedPositions with state and include_paper when source is recompute", () => {
    renderWithRoute(<PositionsPage />, "/positions?source=recompute");
    expect(mockUseUnifiedPositions).toHaveBeenCalledWith(
      expect.objectContaining({ state: "open", include_paper: true })
    );
  });

  it("document textContent has no FAIL or WARN (R27.9/R28.0)", () => {
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R28.9: when source=db shows Source: Stored and uses db endpoint", () => {
    renderWithRoute(<PositionsPage />, "/positions?source=db");
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Stored");
    expect(mockUseUnifiedPositionsFromDb).toHaveBeenCalled();
  });

  it("R29.0: default source is Stored when no query param", () => {
    render(<PositionsPage />);
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Stored");
    expect(mockUseUnifiedPositionsFromDb).toHaveBeenCalled();
  });

  it("R29.0: when source=recompute shows Source: Computed", () => {
    renderWithRoute(<PositionsPage />, "/positions?source=recompute");
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Computed");
  });

  it("filter state change triggers new request", async () => {
    renderWithRoute(<PositionsPage />, "/positions?source=recompute");
    const stateSelect = screen.getByTestId("positions-filter-state");
    await userEvent.selectOptions(stateSelect, "closed");
    expect(mockUseUnifiedPositions).toHaveBeenLastCalledWith(
      expect.objectContaining({ state: "closed" })
    );
  });

  it("R29.0: when stored and stale, banner renders and rebuild button triggers mutation with include_paper", async () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthStale });
    render(<PositionsPage />);
    expect(screen.getByTestId("positions-stale-banner-title")).toHaveTextContent(/Stored positions may be stale/);
    expect(screen.getByTestId("positions-stale-rebuild-btn")).toHaveTextContent("Rebuild unified positions");
    await userEvent.click(screen.getByTestId("positions-stale-rebuild-btn"));
    expect(screen.getByTestId("positions-rebuild-confirm-modal")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("positions-rebuild-confirm-ok"));
    expect(mockMutate).toHaveBeenCalledWith(
      { include_paper: true },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it("R29.0: when rebuild running, button disabled and shows Rebuild running", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthStale });
    mockUsePositionsUnifiedRebuild.mockReturnValue({
      mutate: mockMutate,
      isPending: true,
      data: undefined,
    });
    render(<PositionsPage />);
    const btn = screen.getByTestId("positions-stale-rebuild-btn");
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent("Rebuild running");
  });

  it("R29.0: document has no FAIL/WARN/PASS tokens", () => {
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
  });

  it("R29.1: when source=db and reconcile status Review, integrity strip shows Review and diff counts; View diff details expands list", async () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthReconcileReview });
    mockUseReconcileDiff.mockReturnValue({ data: mockReconcileDiffPayload, isLoading: false });
    render(<PositionsPage />);
    expect(screen.getByTestId("positions-integrity-strip")).toBeInTheDocument();
    expect(screen.getByTestId("positions-integrity-status")).toHaveTextContent("Review");
    expect(screen.getByTestId("positions-integrity-diff-counts")).toHaveTextContent(/missing: 1.*extra: 0.*mismatched: 1/);
    expect(screen.getByTestId("positions-integrity-view-diff-details")).toHaveTextContent("View diff details");
    await userEvent.click(screen.getByTestId("positions-integrity-view-diff-details"));
    const diffList = screen.getByTestId("positions-integrity-diff-list");
    expect(diffList).toBeInTheDocument();
    expect(within(diffList).getByText("missing")).toBeInTheDocument();
    expect(within(diffList).getByText("AAPL")).toBeInTheDocument();
    expect(screen.getAllByTestId("positions-integrity-view-positions-link").length).toBeGreaterThanOrEqual(1);
  });

  it("R29.1: clicking Rebuild unified positions (Integrity) triggers mutation with include_paper from filter", async () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthReconcileReview });
    render(<PositionsPage />);
    await userEvent.click(screen.getByTestId("positions-integrity-rebuild-btn"));
    expect(screen.getByTestId("positions-rebuild-confirm-modal")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("positions-rebuild-confirm-ok"));
    expect(mockMutate).toHaveBeenCalledWith(
      { include_paper: true },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it("R29.1: clicking Switch to Computed updates to Source: Computed and does not render diff details section", async () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthReconcileReview });
    render(<PositionsPage />);
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Stored");
    await userEvent.click(screen.getByTestId("positions-integrity-switch-to-computed"));
    expect(screen.getByTestId("positions-source-label")).toHaveTextContent("Source: Computed");
    expect(screen.getByTestId("positions-integrity-computed-note")).toHaveTextContent(/Computed \(authoritative\)/);
    expect(screen.queryByTestId("positions-integrity-diff-counts")).not.toBeInTheDocument();
  });

  it("R29.1: document has no FAIL/WARN/PASS tokens", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthReconcileReview });
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
  });

  it("R29.2: when symbol set, Compare button appears; opening Compare shows diff summary and both lists", async () => {
    renderWithRoute(<PositionsPage />, "/positions?symbol=AAPL");
    expect(screen.getByTestId("positions-compare-panel")).toBeInTheDocument();
    expect(screen.getByTestId("positions-compare-toggle-btn")).toHaveTextContent("Compare stored vs computed");
    expect(screen.queryByTestId("positions-compare-diff-summary")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("positions-compare-toggle-btn"));
    expect(mockUseUnifiedPositions).toHaveBeenCalledWith(expect.objectContaining({ symbol: "AAPL", include_paper: true }));
    expect(mockUseUnifiedPositionsFromDb).toHaveBeenCalledWith(expect.objectContaining({ symbol: "AAPL", include_paper: true }));
    expect(screen.getByTestId("positions-compare-diff-summary")).toBeInTheDocument();
    expect(screen.getByTestId("positions-compare-diff-details")).toBeInTheDocument();
    expect(screen.getByTestId("positions-compare-view-diff-diagnostics")).toBeInTheDocument();
  });

  it("R29.2: when Compare closed, diff summary not visible", () => {
    renderWithRoute(<PositionsPage />, "/positions?symbol=AAPL");
    expect(screen.getByTestId("positions-compare-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("positions-compare-diff-summary")).not.toBeInTheDocument();
  });

  it("R29.2: document has no FAIL/WARN/PASS and no FAIL_/WARN_ tokens", () => {
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R29.3: clicking Run integrity check opens confirm modal; confirm calls mutation with include_paper true", async () => {
    renderWithRoute(<PositionsPage />, "/positions?source=db");
    await userEvent.click(screen.getByTestId("positions-integrity-check-btn"));
    expect(screen.getByTestId("positions-integrity-check-confirm-modal")).toBeInTheDocument();
    expect(screen.getByText(/This will run an integrity check comparing stored positions with authoritative sources and staleness\. Manual action\. Continue\?/)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("positions-integrity-check-confirm-ok"));
    expect(mockMutateIntegrity).toHaveBeenCalledWith(
      { include_paper: true },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it("R29.3: document contains no forbidden tokens FAIL/WARN/PASS or FAIL_/WARN_", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthReconcileReview });
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });

  it("R29.3: Run integrity check button disabled and shows Check running when mutation pending", () => {
    mockUsePositionsUnifiedIntegrityCheck.mockReturnValue({
      mutate: mockMutateIntegrity,
      isPending: true,
      data: undefined,
    });
    renderWithRoute(<PositionsPage />, "/positions?source=db");
    const btn = screen.getByTestId("positions-integrity-check-btn");
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent("Check running");
  });

  it("R29.4: Last integrity check summary and View details expand sample items", async () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthWithIntegrityDetails });
    renderWithRoute(<PositionsPage />, "/positions?source=db");
    expect(screen.getByTestId("positions-integrity-last-check")).toHaveTextContent(/Last integrity check/);
    expect(screen.getByTestId("positions-integrity-view-details-btn")).toHaveTextContent("View details");
    await userEvent.click(screen.getByTestId("positions-integrity-view-details-btn"));
    const detailsList = screen.getByTestId("positions-integrity-details-list");
    expect(detailsList).toBeInTheDocument();
    expect(within(detailsList).getByText("missing")).toBeInTheDocument();
    expect(within(detailsList).getByText("AAPL")).toBeInTheDocument();
  });

  it("R29.4: document contains no forbidden tokens FAIL/WARN/PASS or FAIL_/WARN_", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: healthWithIntegrityDetails });
    const { container } = render(<PositionsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(FAIL|WARN|PASS)\b/);
    expect(text).not.toMatch(/FAIL_/);
    expect(text).not.toMatch(/WARN_/);
  });
});
