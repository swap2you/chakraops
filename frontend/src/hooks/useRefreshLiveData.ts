/**
 * "Refresh now" — POST /api/ops/refresh-live-data (ORATS fetch). No cooldown; fails loudly on 503.
 */
import { useState, useCallback } from "react";
import { apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { pushSystemNotification } from "@/lib/notifications";

export interface RefreshLiveDataState {
  loading: boolean;
  message: string | null;
  lastFetchedAt: string | null;
}

export function useRefreshLiveData(): {
  trigger: () => Promise<void>;
  state: RefreshLiveDataState;
} {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<string | null>(null);

  const trigger = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    setMessage(null);
    try {
      const data = await apiPost<{ ok?: boolean; row_count?: number; http_status?: number; sample_keys?: string[] }>(
        ENDPOINTS.refreshLiveData,
        {},
        { timeoutMs: 20000 }
      );
      setLastFetchedAt(new Date().toISOString());
      const ok = data?.ok === true;
      setMessage(ok ? "ORATS LIVE CONFIRMED" : (data ? `Rows: ${data.row_count ?? 0}` : "Updated"));
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: ok ? "ORATS LIVE CONFIRMED" : "ORATS refresh",
        message: ok ? `Row count: ${data?.row_count ?? 0}` : (data ? `Rows: ${data.row_count ?? 0}` : "Live data updated"),
      });
      setTimeout(() => setMessage(null), 4000);
    } catch (e) {
      const detail = e instanceof ApiError && e.body && typeof e.body === "object" && "detail" in e.body
        ? (e.body.detail as { reason?: string })
        : null;
      const reason = detail?.reason ?? (e instanceof ApiError ? `${e.status} ${e.message}` : (e instanceof Error ? e.message : "ORATS unavailable"));
      setMessage(reason);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "ORATS: DOWN",
        message: reason,
      });
    } finally {
      setLoading(false);
    }
  }, [loading]);

  return {
    trigger,
    state: { loading, message, lastFetchedAt },
  };
}
