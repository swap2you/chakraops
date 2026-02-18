/**
 * TanStack Query hooks for UI API endpoints.
 * Requires @tanstack/react-query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost } from "./client";
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

function uiAccountsPath(): string {
  return `/api/ui/accounts`;
}

function uiPositionsPath(): string {
  return `/api/ui/positions`;
}

function uiPositionsManualExecutePath(): string {
  return `/api/ui/positions/manual-execute`;
}

function uiPositionsClosePath(positionId: string): string {
  return `/api/ui/positions/${encodeURIComponent(positionId)}/close`;
}

function uiPositionsDeletePath(positionId: string): string {
  return `/api/ui/positions/${encodeURIComponent(positionId)}`;
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

function uiSchedulerRunOncePath(): string {
  return `/api/ui/scheduler/run_once`;
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

function uiSnapshotsFreezePath(skipEval?: boolean): string {
  const base = `/api/ui/snapshots/freeze`;
  return skipEval ? `${base}?skip_eval=true` : base;
}

function uiSnapshotsLatestPath(): string {
  return `/api/ui/snapshots/latest`;
}

function uiNotificationsPath(limit?: number): string {
  const base = `/api/ui/notifications`;
  return limit != null ? `${base}?limit=${limit}` : base;
}

function uiNotificationAckPath(notificationId: string): string {
  return `/api/ui/notifications/${encodeURIComponent(notificationId)}/ack`;
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
  uiAccounts: () => ["ui", "accounts"] as const,
  uiPortfolio: () => ["ui", "portfolio"] as const,
  uiAlerts: () => ["ui", "alerts"] as const,
  uiDiagnosticsHistory: (limit?: number) => ["ui", "diagnostics", "history", limit ?? 10] as const,
  uiNotifications: (limit?: number) => ["ui", "notifications", limit ?? 100] as const,
  uiMarketStatus: () => ["ui", "marketStatus"] as const,
  uiSnapshotsLatest: () => ["ui", "snapshots", "latest"] as const,
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

/** PR2: Latest EOD snapshot manifest + path. */
export interface UiSnapshotLatestResponse {
  snapshot_dir: string;
  manifest: { created_at_utc?: string; created_at_et?: string; files?: { name: string; size_bytes?: number }[] };
}

export function useLatestSnapshot() {
  return useQuery({
    queryKey: queryKeys.uiSnapshotsLatest(),
    queryFn: async () => {
      try {
        return await apiGet<UiSnapshotLatestResponse>(uiSnapshotsLatestPath());
      } catch (e: unknown) {
        const err = e as { status?: number };
        if (err?.status === 404) return null;
        throw e;
      }
    },
    retry: false,
  });
}

/** PR2: Freeze snapshot response. */
export interface UiFreezeSnapshotResponse {
  status: string;
  mode_used: string;
  snapshot_dir: string;
  manifest: Record<string, unknown>;
  ran_eval: boolean;
  eval_result?: Record<string, unknown>;
}

export function useRunFreezeSnapshot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (skipEval: boolean) =>
      apiPost<UiFreezeSnapshotResponse>(uiSnapshotsFreezePath(skipEval), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiSnapshotsLatest() });
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
      qc.invalidateQueries({ queryKey: ["ui", "decision"] });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
    },
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

export interface UiAccountsResponse {
  accounts: Array<{ account_id: string; [k: string]: unknown }>;
}

export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.uiAccounts(),
    queryFn: () => apiGet<UiAccountsResponse>(uiAccountsPath()),
  });
}

export interface CreateAccountPayload {
  account_id?: string;
  provider: string;
  account_type: string;
  total_capital: number;
  max_capital_per_trade_pct: number;
  max_total_exposure_pct: number;
  allowed_strategies?: string[];
  is_default?: boolean;
}

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateAccountPayload) =>
      apiPost<{ account_id: string; [k: string]: unknown }>(uiAccountsPath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiAccounts() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountsDefault() });
    },
  });
}

export function useClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { positionId: string; close_price: number; close_time_utc?: string; close_fees?: number }) =>
      apiPost(uiPositionsClosePath(payload.positionId), {
        close_price: payload.close_price,
        close_time_utc: payload.close_time_utc,
        close_fees: payload.close_fees,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiTrackedPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
    },
  });
}

export function useDeletePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (positionId: string) =>
      apiDelete<{ deleted: string }>(uiPositionsDeletePath(positionId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiTrackedPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
    },
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

export interface DecisionRef {
  evaluation_timestamp_utc: string;
  artifact_source?: string;
  selected_contract_key?: string;
}

export interface SavePaperPositionPayload {
  symbol: string;
  strategy: string;
  contracts?: number;
  strike?: number;
  expiration?: string;
  credit_expected?: number;
  credit?: number;
  open_credit?: number;
  max_loss?: number;
  decision_snapshot_id?: string;
  decision_ref?: DecisionRef;
  option_symbol?: string;
  contract_key?: string;
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
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
    },
  });
}

/** Phase 10.2: Trigger one scheduler tick. Skips when market closed (no 409). */
export function useRunSchedulerOnce() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ started: boolean; last_run_at?: string; last_result?: string }>(uiSchedulerRunOncePath(), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
      qc.invalidateQueries({ queryKey: ["ui", "decision"] });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
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

// Notifications (Phase 8.3, 8.6, 10.3)
export interface UiNotification {
  id?: string;
  timestamp_utc: string;
  severity: string;
  type: string;
  /** Phase 8.6: Subtype (RUN_ERRORS, LOW_COMPLETENESS, ORATS_STALE, ORATS_DEGRADED, SCHEDULER_MISSED, RECOMPUTE_FAILED, etc.) */
  subtype?: string | null;
  symbol?: string | null;
  message: string;
  details?: Record<string, unknown>;
  /** Phase 10.3: Acknowledgment fields */
  ack_at_utc?: string | null;
  ack_by?: string | null;
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

/** Phase 10.3: Ack a notification. Invalidates notifications query. */
export function useAckNotification(limit = 100) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      apiPost<{ status: string; ack_at_utc?: string }>(
        uiNotificationAckPath(notificationId),
        {}
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiNotifications(limit) });
    },
  });
}
