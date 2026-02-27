/**
 * TanStack Query hooks for UI API endpoints.
 * Requires @tanstack/react-query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost, apiPostText } from "./client";
import type {
  ArtifactListResponse,
  DecisionArtifactV2,
  DecisionResponse,
  UniverseResponse,
  SymbolDiagnosticsResponseExtended,
  UiSystemHealthResponse,
  UiTrackedPositionsResponse,
  PortfolioResponse,
  PortfolioMetricsResponse,
  AccountSummary,
  AccountHolding,
  AccountHoldingsResponse,
  UniverseSymbolsResponse,
  UiAlertsResponse,
  SharesPlan,
  SharePosition,
  SharesPositionsListResponse,
  ClosedSharePosition,
  ClosedSharePositionsListResponse,
} from "./types";
import type { DecisionMode, DecisionRef } from "./types";
export type { DecisionRef };

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

/** Phase 21.3: Universe overlay */
function uiUniverseSymbolsPath(): string {
  return `/api/ui/universe/symbols`;
}
function uiUniverseSymbolRemovePath(symbol: string): string {
  return `/api/ui/universe/symbols/${encodeURIComponent(symbol)}`;
}
function uiUniverseResetPath(): string {
  return `/api/ui/universe/reset`;
}

function symbolDiagnosticsPath(symbol: string, recompute = false, runId?: string | null): string {
  const base = `/api/ui/symbol-diagnostics?symbol=${encodeURIComponent(symbol)}`;
  const params = [base];
  if (recompute) params.push("recompute=1");
  if (runId) params.push(`run_id=${encodeURIComponent(runId)}`);
  return params.length > 1 ? params.join("&") : base;
}

function symbolRecomputePath(symbol: string, force?: boolean): string {
  const base = `/api/ui/symbols/${encodeURIComponent(symbol)}/recompute`;
  return force ? `${base}?force=true` : base;
}

/** R23.2: Delta band overrides (advanced). */
function uiDeltaOverridesPath(): string {
  return `/api/ui/delta-overrides`;
}
function uiDeltaOverrideSymbolPath(symbol: string): string {
  return `/api/ui/delta-overrides/${encodeURIComponent(symbol)}`;
}

function uiSystemHealthPath(): string {
  return `/api/ui/system-health`;
}

/** R22.5: Shares candidates (BUY SHARES recommendation only). */
function sharesCandidatesPath(): string {
  return `/api/ui/shares-candidates`;
}

