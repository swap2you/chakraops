/**
 * R34.0 (H-5 cutover): the live action-needed hook surfaces the canonical
 * authoritative recommendation block and carries the active profile.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as client from "./client";
import { useActionNeeded } from "./queries";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const payload = {
  top_options: [],
  top_shares: [],
  recently_changed: [],
  decision_source: "canonical_decision_engine",
  active_profile: "balanced",
  manual_only: true,
  legacy_lists_role: "diagnostic_non_authoritative",
  authoritative_recommendations: {
    decision_source: "canonical_decision_engine",
    manual_only: true,
    actionable: [
      {
        symbol: "AAPL",
        strategy: "CSP",
        next_action_code: "ENTRY",
        decision_status: "ACTIONABLE",
        manual_only: true,
        authoritative: true,
        recommended_by: "canonical_decision_engine",
      },
    ],
    watch: [],
    blocked: [],
  },
  capital_safety: {
    per_suggestion_not_additive: true,
    note_code: "PER_SUGGESTION_SIZED_INDEPENDENTLY_NOT_JOINTLY_EXECUTABLE",
    total_capital_required_displayed: 10000,
    available_cash: 50000,
    cash_buffer_pct: 20,
    cash_buffer_amount: 10000,
    deployable_capital: 40000,
    exceeds_deployable_capital: false,
    flags: [],
    assumes_leverage_or_margin: false,
  },
};

describe("useActionNeeded (canonical cutover)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("declares the canonical decision source and authoritative block", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(payload);
    const { result } = renderHook(() => useActionNeeded(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith("/api/ui/action-needed");
    expect(result.current.data?.decision_source).toBe("canonical_decision_engine");
    expect(result.current.data?.legacy_lists_role).toBe("diagnostic_non_authoritative");
    expect(
      result.current.data?.authoritative_recommendations?.actionable[0]?.recommended_by,
    ).toBe("canonical_decision_engine");
    expect(result.current.data?.capital_safety?.per_suggestion_not_additive).toBe(true);
  });

  it("carries the active profile via query string", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(payload);
    const { result } = renderHook(() => useActionNeeded("aggressive"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith("/api/ui/action-needed?profile=aggressive");
  });
});
