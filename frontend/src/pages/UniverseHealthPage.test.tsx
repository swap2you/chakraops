/**
 * R25.6: Universe Health page — render with mocked data; no FAIL/WARN in document.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { UniverseHealthPage } from "./UniverseHealthPage";

const mockHealth = {
  total_symbols: 25,
  base_count: 24,
  recently_added: ["NVDA"],
  recently_removed: [],
  warnings_count: 0,
  earnings_upcoming: null,
};

vi.mock("@/api/queries", () => ({
  useUniverseHealth: () => ({ data: mockHealth, isLoading: false, isError: false, error: null }),
}));

describe("UniverseHealthPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders health summary with mocked data", () => {
    render(<UniverseHealthPage />);
    expect(screen.getByRole("heading", { name: /Universe Health/i })).toBeInTheDocument();
    expect(screen.getByText(/Total symbols/i)).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText(/Recently added/i)).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  it("document text does not contain FAIL or WARN", () => {
    const { container } = render(<UniverseHealthPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });
});