/** R24.1: Action Needed — top options + top shares for Dashboard. */
function actionNeededPath(): string {
  return `/api/ui/action-needed`;
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

function uiPositionDecisionPath(positionId: string): string {
  return `/api/ui/positions/${encodeURIComponent(positionId)}/decision`;
}

function uiPositionEventsPath(positionId: string): string {
  return `/api/ui/positions/${encodeURIComponent(positionId)}/events`;
}

function uiPositionRollPath(positionId: string): string {
  return `/api/ui/positions/${encodeURIComponent(positionId)}/roll`;
}

function uiPortfolioPath(): string {
  return `/api/ui/portfolio`;
}

/** Phase 21.1: Account (SQLite) */
function uiAccountSummaryPath(): string {
  return `/api/ui/account/summary`;
}
function uiAccountHoldingsPath(): string {
  return `/api/ui/account/holdings`;
}
function uiAccountHoldingsDeletePath(symbol: string): string {
  return `/api/ui/account/holdings/${encodeURIComponent(symbol)}`;
}
function uiAccountBalancesPath(): string {
  return `/api/ui/account/balances`;
}

function uiPortfolioMetricsPath(accountId?: string | null): string {
  const base = `/api/ui/portfolio/metrics`;
  return accountId ? `${base}?account_id=${encodeURIComponent(accountId)}` : base;
}

function uiPortfolioRiskPath(accountId?: string | null): string {
  const base = `/api/ui/portfolio/risk`;
  return accountId ? `${base}?account_id=${encodeURIComponent(accountId)}` : base;
}

function uiPortfolioMtmPath(accountId?: string | null): string {
  const base = `/api/ui/portfolio/mtm`;
  return accountId ? `${base}?account_id=${encodeURIComponent(accountId)}` : base;
}

function uiPositionsMarksRefreshPath(accountId?: string | null): string {
  const base = `/api/ui/positions/marks/refresh`;
  return accountId ? `${base}?account_id=${encodeURIComponent(accountId)}` : base;
}

function uiAlertsPath(): string {
  return `/api/ui/alerts`;
}

/** R23.0: Share positions */
function uiSharesPositionsListPath(accountId: string): string {
  return `/api/ui/shares/positions?account_id=${encodeURIComponent(accountId)}`;
}
function uiSharePositionGetPath(symbol: string, accountId: string): string {
  return `/api/ui/shares/positions/${encodeURIComponent(symbol)}?account_id=${encodeURIComponent(accountId)}`;
}
function uiSharePositionUpsertPath(symbol: string): string {
  return `/api/ui/shares/positions/${encodeURIComponent(symbol)}`;
}
function uiSharePositionDeletePath(symbol: string, accountId: string): string {
  return `/api/ui/shares/positions/${encodeURIComponent(symbol)}?account_id=${encodeURIComponent(accountId)}`;
}
/** R23.5.0: Close share position */
function uiSharePositionClosePath(symbol: string): string {
  return `/api/ui/shares/positions/${encodeURIComponent(symbol)}/close`;
}
/** R23.5.0: List closed share positions */
function uiSharesPositionsClosedPath(accountId: string): string {
  return `/api/ui/shares/positions/closed?account_id=${encodeURIComponent(accountId)}`;
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

function uiStoresIntegrityPath(): string {
  return `/api/ui/stores/integrity`;
}

function uiStoresRepairPath(store: string): string {
  return `/api/ui/stores/repair?store=${encodeURIComponent(store)}`;
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

function uiWheelOverviewPath(accountId?: string | null): string {
  const base = `/api/ui/wheel/overview`;
  return accountId ? `${base}?account_id=${encodeURIComponent(accountId)}` : base;
}

/** Phase 20.0: Manual wheel actions */
function uiWheelAssignPath(symbol: string): string {
  return `/api/ui/wheel/${encodeURIComponent(symbol)}/assign`;
}
function uiWheelUnassignPath(symbol: string): string {
  return `/api/ui/wheel/${encodeURIComponent(symbol)}/unassign`;
}
function uiWheelResetPath(symbol: string): string {
  return `/api/ui/wheel/${encodeURIComponent(symbol)}/reset`;
}
function uiWheelRepairPath(): string {
  return `/api/ui/wheel/repair`;
}

function uiNotificationsPath(limit?: number, state?: string | null, symbol?: string | null, type?: string | null, offset?: number): string {
  const base = `/api/ui/notifications`;
  const params = new URLSearchParams();
  if (limit != null) params.set("limit", String(limit));
  if (state && state.trim()) params.set("state", state.trim());
  if (symbol && symbol.trim()) params.set("symbol", symbol.trim());
  if (type && type.trim()) params.set("type", type.trim());
  if (offset != null && offset > 0) params.set("offset", String(offset));
  const q = params.toString();
  return q ? `${base}?${q}` : base;
}

function uiNotificationAckPath(notificationId: string): string {
  return `/api/ui/notifications/${encodeURIComponent(notificationId)}/ack`;
}
function uiNotificationArchivePath(notificationId: string): string {
  return `/api/ui/notifications/${encodeURIComponent(notificationId)}/archive`;
}
function uiNotificationDeletePath(notificationId: string): string {
  return `/api/ui/notifications/${encodeURIComponent(notificationId)}`;
}
function uiNotificationsArchiveAllPath(): string {
  return `/api/ui/notifications/archive_all`;
}
function uiNotificationsAckBulkPath(): string {
  return `/api/ui/notifications/ack-bulk`;
}
function uiNotificationsArchiveBulkPath(): string {
  return `/api/ui/notifications/archive-bulk`;
}

/** R25.5: Journal */
function uiJournalPath(params: { from_date?: string; to_date?: string; symbol?: string; strategy?: string; limit?: number; offset?: number }): string {
  const p = new URLSearchParams();
  if (params.from_date) p.set("from_date", params.from_date);
  if (params.to_date) p.set("to_date", params.to_date);
  if (params.symbol) p.set("symbol", params.symbol);
  if (params.strategy) p.set("strategy", params.strategy);
  if (params.limit != null) p.set("limit", String(params.limit));
  if (params.offset != null) p.set("offset", String(params.offset));
  const q = p.toString();
  return q ? `/api/ui/journal?${q}` : "/api/ui/journal";
}
function uiJournalExportPath(from_date: string, to_date: string): string {
  return `/api/ui/journal/export?from_date=${encodeURIComponent(from_date)}&to_date=${encodeURIComponent(to_date)}`;
}
function uiJournalEntryPath(id: string): string {
  return `/api/ui/journal/${encodeURIComponent(id)}`;
}
/** R25.5: Reports monthly */
function uiReportsMonthlyPath(month: string): string {
  return `/api/ui/reports/monthly?month=${encodeURIComponent(month)}`;
}
function uiAdminSlackTestPath(channel?: string): string {
  const base = `/api/ui/admin/slack/test`;
  if (channel && channel.trim()) {
    return `${base}?channel=${encodeURIComponent(channel.trim())}`;
  }
  return base;
}
function uiAdminEvaluationForcePath(): string {
  return `/api/ui/admin/evaluation/force`;
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
  uiUniverseSymbols: () => ["ui", "universe", "symbols"] as const,
  symbolDiagnostics: (symbol: string, runId?: string | null) =>
    (["ui", "symbolDiagnostics", symbol, runId ?? ""] as const),
  uiSystemHealth: () => ["ui", "systemHealth"] as const,
  sharesCandidates: () => ["ui", "sharesCandidates"] as const,
  actionNeeded: () => ["ui", "actionNeeded"] as const,
  uiPositions: () => ["ui", "positions"] as const,
  uiTrackedPositions: () => ["ui", "positions", "tracked"] as const,
  uiAccountsDefault: () => ["ui", "accounts", "default"] as const,
  uiAccounts: () => ["ui", "accounts"] as const,
  uiPortfolio: () => ["ui", "portfolio"] as const,
  uiAccountSummary: () => ["ui", "account", "summary"] as const,
  uiAccountHoldings: () => ["ui", "account", "holdings"] as const,
  /** R23.0 */
  uiSharesPositions: (accountId: string) => ["ui", "shares", "positions", accountId] as const,
  uiSharePosition: (accountId: string, symbol: string) => ["ui", "shares", "positions", accountId, symbol] as const,
  /** R23.5.0: Closed share positions */
  uiClosedSharePositions: (accountId: string) => ["ui", "shares", "positions", "closed", accountId] as const,
  uiPortfolioMetrics: (accountId?: string | null) => ["ui", "portfolio", "metrics", accountId ?? ""] as const,
  uiPortfolioRisk: (accountId?: string | null) => ["ui", "portfolio", "risk", accountId ?? ""] as const,
  uiPortfolioMtm: (accountId?: string | null) => ["ui", "portfolio", "mtm", accountId ?? ""] as const,
  uiPositionDecision: (positionId: string) =>
    ["ui", "positionDecision", positionId] as const,
  uiPositionEvents: (positionId: string) =>
    ["ui", "positionEvents", positionId] as const,
  uiAlerts: () => ["ui", "alerts"] as const,
  uiDiagnosticsHistory: (limit?: number) => ["ui", "diagnostics", "history", limit ?? 10] as const,
  uiStoresIntegrity: () => ["ui", "stores", "integrity"] as const,
  uiNotifications: (limit?: number, state?: string | null) =>
    (["ui", "notifications", limit ?? 100, state ?? ""] as const),
  uiWheelOverview: (accountId?: string | null) => ["ui", "wheel", "overview", accountId ?? ""] as const,
  uiMarketStatus: () => ["ui", "marketStatus"] as const,
  uiSnapshotsLatest: () => ["ui", "snapshots", "latest"] as const,
  /** R23.2 */
  uiDeltaOverrides: () => ["ui", "deltaOverrides"] as const,
  /** R25.5 */
  uiJournal: (params?: Record<string, unknown>) => ["ui", "journal", params ?? ""] as const,
  uiReportsMonthly: (month: string) => ["ui", "reports", "monthly", month] as const,
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

/** Phase 21.3: GET /api/ui/universe/symbols — effective list + overlay counts */
export function useUniverseSymbols() {
  return useQuery({
    queryKey: queryKeys.uiUniverseSymbols(),
    queryFn: () => apiGet<UniverseSymbolsResponse>(uiUniverseSymbolsPath()),
  });
}

/** Phase 21.3: POST /api/ui/universe/symbols — add symbol to overlay */
export function useUniverseAddSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { symbol: string }) =>
      apiPost<{ symbol: string; symbols: string[] }>(uiUniverseSymbolsPath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiUniverseSymbols() });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
    },
  });
}

