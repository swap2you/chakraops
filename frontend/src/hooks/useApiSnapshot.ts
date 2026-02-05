/**
 * System snapshot hook — fetches /api/ops/snapshot for dashboard state.
 * Does NOT trigger ORATS calls. Provides lifecycle, universe counts, final trade, warnings, errors.
 * Polling every 15 minutes (snapshot endpoint doesn't call ORATS).
 */
import { useState, useEffect, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";

// 15-minute polling for snapshot (doesn't trigger ORATS)
const SNAPSHOT_POLL_MS = 900_000;

export type SnapshotPhase = "IDLE" | "EVALUATING" | "COMPLETE" | "STALE" | "ERROR";

export interface SnapshotMarketStatus {
  phase: string | null;
  last_market_check: string | null;
  last_evaluated_at: string | null;
  evaluation_attempted: boolean;
  evaluation_emitted: boolean;
  skip_reason: string | null;
}

export interface SnapshotUniverse {
  total: number;
  evaluated: number;
  eligible: number;
  shortlisted: number;
}

export interface SnapshotFinalTrade {
  symbol: string;
  strategy: string | null;
  direction: string | null;
  confidence: number | null;
}

export interface EvaluationWindow {
  date: string;
  asof_time_utc: string;
}

export interface SnapshotDecisionState {
  last_decision_id: string | null;
  last_decision_time_utc: string | null;
  decision_age_seconds: number | null;
  decision_source: "artifact" | "none";
  decision_stale: boolean;
}

export interface SnapshotWarning {
  code: string;
  message: string;
}

export interface SnapshotError {
  code: string;
  message: string;
}

export interface PipelineStep {
  step: string;
  status: "OK" | "WARN" | "ERROR" | "NOT_RUN" | "PENDING" | "RUNNING";
  detail: string;
  last_transition_time?: string | null;
  blocking?: boolean;
  explanation?: string;
}

export type EvaluationState = "IDLE" | "RUNNING" | "COMPLETED" | "FAILED";

export interface SystemSnapshot {
  // Snapshot contract (NEVER throws - always check these)
  snapshot_ok: boolean;
  has_run: boolean;
  reason: string | null;
  
  // Core identification
  snapshot_id: string;
  snapshot_time_utc: string;
  snapshot_age_seconds: number;
  
  // Lifecycle
  snapshot_phase: SnapshotPhase;
  stale_threshold_seconds: number;
  next_scheduled_refresh_utc: string | null;
  
  // Explicit evaluation state: IDLE | RUNNING | COMPLETED | FAILED
  evaluation_state: EvaluationState;
  evaluation_state_reason: string;
  
  // Explicit boolean flags (for UI rendering decisions)
  has_evaluation_run: boolean;
  has_decision_artifact: boolean;
  orats_connected: boolean;
  data_stale: boolean;
  
  // Run configuration
  run_mode: string;
  
  // Market status
  market_status: SnapshotMarketStatus;
  
  // Evaluation window
  evaluation_window: EvaluationWindow | null;
  
  // Universe counts
  universe: SnapshotUniverse;
  
  // Universe evaluation counts (from batch evaluation)
  universe_counts?: SnapshotUniverse;
  alerts_count?: number;
  last_alerts_generated_at?: string | null;
  
  // Decision state
  snapshot_state: SnapshotDecisionState;
  
  // Trade result
  final_trade: SnapshotFinalTrade | null;
  
  // ORATS status (cached) with reasoned status
  orats_status: string;
  orats_status_reason: string;
  last_orats_success_at: string | null;
  
  // Pipeline steps for diagnostics (with full explainability)
  pipeline_steps: PipelineStep[];
  
  // Issues (structured)
  warnings: SnapshotWarning[];
  errors: SnapshotError[];
}

export interface SnapshotHookState {
  snapshot: SystemSnapshot | null;
  loading: boolean;
  error: string | null;
  lastFetchedAt: string | null;
  /** True if snapshot_ok: false (no run yet, but NOT an error) */
  noRunYet: boolean;
}

const DEFAULT: SnapshotHookState = {
  snapshot: null,
  loading: false,
  error: null,
  lastFetchedAt: null,
  noRunYet: false,
};

export function useApiSnapshot(): SnapshotHookState & { refetch: () => void } {
  const { mode } = useDataMode();
  const [state, setState] = useState<SnapshotHookState>(DEFAULT);
  const [hasFailed, setHasFailed] = useState(false);

  const fetchSnapshot = useCallback(async () => {
    if (mode !== "LIVE") return;
    // Stop polling after persistent failure
    if (hasFailed) return;
    
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await apiGet<SystemSnapshot>(ENDPOINTS.snapshot);
      
      // Handle snapshot_ok: false (not an error, just no run yet)
      const noRunYet = data?.snapshot_ok === false || data?.has_run === false;
      
      setState({
        snapshot: data ?? null,
        loading: false,
        error: null,
        lastFetchedAt: new Date().toISOString(),
        noRunYet,
      });
      
      // Reset failure state on success
      setHasFailed(false);
    } catch (e) {
      // On error, stop retrying (no exponential backoff spam)
      setHasFailed(true);
      const errMsg = e instanceof ApiError ? `${e.status}: ${e.message}` : (e instanceof Error ? e.message : "Failed to fetch snapshot");
      setState((prev) => ({
        ...prev,
        loading: false,
        error: errMsg,
        noRunYet: false,
      }));
    }
  }, [mode, hasFailed]);

  useEffect(() => {
    if (mode !== "LIVE") {
      setState(DEFAULT);
      setHasFailed(false);
      return;
    }
    fetchSnapshot();
    const id = setInterval(fetchSnapshot, SNAPSHOT_POLL_MS);
    return () => clearInterval(id);
  }, [mode, fetchSnapshot]);

  // Manual refetch resets failure state to allow retry
  const manualRefetch = useCallback(() => {
    setHasFailed(false);
    fetchSnapshot();
  }, [fetchSnapshot]);

  return { ...state, refetch: manualRefetch };
}

/** Check if snapshot has critical errors */
export function hasSnapshotErrors(snapshot: SystemSnapshot | null): boolean {
  return (snapshot?.errors?.length ?? 0) > 0 || snapshot?.snapshot_phase === "ERROR";
}

/** Check if snapshot has warnings */
export function hasSnapshotWarnings(snapshot: SystemSnapshot | null): boolean {
  return (snapshot?.warnings?.length ?? 0) > 0;
}

/** Get warning codes as array */
export function getWarningCodes(snapshot: SystemSnapshot | null): string[] {
  return snapshot?.warnings?.map(w => w.code) ?? [];
}

/** Get error codes as array */
export function getErrorCodes(snapshot: SystemSnapshot | null): string[] {
  return snapshot?.errors?.map(e => e.code) ?? [];
}

/** Format relative time for snapshot age */
export function formatSnapshotAge(iso: string | null | undefined): string | null {
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
