/**
 * TanStack Query hooks for UI API endpoints.
 * Requires @tanstack/react-query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./client";
import type {
  ArtifactListResponse,
  DecisionResponse,
  UniverseResponse,
  SymbolDiagnosticsResponseExtended,
  UiSystemHealthResponse,
  UiTrackedPositionsResponse,
  PortfolioResponse,
  UiAlertsResponse,
} from "./types";
import type { DecisionMode } from "./types";

// =============================================================================
// Paths
// =============================================================================

function decisionFilesPath(mode: DecisionMode): string {
  return `/api/ui/decision/files?mode=${mode}`;
}

function decisionLatestPath(mode: DecisionMode): string {
  return `/api/ui/decision/latest?mode=${mode}`;
}

function decisionFilePath(filename: string, mode: DecisionMode): string {
  return `/api/ui/decision/file/${encodeURIComponent(filename)}?mode=${mode}`;
}

function universePath(): string {
  return `/api/ui/universe`;
}

function symbolDiagnosticsPath(symbol: string, recompute = false): string {
  const base = `/api/ui/symbol-diagnostics?symbol=${encodeURIComponent(symbol)}`;
  return recompute ? `${base}&recompute=1` : base;
}

function symbolRecomputePath(symbol: string, force?: boolean): string {
  const base = `/api/ui/symbols/${encodeURIComponent(symbol)}/recompute`;
  return force ? `${base}?force=true` : base;
}

function uiSystemHealthPath(): string {
  return `/api/ui/system-health`;
}

function uiTrackedPositionsPath(): string {
  return `/api/ui/positions/tracked`;
}

function uiAccountsDefaultPath(): string {
  return `/api/ui/accounts/default`;
}

function uiPositionsPath(): string {
  return `/api/ui/positions`;
}

function uiPositionsManualExecutePath(): string {
  return `/api/ui/positions/manual-execute`;
}

function uiPortfolioPath(): string {
  return `/api/ui/portfolio`;
}

function uiAlertsPath(): string {
  return `/api/ui/alerts`;
}

function uiEvalRunPath(force?: boolean): string {
  const base = `/api/ui/eval/run`;
  return force ? `${base}?force=true` : base;
}

function uiDiagnosticsRunPath(checks?: string): string {
  const base = `/api/ui/diagnostics/run`;
  return checks ? `${base}?checks=${encodeURIComponent(checks)}` : base;
}

function uiDiagnosticsHistoryPath(limit?: number): string {
  const base = `/api/ui/diagnostics/history`;
  return limit != null ? `${base}?limit=${limit}` : base;
}

function uiMarketStatusPath(): string {
  return `/api/ui/market/status`;
}

function uiNotificationsPath(limit?: number): string {
  const base = `/api/ui/notifications`;
  return limit != null ? `${base}?limit=${limit}` : base;
}

// =============================================================================
// Query keys
// =============================================================================

export const queryKeys = {
  artifactList: (mode: DecisionMode) => ["ui", "artifactList", mode] as const,
  decision: (mode: DecisionMode, filename?: string) =>
    filename
      ? (["ui", "decision", mode, filename] as const)
      : (["ui", "decision", mode, "latest"] as const),
  universe: () => ["ui", "universe"] as const,
  symbolDiagnostics: (symbol: string) =>
    ["ui", "symbolDiagnostics", symbol] as const,
  uiSystemHealth: () => ["ui", "systemHealth"] as const,
  uiPositions: () => ["ui", "positions"] as const,
  uiTrackedPositions: () => ["ui", "positions", "tracked"] as const,
  uiAccountsDefault: () => ["ui", "accounts", "default"] as const,
  uiPortfolio: () => ["ui", "portfolio"] as const,
  uiAlerts: () => ["ui", "alerts"] as const,
  uiDiagnosticsHistory: (limit?: number) => ["ui", "diagnostics", "history", limit ?? 10] as const,
  uiNotifications: (limit?: number) => ["ui", "notifications", limit ?? 100] as const,
  uiMarketStatus: () => ["ui", "marketStatus"] as const,
};

// =============================================================================
// Hooks
// =============================================================================

export function useArtifactList(mode: DecisionMode) {
  return useQuery({
    queryKey: queryKeys.artifactList(mode),
    queryFn: () => apiGet<ArtifactListResponse>(decisionFilesPath(mode)),
  });
}

export function useDecision(mode: DecisionMode, filename?: string) {
  const path =
    filename && filename !== "decision_latest.json"
      ? decisionFilePath(filename, mode)
      : decisionLatestPath(mode);
  return useQuery({
    queryKey: queryKeys.decision(mode, filename),
    queryFn: () => apiGet<DecisionResponse>(path),
  });
}

export function useUniverse() {
  return useQuery({
    queryKey: queryKeys.universe(),
    queryFn: () => apiGet<UniverseResponse>(universePath()),
  });
}

export function useSymbolDiagnostics(
  symbol: string,
  enabled = true
) {
  return useQuery({
    queryKey: queryKeys.symbolDiagnostics(symbol),
    queryFn: () =>
      apiGet<SymbolDiagnosticsResponseExtended>(symbolDiagnosticsPath(symbol)),
    enabled: enabled && symbol.trim().length > 0,
  });
}

/** Response from POST /api/ui/symbols/{symbol}/recompute */
export interface SymbolRecomputeResponse {
  symbol: string;
  pipeline_timestamp: string;
  artifact_version: string;
  updated: boolean;
  score?: number;
  band?: string;
  verdict?: string;
}

