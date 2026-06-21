/**
 * R33.0: decision-engine query hooks call the correct endpoints and surface the
 * advisory, manual-only contract (profiles + ranked evaluate output).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as client from "./client";
import { useDecisionProfiles, useEvaluateDecisions } from "./queries";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("decision-engine query hooks", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("useDecisionProfiles GETs the profiles endpoint", async () => {
    const payload = {
      profiles: { balanced: { name: "balanced" } },
      manual_only: true,
    };
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(payload);
    const { result } = renderHook(() => useDecisionProfiles(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith("/api/ui/decision-engine/profiles");
    expect(result.current.data?.manual_only).toBe(true);
  });

  it("useEvaluateDecisions POSTs candidates to the evaluate endpoint", async () => {
    const response = {
      profile: { name: "balanced" },
      as_of_utc: "2026-06-21T12:00:00Z",
      manual_only: true,
      actionable: [{ symbol: "AAA", rank: 1, decision_status: "ACTIONABLE" }],
      watch: [],
      blocked: [],
      stay_in_cash: { decision_status: "STAY_IN_CASH" },
      counts: { actionable: 1, shown: 1, watch: 0, blocked: 0, total_candidates: 1 },
    };
    const spy = vi.spyOn(client, "apiPost").mockResolvedValue(response);
    const { result } = renderHook(() => useEvaluateDecisions(), {
      wrapper: makeWrapper(),
    });
    const payload = {
      profile: "balanced",
      portfolio: { total_value: 100000, available_cash: 60000 },
      candidates: [{ symbol: "AAA", strategy: "CSP", market_regime: "BULL" }],
    };
    result.current.mutate(payload);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(
      "/api/ui/decision-engine/evaluate",
      payload,
    );
    expect(result.current.data?.counts.actionable).toBe(1);
    expect(result.current.data?.manual_only).toBe(true);
  });
});
