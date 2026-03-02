import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { render, screen, renderWithRoute } from "@/test/test-utils";
import { TodayPage } from "./TodayPage";

const mockSummary = {
  latest_run_ts: "2026-02-27T17:00:00Z",
  as_of_et: "2026-02-27 12:00 ET",
  cadence: { mode: "EOD_BIASED", eligibility_as_of: "2026-02-27T17:00:00Z" },
  orats_status: "OK",
  orats_freshness_state_label: "OK",
  guardrails: { status: "OK" },
  notifications_health: { count_new: 1, count_acked: 0, count_archived: 0 },
  notifications_new_count: 1,
  earnings_probe: { status: "OK" },
  action_needed_count: null,
};

const mockActionNeeded = {
  top_options: [
    { symbol: "SPY", strategy: "CSP", next_action_code: "ENTRY", sizing_constraints_hit: [], recommended_contracts: 2 },
  ],
  top_shares: [],
  recently_changed: [],
};

const mockRunEval = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));
const mockAck = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));
const mockArchive = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));
const mockAckBulk = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));
const mockArchiveBulk = vi.fn(() => ({ mutate: vi.fn(), isPending: false }));

vi.mock("@/api/queries", () => ({
  useTodaySummary: vi.fn(() => ({ data: mockSummary, isLoading: false, refetch: vi.fn() })),
  useActionNeeded: vi.fn(() => ({ data: mockActionNeeded, refetch: vi.fn() })),
  useRunEval: () => mockRunEval(),
  useJournal: vi.fn(() => ({ data: { entries: [] } })),
  useNotifications: vi.fn(() => ({ data: { notifications: [{ id: "n1", state: "NEW", symbol: "SPY", type: "LIFECYCLE" }] }, refetch: vi.fn() })),
  useAckNotification: () => mockAck(),
  useArchiveNotification: () => mockArchive(),
  useAckBulkNotifications: () => mockAckBulk(),
  useArchiveBulkNotifications: () => mockArchiveBulk(),
}));

describe("TodayPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("renders all sections with mocked data", () => {
    renderWithRoute(<TodayPage />, "/today");
    expect(screen.getByTestId("today-run-section")).toBeInTheDocument();
    expect(screen.getByTestId("today-action-needed-card")).toBeInTheDocument();
    expect(screen.getByTestId("today-queue-card")).toBeInTheDocument();
    expect(screen.getByTestId("today-journal-card")).toBeInTheDocument();
    expect(screen.getByTestId("today-notifications-card")).toBeInTheDocument();
  });

  it("Run evaluation button exists and triggers mutation when clicked", async () => {
    const mutate = vi.fn();
    mockRunEval.mockReturnValue({ mutate, isPending: false });
    renderWithRoute(<TodayPage />, "/today");
    const btn = screen.getByTestId("today-run-eval-btn");
    await userEvent.click(btn);
    expect(mutate).toHaveBeenCalled();
  });

  it("Action Needed shows row and Add to queue adds to queue", async () => {
    renderWithRoute(<TodayPage />, "/today");
    expect(screen.getByTestId("today-action-row-SPY")).toBeInTheDocument();
    const addBtn = screen.getByTestId("today-add-queue-SPY");
    await userEvent.click(addBtn);
    expect(screen.getByTestId("today-queue-item-SPY")).toBeInTheDocument();
  });

  it("Queue remove and Mark Done work", async () => {
    renderWithRoute(<TodayPage />, "/today");
    await userEvent.click(screen.getByTestId("today-add-queue-SPY"));
    expect(screen.getByTestId("today-queue-item-SPY")).toBeInTheDocument();
    const removeBtn = screen.getByRole("button", { name: /Remove/i });
    await userEvent.click(removeBtn);
    expect(screen.queryByTestId("today-queue-item-SPY")).not.toBeInTheDocument();
  });

  it("Notifications Ack all NEW and Archive all ACKED buttons exist", () => {
    renderWithRoute(<TodayPage />, "/today");
    expect(screen.getByTestId("today-ack-all-new")).toBeInTheDocument();
    expect(screen.getByTestId("today-archive-all-acked")).toBeInTheDocument();
  });

  it("no FAIL or WARN in DOM", () => {
    renderWithRoute(<TodayPage />, "/today");
    expect(document.body.textContent).not.toMatch(/\bFAIL\b/);
    expect(document.body.textContent).not.toMatch(/\bWARN\b/);
  });

  it("Add manual entry link goes to journal", () => {
    renderWithRoute(<TodayPage />, "/today");
    const link = screen.getByTestId("today-journal-add");
    expect(link).toHaveAttribute("href", "/journal");
  });
});
