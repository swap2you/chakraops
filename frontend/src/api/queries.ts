/**
 * TanStack Query hooks for UI API endpoints.
 * Requires @tanstack/react-query.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiGetBlob, apiPatch, apiPost, apiPostNoBody, apiPostText } from "./client";
import type {
  ArtifactListResponse,
  DecisionArtifactV2,
  DecisionResponse,
  UniverseResponse,
  SymbolDiagnosticsResponseExtended,
  UiSystemHealthResponse,
  UiEarningsDebugResponse,
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
  UiPositionsUnifiedResponse,
  UiPositionsUnifiedRebuildResponse,
  UiPositionsUnifiedIntegrityCheckResponse,
  UiPositionsUnifiedIntegrityCheckResult,
  UiReconcileDiffResponse,
  UiPositionsUnifiedDbResponse,
  DataReliabilityHealthResponse,
  WeeklyUniverseResponse,
  RefreshHistoryResponse,
  DecisionProfilesResponse,
  DecisionEvaluateRequest,
  DecisionEvaluateResponse,
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

/** R28.8: GET /api/ui/positions/unified/reconcile-diff */
function uiPositionsUnifiedReconcileDiffPath(params: {
  include_paper?: boolean;
  symbol?: string | null;
  limit?: number;
}): string {
  const q = new URLSearchParams();
  q.set("include_paper", String(params.include_paper !== false));
  if (params.symbol?.trim()) q.set("symbol", params.symbol.trim());
  if (params.limit != null) q.set("limit", String(params.limit));
  return `/api/ui/positions/unified/reconcile-diff?${q.toString()}`;
}

/** R28.9: GET /api/ui/positions/unified/db — DB-first read (what is stored). */
function uiPositionsUnifiedDbPath(params: {
  state?: string;
  include_paper?: boolean;
  instrument_type?: string | null;
  symbol?: string | null;
  limit?: number;
}): string {
  const q = new URLSearchParams();
  if (params.state) q.set("state", params.state);
  if (params.include_paper !== undefined) q.set("include_paper", String(params.include_paper));
  if (params.instrument_type?.trim()) q.set("instrument_type", params.instrument_type.trim());
  if (params.symbol?.trim()) q.set("symbol", params.symbol.trim());
  if (params.limit != null) q.set("limit", String(params.limit));
  return `/api/ui/positions/unified/db?${q.toString()}`;
}

/** R28.7: POST /api/ui/positions/unified/rebuild */
function uiPositionsUnifiedRebuildPath(includePaper: boolean): string {
  return `/api/ui/positions/unified/rebuild?include_paper=${includePaper}`;
}

/** R29.3: POST /api/ui/positions/unified/integrity-check — body: { include_paper: boolean }. */
const UI_POSITIONS_UNIFIED_INTEGRITY_CHECK_PATH = "/api/ui/positions/unified/integrity-check";

/** R29.7: GET /api/ui/positions/unified/integrity-bundle — returns ZIP; query params include_paper, symbol?, limit. */
export function uiIntegrityBundlePath(includePaper: boolean, symbol: string | null | undefined, limit: number = 200): string {
  const q = new URLSearchParams();
  q.set("include_paper", String(includePaper));
  q.set("limit", String(Math.min(1000, Math.max(1, limit))));
  if (symbol != null && symbol.trim() !== "") q.set("symbol", symbol.trim());
  return `/api/ui/positions/unified/integrity-bundle?${q.toString()}`;
}

