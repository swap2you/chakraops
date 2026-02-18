import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@/test/test-utils";
import { AfterHoursBanner } from "./AfterHoursBanner";

const mockMutate = vi.fn();
const mockUseUiSystemHealth = vi.fn(() => ({ data: { market: { phase: "OPEN" } } }));
vi.mock("@/api/queries", () => ({
  useUiSystemHealth: (...args: unknown[]) => mockUseUiSystemHealth(...args),
  useRunFreezeSnapshot: () => ({
    mutate: mockMutate,
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

describe("AfterHoursBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when market OPEN", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: { market: { phase: "OPEN" } } });
    render(<AfterHoursBanner />);
    expect(screen.queryByText(/Evaluation\/recompute disabled/)).not.toBeInTheDocument();
  });

  it("renders when market POST", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: { market: { phase: "POST" } } });
    render(<AfterHoursBanner />);
    expect(screen.getByText(/Evaluation\/recompute disabled/)).toBeInTheDocument();
    expect(screen.getByText(/market POST/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Archive Now/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /System Status/i })).toHaveAttribute("href", "/system");
  });

  it("renders when market CLOSED", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: { market: { phase: "CLOSED" } } });
    render(<AfterHoursBanner />);
    expect(screen.getByText(/Evaluation\/recompute disabled/)).toBeInTheDocument();
    expect(screen.getByText(/market CLOSED/)).toBeInTheDocument();
  });

  it("Archive Now calls useRunFreezeSnapshot with skip_eval=true", () => {
    mockUseUiSystemHealth.mockReturnValue({ data: { market: { phase: "POST" } } });
    render(<AfterHoursBanner />);
    fireEvent.click(screen.getByRole("button", { name: /Archive Now/i }));
    expect(mockMutate).toHaveBeenCalledWith(true);
  });
});
