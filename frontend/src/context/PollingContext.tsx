/**
 * Phase 10: LIVE polling — pollTick every 60s when LIVE; backoff to 120s when API is DOWN.
 */
import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { useApiHealth } from "@/hooks/useApiHealth";

const POLL_INTERVAL_MS = 60_000;
const POLL_BACKOFF_MS = 120_000;

type PollingContextValue = {
  pollTick: number;
  triggerRefetch: () => void;
  pollIntervalMs: number;
};

const PollingContext = createContext<PollingContextValue | null>(null);

export function PollingProvider(props: { children: React.ReactNode }) {
  const { mode } = useDataMode();
  const apiHealth = useApiHealth();
  const [pollTick, setPollTick] = useState(0);
  const intervalMs = mode === "LIVE" && !apiHealth.ok ? POLL_BACKOFF_MS : POLL_INTERVAL_MS;
  const triggerRefetch = useCallback(() => setPollTick((t) => t + 1), []);

  useEffect(() => {
    if (mode !== "LIVE") return;
    const id = setInterval(() => setPollTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [mode, intervalMs]);

  const value: PollingContextValue = {
    pollTick,
    triggerRefetch,
    pollIntervalMs: intervalMs,
  };
  return (
    <PollingContext.Provider value={value}>
      {props.children}
    </PollingContext.Provider>
  );
}

export function usePolling() {
  const ctx = useContext(PollingContext);
  return ctx;
}