/** Phase 21.3: DELETE /api/ui/universe/symbols/{symbol} — remove symbol (overlay) */
export function useUniverseRemoveSymbol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) =>
      apiDelete<{ removed: string; symbols: string[] }>(uiUniverseSymbolRemovePath(symbol)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiUniverseSymbols() });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
    },
  });
}

/** Phase 21.3: POST /api/ui/universe/reset — clear overlay */
export function useUniverseReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ reset: boolean; symbols: string[] }>(uiUniverseResetPath(), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiUniverseSymbols() });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
    },
  });
}

export function useSymbolDiagnostics(
  symbol: string,
  enabled = true,
  runId?: string | null
) {
  return useQuery({
    queryKey: queryKeys.symbolDiagnostics(symbol, runId),
    queryFn: () =>
      apiGet<SymbolDiagnosticsResponseExtended>(
        symbolDiagnosticsPath(symbol, false, runId)
      ),
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
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics", result.symbol] });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiUniverseSymbols() });
      qc.invalidateQueries({ queryKey: queryKeys.universe() });
      qc.invalidateQueries({ queryKey: queryKeys.sharesCandidates() });
      qc.invalidateQueries({ queryKey: ["ui", "decision"] });
    },
  });
}

/** R23.2: GET /api/ui/delta-overrides */
export function useDeltaOverridesList() {
  return useQuery({
    queryKey: queryKeys.uiDeltaOverrides(),
    queryFn: () => apiGet<{ overrides: Record<string, { delta_lo: number; delta_hi: number; updated_at_utc?: string }> }>(uiDeltaOverridesPath()),
  });
}

