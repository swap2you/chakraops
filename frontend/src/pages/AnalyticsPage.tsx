/**
 * Universe: Universe panel showing all evaluation symbols with last evaluation results.
 * Shows: symbol, source, price, verdict, score, reason, actions
 * 
 * CRITICAL RULES:
 * 1. Use evaluation/latest endpoint for persistent results (all screens read same truth)
 * 2. Use dedicated AbortController for fetches
 * 3. Completed response ALWAYS renders, even if slow
 * 4. NEVER show "pending" - use explicit "No evaluation run yet" or "Last run at..."
 * 5. Show banner if a run is currently in progress
 */
import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { Link } from "react-router-dom";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { useApiSnapshot } from "@/hooks/useApiSnapshot";
import { pushSystemNotification } from "@/lib/notifications";
import type { UniverseView } from "@/types/universe";
import type {
  UniverseEvaluationResult,
  SymbolEvaluationResult,
  EvaluateNowResponse,
  SlackNotifyResponse,
  EvaluationLatestResponse,
  EvaluationStatusCurrentResponse,
} from "@/types/universeEvaluation";
import { getVerdictColor, formatPrice, formatReason, formatStage, formatSelectedContract } from "@/types/universeEvaluation";
import { Info, RefreshCw, XCircle, ExternalLink, Loader2, AlertTriangle, Clock, Play, Send, Search, CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

// 90 second timeout - ORATS can be slow
const UNIVERSE_FETCH_TIMEOUT_MS = 90_000;
const UNIVERSE_TOOLTIP = "Evaluation scope = Universe symbols";

type AbortReason = "navigation" | "timeout" | "retry" | null;

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Not available";
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "Not available" : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "Not available";
  }
}

