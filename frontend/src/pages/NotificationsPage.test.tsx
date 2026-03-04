import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { useNotifications } from "@/api/queries";
import { NotificationsPage } from "./NotificationsPage";

const mockNotifications = {
  notifications: [
    {
      id: "n-abc123",
      timestamp_utc: "2026-01-01T12:00:00Z",
      severity: "WARN",
      type: "ORATS_WARN",
      subtype: "ORATS_STALE",
      symbol: null,
      message: "ORATS status WARN; data may be stale",
      details: {},
      state: "NEW" as const,
      updated_at: "2026-01-01T12:00:00Z",
    },
  ],
};

const mockAck = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
const mockArchive = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
const mockDelete = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
const mockArchiveAll = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

const { mockAckBulk, mockArchiveBulk } = vi.hoisted(() => ({
  mockAckBulk: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
  mockArchiveBulk: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
}));

vi.mock("@/api/queries", () => ({
  useNotifications: vi.fn(() => ({
    data: mockNotifications,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })),
  useAckNotification: () => mockAck,
  useArchiveNotification: () => mockArchive,
  useDeleteNotification: () => mockDelete,
  useArchiveAllNotifications: () => mockArchiveAll,
  useAckBulkNotifications: () => mockAckBulk,
  useArchiveBulkNotifications: () => mockArchiveBulk,
}));

describe("NotificationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders without throwing", () => {
    expect(() => render(<NotificationsPage />)).not.toThrow();
  });

  it("shows Notifications page content", () => {
    render(<NotificationsPage />);
    expect(screen.getAllByText(/Notifications/i).length).toBeGreaterThan(0);
  });

  it("shows filter input", () => {
    render(<NotificationsPage />);
    expect(screen.getByPlaceholderText(/Filter by type/i)).toBeInTheDocument();
  });

  it("shows notification row", () => {
    render(<NotificationsPage />);
    expect(screen.getByText(/ORATS_WARN/i)).toBeInTheDocument();
    expect(screen.getByText(/ORATS status Degraded/i)).toBeInTheDocument();
  });

  it("shows subtype in table and filter includes subtype", () => {
    render(<NotificationsPage />);
    expect(screen.getByText(/ORATS_STALE/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Filter by type, subtype/i)).toBeInTheDocument();
  });

  it("shows NEW / ACKED / ARCHIVED / ALL tabs (Phase 21.5)", () => {
    render(<NotificationsPage />);
    expect(screen.getByRole("button", { name: /^NEW$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ACKED$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ARCHIVED$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ALL$/i })).toBeInTheDocument();
  });

  it("shows Archive all button when on NEW tab (Phase 21.5)", () => {
    render(<NotificationsPage />);
    expect(screen.getByRole("button", { name: /Archive all/i })).toBeInTheDocument();
  });

  it("shows per-row Ack, Archive, Delete actions (Phase 21.5)", () => {
    render(<NotificationsPage />);
    const ackButtons = screen.getAllByRole("button", { name: /Ack/i });
    const archiveButtons = screen.getAllByRole("button", { name: /Archive/i });
    const deleteButtons = screen.getAllByRole("button", { name: /Delete/i });
    expect(ackButtons.length).toBeGreaterThan(0);
    expect(archiveButtons.length).toBeGreaterThan(0);
    expect(deleteButtons.length).toBeGreaterThan(0);
  });

  it("shows Ack button in detail when notification state NEW (Phase 10.3)", () => {
    render(<NotificationsPage />);
    fireEvent.click(screen.getByText(/ORATS status Degraded/i));
    const ackButtons = screen.getAllByRole("button", { name: /^Ack$/i });
    expect(ackButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("R25.4: does not display raw FAIL or WARN in document (safe labels only)", () => {
    const { container } = render(<NotificationsPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });

  it("R27.7: renders CC_ELIGIBLE with safe label and Open CC ticket link", () => {
    vi.mocked(useNotifications).mockReturnValueOnce({
      data: {
        notifications: [
          {
            id: "n-cc1",
            timestamp_utc: "2026-02-01T12:00:00Z",
            severity: "INFO",
            type: "CC_ELIGIBLE",
            subtype: "CC_ELIGIBLE",
            symbol: "SPY",
            message: "Shares eligible for covered call: SPY. Consider opening CC ticket.",
            details: { symbol: "SPY" },
            state: "NEW" as const,
            updated_at: "2026-02-01T12:00:00Z",
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(<NotificationsPage />);
    expect(screen.getByText("Covered call eligible")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Covered call eligible"));
    expect(screen.getByRole("link", { name: /open cc ticket for spy/i })).toBeInTheDocument();
  });
});