/** R23.2: POST /api/ui/delta-overrides/{symbol} */
export function useSetDeltaOverride(symbol: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { delta_lo: number; delta_hi: number }) =>
      apiPost<{ symbol: string; delta_lo: number; delta_hi: number }>(uiDeltaOverrideSymbolPath(symbol), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiDeltaOverrides() });
      qc.invalidateQueries({ queryKey: queryKeys.symbolDiagnostics(symbol, "") });
    },
  });
}

/** R23.2: DELETE /api/ui/delta-overrides/{symbol} */
export function useDeleteDeltaOverride(symbol: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete(uiDeltaOverrideSymbolPath(symbol)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiDeltaOverrides() });
      qc.invalidateQueries({ queryKey: queryKeys.symbolDiagnostics(symbol, "") });
    },
  });
}

export function useUiSystemHealth() {
  return useQuery({
    queryKey: queryKeys.uiSystemHealth(),
    queryFn: () => apiGet<UiSystemHealthResponse>(uiSystemHealthPath()),
  });
}

/** R22.5: Shares candidates (BUY SHARES recommendation only; no order placement). */
export interface SharesCandidatesResponse {
  shares_candidates: SharesPlan[];
}

export function useSharesCandidates() {
  return useQuery({
    queryKey: queryKeys.sharesCandidates(),
    queryFn: () => apiGet<SharesCandidatesResponse>(sharesCandidatesPath()),
  });
}

/** R24.1/R24.2: Action Needed — top_options, top_shares, recently_changed; severity and lifecycle fields. */
export interface ActionNeededItem {
  symbol: string;
  strategy: string;
  next_action_code: string;
  rationale_lines: string[];
  key_number: string | null;
  tab: string;
  accordion: string;
  accordion_id?: string;
  /** R24.2: high | medium | low for sort/display */
  severity?: string;
  /** R24.2: options — expiry, strike, dte, size, notional, pct_max_profit */
  expiry?: string;
  strike?: number;
  dte?: number;
  size?: number;
  notional?: number;
  pct_max_profit?: number;
  recommended_by?: string;
  /** R24.3: position lifecycle (request-time only) */
  mark_proxy?: number;
  assignment_risk?: { active: boolean; reason_code?: string | null };
  roll_window?: { active: boolean; dte?: number | null };
  recommended_action_code?: string;
  /** R24.4: mark provenance/freshness + roll rationale (request-time only; safe labels) */
  mark_value?: number;
  mark_source?: string;
  quote_ts?: string | null;
  mark_age_sec?: number | null;
  roll_window_threshold_dte?: number | null;
  roll_reason_codes?: string[] | null;
}
export interface ActionNeededResponse {
  top_options: ActionNeededItem[];
  top_shares: ActionNeededItem[];
  options?: ActionNeededItem[];
  shares?: ActionNeededItem[];
  recently_changed: unknown[];
}
export function useActionNeeded() {
  return useQuery({
    queryKey: queryKeys.actionNeeded(),
    queryFn: () => apiGet<ActionNeededResponse>(actionNeededPath()),
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
      qc.invalidateQueries({ queryKey: queryKeys.uiUniverseSymbols() });
      qc.invalidateQueries({ queryKey: queryKeys.sharesCandidates() });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
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
      qc.invalidateQueries({ queryKey: ["ui", "portfolio", "metrics"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioRisk() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
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
      qc.invalidateQueries({ queryKey: ["ui", "portfolio", "metrics"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioRisk() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
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
      qc.invalidateQueries({ queryKey: ["ui", "portfolio", "metrics"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioRisk() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
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
      qc.invalidateQueries({ queryKey: ["ui", "portfolio", "metrics"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioRisk() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
    },
  });
}

export function usePortfolio() {
  return useQuery({
    queryKey: queryKeys.uiPortfolio(),
    queryFn: () => apiGet<PortfolioResponse>(uiPortfolioPath()),
  });
}

/** Phase 21.1: GET /api/ui/account/summary */
export function useAccountSummary() {
  return useQuery({
    queryKey: queryKeys.uiAccountSummary(),
    queryFn: () => apiGet<AccountSummary>(uiAccountSummaryPath()),
  });
}

/** Phase 21.1: GET /api/ui/account/holdings */
export function useAccountHoldings() {
  return useQuery({
    queryKey: queryKeys.uiAccountHoldings(),
    queryFn: () => apiGet<AccountHoldingsResponse>(uiAccountHoldingsPath()),
  });
}

/** Phase 21.1: POST /api/ui/account/balances */
export function useSetBalances() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { cash: number; buying_power: number }) =>
      apiPost<{ summary: AccountSummary }>(uiAccountBalancesPath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountSummary() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountHoldings() });
    },
  });
}

/** Phase 21.1: POST /api/ui/account/holdings */
export function useUpsertHolding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { symbol: string; shares: number; avg_cost?: number | null }) =>
      apiPost<{ holding: AccountHolding }>(uiAccountHoldingsPath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountSummary() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountHoldings() });
    },
  });
}

