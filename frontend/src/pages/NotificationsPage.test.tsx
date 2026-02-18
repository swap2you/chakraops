import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
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
    },
  ],
};

vi.mock("@/api/queries", () => ({
  useNotifications: () => ({
    data: mockNotifications,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useAckNotification: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  }),
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
    expect(screen.getByText(/ORATS status WARN/i)).toBeInTheDocument();
  });

  it("shows subtype in table and filter includes subtype", () => {
    render(<NotificationsPage />);
    expect(screen.getByText(/ORATS_STALE/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Filter by type, subtype/i)).toBeInTheDocument();
  });

  it("shows Unacknowledged only toggle (Phase 10.3)", () => {
    render(<NotificationsPage />);
    expect(screen.getByLabelText(/Unacknowledged only/i)).toBeInTheDocument();
  });

  it("shows Ack button in detail when notification not acked (Phase 10.3)", () => {
    render(<NotificationsPage />);
    fireEvent.click(screen.getByText(/ORATS status WARN/i));
    expect(screen.getByRole("button", { name: /Ack/i })).toBeInTheDocument();
  });
});
