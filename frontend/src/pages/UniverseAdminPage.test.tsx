/**
 * R25.6: Universe Admin page — render with mocked data; no FAIL/WARN in document.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/test-utils";
import { UniverseAdminPage } from "./UniverseAdminPage";

const mockAdmin = {
  symbols: ["AAPL", "MSFT", "GOOGL"],
  base_count: 2,
  overlay_added_count: 1,
  overlay_removed_count: 0,
  history: [
    { id: "h1", ts: "2026-02-20T12:00:00Z", action: "PROPOSE_ADD", symbol: "GOOGL", status: "OPEN" },
  ],
};

vi.mock("@/api/queries", () => ({
  useUniverseAdmin: () => ({ data: mockAdmin, isLoading: false, isError: false, error: null }),
  useUniverseProposeAdd: () => ({ mutate: vi.fn(), isPending: false }),
  useUniverseProposeRemove: () => ({ mutate: vi.fn(), isPending: false }),
  useUniverseApply: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("UniverseAdminPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders admin list and history with mocked data", () => {
    render(<UniverseAdminPage />);
    expect(screen.getByRole("heading", { name: /Universe Admin/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Propose Add/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Propose Remove/i })).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getAllByText("GOOGL").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("PROPOSE_ADD")).toBeInTheDocument();
  });

  it("document text does not contain FAIL or WARN", () => {
    const { container } = render(<UniverseAdminPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bFAIL\b/);
    expect(text).not.toMatch(/\bWARN\b/);
  });
});