/** Phase 21.1: DELETE /api/ui/account/holdings/{symbol} */
export function useDeleteHolding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) =>
      apiDelete<{ deleted: boolean; symbol: string }>(uiAccountHoldingsDeletePath(symbol)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountSummary() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAccountHoldings() });
    },
  });
}

/** R23.0: GET /api/ui/shares/positions?account_id= */
export function useSharesPositions(accountId: string | null) {
  return useQuery({
    queryKey: queryKeys.uiSharesPositions(accountId ?? "default"),
    queryFn: () => apiGet<SharesPositionsListResponse>(uiSharesPositionsListPath(accountId ?? "default")),
    enabled: !!accountId,
  });
}

/** R23.0: GET /api/ui/shares/positions/{symbol}?account_id= */
export function useSharePosition(accountId: string | null, symbol: string | null) {
  return useQuery({
    queryKey: queryKeys.uiSharePosition(accountId ?? "default", symbol ?? ""),
    queryFn: () =>
      apiGet<SharePosition>(uiSharePositionGetPath(symbol!, accountId ?? "default")),
    enabled: !!accountId && !!symbol,
  });
}

/** R23.0: POST /api/ui/shares/positions/{symbol} */
export function useUpsertSharePosition(symbol: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { account_id: string; quantity: number; avg_cost?: number | null; opened_at?: string | null; target_price?: number | null; stop_price?: number | null }) =>
      apiPost<SharePosition>(uiSharePositionUpsertPath(symbol!), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "shares"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
    },
  });
}

/** R23.0: DELETE /api/ui/shares/positions/{symbol}?account_id= */
export function useDeleteSharePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ accountId, symbol }: { accountId: string; symbol: string }) =>
      apiDelete<{ deleted: boolean; symbol: string }>(uiSharePositionDeletePath(symbol, accountId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "shares"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
    },
  });
}

/** R23.5.0: POST /api/ui/shares/positions/{symbol}/close — close position (exit_price, exit_date?, notes?). */
export function useCloseSharePosition(symbol: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { account_id: string; exit_price: number; exit_date?: string | null; notes?: string | null }) =>
      apiPost<ClosedSharePosition>(uiSharePositionClosePath(symbol!), payload),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["ui", "shares"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiSharesPositions(variables.account_id) });
      qc.invalidateQueries({ queryKey: queryKeys.uiClosedSharePositions(variables.account_id) });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
    },
  });
}

/** R23.5.0: GET /api/ui/shares/positions/closed?account_id= */
export function useClosedSharePositions(accountId: string | null) {
  return useQuery({
    queryKey: queryKeys.uiClosedSharePositions(accountId ?? "default"),
    queryFn: () => apiGet<ClosedSharePositionsListResponse>(uiSharesPositionsClosedPath(accountId ?? "default")),
    enabled: !!accountId,
  });
}

/** Phase 12.0: GET /api/ui/portfolio/metrics */
export function usePortfolioMetrics(accountId?: string | null) {
  return useQuery({
    queryKey: queryKeys.uiPortfolioMetrics(accountId),
    queryFn: () => apiGet<PortfolioMetricsResponse>(uiPortfolioMetricsPath(accountId)),
  });
}

/** Phase 14.0: GET /api/ui/portfolio/risk */
export interface PortfolioRiskBreach {
  type: string;
  subtype: string;
  current: number;
  limit: number;
  message: string;
  affected_symbols?: string[];
}

