/**
 * ORATS data health: status (OK/DEGRADED/DOWN), last_success_at, entitlement.
 * Used for ORATS badge and warning banner when data is stale or down.
 */
import { useState, useEffect } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";

const POLL_MS = 60_000;

/** Phase 8B: UNKNOWN = no success ever; OK = within window; WARN = stale; DOWN = failed */
export interface DataHealthState {
  provider: string;
  status: "OK" | "DEGRADED" | "DOWN" | "WARN" | "UNKNOWN" | string;
  last_success_at: string | null;
  last_error_at: string | null;
  last_error_reason: string | null;
  avg_latency_seconds: number | null;
  entitlement: "LIVE" | "DELAYED" | "UNKNOWN" | string;
}

const DEFAULT: DataHealthState = {
  provider: "ORATS",
  status: "UNKNOWN",
  last_success_at: null,
  last_error_at: null,
  last_error_reason: null,
  avg_latency_seconds: null,
  entitlement: "UNKNOWN",
};

export function useApiDataHealth(): DataHealthState {
  const { mode } = useDataMode();
  const [state, setState] = useState<DataHealthState>(DEFAULT);

  useEffect(() => {
    if (mode !== "LIVE") return;
    const fetch_ = async () => {
      try {
        const data = await apiGet<DataHealthState & { checked_at?: string; error?: string }>(ENDPOINTS.dataHealth);
        setState({
          provider: data?.provider ?? "ORATS",
          status: data?.status ?? "UNKNOWN",
          last_success_at: data?.last_success_at ?? data?.checked_at ?? null,
          last_error_at: data?.last_error_at ?? (data?.error ? new Date().toISOString() : null),
          last_error_reason: data?.last_error_reason ?? data?.error ?? null,
          avg_latency_seconds: typeof data?.avg_latency_seconds === "number" ? data.avg_latency_seconds : null,
          entitlement: data?.entitlement ?? "UNKNOWN",
        });
      } catch (e) {
        const reason = e instanceof ApiError && e.status === 404
          ? "Data-health endpoint not found (check proxy/backend)"
          : "Failed to fetch data health";
        setState((prev) => ({ ...prev, status: "DOWN", last_error_reason: reason }));
      }
    };
    fetch_();
    const id = setInterval(fetch_, POLL_MS);
    return () => clearInterval(id);
  }, [mode]);

  return state;
}

/** Format "updated Xm ago" from ISO timestamp. */
export function formatDataAge(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return "just now";
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  } catch {
    return null;
  }
}