/** R29.7: Download integrity bundle ZIP (manual; when status is Review). */
export async function downloadIntegrityBundle(includePaper: boolean, symbol?: string | null): Promise<void> {
  const { apiGetBlob } = await import("@/api/client");
  const path = uiIntegrityBundlePath(includePaper, symbol ?? null, 200);
  const blob = await apiGetBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `integrity_bundle_${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

/** R25.8: Earnings debug (diagnostics only; safe fields). */
function uiEarningsDebugPath(symbol: string): string {
  return `/api/ui/earnings/debug?symbol=${encodeURIComponent(symbol)}`;
}

/** R22.5: Shares candidates (BUY SHARES recommendation only). */
function sharesCandidatesPath(): string {
  return `/api/ui/shares-candidates`;
}

/** R24.1: Action Needed — top options + top shares for Dashboard. */
function actionNeededPath(): string {
  return `/api/ui/action-needed`;
}

/** R26.3: Today summary for Today page. */
function todaySummaryPath(): string {
  return `/api/ui/today/summary`;
}

/** R26.4: Ops checklist and summaries. */
function opsChecklistPath(kind: string, key: string): string {
  return `/api/ui/ops/checklist?kind=${encodeURIComponent(kind)}&key=${encodeURIComponent(key)}`;
}
function opsChecklistMarkDonePath(): string {
  return `/api/ui/ops/checklist/mark-done`;
}
/** R26.9: Ops execution log (write event). */
function opsExecutionLogPath(): string {
  return `/api/ui/ops/execution-log`;
}
function opsEodSummaryPath(date: string): string {
  return `/api/ui/ops/eod-summary?date=${encodeURIComponent(date)}`;
}
function opsWeeklySummaryPath(week: string): string {
  return `/api/ui/ops/weekly-summary?week=${encodeURIComponent(week)}`;
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

/** R27.9: GET /api/ui/positions/unified */
function uiPositionsUnifiedPath(params: {
  state?: string;
  include_paper?: boolean;
  instrument_type?: string | null;
  symbol?: string | null;
}): string {
  const q = new URLSearchParams();
  if (params.state) q.set("state", params.state);
  if (params.include_paper !== undefined) q.set("include_paper", String(params.include_paper));
  if (params.instrument_type?.trim()) q.set("instrument_type", params.instrument_type.trim());
  if (params.symbol?.trim()) q.set("symbol", params.symbol.trim());
  const s = q.toString();
  return s ? `/api/ui/positions/unified?${s}` : "/api/ui/positions/unified";
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
/** R26.2: Trade ticket */
function tradeTicketPath(symbol: string, strategy: string, action: string): string {
  const p = new URLSearchParams();
  p.set("symbol", symbol);
  p.set("strategy", strategy);
  p.set("action", action);
  return `/api/ui/trade-ticket?${p.toString()}`;
}

/** R30.0: GET /api/ui/trade-ticket/readiness — execution readiness checks (safe labels only). */
function tradeTicketReadinessPath(symbol: string, mode: "live" | "paper", ticketKind: string): string {
  const p = new URLSearchParams();
  p.set("symbol", symbol);
  p.set("mode", mode);
  p.set("ticket_kind", ticketKind);
  return `/api/ui/trade-ticket/readiness?${p.toString()}`;
}

/** R30.2: GET /api/ui/trade-ticket/readiness-pack — returns ZIP; query symbol, mode, ticket_kind, include_paper. */
export function readinessPackPath(
  symbol: string,
  mode: "live" | "paper",
  ticketKind: string,
  includePaper: boolean = true
): string {
  const p = new URLSearchParams();
  p.set("symbol", symbol.trim());
  p.set("mode", mode);
  p.set("ticket_kind", ticketKind);
  p.set("include_paper", String(includePaper));
  return `/api/ui/trade-ticket/readiness-pack?${p.toString()}`;
}

/** R30.2: Download readiness pack ZIP (manual; sanitized, deterministic). */
export async function downloadReadinessPack(
  symbol: string,
  mode: "live" | "paper",
  ticketKind: string,
  includePaper: boolean = true
): Promise<void> {
  const path = readinessPackPath(symbol, mode, ticketKind, includePaper);
  const blob = await apiGetBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `readiness_pack_${symbol}_${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

/** R30.3: Download attached readiness pack JSON for a journal entry. */
export async function downloadJournalReadinessPack(entryId: string, symbol: string): Promise<void> {
  const path = uiJournalEntryReadinessPackPath(entryId);
  const data = await apiGet<Record<string, unknown>>(path);
  const jsonStr = JSON.stringify(data, null, 2);
  const blob = new Blob([jsonStr], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `readiness_pack_${symbol}_${entryId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/** R30.4: Readiness pack bundle shape (from GET attachment). */
export interface ReadinessPackBundle {
  manifest?: Record<string, unknown>;
  readiness?: {
    status?: string;
    status_label?: string;
    as_of_utc?: string;
    checks?: Array<{ code?: string; status?: string; label?: string; detail?: string; action_label?: string; action_href?: string }>;
    order_stub?: { title?: string; lines?: string[] };
  };
  system_health_subset?: Record<string, unknown>;
  notes?: Record<string, unknown>;
}

/** R30.4: Fetch journal entry readiness pack JSON for in-app viewer. */
export function useJournalEntryReadinessPack(entryId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["ui", "journal", "readiness-pack", entryId],
    queryFn: () => apiGet<ReadinessPackBundle>(uiJournalEntryReadinessPackJsonPath(entryId!)),
    enabled: !!entryId && enabled,
  });
}

function uiJournalPath(params: { from_date?: string; to_date?: string; symbol?: string; strategy?: string; limit?: number; offset?: number; include_paper?: boolean; paper_only?: boolean }): string {
  const p = new URLSearchParams();
  if (params.from_date) p.set("from_date", params.from_date);
  if (params.to_date) p.set("to_date", params.to_date);
  if (params.symbol) p.set("symbol", params.symbol);
  if (params.strategy) p.set("strategy", params.strategy);
  if (params.limit != null) p.set("limit", String(params.limit));
  if (params.offset != null) p.set("offset", String(params.offset));
  if (params.include_paper !== undefined) p.set("include_paper", String(params.include_paper));
  if (params.paper_only !== undefined) p.set("paper_only", String(params.paper_only));
  const q = p.toString();
  return q ? `/api/ui/journal?${q}` : "/api/ui/journal";
}
function uiJournalFromTicketPath(): string {
  return "/api/ui/journal/from-ticket";
}
function uiJournalExportPath(from_date: string, to_date: string): string {
  return `/api/ui/journal/export?from_date=${encodeURIComponent(from_date)}&to_date=${encodeURIComponent(to_date)}`;
}
function uiJournalEntryPath(id: string): string {
  return `/api/ui/journal/${encodeURIComponent(id)}`;
}
/** R30.3/R30.4: GET journal entry attachment readiness-pack (JSON bundle) */
export function uiJournalEntryReadinessPackJsonPath(entryId: string): string {
  return `/api/ui/journal/entry/${encodeURIComponent(entryId)}/attachment/readiness-pack`;
}
function uiJournalEntryReadinessPackPath(entryId: string): string {
  return uiJournalEntryReadinessPackJsonPath(entryId);
}

/** R30.5: GET journal readiness-packs bulk export (JSONL). Params: has_pack, start_utc?, end_utc?, limit. */
export function uiJournalReadinessPacksExportPath(params: {
  has_pack?: boolean;
  start_utc?: string;
  end_utc?: string;
  limit?: number;
}): string {
  const p = new URLSearchParams();
  if (params.has_pack !== undefined) p.set("has_pack", String(params.has_pack));
  if (params.start_utc) p.set("start_utc", params.start_utc);
  if (params.end_utc) p.set("end_utc", params.end_utc);
  if (params.limit != null) p.set("limit", String(params.limit));
  return `/api/ui/journal/readiness-packs/export?${p.toString()}`;
}

/** R30.5: Download readiness packs as JSONL (uses current filters: has_pack, date range, limit). */
export async function downloadJournalReadinessPacksJsonl(params: {
  has_pack: boolean;
  from_date: string;
  to_date: string;
  limit?: number;
}): Promise<void> {
  const start_utc = `${params.from_date}T00:00:00Z`;
  const end_utc = `${params.to_date}T23:59:59Z`;
  const path = uiJournalReadinessPacksExportPath({
    has_pack: params.has_pack,
    start_utc,
    end_utc,
    limit: params.limit ?? 200,
  });
  const blob = await apiGetBlob(path);
  const ts = new Date().toISOString().slice(0, 19).replace(/:/g, "-");
  const filename = `readiness_packs_${ts}Z.jsonl`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
/** R25.5: Reports monthly. R27.0: include_paper */
function uiReportsMonthlyPath(month: string, include_paper?: boolean): string {
  const p = new URLSearchParams();
  p.set("month", month);
  if (include_paper !== undefined) p.set("include_paper", String(include_paper));
  return `/api/ui/reports/monthly?${p.toString()}`;
}
/** R27.0: Paper trading */
function paperExecutePath(): string {
  return "/api/ui/paper/execute";
}
function paperPositionsPath(params: { status?: string; symbol?: string; strategy?: string; include_marks?: boolean }): string {
  const p = new URLSearchParams();
  if (params.status) p.set("status", params.status);
  if (params.symbol) p.set("symbol", params.symbol);
  if (params.strategy) p.set("strategy", params.strategy);
  if (params.include_marks !== undefined) p.set("include_marks", String(params.include_marks));
  const q = p.toString();
  return q ? `/api/ui/paper/positions?${q}` : "/api/ui/paper/positions";
}
/** R27.2: Single paper position by id */
function paperPositionByIdPath(positionId: string, include_marks?: boolean): string {
  const p = new URLSearchParams();
  if (include_marks !== undefined) p.set("include_marks", String(include_marks));
  const q = p.toString();
  const base = `/api/ui/paper/positions/${encodeURIComponent(positionId)}`;
  return q ? `${base}?${q}` : base;
}
/** R27.2: Close paper position */
function paperClosePath(): string {
  return "/api/ui/paper/close";
}
function paperSummaryPath(month: string): string {
  return `/api/ui/paper/summary?month=${encodeURIComponent(month)}`;
}
/** R26.5: Monthly close pack. R27.1: pack=live|paper, include_paper for generate */
function uiMonthlyCloseFilesPath(month: string, pack?: "live" | "paper"): string {
  const p = new URLSearchParams();
  p.set("month", month);
  if (pack) p.set("pack", pack);
  return `/api/ui/reports/monthly/close/files?${p.toString()}`;
}
function uiMonthlyCloseDownloadPath(month: string, file: string, pack?: "live" | "paper"): string {
  const p = new URLSearchParams();
  p.set("month", month);
  p.set("file", file);
  if (pack) p.set("pack", pack);
  return `/api/ui/reports/monthly/close/download?${p.toString()}`;
}
function uiMonthlyCloseGeneratePath(month: string, include_paper?: boolean): string {
  const p = new URLSearchParams();
  p.set("month", month);
  if (include_paper) p.set("include_paper", "true");
  return `/api/ui/reports/monthly/close?${p.toString()}`;
}
/** R27.5: Backtest replay */
function uiBacktestRunPath(): string {
  return "/api/ui/backtest/run";
}
function uiBacktestRunsPath(limit?: number, offset?: number): string {
  const p = new URLSearchParams();
  if (limit != null) p.set("limit", String(limit));
  if (offset != null) p.set("offset", String(offset));
  const q = p.toString();
  return q ? `/api/ui/backtest/runs?${q}` : "/api/ui/backtest/runs";
}
function uiBacktestDownloadPath(run_id: string, file: "summary_json" | "trades_csv"): string {
  const p = new URLSearchParams();
  p.set("run_id", run_id);
  p.set("file", file);
  return `/api/ui/backtest/download?${p.toString()}`;
}
/** R25.6: Universe Admin */
function uiUniverseAdminPath(params: { limit?: number; offset?: number; status?: string }): string {
  const p = new URLSearchParams();
  if (params.limit != null) p.set("limit", String(params.limit));
  if (params.offset != null) p.set("offset", String(params.offset));
  if (params.status) p.set("status", params.status);
  const q = p.toString();
  return q ? `/api/ui/universe/admin?${q}` : "/api/ui/universe/admin";
}
/** R25.6: Universe Health */
function uiUniverseHealthPath(): string {
  return "/api/ui/universe/health";
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
  operationsStatus: () => ["operations", "status"] as const,
  dataReliabilityHealth: () => ["ui", "dataReliability", "health"] as const,
  dataReliabilityWeeklyUniverse: () => ["ui", "dataReliability", "weeklyUniverse"] as const,
  dataReliabilityRefreshHistory: (limit: number) =>
    ["ui", "dataReliability", "refreshHistory", limit] as const,
  decisionEngineProfiles: () => ["ui", "decisionEngine", "profiles"] as const,
  uiEarningsDebug: (symbol: string) => ["ui", "earningsDebug", symbol] as const,
  sharesCandidates: () => ["ui", "sharesCandidates"] as const,
  actionNeeded: () => ["ui", "actionNeeded"] as const,
  todaySummary: () => ["ui", "todaySummary"] as const,
  opsChecklist: (kind: string, key: string) => ["ui", "opsChecklist", kind, key] as const,
  opsEodSummary: (date: string) => ["ui", "opsEodSummary", date] as const,
  opsWeeklySummary: (week: string) => ["ui", "opsWeeklySummary", week] as const,
  paperPositions: (params: Record<string, unknown>) => ["ui", "paper", "positions", params] as const,
  paperSummary: (month: string) => ["ui", "paper", "summary", month] as const,
  uiPositions: () => ["ui", "positions"] as const,
  /** R27.9 */
  uiPositionsUnified: (params: Record<string, unknown>) => ["ui", "positions", "unified", params] as const,
  /** R28.8 */
  uiReconcileDiff: (params: { include_paper?: boolean; symbol?: string | null; limit?: number }) =>
    ["ui", "positions", "unified", "reconcile-diff", params] as const,
  /** R29.4 */
  uiIntegrityCheckResult: () => ["ui", "positions", "unified", "integrity-check"] as const,
  /** R28.9 */
  uiPositionsUnifiedDb: (params: Record<string, unknown>) => ["ui", "positions", "unified", "db", params] as const,
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
  tradeTicket: (symbol: string, strategy: string, action: string) =>
    ["ui", "tradeTicket", symbol, strategy, action] as const,
  uiReportsMonthly: (month: string) => ["ui", "reports", "monthly", month] as const,
  uiMonthlyCloseFiles: (month: string, pack?: "live" | "paper") => ["ui", "reports", "monthly", "close", "files", month, pack ?? "live"] as const,
  /** R27.5 */
  uiBacktestRuns: (limit?: number, offset?: number) => ["ui", "backtest", "runs", limit ?? 50, offset ?? 0] as const,
  /** R25.6 */
  uiUniverseAdmin: (params?: Record<string, unknown>) => ["ui", "universe", "admin", params ?? ""] as const,
  uiUniverseHealth: () => ["ui", "universe", "health"] as const,
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

// R36.2 — Universe V2 (additive, read-only). Authoritative reads serve the published snapshot.
export function useUniverseV2Summary() {
  return useQuery({
    queryKey: ["ui", "universe-v2", "summary"] as const,
    queryFn: () => apiGet<import("./types").UniverseV2Summary>("/api/ui/universe-v2/summary"),
  });
}

export function useUniverseV2Records(params: { page?: number; page_size?: number; lifecycle?: string } = {}) {
  const { page = 1, page_size = 200, lifecycle } = params;
  const qs = new URLSearchParams();
  qs.set("page", String(page));
  qs.set("page_size", String(page_size));
  if (lifecycle) qs.set("lifecycle", lifecycle);
  return useQuery({
    queryKey: ["ui", "universe-v2", "records", page, page_size, lifecycle ?? "all"] as const,
    queryFn: () => apiGet<import("./types").UniverseV2RecordsResponse>(`/api/ui/universe-v2/records?${qs.toString()}`),
  });
}

export function useUniverseV2Record(symbol: string | null) {
  return useQuery({
    queryKey: ["ui", "universe-v2", "record", symbol] as const,
    queryFn: () => apiGet<import("./types").UniverseV2Record>(`/api/ui/universe-v2/records/${encodeURIComponent(symbol!)}`),
    enabled: !!symbol,
    retry: false,
  });
}

export function useUniverseV2Membership(strategy: string | null) {
  return useQuery({
    queryKey: ["ui", "universe-v2", "membership", strategy] as const,
    queryFn: () => apiGet<import("./types").UniverseV2MembershipResponse>(`/api/ui/universe-v2/membership/${encodeURIComponent(strategy!)}`),
    enabled: !!strategy,
  });
}

export function useUniverseV2Refresh() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ ok: boolean; version: number; status: string }>("/api/ui/universe-v2/refresh", {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "universe-v2"] });
    },
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

/** R35.0: operations scheduler, jobs, backup status */
export function useOperationsStatus() {
  return useQuery({
    queryKey: queryKeys.operationsStatus(),
    queryFn: () => apiGet<import("./types").OperationsStatusResponse>("/api/operations/status"),
  });
}

// R32.0: read-only data-reliability hooks (provider health, freshness/cache/
// retry/rate-limit policy, deterministic weekly universe, refresh history,
// explicit event/earnings calendar availability). No secrets are exposed.
export function useDataReliabilityHealth() {
  return useQuery({
    queryKey: queryKeys.dataReliabilityHealth(),
    queryFn: () =>
      apiGet<DataReliabilityHealthResponse>("/api/ui/data-reliability/health"),
  });
}

export function useWeeklyUniverse() {
  return useQuery({
    queryKey: queryKeys.dataReliabilityWeeklyUniverse(),
    queryFn: () =>
      apiGet<WeeklyUniverseResponse>("/api/ui/data-reliability/universe/weekly"),
  });
}

export function useUniverseRefreshHistory(limit = 20) {
  return useQuery({
    queryKey: queryKeys.dataReliabilityRefreshHistory(limit),
    queryFn: () =>
      apiGet<RefreshHistoryResponse>(
        `/api/ui/data-reliability/universe/refresh-history?limit=${limit}`,
      ),
  });
}

// R33.0: canonical decision-engine read-only contract. Advisory, manual-only.
export function useDecisionProfiles() {
  return useQuery({
    queryKey: queryKeys.decisionEngineProfiles(),
    queryFn: () =>
      apiGet<DecisionProfilesResponse>("/api/ui/decision-engine/profiles"),
  });
}

export function useEvaluateDecisions() {
  return useMutation({
    mutationFn: (payload: DecisionEvaluateRequest) =>
      apiPost<DecisionEvaluateResponse>(
        "/api/ui/decision-engine/evaluate",
        payload,
      ),
  });
}

/** R25.8: Earnings debug for probe symbol (diagnostics only; safe fields). */
export function useEarningsDebug(symbol: string) {
  return useQuery({
    queryKey: queryKeys.uiEarningsDebug(symbol),
    queryFn: () => apiGet<UiEarningsDebugResponse>(uiEarningsDebugPath(symbol)),
    enabled: !!symbol?.trim(),
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
  /** R26.0: Portfolio-aware sizing (request-time only; safe codes). */
  recommended_qty?: number | null;
  recommended_contracts?: number | null;
  recommended_notional_usd?: number | null;
  sizing_constraints_hit?: string[] | null;
  sizing_recommended_by?: string | null;
  /** R26.1: CSP cash-secured + risk proxy (advisory). */
  cash_secured_available_usd?: number | null;
  csp_risk_proxy_move_pct?: number | null;
  csp_risk_proxy_loss_per_contract_usd?: number | null;
  csp_risk_proxy_cap_contracts?: number | null;
  csp_risk_proxy_enforced?: boolean | null;
}
// R34.0 (H-5 cutover): canonical authoritative live recommendation block.
export interface CanonicalLiveItem {
  symbol: string;
  strategy: string;
  profile?: string;
  next_action_code: string;
  decision_status: string;
  capital_required?: number | null;
  expected_return_pct?: number | null;
  expected_return_dollars?: number | null;
  score?: number | null;
  rank?: number | null;
  reason_codes?: string[];
  risk_flags?: string[];
  sizing?: Record<string, unknown> | null;
  selected_contract?: Record<string, unknown> | null;
  data_quality?: string | null;
  data_freshness?: Record<string, unknown> | null;
  event_risk?: Record<string, unknown> | null;
  manual_only: boolean;
  authoritative: boolean;
  recommended_by: string;
  /** R36.1: additive, optional per-recommendation explainability contract. */
  explanation?: import("@/api/types").RecommendationExplanation | null;
}
export interface CapitalSetSafety {
  per_suggestion_not_additive: boolean;
  note_code: string;
  total_capital_required_displayed: number;
  available_cash: number | null;
  cash_known?: boolean;
  cash_buffer_pct: number;
  cash_buffer_amount: number;
  deployable_capital: number;
  exceeds_deployable_capital: boolean;
  flags: string[];
  assumes_leverage_or_margin: boolean;
}
export interface AuthoritativeRecommendations {
  decision_source: string;
  status?: string;
  manual_only: boolean;
  active_profile?: string;
  profile?: Record<string, unknown> | null;
  as_of_utc?: string | null;
  actionable: CanonicalLiveItem[];
  watch: CanonicalLiveItem[];
  blocked: CanonicalLiveItem[];
  stay_in_cash?: Record<string, unknown> | null;
  reason_codes?: string[];
  counts?: Record<string, number> | null;
}
export interface ActionNeededResponse {
  top_options: ActionNeededItem[];
  top_shares: ActionNeededItem[];
  options?: ActionNeededItem[];
  shares?: ActionNeededItem[];
  recently_changed: unknown[];
  // R34.0 cutover: the authoritative primary recommendation is canonical.
  decision_source?: string;
  authoritative_recommendations?: AuthoritativeRecommendations | null;
  capital_safety?: CapitalSetSafety | null;
  active_profile?: string;
  manual_only?: boolean;
  legacy_lists_role?: string;
  profile_error?: string;
}
export function useActionNeeded(profile?: string) {
  return useQuery({
    queryKey: [...queryKeys.actionNeeded(), profile ?? "balanced"] as const,
    queryFn: () =>
      apiGet<ActionNeededResponse>(
        profile ? `${actionNeededPath()}?profile=${encodeURIComponent(profile)}` : actionNeededPath(),
      ),
  });
}

/** R26.3: Today summary — run status, cadence, guardrails, notifications count, earnings probe. */
export interface TodaySummaryResponse {
  latest_run_ts: string | null;
  as_of_et: string;
  cadence: { mode: string; eligibility_as_of: string | null };
  orats_status: string;
  orats_freshness_state_label: string | null;
  guardrails: Record<string, unknown>;
  notifications_health: Record<string, unknown>;
  notifications_new_count: number;
  earnings_probe: Record<string, unknown>;
  action_needed_count: number | null;
}
export function useTodaySummary() {
  return useQuery({
    queryKey: queryKeys.todaySummary(),
    queryFn: () => apiGet<TodaySummaryResponse>(todaySummaryPath()),
  });
}

/** R26.4: Ops checklist (EOD / WEEKLY). */
export interface OpsChecklistResponse {
  kind: string;
  key: string;
  row: { id?: string; kind?: string; key?: string; status?: string; done_ts?: string; notes?: string };
}
export function useOpsChecklist(kind: string, key: string) {
  return useQuery({
    queryKey: queryKeys.opsChecklist(kind, key),
    queryFn: () => apiGet<OpsChecklistResponse>(opsChecklistPath(kind, key)),
    enabled: !!kind && !!key,
  });
}
export function useOpsChecklistMarkDone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { kind: string; key: string; notes?: string; override_reason?: string }) =>
      apiPost<{ status: string; row: OpsChecklistResponse["row"] }>(opsChecklistMarkDonePath(), payload),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: queryKeys.opsChecklist(variables.kind, variables.key) });
      qc.invalidateQueries({ queryKey: queryKeys.opsEodSummary(variables.key) });
      qc.invalidateQueries({ queryKey: queryKeys.opsWeeklySummary(variables.key) });
    },
  });
}

/** R26.9: Post one execution log event (MARK_DONE, SKIP_JOURNAL, EOD_OVERRIDE). */
export interface ExecutionLogPayload {
  event_type: string;
  symbol?: string;
  strategy?: string;
  action?: string;
  ticket_id?: string;
  reason?: string;
}
export function useExecutionLogPost() {
  return useMutation({
    mutationFn: (payload: ExecutionLogPayload) =>
      apiPost<{ status: string; row: Record<string, unknown> }>(opsExecutionLogPath(), payload),
  });
}

/** R27.0: Paper trading */
export interface PaperExecutePayload {
  mode: "PAPER";
  symbol: string;
  strategy: string;
  action: "OPEN" | "CLOSE";
  qty: number;
  shares_price?: number;
  premium?: number;
  fees?: number;
  position_id?: string;
  contract_key?: string;
  expiry?: string;
  strike?: number;
  right?: string;
  notes?: string;
  /** R27.1: Safe constraint codes for journal tags */
  sizing_constraints_hit?: string[];
}
export interface PaperPosition {
  id: string;
  symbol: string;
  strategy: string;
  qty: number;
  open_price: number;
  open_ts: string;
  status: string;
  realized_pl?: number;
  close_ts?: string;
  contract_key?: string;
  expiry?: string;
  strike?: number;
  right?: string;
  /** R27.1: Request-time mark (not persisted) */
  mark_value?: number | null;
  mark_source?: string | null;
  mark_age_sec?: number | null;
  quote_ts?: string | null;
  unrealized_pl_usd?: number | null;
}
export function usePaperExecute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PaperExecutePayload) =>
      apiPost<{ status: string; reason?: string; position: PaperPosition }>(paperExecutePath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "paper"] });
      qc.invalidateQueries({ queryKey: ["ui", "journal"] });
    },
  });
}
export function usePaperPositions(params: { status?: string; symbol?: string; strategy?: string; include_marks?: boolean }) {
  return useQuery({
    queryKey: queryKeys.paperPositions(params),
    queryFn: () => apiGet<{ positions: PaperPosition[] }>(paperPositionsPath(params)),
  });
}
/** R27.2: Single paper position (enriched when OPEN and include_marks) */
export function usePaperPositionById(positionId: string | null, include_marks = true) {
  return useQuery({
    queryKey: ["ui", "paper", "position", positionId, include_marks] as const,
    queryFn: () => apiGet<PaperPosition>(paperPositionByIdPath(positionId!, include_marks)),
    enabled: !!positionId?.trim(),
  });
}
/** R27.2: Close paper position mutation. Payload: position_id, close_price (shares) or close_premium (options), close_fees?, ts? */
export interface PaperClosePayload {
  position_id: string;
  close_price?: number;
  close_premium?: number;
  close_fees?: number;
  ts?: string;
}
export function usePaperClose() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PaperClosePayload) =>
      apiPost<{ status: string; reason?: string; position: PaperPosition }>(paperClosePath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "paper"] });
      qc.invalidateQueries({ queryKey: ["ui", "journal"] });
    },
  });
}
export function usePaperSummary(month: string) {
  return useQuery({
    queryKey: queryKeys.paperSummary(month),
    queryFn: () => apiGet<{ month: string; realized_pl: number; trade_count: number; win_rate: number; fees_total: number; by_strategy: Record<string, number> }>(paperSummaryPath(month)),
    enabled: !!month && month.length === 7 && month[4] === "-",
  });
}

/** R26.4: EOD summary for a date. */
export interface OpsEodSummaryResponse {
  date: string;
  eval_as_of: string | null;
  action_needed_count: number | null;
  notifications_new_count: number;
  journal_entries_count: number;
}
export function useOpsEodSummary(date: string) {
  return useQuery({
    queryKey: queryKeys.opsEodSummary(date),
    queryFn: () => apiGet<OpsEodSummaryResponse>(opsEodSummaryPath(date)),
    enabled: !!date && date.length === 10,
  });
}

/** R26.4: Weekly summary. */
export interface OpsWeeklySummaryResponse {
  week: string;
  from_date: string;
  to_date: string;
  realized_pl_total: number;
  trade_count: number;
  winners: { symbol: string; realized_pl: number }[];
  losers: { symbol: string; realized_pl: number }[];
  guardrails: Record<string, unknown>;
}
export function useOpsWeeklySummary(week: string) {
  return useQuery({
    queryKey: queryKeys.opsWeeklySummary(week),
    queryFn: () => apiGet<OpsWeeklySummaryResponse>(opsWeeklySummaryPath(week)),
    enabled: !!week && week.length >= 6,
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

/** R27.9: GET /api/ui/positions/unified — read-only aggregation (live shares, live options, paper). R29.2: enabled for compare. */
export function useUnifiedPositions(params: {
  state?: "open" | "closed";
  include_paper?: boolean;
  instrument_type?: string | null;
  symbol?: string | null;
  enabled?: boolean;
} = {}) {
  const { state = "open", include_paper = true, instrument_type, symbol, enabled = true } = params;
  return useQuery({
    queryKey: queryKeys.uiPositionsUnified({ state, include_paper, instrument_type, symbol }),
    queryFn: () =>
      apiGet<UiPositionsUnifiedResponse>(
        uiPositionsUnifiedPath({ state, include_paper, instrument_type, symbol })
      ),
    enabled,
  });
}

/** R28.7: POST /api/ui/positions/unified/rebuild — manual rebuild; invalidates system-health and unified positions. */
export function usePositionsUnifiedRebuild() {
  const qc = useQueryClient();
  return useMutation<UiPositionsUnifiedRebuildResponse, Error, { include_paper?: boolean }>({
    mutationFn: (params: { include_paper?: boolean } = {}) => {
      const includePaper = params?.include_paper !== false;
      return apiPostNoBody<UiPositionsUnifiedRebuildResponse>(
        uiPositionsUnifiedRebuildPath(includePaper)
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
      qc.invalidateQueries({ queryKey: ["ui", "positions", "unified"] });
      qc.invalidateQueries({ queryKey: ["ui", "positions", "unified", "reconcile-diff"] });
    },
  });
}

/** R29.3: POST /api/ui/positions/unified/integrity-check — manual integrity check; invalidates system-health and reconcile-diff. */
export function usePositionsUnifiedIntegrityCheck() {
  const qc = useQueryClient();
  return useMutation<
    UiPositionsUnifiedIntegrityCheckResponse,
    Error,
    { include_paper?: boolean }
  >({
    mutationFn: (params: { include_paper?: boolean } = {}) => {
      const includePaper = params?.include_paper !== false;
      return apiPost<UiPositionsUnifiedIntegrityCheckResponse>(
        UI_POSITIONS_UNIFIED_INTEGRITY_CHECK_PATH,
        { include_paper: includePaper }
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.uiSystemHealth() });
      qc.invalidateQueries({ queryKey: queryKeys.uiIntegrityCheckResult() });
      qc.invalidateQueries({ queryKey: ["ui", "positions", "unified", "reconcile-diff"] });
    },
  });
}

/** R29.4: GET /api/ui/positions/unified/integrity-check — last result + history (read-only). */
export function useIntegrityCheckResult(params: { enabled?: boolean } = {}) {
  const { enabled = true } = params;
  return useQuery({
    queryKey: queryKeys.uiIntegrityCheckResult(),
    queryFn: () => apiGet<UiPositionsUnifiedIntegrityCheckResult>(UI_POSITIONS_UNIFIED_INTEGRITY_CHECK_PATH),
    enabled,
  });
}

/** R28.9: GET /api/ui/positions/unified/db — DB-first read (what is stored). R29.2: enabled for compare. */
export function useUnifiedPositionsFromDb(params: {
  state?: "open" | "closed";
  include_paper?: boolean;
  instrument_type?: string | null;
  symbol?: string | null;
  limit?: number;
  enabled?: boolean;
} = {}) {
  const { state = "open", include_paper = true, instrument_type, symbol, limit = 500, enabled = true } = params;
  return useQuery({
    queryKey: queryKeys.uiPositionsUnifiedDb({ state, include_paper, instrument_type, symbol, limit }),
    queryFn: () =>
      apiGet<UiPositionsUnifiedDbResponse>(
        uiPositionsUnifiedDbPath({ state, include_paper, instrument_type, symbol, limit })
      ),
    enabled,
  });
}

/** R28.8: GET /api/ui/positions/unified/reconcile-diff — read-only diff (source vs unified). */
export function useReconcileDiff(params: {
  include_paper?: boolean;
  symbol?: string | null;
  limit?: number;
  enabled?: boolean;
} = {}) {
  const { include_paper = true, symbol, limit = 200, enabled = true } = params;
  return useQuery({
    queryKey: queryKeys.uiReconcileDiff({ include_paper, symbol, limit }),
    queryFn: () =>
      apiGet<UiReconcileDiffResponse>(
        uiPositionsUnifiedReconcileDiffPath({ include_paper, symbol, limit })
      ),
    enabled,
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

/** R23.5.0/R27.3: POST /api/ui/shares/positions/{symbol}/close — exit_price, exit_date? (ts), fees?, notes?; creates journal entry. */
export function useCloseSharePosition(symbol: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      account_id: string;
      exit_price: number;
      exit_date?: string | null;
      ts?: string | null;
      fees?: number | null;
      notes?: string | null;
    }) =>
      apiPost<ClosedSharePosition>(
        uiSharePositionClosePath(symbol!),
        {
          account_id: payload.account_id,
          exit_price: payload.exit_price,
          exit_date: payload.exit_date ?? payload.ts ?? undefined,
          fees: payload.fees ?? undefined,
          notes: payload.notes ?? undefined,
        }
      ),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["ui", "shares"] });
      qc.invalidateQueries({ queryKey: queryKeys.uiSharesPositions(variables.account_id) });
      qc.invalidateQueries({ queryKey: queryKeys.uiClosedSharePositions(variables.account_id) });
      qc.invalidateQueries({ queryKey: queryKeys.uiPortfolio() });
      qc.invalidateQueries({ queryKey: ["ui", "symbolDiagnostics"] });
      qc.invalidateQueries({ queryKey: ["ui", "journal"] });
    },
  });
}

/** R27.3: POST /api/ui/journal/record-close — record options close/roll in Journal only (no execution). */
export function uiJournalRecordClosePath(): string {
  return "/api/ui/journal/record-close";
}

export interface RecordClosePayload {
  symbol: string;
  strategy: "CSP" | "CC";
  action: "CLOSE_CSP" | "CLOSE_CC" | "ROLL";
  qty: number;
  premium?: number | null;
  contract_key?: string | null;
  expiry?: string | null;
  strike?: number | null;
  right?: string | null;
  fees?: number | null;
  notes?: string | null;
  trade_date?: string | null;
}

export function useJournalRecordClose() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RecordClosePayload) =>
      apiPost<{ status: string; entry: JournalEntry }>(uiJournalRecordClosePath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "journal"] });
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
      qc.invalidateQueries({ queryKey: queryKeys.todaySummary() });
      qc.invalidateQueries({ queryKey: queryKeys.actionNeeded() });
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
  /** R28.3: Safe severity (Low/Medium/High). Never FAIL/WARN/PASS. */
  severity: string;
  /** R28.3: Human-safe label for severity (e.g. Advisory, Review). */
  severity_label?: string | null;
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
      qc.invalidateQueries({ queryKey: queryKeys.todaySummary() });
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
      qc.invalidateQueries({ queryKey: queryKeys.todaySummary() });
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
  /** R27.4: Request-time deep-link hint; { kind, id } when link_id recognized */
  link_target?: { kind: string; id: string } | null;
  /** R27.0: Paper trade flag (0/1 from API) */
  is_paper?: number | null;
  /** R30.3: True when entry has an attached readiness pack */
  has_readiness_pack?: boolean;
}
export interface JournalListResponse {
  entries: JournalEntry[];
}
export interface JournalCreateResponse {
  entry: JournalEntry;
}
/** R27.2: Same shape as aggregate for live/paper split */
export interface MonthlyReportTotals {
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
export interface MonthlyReportResponse extends MonthlyReportTotals {
  /** R27.1 */
  included_paper?: boolean;
  mode?: "LIVE_ONLY" | "PAPER_ONLY" | "MIXED";
  /** R27.2: When include_paper enabled */
  live_totals?: MonthlyReportTotals;
  paper_totals?: MonthlyReportTotals;
}

export function useJournal(params: {
  from_date?: string;
  to_date?: string;
  symbol?: string;
  strategy?: string;
  limit?: number;
  offset?: number;
  include_paper?: boolean;
  paper_only?: boolean;
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

/** R26.2: Trade ticket payload */
export interface TradeTicketResponse {
  symbol: string;
  strategy: string;
  action: string;
  snapshot_header: Record<string, unknown>;
  sizing: Record<string, unknown>;
  contract_details: Record<string, unknown>;
  execution_steps: string[];
  journal_draft: Record<string, unknown>;
  guardrails: Record<string, unknown>;
  earnings_advisory: Record<string, unknown>;
  error?: string;
}

/** R30.0/R30.1: Trade ticket readiness response (safe labels only; optional action links per check). */
export interface TradeTicketReadinessResponse {
  status: "OK" | "Review";
  status_label: string;
  as_of_utc: string;
  checks: Array<{
    code: string;
    status: "OK" | "Review";
    label: string;
    detail: string;
    action_label?: string;
    action_href?: string;
  }>;
  order_stub: { title: string; lines: string[] };
}
export function useTradeTicketReadiness(symbol: string, mode: "live" | "paper", ticketKind: string) {
  return useQuery({
    queryKey: ["ui", "trade-ticket", "readiness", symbol, mode, ticketKind],
    queryFn: () => apiGet<TradeTicketReadinessResponse>(tradeTicketReadinessPath(symbol, mode, ticketKind)),
    enabled: !!symbol?.trim(),
  });
}

export function useTradeTicket(symbol: string, strategy: string, action: string) {
  return useQuery({
    queryKey: queryKeys.tradeTicket(symbol, strategy, action),
    queryFn: () => apiGet<TradeTicketResponse>(tradeTicketPath(symbol, strategy, action)),
    enabled: !!symbol?.trim(),
  });
}

/** R26.2: Create journal entry from ticket payload */
export function useJournalFromTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<JournalCreateResponse>(uiJournalFromTicketPath(), payload).then((r) => r.entry),
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

export function useReportsMonthly(month: string, include_paper?: boolean) {
  return useQuery({
    queryKey: [...queryKeys.uiReportsMonthly(month), include_paper ?? false] as const,
    queryFn: () => apiGet<MonthlyReportResponse>(uiReportsMonthlyPath(month, include_paper)),
    enabled: !!month && month.length === 7 && month[4] === "-",
  });
}

/** R26.5: Monthly close pack — files list + generate + download */
export interface MonthlyCloseFilesResponse {
  month: string;
  pack?: "live" | "paper";
  files: { name: string; size: number }[];
  generated_ts?: string | null;
  paths?: string[];
}
export function useMonthlyCloseFiles(month: string, pack: "live" | "paper" = "live") {
  return useQuery({
    queryKey: queryKeys.uiMonthlyCloseFiles(month, pack),
    queryFn: () => apiGet<MonthlyCloseFilesResponse>(uiMonthlyCloseFilesPath(month, pack)),
    enabled: !!month && month.length === 7 && month[4] === "-",
  });
}
export function useMonthlyCloseGenerate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (arg: { month: string; include_paper?: boolean }) =>
      apiPostNoBody<{ status: string; month: string; pack?: string; generated_ts: string; paths: string[] }>(
        uiMonthlyCloseGeneratePath(arg.month, arg.include_paper)
      ),
    onSuccess: (_, arg) => {
      qc.invalidateQueries({ queryKey: queryKeys.uiMonthlyCloseFiles(arg.month, "live") });
      qc.invalidateQueries({ queryKey: queryKeys.uiMonthlyCloseFiles(arg.month, "paper") });
    },
  });
}
export function getMonthlyCloseDownloadPath(month: string, file: string, pack?: "live" | "paper"): string {
  return uiMonthlyCloseDownloadPath(month, file, pack);
}

/** R27.5: Backtest replay */
export interface BacktestRunPayload {
  start_date: string;
  end_date: string;
  include_paper?: boolean;
  paper_only?: boolean;
}
export interface BacktestRunResponse {
  status: string;
  run_id: string;
  created_ts: string;
  mode: string;
  paths: { summary_json: string; trades_csv: string };
  metrics: {
    start_date: string;
    end_date: string;
    mode: string;
    total_realized_pl: number;
    total_fees: number;
    trade_count: number;
    win_count: number;
    loss_count: number;
    win_rate: number;
    by_strategy: Record<string, { realized_pl: number; trades: number; wins: number; losses: number }>;
    max_drawdown_proxy?: number | null;
  };
  trades?: Array<{
    trade_date?: string;
    symbol?: string;
    strategy?: string;
    action?: string;
    qty?: number;
    price?: number;
    premium?: number;
    fees?: number;
    realized_pl?: number;
    is_paper?: boolean;
    link_id?: string;
    tags?: string;
  }>;
}
export interface BacktestRunRow {
  id: string;
  start_date: string;
  end_date: string;
  mode: string;
  created_ts: string;
  path_json: string;
}
export interface BacktestRunsResponse {
  runs: BacktestRunRow[];
}
export function useBacktestRuns(limit = 50, offset = 0) {
  return useQuery({
    queryKey: queryKeys.uiBacktestRuns(limit, offset),
    queryFn: () => apiGet<BacktestRunsResponse>(uiBacktestRunsPath(limit, offset)),
  });
}
export function useBacktestRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: BacktestRunPayload) =>
      apiPost<BacktestRunResponse>(uiBacktestRunPath(), payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "backtest", "runs"] });
    },
  });
}
export async function downloadBacktestFile(run_id: string, file: "summary_json" | "trades_csv"): Promise<void> {
  const blob = await apiGetBlob(uiBacktestDownloadPath(run_id, file));
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file === "summary_json" ? "backtest_summary.json" : "backtest_trades.csv";
  a.click();
  URL.revokeObjectURL(url);
}
export async function downloadMonthlyCloseFile(month: string, file: string, pack: "live" | "paper" = "live"): Promise<void> {
  const blob = await apiGetBlob(uiMonthlyCloseDownloadPath(month, file, pack));
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file;
  a.click();
  URL.revokeObjectURL(url);
}

/** R25.6: Universe Admin — current list + history */
export interface UniverseAdminResponse {
  symbols: string[];
  base_count: number;
  overlay_added_count: number;
  overlay_removed_count: number;
  history: { id: string; ts: string; action: string; symbol: string; reason_code?: string | null; notes?: string | null; status: string }[];
}
export function useUniverseAdmin(params?: { limit?: number; offset?: number; status?: string }) {
  return useQuery({
    queryKey: queryKeys.uiUniverseAdmin(params ?? {}),
    queryFn: () => apiGet<UniverseAdminResponse>(uiUniverseAdminPath(params ?? {})),
  });
}

/** R25.6: Universe Health */
export interface UniverseHealthResponse {
  total_symbols: number;
  base_count: number;
  recently_added: string[];
  recently_removed: string[];
  warnings_count: number;
  earnings_upcoming?: number | null;
}
export function useUniverseHealth() {
  return useQuery({
    queryKey: queryKeys.uiUniverseHealth(),
    queryFn: () => apiGet<UniverseHealthResponse>(uiUniverseHealthPath()),
  });
}

export function useUniverseProposeAdd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { symbol: string; reason_code?: string; notes?: string }) =>
      apiPost<{ proposal: Record<string, unknown> }>("/api/ui/universe/propose-add", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "universe", "admin"] });
    },
  });
}
export function useUniverseProposeRemove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { symbol: string; reason_code?: string; notes?: string }) =>
      apiPost<{ proposal: Record<string, unknown> }>("/api/ui/universe/propose-remove", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "universe", "admin"] });
    },
  });
}
export function useUniverseApply() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { proposal_id?: string; symbol?: string; action?: string }) =>
      apiPost<{ applied: boolean; symbol: string; symbols: string[] }>("/api/ui/universe/apply", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ui", "universe", "admin"] });
      qc.invalidateQueries({ queryKey: ["ui", "universe", "health"] });
      qc.invalidateQueries({ queryKey: ["ui", "universe", "symbols"] });
    },
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
