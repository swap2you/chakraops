/**
 * Recompute mutation: calls POST /api/ui/symbols/{symbol}/recompute and invalidates
 * symbolDiagnostics, universe, and decision so UI updates.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as client from "./client";
import { useRecomputeSymbolDiagnostics } from "./queries";

const mockRecomputeResponse = {
  symbol: "SPY",
  pipeline_timestamp: "2026-02-17T18:00:00Z",
  artifact_version: "v2",
  updated: true,
  score: 65,
  band: "B",
  verdict: "HOLD",
};

describe("useRecomputeSymbolDiagnostics", () => {
  let queryClient: QueryClient;
  let invalidateSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    invalidateSpy = vi.fn();
    queryClient.invalidateQueries = invalidateSpy;
    vi.spyOn(client, "apiPost").mockResolvedValue(mockRecomputeResponse);
  });

  it("on success invalidates symbolDiagnostics, universe, and decision", async () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useRecomputeSymbolDiagnostics(), { wrapper });
    result.current.mutate("SPY");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const apiPost = vi.mocked(client.apiPost);
    expect(apiPost).toHaveBeenCalledWith("/api/ui/symbols/SPY/recompute", {});
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["ui", "symbolDiagnostics", "SPY"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ui", "universe"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["ui", "decision"] });
  });
});