export interface PortfolioRiskResponse {
  status: "PASS" | "WARN" | "FAIL";
  account_id?: string;
  metrics: {
    capital_deployed?: number;
    total_capital?: number;
    buying_power?: number;
    deployed_pct?: number;
    top_symbol?: string;
    top_symbol_collateral?: number;
    near_expiry_count?: number;
    open_positions_count?: number;
  };
  breaches: PortfolioRiskBreach[];
  error?: string;
}

export function usePortfolioRisk(accountId?: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.uiPortfolioRisk(accountId),
    queryFn: () => apiGet<PortfolioRiskResponse>(uiPortfolioRiskPath(accountId)),
    enabled,
  });
}

/** Phase 18.0: GET /api/ui/wheel/overview */
export interface WheelOverviewNextAction {
  action_type: string;
  suggested_contract_key?: string | null;
  reasons?: string[];
  blocked_by?: string[];
}

export interface WheelOverviewSuggestedCandidate {
  strategy?: string;
  expiry?: string;
  strike?: number;
  delta?: number;
  credit_estimate?: number;
  max_loss?: number;
  contract_key?: string;
  option_symbol?: string;
}

/** Phase 20.0: Last wheel action for manual override indicator */
export interface WheelOverviewLastWheelAction {
  action?: string;
  at_utc?: string;
}

export interface WheelOverviewRow {
  symbol: string;
  wheel_state: string;
  last_updated_utc?: string | null;
  /** Phase 20.0: True when symbol has a recent ASSIGNED/UNASSIGNED/RESET action */
  manual_override?: boolean;
  last_wheel_action?: WheelOverviewLastWheelAction | null;
  next_action: WheelOverviewNextAction;
  suggested_candidate?: WheelOverviewSuggestedCandidate | null;
  risk_status: string;
  last_decision_score?: number | null;
  last_decision_band?: string | null;
  last_decision_verdict?: string | null;
  links: { run_id?: string | null };
  open_position?: {
    position_id?: string;
    contract_key?: string;
    strategy?: string;
    contracts?: number;
  } | null;
}

/** Phase 20.0: Wheel state integrity from diagnostics (enables Repair button when FAIL) */
export interface WheelOverviewIntegrity {
  status?: "PASS" | "FAIL";
  recommended_action?: string | null;
  details?: { mismatches?: unknown[]; symbols_checked?: number };
}

export interface WheelOverviewResponse {
  symbols: Record<string, WheelOverviewRow>;
  risk_status: string;
  run_id?: string | null;
  wheel_integrity?: WheelOverviewIntegrity | null;
  error?: string;
}

export function useWheelOverview(accountId?: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.uiWheelOverview(accountId),
    queryFn: () => apiGet<WheelOverviewResponse>(uiWheelOverviewPath(accountId)),
    enabled,
  });
}

/** Phase 20.0: POST /api/ui/wheel/{symbol}/assign */
export function useWheelAssign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => apiPost<{ symbol: string; state: string }>(uiWheelAssignPath(symbol), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
    },
  });
}

/** Phase 20.0: POST /api/ui/wheel/{symbol}/unassign */
export function useWheelUnassign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => apiPost<{ symbol: string; state: string }>(uiWheelUnassignPath(symbol), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
    },
  });
}

/** Phase 20.0: POST /api/ui/wheel/{symbol}/reset (body: { confirm: true }) */
export function useWheelReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => apiPost<{ symbol: string; state: string }>(uiWheelResetPath(symbol), { confirm: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
    },
  });
}

/** Phase 20.0: POST /api/ui/wheel/repair — rebuild wheel_state from open positions */
export interface WheelRepairResponse {
  repaired_symbols: string[];
  removed_symbols: string[];
  status: string;
}
export function useWheelRepair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<WheelRepairResponse>(uiWheelRepairPath(), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "wheel"] });
    },
  });
}

/** Phase 15.0: GET /api/ui/portfolio/mtm */
export interface PortfolioMtmResponse {
  realized_total: number;
  unrealized_total: number;
  positions: Array<{
    position_id: string;
    symbol: string;
    status?: string;
    mark?: number;
    unrealized_pnl?: number;
    realized_pnl?: number;
  }>;
}

export function usePortfolioMtm(accountId?: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.uiPortfolioMtm(accountId),
    queryFn: () => apiGet<PortfolioMtmResponse>(uiPortfolioMtmPath(accountId)),
    enabled,
  });
}

/** Phase 15.0: POST /api/ui/positions/marks/refresh */
export interface MarksRefreshResponse {
  updated_count: number;
  skipped_count: number;
  errors: string[];
}

