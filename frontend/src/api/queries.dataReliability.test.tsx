/**
 * R32.0: read-only data-reliability query hooks call the correct endpoints
 * and surface provider health, deterministic weekly universe, and refresh
 * history without exposing secrets.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as client from "./client";
import {
  useDataReliabilityHealth,
  useWeeklyUniverse,
  useUniverseRefreshHistory,
} from "./queries";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("data-reliability query hooks", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("useDataReliabilityHealth GETs the health endpoint", async () => {
    const payload = {
      as_of_utc: "2026-06-21T12:00:00Z",
      provider: {
        provider: "ORATS",
        sole_provider: true,
        fallback_provider: null,
        auth_mode: "env",
        token_present: true,
        status: "READY",
        blocked_reason: null,
        retry_policy: {},
        rate_limit_policy: {},
        cache_policy: {},
        failure_categories: ["AUTH"],
        read_only_contract: {
          ok: true,
          allowed_endpoints: ["strikes"],
          violations: [],
          method: "GET",
          mutating_endpoints: false,
        },
      },
      event_calendar: { kind: "macro_events", state: "UNAVAILABLE", available: false, reason: "NO_PROVIDER_CONFIGURED", as_of_utc: "x", events: [] },
      earnings_calendar: { kind: "earnings", state: "AVAILABLE", available: true, reason: "OK", as_of_utc: "x", events: [] },
    };
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(payload);
    const { result } = renderHook(() => useDataReliabilityHealth(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith("/api/ui/data-reliability/health");
    expect(result.current.data?.provider.sole_provider).toBe(true);
    expect(result.current.data?.provider.fallback_provider).toBeNull();
  });

  it("useWeeklyUniverse GETs the weekly endpoint", async () => {
    const payload = {
      week_id: "2026-W25",
      as_of: "2026-06-21",
      symbols: ["AAPL", "SPY"],
      added: [],
      removed: [],
      reason_codes: ["UNCHANGED"],
      count: 2,
      refresh_due: false,
      last_refresh_at_utc: null,
    };
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(payload);
    const { result } = renderHook(() => useWeeklyUniverse(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith("/api/ui/data-reliability/universe/weekly");
    expect(result.current.data?.week_id).toBe("2026-W25");
  });

  it("useUniverseRefreshHistory passes the limit", async () => {
    const spy = vi
      .spyOn(client, "apiGet")
      .mockResolvedValue({ as_of_utc: "x", records: [] });
    const { result } = renderHook(() => useUniverseRefreshHistory(5), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(
      "/api/ui/data-reliability/universe/refresh-history?limit=5",
    );
  });
});
