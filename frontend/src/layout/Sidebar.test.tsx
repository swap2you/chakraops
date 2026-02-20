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

  it("renders nav with Dashboard, Universe, Symbol, Wheel, Portfolio, Notifications, System", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /universe/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /symbol/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /wheel/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /account & portfolio/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /notifications/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /system/i })).toBeInTheDocument();
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
});