export function AnalyticsPage() {
  const { mode } = useDataMode();
  const { snapshot, refetch: refetchSnapshot } = useApiSnapshot();
  const [universe, setUniverse] = useState<UniverseView | null>(null);
  const [universeEval, setUniverseEval] = useState<UniverseEvaluationResult | null>(null);
  const [latestRun, setLatestRun] = useState<EvaluationLatestResponse | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_evalStatus, setEvalStatus] = useState<EvaluationStatusCurrentResponse | null>(null);
  const [universeError, setUniverseError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [evalRunning, setEvalRunning] = useState(false);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [slackSending, setSlackSending] = useState<string | null>(null);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [abortReason, setAbortReason] = useState<AbortReason>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const abortReasonRef = useRef<AbortReason>(null);
  const isMountedRef = useRef(true);
  const fetchStartTimeRef = useRef<number>(0);

  // Single source of truth: only evaluation/latest (Phase C).
  const fetchLatestRun = useCallback(async () => {
    if (mode !== "LIVE") return;
    try {
      const data = await apiGet<EvaluationLatestResponse>(ENDPOINTS.evaluationLatest);
      setLatestRun(data);
      if (data.has_completed_run && data.symbols) {
        setUniverseEval({
          evaluation_state: "COMPLETED",
          evaluation_state_reason: "From persisted run",
          last_evaluated_at: data.completed_at ?? null,
          duration_seconds: data.duration_seconds ?? 0,
          counts: {
            total: data.counts?.total ?? 0,
            evaluated: data.counts?.evaluated ?? 0,
            eligible: data.counts?.eligible ?? 0,
            shortlisted: data.counts?.shortlisted ?? 0,
          },
          symbols: data.symbols,
          alerts_count: data.alerts_count ?? 0,
          errors: [],
        });
      } else {
        setUniverseEval(null);
      }
    } catch (e) {
      console.error("Failed to fetch latest evaluation:", e);
      setUniverseEval(null);
    }
  }, [mode]);

  // Fetch current evaluation status (is running?)
  const fetchEvalStatus = useCallback(async () => {
    if (mode !== "LIVE") return;
    try {
      const data = await apiGet<EvaluationStatusCurrentResponse>(ENDPOINTS.evaluationStatusCurrent);
      setEvalStatus(data);
      setEvalRunning(data.is_running);
      if (data.current_run_id) {
        setCurrentRunId(data.current_run_id);
      }
    } catch (e) {
      console.error("Failed to fetch evaluation status:", e);
    }
  }, [mode]);

  // Trigger evaluation
  const triggerEvaluation = useCallback(async () => {
    if (evalRunning) return;
    setEvalRunning(true);
    try {
      const result = await apiPost<EvaluateNowResponse>(ENDPOINTS.evaluateNow, {});
      if (result.started) {
        setCurrentRunId(result.run_id);
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Evaluation started",
          message: `Run ${result.run_id?.slice(-12) ?? "unknown"} is running. Results will appear shortly.`,
        });
        // Poll for completion using the new status endpoint
        const pollInterval = setInterval(async () => {
          await fetchEvalStatus();
          const status = await apiGet<EvaluationStatusCurrentResponse>(ENDPOINTS.evaluationStatusCurrent);
          if (!status.is_running) {
            clearInterval(pollInterval);
            setEvalRunning(false);
            setCurrentRunId(null);
            // Refresh both latest run and in-memory cache
            await fetchLatestRun();
            await refetchSnapshot();
            pushSystemNotification({
              source: "system",
              severity: status.evaluation_state === "COMPLETED" ? "info" : "warning",
              title: `Evaluation ${status.evaluation_state.toLowerCase()}`,
              message: status.evaluation_state_reason,
            });
          }
        }, 3000);
        // Safety timeout
        setTimeout(() => {
          clearInterval(pollInterval);
          setEvalRunning(false);
          setCurrentRunId(null);
        }, 120000);
      } else {
        pushSystemNotification({
          source: "system",
          severity: "warning",
          title: "Evaluation not started",
          message: result.reason,
        });
        setEvalRunning(false);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Evaluation failed",
        message: msg,
      });
      setEvalRunning(false);
    }
  }, [evalRunning, fetchEvalStatus, fetchLatestRun, refetchSnapshot]);

  // Send to Slack
  const sendToSlack = useCallback(async (symbol: SymbolEvaluationResult) => {
    const key = symbol.symbol;
    setSlackSending(key);
    try {
      const result = await apiPost<SlackNotifyResponse>(ENDPOINTS.notifySlack, {
        meta: {
          symbol: symbol.symbol,
          strategy: symbol.verdict,
          score: symbol.score,
          reason: symbol.primary_reason,
        },
      });
      if (result.sent) {
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Sent to Slack",
          message: result.reason ?? `${symbol.symbol} notification sent`,
        });
      } else {
        // Check if "not configured" - show warning instead of error
        const isNotConfigured = result.reason?.toLowerCase().includes("not configured") || 
                                result.reason?.toLowerCase().includes("slack_webhook_url");
        pushSystemNotification({
          source: "system",
          severity: "warning",
          title: isNotConfigured ? "Slack not configured" : "Slack not sent",
          message: isNotConfigured ? "Add SLACK_WEBHOOK_URL to enable alerts" : (result.reason ?? "Unknown error"),
        });
      }
    } catch (e) {
      // Treat 503 "not configured" as warning, not error
      const msg = e instanceof Error ? e.message : String(e);
      const isNotConfigured = msg.toLowerCase().includes("not configured") || msg.toLowerCase().includes("503");
      pushSystemNotification({
        source: "system",
        severity: isNotConfigured ? "warning" : "error",
        title: isNotConfigured ? "Slack not configured" : "Slack failed",
        message: isNotConfigured ? "Add SLACK_WEBHOOK_URL to enable alerts" : msg,
      });
    } finally {
      setSlackSending(null);
    }
  }, []);

  const fetchUniverse = useCallback(async (isRetry = false) => {
    if (mode !== "LIVE") return;
    
    // Cancel previous request ONLY if user explicitly retries
    if (isRetry && abortControllerRef.current) {
      abortReasonRef.current = "retry";
      abortControllerRef.current.abort();
    }
    
    // Create DEDICATED controller for this request (not shared with anything)
    const controller = new AbortController();
    abortControllerRef.current = controller;
    abortReasonRef.current = null;
    
    setUniverseError(null);
    setAbortReason(null);
    setLoading(true);
    fetchStartTimeRef.current = Date.now();
    
    // Set up timeout abort
    const timeoutId = setTimeout(() => {
      if (abortControllerRef.current === controller) {
        abortReasonRef.current = "timeout";
        controller.abort();
      }
    }, UNIVERSE_FETCH_TIMEOUT_MS);
    
    try {
      // Snapshot-only: universe list + evaluation/latest only (Phase C).
      const [universeData, latestData] = await Promise.all([
        apiGet<UniverseView>(ENDPOINTS.universe, { signal: controller.signal }),
        apiGet<EvaluationLatestResponse>(ENDPOINTS.evaluationLatest).catch(() => null),
      ]);
      
      clearTimeout(timeoutId);
      
      if (universeData) {
        setUniverse(universeData);
        setUniverseError(null);
        setAbortReason(null);
      }
      if (latestData?.has_completed_run && latestData.symbols) {
        setUniverseEval({
          evaluation_state: "COMPLETED",
          evaluation_state_reason: "From persisted run",
          last_evaluated_at: latestData.completed_at ?? null,
          duration_seconds: latestData.duration_seconds ?? 0,
          counts: {
            total: latestData.counts?.total ?? 0,
            evaluated: latestData.counts?.evaluated ?? 0,
            eligible: latestData.counts?.eligible ?? 0,
            shortlisted: latestData.counts?.shortlisted ?? 0,
          },
          symbols: latestData.symbols,
          alerts_count: latestData.alerts_count ?? 0,
          errors: [],
        });
      } else if (latestData) {
        setUniverseEval(null);
      }
      setLoading(false);
      
    } catch (e) {
      clearTimeout(timeoutId);
      
      if (!isMountedRef.current) return;
      
      setLoading(false);
      
      // Handle abort with specific reason
      if (e instanceof Error && e.name === "AbortError") {
        const reason = abortReasonRef.current;
        setAbortReason(reason || "navigation");
        
        if (reason === "timeout") {
          setUniverseError(`Universe fetch timed out after ${UNIVERSE_FETCH_TIMEOUT_MS / 1000}s - click Retry`);
        } else if (reason === "navigation") {
          setUniverseError("Canceled due to navigation");
        } else if (reason === "retry") {
          // Don't show error for retry-triggered abort
          setUniverseError(null);
        }
        return;
      }
      
      // Handle API errors
      const status = e instanceof ApiError ? e.status : 0;
      const is404 = status === 404;
      const is503 = status === 503;
      
      if (import.meta.env?.DEV && typeof console !== "undefined") {
        console.warn("[ChakraOps] Universe fetch failed:", ENDPOINTS.universe, status);
      }
      
      setUniverseError(
        is503 ? "ORATS data unavailable - universe cannot be loaded" 
        : is404 ? "Universe endpoint not found - check that backend is running" 
        : `Universe request failed with error ${status || "unknown"}`
      );
      
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: is404 ? "Universe endpoint missing" : "Universe load failed",
        message: is404 
          ? "Backend endpoint not found. Verify backend is running on port 8000." 
          : is503 
            ? "ORATS data provider is unavailable." 
            : `${ENDPOINTS.universe} returned HTTP ${status || "error"}.`,
      });
    }
  }, [mode]);

  useEffect(() => {
    isMountedRef.current = true;
    
    if (mode === "LIVE") {
      fetchUniverse();
      fetchLatestRun();
      fetchEvalStatus();
    }
    
    return () => {
      isMountedRef.current = false;
      // Mark abort reason as navigation on unmount
      if (abortControllerRef.current) {
        abortReasonRef.current = "navigation";
        abortControllerRef.current.abort();
      }
    };
  }, [mode]); // Intentionally omit fetch functions to prevent re-fetch loops

  // Summary counts
  const totalSymbols = universe?.symbols?.length ?? 0;
  const excludedCount = universe?.excluded?.length ?? 0;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Universe</h1>
          <p className="text-muted-foreground">All symbols evaluated by ChakraOps.</p>
        </div>
        {mode === "LIVE" && (
          <button
            type="button"
            onClick={() => fetchUniverse(true)}
            disabled={loading}
            className={cn(
              "flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm font-medium",
              loading ? "cursor-not-allowed bg-muted text-muted-foreground" : "bg-secondary/50 text-foreground hover:bg-secondary"
            )}
            title="Refresh universe data"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            {loading ? "Loading..." : "Refresh"}
          </button>
        )}
      </div>

      {/* Run in progress banner */}
      {mode === "LIVE" && evalRunning && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
          <Loader2 className="h-5 w-5 animate-spin text-blue-600 dark:text-blue-400" />
          <div className="flex-1">
            <p className="font-medium text-blue-700 dark:text-blue-300">Evaluation run in progress...</p>
            <p className="text-sm text-blue-600 dark:text-blue-400">
              {currentRunId ? `Run ID: ${currentRunId.slice(-12)}` : "Processing symbols"}. Results will update automatically.
            </p>
          </div>
        </div>
      )}

      {/* Showing last completed run banner */}
      {mode === "LIVE" && latestRun?.has_completed_run && !evalRunning && (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
          <div className="flex-1">
            <p className="font-medium text-emerald-700 dark:text-emerald-300">
              Showing last completed run at {latestRun.completed_at ? new Date(latestRun.completed_at).toLocaleString() : "unknown"}
            </p>
            <p className="text-sm text-emerald-600 dark:text-emerald-400">
              {latestRun.counts?.evaluated ?? 0} evaluated • {latestRun.counts?.eligible ?? 0} eligible • {latestRun.counts?.shortlisted ?? 0} shortlisted
              {latestRun.duration_seconds && ` • ${latestRun.duration_seconds.toFixed(1)}s`}
            </p>
          </div>
          <Link
            to="/history"
            className="text-xs text-emerald-700 hover:underline dark:text-emerald-300"
          >
            View history
          </Link>
        </div>
      )}

      {/* Awaiting evaluation banner */}
      {mode === "LIVE" && !latestRun?.has_completed_run && !evalRunning && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
          <div>
            <p className="font-medium text-amber-700 dark:text-amber-300">No completed evaluation run yet.</p>
            <p className="text-sm text-amber-600 dark:text-amber-400">
              {snapshot?.universe.total ?? 0} symbols in universe. Click "Run evaluation now" to start.
            </p>
          </div>
        </div>
      )}

      {/* Summary stats with explicit state */}
      {mode === "LIVE" && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <div className="rounded-lg border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">Universe Total</p>
            <p className="text-xl font-semibold text-foreground">{universeEval?.counts.total ?? snapshot?.universe.total ?? 0}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">Evaluated</p>
            <p className={cn(
              "text-xl font-semibold",
              (universeEval?.counts.evaluated ?? 0) === 0 ? "text-muted-foreground" : "text-foreground"
            )}>
              {universeEval?.counts.evaluated ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">Eligible</p>
            <p className={cn(
              "text-xl font-semibold",
              (universeEval?.counts.eligible ?? 0) === 0 ? "text-muted-foreground" : "text-emerald-600 dark:text-emerald-400"
            )}>
              {universeEval?.counts.eligible ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">Shortlisted</p>
            <p className={cn(
              "text-xl font-semibold",
              (universeEval?.counts.shortlisted ?? 0) === 0 ? "text-muted-foreground" : "text-foreground"
            )}>
              {universeEval?.counts.shortlisted ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">State</p>
            <p className={cn(
              "text-sm font-medium",
              universeEval?.evaluation_state === "COMPLETED" && "text-emerald-600 dark:text-emerald-400",
              universeEval?.evaluation_state === "RUNNING" && "text-blue-600 dark:text-blue-400",
              universeEval?.evaluation_state === "FAILED" && "text-destructive",
              universeEval?.evaluation_state === "IDLE" && "text-muted-foreground"
            )}>
              {universeEval?.evaluation_state ?? "IDLE"}
            </p>
            {universeEval?.last_evaluated_at && (
              <p className="text-xs text-muted-foreground">
                {new Date(universeEval.last_evaluated_at).toLocaleTimeString()}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Universe panel (LIVE only) */}
      {mode === "LIVE" && (
        <section className="rounded-lg border border-border bg-card p-4" aria-label="Universe">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-foreground">Symbol List</h2>
              <span
                className="text-muted-foreground"
                title={UNIVERSE_TOOLTIP}
                aria-label={UNIVERSE_TOOLTIP}
              >
                <Info className="h-4 w-4" />
              </span>
            </div>
            {universe && (
              <span className="text-xs text-muted-foreground">
                {totalSymbols} symbols • {excludedCount} excluded
              </span>
            )}
          </div>

          {/* Loading state */}
          {loading && !universe && (
            <div className="mt-4 flex items-center justify-center gap-2 py-8 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>Loading universe data...</span>
            </div>
          )}

          {/* Error state with retry */}
          {universeError && (
            <div className={cn(
              "mt-3 flex items-center gap-3 rounded-lg p-3",
              abortReason === "timeout" ? "border border-amber-500/30 bg-amber-500/10" 
              : abortReason === "navigation" ? "border border-muted bg-muted/30"
              : "border border-destructive/30 bg-destructive/5"
            )}>
              {abortReason === "timeout" ? (
                <Clock className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
              ) : abortReason === "navigation" ? (
                <AlertTriangle className="h-5 w-5 shrink-0 text-muted-foreground" />
              ) : (
                <XCircle className="h-5 w-5 shrink-0 text-destructive" />
              )}
              <div className="flex-1">
                <p className={cn(
                  "font-medium",
                  abortReason === "timeout" ? "text-amber-700 dark:text-amber-300"
                  : abortReason === "navigation" ? "text-muted-foreground"
                  : "text-destructive"
                )}>{universeError}</p>
                {abortReason === "timeout" && (
                  <p className="text-sm text-amber-600 dark:text-amber-400">
                    ORATS data fetching can be slow. Try again or check backend logs.
                  </p>
                )}
                {abortReason === "navigation" && (
                  <p className="text-sm text-muted-foreground">
                    Request was canceled because you navigated away.
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => fetchUniverse(true)}
                disabled={loading}
                className="rounded-md border border-border bg-secondary px-3 py-1.5 text-sm font-medium text-foreground hover:bg-secondary/80 disabled:opacity-50"
              >
                Retry
              </button>
            </div>
          )}

          {/* Run Evaluation Button */}
          <div className="mt-3 flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              {universeEval?.evaluation_state === "COMPLETED" && universeEval?.last_evaluated_at && (
                <span>Last run: {new Date(universeEval.last_evaluated_at).toLocaleString()}</span>
              )}
              {universeEval?.evaluation_state === "IDLE" && (
                <span>No evaluation run yet</span>
              )}
              {universeEval?.evaluation_state === "RUNNING" && (
                <span className="text-blue-600">Evaluation in progress...</span>
              )}
            </div>
            <button
              onClick={triggerEvaluation}
              disabled={evalRunning}
              className={cn(
                "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
                evalRunning
                  ? "cursor-not-allowed bg-muted text-muted-foreground"
                  : "bg-primary text-primary-foreground hover:bg-primary/90"
              )}
            >
              {evalRunning ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Run evaluation now
                </>
              )}
            </button>
          </div>

          {/* Data table with evaluation results */}
          {(universeEval?.symbols?.length ?? 0) > 0 && !universeError && (
            <>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Symbol</th>
                      <th className="py-2 pr-4 font-medium">Stage</th>
                      <th className="py-2 pr-4 font-medium">Price</th>
                      <th className="py-2 pr-4 font-medium">Verdict</th>
                      <th className="py-2 pr-4 font-medium">Score</th>
                      <th className="py-2 pr-4 font-medium">Reason / Contract</th>
                      <th className="py-2 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {universeEval!.symbols.map((row) => {
                      const reasonInfo = formatReason(row.primary_reason);
                      const stageInfo = formatStage(row.stage_reached);
                      const selectedContractStr = formatSelectedContract(row.selected_contract);
                      const hasBreakdown = row.score_breakdown || row.rank_reasons;
                      const isExpanded = expandedSymbol === row.symbol;
                      return (
                      <Fragment key={row.symbol}>
                      <tr
                        className={cn(
                          "border-b border-border/50 hover:bg-muted/30",
                          hasBreakdown && "cursor-pointer"
                        )}
                        onClick={hasBreakdown ? () => setExpandedSymbol(isExpanded ? null : row.symbol) : undefined}
                      >
                        <td className="py-2 pr-4 font-medium">
                          {hasBreakdown ? (
                            <span className="inline-flex items-center gap-1">
                              {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                              {row.symbol}
                            </span>
                          ) : (
                            row.symbol
                          )}
                        </td>
                        <td className="py-2 pr-4">
                          <span
                            className={cn("rounded-full px-2 py-0.5 text-xs font-medium", stageInfo.color)}
                            title={stageInfo.description}
                          >
                            {row.stage_reached === "STAGE2_CHAIN" ? "Chain" : "Stock"}
                          </span>
                        </td>
                        <td className="py-2 pr-4">
                          <span className={row.price === null ? "text-muted-foreground italic" : ""}>
                            {formatPrice(row.price)}
                          </span>
                        </td>
                        <td className="py-2 pr-4">
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", getVerdictColor(row.verdict))}>
                            {row.verdict}
                          </span>
                        </td>
                        <td className="py-2 pr-4">
                          <span className={cn(
                            "font-medium",
                            row.score >= 70 ? "text-emerald-600 dark:text-emerald-400" :
                            row.score >= 50 ? "text-amber-600 dark:text-amber-400" :
                            "text-muted-foreground"
                          )}>
                            {row.score}
                            {/* Show indicator if score is capped due to missing data */}
                            {row.missing_fields && row.missing_fields.length > 0 && row.data_completeness && row.data_completeness < 0.75 && (
                              <span className="ml-1 text-xs text-amber-600 dark:text-amber-400" title="Score capped due to incomplete data">*</span>
                            )}
                          </span>
                        </td>
                        <td className="py-2 pr-4 max-w-[280px]" title={row.primary_reason}>
                          {/* Show selected contract if available */}
                          {selectedContractStr ? (
                            <div className="flex flex-col gap-1">
                              <span className="text-xs font-mono text-emerald-600 dark:text-emerald-400">
                                {selectedContractStr}
                              </span>
                              <span className="text-xs text-muted-foreground truncate">
                                {row.primary_reason.slice(0, 40)}
                              </span>
                            </div>
                          ) : reasonInfo.isDataIncomplete ? (
                            <div className="flex flex-col gap-1">
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/50 dark:text-amber-300">
                                <AlertTriangle className="h-3 w-3" />
                                DATA_INCOMPLETE
                              </span>
                              <span className="text-xs text-muted-foreground truncate">
                                missing: {reasonInfo.missingFields.join(", ")}
                              </span>
                            </div>
                          ) : (
                            <span className="text-muted-foreground truncate block">
                              {row.primary_reason.slice(0, 50)}{row.primary_reason.length > 50 ? "..." : ""}
                            </span>
                          )}
                        </td>
                        <td className="py-2" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center gap-2">
                            <Link
                              to={`/analysis?symbol=${encodeURIComponent(row.symbol)}`}
                              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-primary hover:bg-muted"
                            >
                              <Search className="h-3 w-3" />
                              Analyze
                            </Link>
                            <button
                              onClick={() => sendToSlack(row)}
                              disabled={slackSending === row.symbol}
                              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                              {slackSending === row.symbol ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Send className="h-3 w-3" />
                              )}
                              Slack
                            </button>
                          </div>
                        </td>
                      </tr>
                      {isExpanded && hasBreakdown && (
                        <tr key={`${row.symbol}-expand`} className="border-b border-border/50 bg-muted/20">
                          <td colSpan={7} className="py-3 pr-4 pl-8 text-xs">
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
                              {row.score_breakdown && (
                                <>
                                  <span className="text-muted-foreground">Data quality</span>
                                  <span>{row.score_breakdown.data_quality_score}</span>
                                  <span className="text-muted-foreground">Regime</span>
                                  <span>{row.score_breakdown.regime_score}</span>
                                  <span className="text-muted-foreground">Liquidity</span>
                                  <span>{row.score_breakdown.options_liquidity_score}</span>
                                  <span className="text-muted-foreground">Strategy fit</span>
                                  <span>{row.score_breakdown.strategy_fit_score}</span>
                                  <span className="text-muted-foreground">Capital eff.</span>
                                  <span>{row.score_breakdown.capital_efficiency_score}</span>
                                  <span className="text-muted-foreground font-medium">Composite</span>
                                  <span className="font-semibold">{row.score_breakdown.composite_score}</span>
                                </>
                              )}
                            </div>
                            {(row.csp_notional != null || row.notional_pct != null) && (
                              <p className="mt-1 text-muted-foreground">
                                {row.csp_notional != null && `CSP notional: $${row.csp_notional.toLocaleString()}`}
                                {row.notional_pct != null && ` • ${(row.notional_pct * 100).toFixed(1)}% of account`}
                              </p>
                            )}
                            {row.rank_reasons && (
                              <div className="mt-1">
                                {row.rank_reasons.reasons?.length > 0 && (
                                  <p className="text-muted-foreground">
                                    <span className="font-medium text-foreground">Reasons: </span>
                                    {row.rank_reasons.reasons.join(" • ")}
                                  </p>
                                )}
                                {row.rank_reasons.penalty && (
                                  <p className="text-amber-700 dark:text-amber-400">
                                    <span className="font-medium">Penalty: </span>
                                    {row.rank_reasons.penalty}
                                  </p>
                                )}
                              </div>
                            )}
                            {row.band_reason && (
                              <p className="mt-0.5 text-muted-foreground" title="Why this band">
                                {row.band_reason}
                              </p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                    );
                    })}
                  </tbody>
                </table>
              </div>

              {universeEval?.last_evaluated_at && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Last evaluated: {formatDate(universeEval.last_evaluated_at)}
                  {universeEval.duration_seconds && ` (${universeEval.duration_seconds.toFixed(1)}s)`}
                </p>
              )}
            </>
          )}

          {/* Fallback: Basic universe table if no evaluation yet */}
          {universe && (!universeEval || universeEval.symbols.length === 0) && !universeError && (
            <>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[600px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Symbol</th>
                      <th className="py-2 pr-4 font-medium">Source</th>
                      <th className="py-2 pr-4 font-medium">Last Price</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {universe.symbols.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-muted-foreground">
                          No symbols in universe. Check config/universe.csv.
                        </td>
                      </tr>
                    )}
                    {universe.symbols.map((row) => (
                      <tr key={row.symbol} className="border-b border-border/50 hover:bg-muted/30">
                        <td className="py-2 pr-4 font-medium">{row.symbol}</td>
                        <td className="py-2 pr-4 text-muted-foreground">{row.source ?? "orats"}</td>
                        <td className="py-2 pr-4">
                          {row.last_price != null ? `$${row.last_price.toFixed(2)}` : "Not available"}
                        </td>
                        <td className="py-2 pr-4">
                          {row.exclusion_reason ? (
                            <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400" title={row.exclusion_reason}>
                              <XCircle className="h-4 w-4" />
                              Excluded
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-muted-foreground">
                              <Clock className="h-4 w-4" />
                              Not evaluated yet
                            </span>
                          )}
                        </td>
                        <td className="py-2">
                          <Link
                            to={`/analysis?symbol=${encodeURIComponent(row.symbol)}`}
                            className="flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            Analyze <ExternalLink className="h-3 w-3" />
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {universe.updated_at && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Universe loaded: {formatDate(universe.updated_at)}
                </p>
              )}
            </>
          )}
        </section>
      )}

      {/* MOCK mode notice */}
      {mode !== "LIVE" && (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-muted-foreground">Switch to LIVE mode to view the universe.</p>
        </div>
      )}
    </div>
  );
}