export function useRefreshMarks(accountId?: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<MarksRefreshResponse>(uiPositionsMarksRefreshPath(accountId), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioMetrics(accountId ?? undefined) });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioMtm(accountId ?? undefined) });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioRisk(accountId ?? undefined) });
      qc.invalidateQueries({ queryKey: queryKeys.uiTrackedPositions() });
    },
  });
}

/** Phase 11.1: GET /api/ui/positions/{id}/decision — decision for a position (exact run or latest with warning) */
export interface PositionDecisionResponse {
  artifact: DecisionArtifactV2;
  artifact_version?: string;
  evaluation_timestamp_utc?: string | null;
  run_id?: string | null;
  exact_run: boolean;
  warning?: string | null;
}

export function usePositionDecision(positionId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.uiPositionDecision(positionId ?? ""),
    queryFn: () =>
      apiGet<PositionDecisionResponse>(uiPositionDecisionPath(positionId!)),
    enabled: enabled && !!positionId,
  });
}

/** Phase 13.0: GET /api/ui/positions/{id}/events */
export interface PositionEvent {
  event_id: string;
  position_id: string;
  type: string;
  at_utc: string;
  payload?: Record<string, unknown>;
}

export interface PositionEventsResponse {
  position_id: string;
  events: PositionEvent[];
}

export function usePositionEvents(positionId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.uiPositionEvents(positionId ?? ""),
    queryFn: () =>
      apiGet<PositionEventsResponse>(uiPositionEventsPath(positionId!)),
    enabled: enabled && !!positionId,
  });
}

export interface RollPositionPayload {
  contract_key?: string;
  option_symbol?: string;
  strike?: number;
  expiration?: string;
  expiry?: string;
  contracts?: number;
  close_debit: number;
  open_credit: number;
}

export interface RollPositionResponse {
  closed_position_id: string;
  new_position: Record<string, unknown>;
}

export function useRollPosition(positionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RollPositionPayload) =>
      apiPost<RollPositionResponse>(uiPositionRollPath(positionId!), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiTrackedPositions() });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: ["ui", "portfolio", "metrics"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolioRisk() });
      qc.invalidateQueries({ queryKey: queryKeys.uiAlerts() });
      if (positionId) {
        qc.invalidateQueries({ queryKey: queryKeys.uiPositionEvents(positionId) });
      }
    },
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
      qc.invalidateQueries({ queryKey: queryKeys.uiUniverseSymbols() });
      qc.invalidateQueries({ queryKey: queryKeys.sharesCandidates() });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
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
  checks: Array<{ check: string; status: string; details: Record<string, unknown>; recommended_action?: string | null }>;
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

/** Phase 17.0: Store integrity scan */
export interface StoresIntegrityResponse {
  stores: Record<
    string,
    {
      path: string;
      exists: boolean;
      total_lines: number;
      invalid_lines: number;
      invalid_line_numbers?: number[];
      last_valid_line: number;
      last_valid_offset: number;
    }
  >;
}

export function useStoresIntegrity() {
  return useQuery({
    queryKey: queryKeys.uiStoresIntegrity(),
    queryFn: () => apiGet<StoresIntegrityResponse>(uiStoresIntegrityPath()),
  });
}

/** Phase 17.0: Repair store */
export interface StoresRepairResponse {
  store: string;
  before: { total_lines: number; invalid_lines: number };
  after: { valid_count: number; removed_count: number };
  backup_path?: string | null;
}

export function useRepairStore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (store: string) =>
      apiPost<StoresRepairResponse>(uiStoresRepairPath(store), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiStoresIntegrity() });
      qc.invalidateQueries({ queryKey: queryKeys.uiDiagnosticsHistory() });
    },
  });
}

// Notifications (Phase 8.3, 8.6, 10.3)
export interface UiNotification {
  id?: string;
  timestamp_utc: string;
  /** R25.4: Alias for timestamp_utc */
  created_ts?: string | null;
  severity: string;
  type: string;
  /** Phase 8.6: Subtype (RUN_ERRORS, LOW_COMPLETENESS, ORATS_STALE, etc.) */
  subtype?: string | null;
  symbol?: string | null;
  message: string;
  details?: Record<string, unknown>;
  /** Phase 10.3: Acknowledgment fields */
  ack_at_utc?: string | null;
  ack_by?: string | null;
  /** R25.4: When acked/archived */
  acked_ts?: string | null;
  archived_ts?: string | null;
  /** Phase 21.5: Lifecycle state */
  state?: "NEW" | "ACKED" | "ARCHIVED" | "DELETED";
  updated_at?: string | null;
}

export interface UiNotificationsResponse {
  notifications: UiNotification[];
}

