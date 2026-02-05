/**
 * Phase 10: LIVE market status — last_market_check, last_evaluated_at, evaluation_attempted, evaluation_emitted.
 * Degrades gracefully if /api/market-status returns 404 (use healthz only).
 */
import { useState, useEffect } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";

const POLL_MS = 60_000;

export interface MarketStatusState {
  ok: boolean;
  market_phase: string | null;
  last_market_check: string | null;
  last_evaluated_at: string | null;
  evaluation_attempted: boolean;
  evaluation_emitted: boolean;
  skip_reason: string | null;
}

const DEFAULT: MarketStatusState = {
  ok: false,
  market_phase: null,
  last_market_check: null,
  last_evaluated_at: null,
  evaluation_attempted: false,
  evaluation_emitted: false,
  skip_reason: null,
};

export function useApiMarketStatus(): MarketStatusState {
  const { mode } = useDataMode();
  const [state, setState] = useState<MarketStatusState>(DEFAULT);

  useEffect(() => {
    if (mode !== "LIVE") return;
    const fetch_ = async () => {
      try {
        const data = await apiGet<MarketStatusState>(ENDPOINTS.marketStatus);
        setState({
          ok: data?.ok ?? true,
          market_phase: data?.market_phase ?? null,
          last_market_check: data?.last_market_check ?? null,
          last_evaluated_at: data?.last_evaluated_at ?? null,
          evaluation_attempted: Boolean(data?.evaluation_attempted),
          evaluation_emitted: Boolean(data?.evaluation_emitted),
          skip_reason: data?.skip_reason ?? null,
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