export function useRecomputeSymbolDiagnostics() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: string | { symbol: string; force?: boolean }) => {
      const symbol = typeof payload === "string" ? payload : payload.symbol;
      const force = typeof payload === "string" ? false : payload.force ?? false;
      const res = await apiPost<SymbolRecomputeResponse>(symbolRecomputePath(symbol, force), {});
      return { symbol, data: res };
    },
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: queryKeys.symbolDiagnostics(result.symbol) });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
      qc.invalidateQueries({ queryKey: ["ui", "decision"] });
    },
  });
}

export function useUiSystemHealth() {
  return useQuery({
    queryKey: queryKeys.uiSystemHealth(),
    queryFn: () => apiGet<UiSystemHealthResponse>(uiSystemHealthPath()),
  });
}

/** Phase 9: Market status for guardrails (is_open, phase, now_utc, now_et, next_open_et, next_close_et). */
export interface UiMarketStatusResponse {
  is_open: boolean;
  phase: string;
  now_utc: string;
  now_et: string | null;
  next_open_et?: string | null;
  next_close_et?: string | null;
  error?: string;
}

export function useMarketStatus() {
  return useQuery({
    queryKey: queryKeys.uiMarketStatus(),
    queryFn: () => apiGet<UiMarketStatusResponse>(uiMarketStatusPath()),
  });
}

export function useUiTrackedPositions() {
  return useQuery({
    queryKey: queryKeys.uiTrackedPositions(),
    queryFn: () => apiGet<UiTrackedPositionsResponse>(uiTrackedPositionsPath()),
  });
}

export interface UiAccountsDefaultResponse {
  account: { account_id: string; [k: string]: unknown } | null;
  message?: string;
}

export function useDefaultAccount() {
  return useQuery({
    queryKey: queryKeys.uiAccountsDefault(),
    queryFn: () => apiGet<UiAccountsDefaultResponse>(uiAccountsDefaultPath()),
  });
}

export interface ManualExecutePayload {
  account_id: string;
  symbol: string;
  strategy: string;
  contracts?: number;
  strike?: number;
  expiration?: string;
  credit_expected?: number;
  entry_credit?: number;
}

export function useManualExecute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ManualExecutePayload) =>
      apiPost(uiPositionsManualExecutePath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiTrackedPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
    },
  });
}

export interface SavePaperPositionPayload {
  symbol: string;
  strategy: string;
  contracts?: number;
  strike?: number;
  expiration?: string;
  credit_expected?: number;
  credit?: number;
  max_loss?: number;
  decision_snapshot_id?: string;
  created_at?: string;
}

export function useSavePaperPosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SavePaperPositionPayload) =>
      apiPost<{ position_id: string; symbol: string; [k: string]: unknown }>(uiPositionsPath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiTrackedPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
    },
  });
}

export function usePortfolio() {
  return useQuery({
    queryKey: queryKeys.uiPortfolio(),
    queryFn: () => apiGet<PortfolioResponse>(uiPortfolioPath()),
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: queryKeys.uiAlerts(),
    queryFn: () => apiGet<UiAlertsResponse>(uiAlertsPath()),
  });
}

export interface RunEvalPayload {
  mode?: DecisionMode;
  symbols?: string[];
  force?: boolean;
}

export interface RunEvalResponse {
  status: "OK" | "FAILED";
  reason?: string;
  pipeline_timestamp?: string;
  counts?: { universe_size?: number; evaluated_count_stage1?: number; evaluated_count_stage2?: number; eligible_count?: number };
}

export function useRunEval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload?: RunEvalPayload) => {
      const force = payload?.force ?? false;
      return apiPost<RunEvalResponse>(uiEvalRunPath(force), payload ?? { mode: "LIVE" });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "decision"] });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
    },
  });
}

// Diagnostics (Phase 8.2)
export interface DiagnosticsRunResponse {
  timestamp_utc: string;
  checks: Array<{ check: string; status: string; details: Record<string, unknown> }>;
  overall_status: string;
}

export interface DiagnosticsHistoryResponse {
  runs: DiagnosticsRunResponse[];
}

export function useDiagnosticsHistory(limit = 10) {
  return useQuery({
    queryKey: queryKeys.uiDiagnosticsHistory(limit),
    queryFn: () => apiGet<DiagnosticsHistoryResponse>(uiDiagnosticsHistoryPath(limit)),
  });
}

export function useRunDiagnostics() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (checks?: string) =>
      apiPost<DiagnosticsRunResponse>(uiDiagnosticsRunPath(checks), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiDiagnosticsHistory() });
    },
  });
}

// Notifications (Phase 8.3, 8.6)
export interface UiNotification {
  timestamp_utc: string;
  severity: string;
  type: string;
  /** Phase 8.6: Subtype (RUN_ERRORS, LOW_COMPLETENESS, ORATS_STALE, ORATS_DEGRADED, SCHEDULER_MISSED, RECOMPUTE_FAILED, etc.) */
  subtype?: string | null;
  symbol?: string | null;
  message: string;
  details?: Record<string, unknown>;
}

export interface UiNotificationsResponse {
  notifications: UiNotification[];
}

export function useNotifications(limit = 100) {
  return useQuery({
    queryKey: queryKeys.uiNotifications(limit),
    queryFn: () => apiGet<UiNotificationsResponse>(uiNotificationsPath(limit)),
  });
}
