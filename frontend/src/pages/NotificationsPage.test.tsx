import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { NotificationsPage } from "./NotificationsPage";

const mockNotifications = {
  notifications: [
    {
      timestamp_utc: "2026-01-01T12:00:00Z",
      severity: "WARN",
      type: "ORATS_WARN",
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
});
