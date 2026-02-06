import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { NotificationsPage } from "./NotificationsPage";
import { DataModeProvider } from "@/context/DataModeContext";
import { ScenarioProvider } from "@/context/ScenarioContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { BrowserRouter } from "react-router-dom";
import { loadPendingSystemNotifications } from "@/lib/notifications";

// LIVE test needs API to reject; other tests use MOCK (scenario.bundle), so no fetch.
vi.mock("@/data/source", () => ({
  getAlerts: () => Promise.reject(new Error("network")),
  getDailyOverview: () => Promise.reject(new Error("network")),
  getPositions: () => Promise.resolve([]),
  getTradePlan: () => Promise.resolve(null),
  getDecisionHistory: () => Promise.resolve([]),
}));

describe("NotificationsPage", () => {
  it("renders without throwing", () => {
    expect(() => render(<NotificationsPage />)).not.toThrow();
  });

  it("shows Notifications heading or empty state", () => {
    render(<NotificationsPage />);
    const heading = screen.queryByRole("heading", { name: /notifications/i });
    const empty = screen.queryByText(/no notifications/i);
    expect(heading != null || empty != null).toBe(true);
  });

  it("shows filter buttons", () => {
    render(<NotificationsPage />);
    expect(screen.getByRole("button", { name: /^ALL$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^NIGHTLY$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ELIGIBLE$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^WARN$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^DATA$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^ERRORS$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^INFO$/i })).toBeInTheDocument();
  });

  it("shows search input", () => {
    render(<NotificationsPage />);
    const search = screen.getByRole("searchbox", { name: /search notifications/i });
    expect(search).toBeInTheDocument();
  });

  it("LIVE + API error shows LIVE data unavailable and creates system notification", async () => {
    const LiveWrapper = ({ children }: { children: React.ReactNode }) => (
      <ThemeProvider>
        <DataModeProvider initialMode="LIVE">
          <ScenarioProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</BrowserRouter>
          </ScenarioProvider>
        </DataModeProvider>
      </ThemeProvider>
    );
    render(<NotificationsPage />, { wrapper: LiveWrapper });
    const msg = await screen.findByText(/LIVE data unavailable/i);
    expect(msg).toBeInTheDocument();
    const pending = loadPendingSystemNotifications();
    const fetchFailed = pending.find((n) => n.title === "LIVE fetch failed");
    expect(fetchFailed).toBeDefined();
  });
});
