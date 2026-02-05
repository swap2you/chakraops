/**
 * Phase 12: LIVE ops status — last_run_at, next_run_at, cadence_minutes, symbols_evaluated, trades_found, blockers_summary.
 */
import { useState, useEffect } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";

const POLL_MS = 60_000;

export interface OpsStatusState {
  last_run_at: string | null;
  next_run_at: string | null;
  cadence_minutes: number;
  last_run_reason: string | null;
  symbols_evaluated: number;
  trades_found: number;
  blockers_summary: Record<string, number>;
  market_phase: string | null;
}

const DEFAULT: OpsStatusState = {
  last_run_at: null,
  next_run_at: null,
  cadence_minutes: 15,
  last_run_reason: null,
  symbols_evaluated: 0,
  trades_found: 0,
  blockers_summary: {},
  market_phase: null,
};

export function useApiOpsStatus(): OpsStatusState {
  const { mode } = useDataMode();
  const [state, setState] = useState<OpsStatusState>(DEFAULT);

  useEffect(() => {
    if (mode !== "LIVE") return;
    const fetch_ = async () => {
      try {
        const data = await apiGet<OpsStatusState>(ENDPOINTS.opsStatus);
        setState({
          last_run_at: data?.last_run_at ?? null,
          next_run_at: data?.next_run_at ?? null,
          cadence_minutes: typeof data?.cadence_minutes === "number" ? data.cadence_minutes : 15,
          last_run_reason: data?.last_run_reason ?? null,
          symbols_evaluated: typeof data?.symbols_evaluated === "number" ? data.symbols_evaluated : 0,
          trades_found: typeof data?.trades_found === "number" ? data.trades_found : 0,
          blockers_summary: data?.blockers_summary && typeof data.blockers_summary === "object" ? data.blockers_summary : {},
          market_phase: data?.market_phase ?? null,
        });
      } catch {
        setState(DEFAULT);
      }
    };
    fetch_();
    const id = setInterval(fetch_, POLL_MS);
    return () => clearInterval(id);
  }, [mode]);

  return state;
}
