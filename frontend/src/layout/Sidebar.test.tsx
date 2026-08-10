import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { Sidebar } from "./Sidebar";

const mockGetWheelPageMode = vi.fn();
const mockIsWheelLinkVisible = vi.fn();
const mockGetShowAdvanced = vi.fn();
const mockSetShowAdvanced = vi.fn();

vi.mock("@/config/features", () => ({
  getWheelPageMode: () => mockGetWheelPageMode(),
  isWheelLinkVisible: () => mockIsWheelLinkVisible(),
  getShowAdvanced: () => mockGetShowAdvanced(),
  setShowAdvanced: (v: boolean) => mockSetShowAdvanced(v),
}));

describe("Sidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWheelPageMode.mockReturnValue("admin");
    mockIsWheelLinkVisible.mockReturnValue(true);
    mockGetShowAdvanced.mockReturnValue(false);
  });

  it("renders R39 nav groups and primary destinations", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: /^command center$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^opportunities$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Universe$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /symbol diagnostics/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /wheel/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Portfolio$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Paper$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Learn$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /strategy lab/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /notifications/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /system diagnostics/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Journal$/i })).toBeInTheDocument();
  });

  it("R22.3 admin mode: shows Wheel (Admin) label", () => {
    mockGetWheelPageMode.mockReturnValue("admin");
    mockIsWheelLinkVisible.mockReturnValue(true);
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: /wheel \(admin\)/i })).toBeInTheDocument();
  });

  it("R22.3 hidden mode: no Wheel link", () => {
    mockGetWheelPageMode.mockReturnValue("hidden");
    mockIsWheelLinkVisible.mockReturnValue(false);
    render(<Sidebar />);
    expect(screen.queryByRole("link", { name: /wheel/i })).not.toBeInTheDocument();
  });

  it("R22.3 advanced mode: shows Show advanced toggle", () => {
    mockGetWheelPageMode.mockReturnValue("advanced");
    mockIsWheelLinkVisible.mockReturnValue(false);
    render(<Sidebar />);
    expect(screen.getByLabelText(/show advanced/i)).toBeInTheDocument();
  });

  it("R22.3 advanced mode when showAdvanced true: shows Wheel link", () => {
    mockGetWheelPageMode.mockReturnValue("advanced");
    mockIsWheelLinkVisible.mockReturnValue(true);
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: /wheel/i })).toBeInTheDocument();
  });

  it("R39: renders Command Center IA groups", () => {
    render(<Sidebar />);
    expect(screen.getByTestId("nav-group-command-center")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-opportunities")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-portfolio")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-research")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-strategy-lab")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-operations")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-advanced-legacy")).toBeInTheDocument();
    expect(screen.getByTestId("nav-legacy-note")).toHaveTextContent(/non-primary/i);
    expect(screen.getByRole("link", { name: /^Positions$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /strategy lab/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /today checklist/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Journal$/i })).toBeInTheDocument();
  });
});