export function useNotifications(
  limit = 100,
  state?: string | null,
  symbol?: string | null,
  type?: string | null,
  offset?: number
) {
  return useQuery({
    queryKey: queryKeys.uiNotifications(limit, state),
    queryFn: () =>
      apiGet<UiNotificationsResponse>(uiNotificationsPath(limit, state, symbol, type, offset)),
  });
}

/** Phase 10.3: Ack a notification. Invalidates notifications query. */
export function useAckNotification(_limit = 100) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      apiPost<{ status: string; ack_at_utc?: string }>(
        uiNotificationAckPath(notificationId),
        {}
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "notifications"] });
    },
  });
}

/** Phase 21.5: Archive a notification. */
export function useArchiveNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      apiPost<{ status: string; updated_at?: string }>(
        uiNotificationArchivePath(notificationId),
        {}
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "notifications"] });
    },
  });
}

/** Phase 21.5: Delete (soft) a notification. */
export function useDeleteNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) =>
      apiDelete<{ status: string; updated_at?: string }>(
        uiNotificationDeletePath(notificationId)
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "notifications"] });
    },
  });
}

/** Phase 21.5: Archive all NEW/ACKED notifications. */
export function useArchiveAllNotifications() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ status: string; archived_count: number }>(
        uiNotificationsArchiveAllPath(),
        {}
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "notifications"] });
    },
  });
}

/** R25.4: Ack all NEW notifications. */
export function useAckBulkNotifications() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ status: string; acked_count: number }>(uiNotificationsAckBulkPath(), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "notifications"] });
    },
  });
}

/** R25.4: Archive all ACKED notifications. */
export function useArchiveBulkNotifications() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ status: string; archived_count: number }>(
        uiNotificationsArchiveBulkPath(),
        {}
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "notifications"] });
    },
  });
}

/** R25.5: Journal entry (SQLite-backed). */
export interface JournalEntry {
  id: string;
  created_ts: string;
  trade_date: string;
  as_of_ts?: string | null;
  symbol: string;
  strategy: string;
  action: string;
  qty: number;
  price?: number | null;
  premium?: number | null;
  fees?: number | null;
  contract_key?: string | null;
  expiry?: string | null;
  strike?: number | null;
  right?: string | null;
  notes?: string | null;
  tags?: string | null;
  realized_pl?: number | null;
  link_id?: string | null;
}
export interface JournalListResponse {
  entries: JournalEntry[];
}
export interface JournalCreateResponse {
  entry: JournalEntry;
}
export interface MonthlyReportResponse {
  month: string;
  total_realized_pl: number;
  by_strategy: Record<string, number>;
  trade_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_hold_days: number | null;
  top_winners: { symbol: string; realized_pl: number | null; strategy: string }[];
  top_losers: { symbol: string; realized_pl: number | null; strategy: string }[];
  fees_total: number;
}

export function useJournal(params: {
  from_date?: string;
  to_date?: string;
  symbol?: string;
  strategy?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: queryKeys.uiJournal(params),
    queryFn: () => apiGet<JournalListResponse>(uiJournalPath(params)),
  });
}

export function useJournalCreate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<JournalCreateResponse>(uiJournalPath({}), payload).then((r) => r.entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "journal"] });
    },
  });
}

export function useJournalUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      apiPatch<JournalCreateResponse>(uiJournalEntryPath(id), payload).then((r) => r.entry),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "journal"] });
    },
  });
}

export function useJournalExport() {
  return useMutation({
    mutationFn: ({ from_date, to_date }: { from_date: string; to_date: string }) =>
      apiPostText(uiJournalExportPath(from_date, to_date)),
  });
}

export function useReportsMonthly(month: string) {
  return useQuery({
    queryKey: queryKeys.uiReportsMonthly(month),
    queryFn: () => apiGet<MonthlyReportResponse>(uiReportsMonthlyPath(month)),
    enabled: !!month && month.length === 7 && month[4] === "-",
  });
}

/** Phase 21.5: Send test Slack message (admin). */
/** R21.5.1: Send test Slack to a channel (signals | daily | data_health | critical). */
export function useAdminSlackTest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (channel: string) =>
      apiPost<{
        status: string;
        channel?: string;
        message?: string;
        ok?: boolean;
        updated_status?: Record<string, unknown>;
      }>(uiAdminSlackTestPath(channel), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
    },
  });
}

/** Phase 21.5: Force evaluation now (admin). */
export function useAdminEvaluationForce() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{
        status: string;
        started?: boolean;
        run_id?: string;
        reason?: string;
        forced?: boolean;
      }>(uiAdminEvaluationForcePath(), {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
      qc.invalidateQueries({ queryKey: ["ui", "decision"] });
    },
  });
}
