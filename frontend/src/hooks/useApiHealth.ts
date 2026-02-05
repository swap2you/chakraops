/**
 * Phase 8.7: LIVE API health check — polls /api/healthz on interval when mode is LIVE.
 * Degrades gracefully if endpoint does not exist (ok: false, no throw).
 */
import { useState, useEffect } from "react";
import { useDataMode } from "@/context/DataModeContext";

const API_BASE = (import.meta as unknown as { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL ?? "";
const INTERVAL_MS = 60_000;

export interface ApiHealthState {
  ok: boolean;
  statusText: string;
  lastCheckedAt: Date | null;
}

export function useApiHealth(): ApiHealthState {
  const { mode } = useDataMode();
  const [state, setState] = useState<ApiHealthState>({ ok: false, statusText: "unknown", lastCheckedAt: null });

  useEffect(() => {
    if (mode !== "LIVE") return;

    const check = async () => {
      const url = API_BASE ? `${API_BASE.replace(/\/$/, "")}/api/healthz` : "/api/healthz";
      try {
        const res = await fetch(url, { method: "GET", signal: AbortSignal.timeout(5000) });
        setState({
          ok: res.ok,
          statusText: res.ok ? "OK" : res.statusText || "error",
          lastCheckedAt: new Date(),
        });
      } catch {
        setState({ ok: false, statusText: "unreachable", lastCheckedAt: new Date() });
      }
    };

    check();
    const id = setInterval(check, INTERVAL_MS);
    return () => clearInterval(id);
  }, [mode]);

  return state;
}
