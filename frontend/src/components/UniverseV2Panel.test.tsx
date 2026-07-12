// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R36.2 — UniverseV2Panel component tests.

import { render, screen } from "@/test/test-utils";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { UniverseV2Panel } from "./UniverseV2Panel";

const mockUseSummary = vi.fn();
const mockRefresh = vi.fn();
const mockRefreshState = { mutate: mockRefresh, isPending: false, isError: false };

vi.mock("@/api/queries", () => ({
  useUniverseV2Summary: () => mockUseSummary(),
  useUniverseV2Refresh: () => mockRefreshState,
}));

function completeSummary() {
  return {
    status: "COMPLETE",
    version: 12,
    created_at_utc: "2026-07-12T00:00:00+00:00",
    stale: false,
    research_pool_count: 167,
    lifecycle_funnel: { ADMITTED: 40, WATCH: 100, QUARANTINE: 20, REMOVED: 7 },
    strategy_eligible: { CORE_WHEEL: 15, BALANCED_WHEEL: 25, AGGRESSIVE_WHEEL: 35, SHARES: 50 },
    top_rejection_reasons: [
      { reason: "Price data is stale", count: 12 },
      { reason: "Under observation", count: 8 },
    ],
  };
}

describe("UniverseV2Panel", () => {
  beforeEach(() => {
    mockUseSummary.mockReset();
    mockRefresh.mockReset();
    mockRefreshState.isPending = false;
    mockRefreshState.isError = false;
  });

  it("renders lifecycle funnel and strategy counts", () => {
    mockUseSummary.mockReturnValue({ data: completeSummary(), isLoading: false, isError: false });
    render(<UniverseV2Panel />);
    const lifecycle = screen.getByTestId("universe-v2-lifecycle");
    expect(lifecycle).toHaveTextContent("ADMITTED: 40");
    expect(lifecycle).toHaveTextContent("QUARANTINE: 20");
    const strategies = screen.getByTestId("universe-v2-strategies");
    expect(strategies).toHaveTextContent("Core Wheel: 15");
    expect(strategies).toHaveTextContent("Shares: 50");
  });

  it("shows research pool count and freshness", () => {
    mockUseSummary.mockReturnValue({ data: completeSummary(), isLoading: false, isError: false });
    render(<UniverseV2Panel />);
    const fresh = screen.getByTestId("universe-v2-freshness");
    expect(fresh).toHaveTextContent("Research pool: 167");
    expect(fresh).toHaveTextContent("v12");
    expect(fresh).toHaveTextContent("Fresh");
  });

  it("renders top rejection reasons humanized (no raw codes)", () => {
    mockUseSummary.mockReturnValue({ data: completeSummary(), isLoading: false, isError: false });
    render(<UniverseV2Panel />);
    const reasons = screen.getByTestId("universe-v2-top-reasons");
    expect(reasons).toHaveTextContent("Price data is stale");
    expect(reasons.textContent ?? "").not.toMatch(/FAIL_|WARN_/);
  });

  it("shows a fail-closed empty state when no snapshot", () => {
    mockUseSummary.mockReturnValue({ data: { status: "NO_SNAPSHOT", version: 0 }, isLoading: false, isError: false });
    render(<UniverseV2Panel />);
    expect(screen.getByTestId("universe-v2-empty")).toBeInTheDocument();
  });

  it("triggers a rebuild on click", () => {
    mockUseSummary.mockReturnValue({ data: completeSummary(), isLoading: false, isError: false });
    render(<UniverseV2Panel />);
    screen.getByText("Rebuild snapshot").click();
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it("surfaces a rebuild failure without dropping the existing snapshot", () => {
    mockUseSummary.mockReturnValue({ data: completeSummary(), isLoading: false, isError: false });
    mockRefreshState.isError = true;
    render(<UniverseV2Panel />);
    expect(screen.getByTestId("universe-v2-refresh-error")).toBeInTheDocument();
    // The prior snapshot data is still rendered.
    expect(screen.getByTestId("universe-v2-freshness")).toHaveTextContent("v12");
  });
});
