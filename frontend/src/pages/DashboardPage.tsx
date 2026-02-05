import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { getDailyOverview, getTradePlan, getAlerts } from "@/data/source";
import { useDataMode } from "@/context/DataModeContext";
import { useScenario } from "@/context/ScenarioContext";
import { usePolling } from "@/context/PollingContext";
import { useApiSnapshot, hasSnapshotErrors, hasSnapshotWarnings } from "@/hooks/useApiSnapshot";
import { DecisionBanner } from "@/components/DecisionBanner";
import { TradePlanCard } from "@/components/TradePlanCard";
import { DailyOverviewCard } from "@/components/DailyOverviewCard";
import { AlertsSection } from "@/components/AlertsSection";
import { EmptyState } from "@/components/EmptyState";
import {
  pushSystemNotification,
  pushSystemNotificationItem,
  systemNotificationFromWarnings,
} from "@/lib/notifications";
import { validateDailyOverview, validateAlerts } from "@/mock/validator";
import type { DailyOverviewView, TradePlanView, AlertsView } from "@/types/views";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { AlertTriangle, CheckCircle2, Info, ExternalLink, XCircle, Play, Send, Loader2, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  UniverseEvaluationResult,
  SymbolEvaluationResult,
  EvaluateNowResponse,
  SlackNotifyResponse,
  EvaluationLatestResponse,
  EvaluationStatusCurrentResponse,
} from "@/types/universeEvaluation";
import { getVerdictColor, formatPrice, formatReason, formatSelectedContract } from "@/types/universeEvaluation";

function liveErrorMessage(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

export function DashboardPage() {
  const { mode } = useDataMode();
  const scenario = useScenario();
  const polling = usePolling();
  const pollTick = polling?.pollTick ?? 0;
  const [overview, setOverview] = useState<DailyOverviewView | null>(null);
  const [tradePlan, setTradePlan] = useState<TradePlanView | null>(null);
  const [alerts, setAlerts] = useState<AlertsView | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);

  // Snapshot-driven state (LIVE only)
  const { snapshot, loading: snapshotLoading, error: snapshotError, refetch: refetchSnapshot } = useApiSnapshot();

  // Universe evaluation state (single source: evaluation/latest only)
  const [universeEval, setUniverseEval] = useState<UniverseEvaluationResult | null>(null);
  const [latestRun, setLatestRun] = useState<EvaluationLatestResponse | null>(null);
  const [evalRunning, setEvalRunning] = useState(false);
  const [, setCurrentRunId] = useState<string | null>(null);
  const [slackSending, setSlackSending] = useState<string | null>(null);

  // Single source of truth: only evaluation/latest (no live recompute from universe-evaluation).
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
          symbols: data.symbols as SymbolEvaluationResult[],
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

  // Fetch current evaluation status (is running, run_id).
  const fetchEvalStatus = useCallback(async () => {
    if (mode !== "LIVE") return;
    try {
      const data = await apiGet<EvaluationStatusCurrentResponse>(ENDPOINTS.evaluationStatusCurrent);
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
        // Poll for completion using the status endpoint
        const pollInterval = setInterval(async () => {
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
  }, [evalRunning, fetchLatestRun, refetchSnapshot]);

  // Send to Slack
  const sendToSlack = useCallback(async (symbol: SymbolEvaluationResult, trade?: { strategy: string; expiry?: string | null; strike?: number | null; delta?: number | null; credit_estimate?: number | null }) => {
    const key = `${symbol.symbol}-${trade?.strategy ?? "default"}`;
    setSlackSending(key);
    try {
      const result = await apiPost<SlackNotifyResponse>(ENDPOINTS.notifySlack, {
        meta: {
          symbol: symbol.symbol,
          strategy: trade?.strategy ?? symbol.verdict,
          expiry: trade?.expiry,
          strike: trade?.strike,
          delta: trade?.delta,
          credit_estimate: trade?.credit_estimate,
          score: symbol.score,
          reason: symbol.primary_reason,
        },
      });
      // Show appropriate notification based on Slack delivery result
      if (result.sent) {
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Sent to Slack",
          message: result.reason ?? `${symbol.symbol} notification sent`,
        });
      } else {
        // Check if this is a "not configured" case - show as WARNING, not error
        const isNotConfigured = result.reason?.toLowerCase().includes("not configured") || 
                                result.reason?.toLowerCase().includes("slack_webhook_url");
        if (isNotConfigured) {
          pushSystemNotification({
            source: "system",
            severity: "warning",
            title: "Slack not configured",
            message: "Add SLACK_WEBHOOK_URL to your .env file to enable alerts",
          });
        } else {
          // Actual delivery failure - show error
          const failureDetails = result.status_code 
            ? `HTTP ${result.status_code}: ${result.reason ?? "Unknown error"}`
            : result.reason ?? "Slack delivery failed";
          pushSystemNotification({
            source: "system",
            severity: "error",
            title: "Slack delivery failed",
            message: failureDetails,
          });
        }
      }
    } catch (e) {
      // Catch 503 responses and treat "not configured" as warning
      const msg = e instanceof Error ? e.message : String(e);
      const isNotConfigured = msg.toLowerCase().includes("not configured") || 
                              msg.toLowerCase().includes("503");
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

  // Snapshot-only reads: only evaluation/latest (no universe-evaluation).
  useEffect(() => {
    if (mode === "LIVE") {
      fetchLatestRun();
      fetchEvalStatus();
    }
  }, [mode, fetchLatestRun, fetchEvalStatus, pollTick]);

  useEffect(() => {
    if (mode === "MOCK" && scenario?.bundle) {
      setLiveError(null);
      setOverview(scenario.bundle.dailyOverview ?? null);
      setTradePlan(scenario.bundle.tradePlan ?? null);
      setAlerts(scenario.bundle.alerts ?? null);
      return;
    }
    if (mode !== "LIVE") return;
    let cancelled = false;
    setLiveError(null);
    Promise.all([getDailyOverview(mode), getTradePlan(mode), getAlerts(mode)])
      .then(([o, t, a]) => {
        if (cancelled) return;
        setOverview(o ?? null);
        setTradePlan(t ?? null);
        setAlerts(a ?? null);
        const evaluatedAt = o?.links?.latest_decision_ts ?? new Date().toISOString();
        const w1 = validateDailyOverview(o ?? null);
        const w2 = validateAlerts(a ?? null);
        const warnings = [...w1, ...w2];
        if (warnings.length > 0) {
          const items = systemNotificationFromWarnings(warnings, "LIVE", evaluatedAt);
          items.forEach((item) => pushSystemNotificationItem(item));
        }
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = liveErrorMessage(e);
          setLiveError(msg);
          pushSystemNotification({
            source: "system",
            severity: "error",
            title: "LIVE fetch failed",
            message: msg,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, scenario?.bundle, mode === "LIVE" ? pollTick : 0]);

  if (mode === "LIVE" && liveError) {
    return (
      <div className="space-y-6 p-6">
        <h1 className="sr-only">Dashboard</h1>
        <EmptyState title="LIVE data unavailable" message={liveError} />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="sr-only">Dashboard</h1>

      {/* Compact System Status Pill (LIVE only) — click to open diagnostics
          Color rules:
          - GREEN: evaluation_state === COMPLETED && no blocking warnings
          - YELLOW: IDLE or STALE
          - RED: FAILED
      */}
      {mode === "LIVE" && snapshot && (
        <Link
          to="/diagnostics"
          className={cn(
            "flex items-center justify-between rounded-lg border p-3 transition-colors hover:bg-muted/50",
            // GREEN: COMPLETED and no errors
            snapshot.evaluation_state === "COMPLETED" && !hasSnapshotErrors(snapshot) && "border-emerald-500/30 bg-emerald-500/5",
            // YELLOW: IDLE or STALE
            (snapshot.evaluation_state === "IDLE" || snapshot.snapshot_phase === "STALE") && "border-amber-500/30 bg-amber-500/5",
            // RED: FAILED or any errors
            (snapshot.evaluation_state === "FAILED" || hasSnapshotErrors(snapshot)) && "border-destructive/30 bg-destructive/5",
            // BLUE: RUNNING (in progress)
            snapshot.evaluation_state === "RUNNING" && "border-blue-500/30 bg-blue-500/5"
          )}
          title="Click to view diagnostics"
        >
          <div className="flex items-center gap-3">
            {/* Status indicator - color based on evaluation_state */}
            <div className={cn(
              "h-3 w-3 rounded-full",
              snapshot.evaluation_state === "COMPLETED" && !hasSnapshotErrors(snapshot) && "bg-emerald-500",
              (snapshot.evaluation_state === "IDLE" || snapshot.snapshot_phase === "STALE") && "bg-amber-500",
              (snapshot.evaluation_state === "FAILED" || hasSnapshotErrors(snapshot)) && "bg-destructive",
              snapshot.evaluation_state === "RUNNING" && "animate-pulse bg-blue-500"
            )} />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">
                  {snapshot.run_mode} • {snapshot.market_status.phase ?? "Unknown market"}
                </span>
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  snapshot.evaluation_state === "COMPLETED" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                  snapshot.evaluation_state === "IDLE" && "bg-muted text-muted-foreground",
                  snapshot.evaluation_state === "RUNNING" && "bg-blue-500/20 text-blue-600 dark:text-blue-400",
                  snapshot.evaluation_state === "FAILED" && "bg-destructive/20 text-destructive"
                )}>
                  {snapshot.evaluation_state}
                </span>
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  snapshot.orats_connected ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground"
                )}>
                  ORATS: {snapshot.orats_connected ? "OK" : snapshot.orats_status}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {snapshot.evaluation_state_reason}
                {snapshot.data_stale && <span className="ml-2 text-amber-600 dark:text-amber-400">(data stale)</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Universe: {snapshot.universe.total}</span>
            <span>Evaluated: {snapshot.universe.evaluated}</span>
            {hasSnapshotWarnings(snapshot) && (
              <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <AlertTriangle className="h-3 w-3" /> {snapshot.warnings.length}
              </span>
            )}
            {hasSnapshotErrors(snapshot) && (
              <span className="flex items-center gap-1 text-destructive">
                <XCircle className="h-3 w-3" /> {snapshot.errors.length}
              </span>
            )}
            <ExternalLink className="h-3 w-3" />
          </div>
        </Link>
      )}

      <DecisionBanner overview={overview} tradePlan={tradePlan} />

      {/* Today's Decision Card — ONLY renders if has_decision_artifact is true */}
      {mode === "LIVE" && snapshot && snapshot.has_decision_artifact && (
        <section className="rounded-lg border border-border bg-card p-4" aria-label="Today's decision">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-medium text-muted-foreground">Today's Decision</h2>
            <span
              className="cursor-help text-muted-foreground"
              title="Dashboard shows only the FINAL trade candidate. Universe contains all symbols; evaluation filters to one best trade."
            >
              <Info className="h-4 w-4" />
            </span>
          </div>
          {snapshot.final_trade ? (
            <div className="mt-3 flex items-center gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
                <span className="text-lg font-semibold text-foreground">{snapshot.final_trade.symbol}</span>
              </div>
              <span className="text-sm text-muted-foreground">
                {snapshot.final_trade.strategy} • {snapshot.final_trade.direction}
                {snapshot.final_trade.confidence != null && ` • ${(snapshot.final_trade.confidence * 100).toFixed(0)}%`}
              </span>
            </div>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">Evaluation complete. No trade candidate today — all symbols blocked or not eligible.</p>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            <span title="From universe.csv">Universe: {snapshot.universe.total}</span>
            {" → "}
            <span title="Symbols that passed initial filters">Evaluated: {snapshot.universe.evaluated}</span>
            {" → "}
            <span title="Symbols eligible for trade">Eligible: {snapshot.universe.eligible}</span>
            {" → "}
            <span title="Final shortlist">Shortlisted: {snapshot.universe.shortlisted}</span>
            {" → "}
            <span title="Best trade selected">Final: {snapshot.final_trade ? 1 : 0}</span>
          </p>
        </section>
      )}

      {/* Backend failure: corrupt or missing run — do not hide */}
      {mode === "LIVE" && latestRun && (latestRun.backend_failure || latestRun.status === "CORRUPTED") && (
        <section className="rounded-lg border border-destructive/50 bg-destructive/10 p-4" aria-label="Backend failure">
          <div className="flex items-center gap-3">
            <XCircle className="h-5 w-5 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Evaluation data unavailable</p>
              <p className="text-sm text-muted-foreground">{latestRun.reason ?? "Persisted run corrupt or missing."}</p>
            </div>
          </div>
        </section>
      )}

      {/* No evaluation run yet banner with Run Now button */}
      {mode === "LIVE" && snapshot && !snapshot.has_decision_artifact && (
        <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4" aria-label="Awaiting evaluation">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              <div>
                <p className="font-medium text-amber-700 dark:text-amber-300">No evaluation run yet for today</p>
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  The system has not completed an evaluation cycle. Trade decisions will appear here once evaluation runs.
                </p>
              </div>
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
        </section>
      )}

      {/* Eligible Candidates Table */}
      {mode === "LIVE" && universeEval && universeEval.symbols.some(s => s.verdict === "ELIGIBLE" && s.stage_reached === "STAGE2_CHAIN") && (
        <section className="rounded-lg border border-border bg-card p-4" aria-label="Eligible candidates">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-medium text-muted-foreground">Eligible Candidates</h2>
              <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                {universeEval.symbols.filter(s => s.verdict === "ELIGIBLE" && s.stage_reached === "STAGE2_CHAIN").length} chain-evaluated
              </span>
            </div>
            {(universeEval.last_evaluated_at || latestRun?.run_id) && (
              <span className="text-xs text-muted-foreground" title={latestRun?.run_id ?? undefined}>
                {latestRun?.run_id && <span className="font-mono">{latestRun.run_id.slice(-8)}</span>}
                {universeEval.last_evaluated_at && <> • {new Date(universeEval.last_evaluated_at).toLocaleTimeString()}</>}
              </span>
            )}
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Price</th>
                  <th className="pb-2 pr-4">Verdict</th>
                  <th className="pb-2 pr-4">Score</th>
                  <th className="pb-2 pr-4">Contract</th>
                  <th className="pb-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {universeEval.symbols
                  .filter((s) => s.verdict === "ELIGIBLE" && s.stage_reached === "STAGE2_CHAIN")
                  .sort((a, b) => b.score - a.score)
                  .slice(0, 10)
                  .map((sym) => {
                    const reasonInfo = formatReason(sym.primary_reason);
                    const selectedContractStr = formatSelectedContract(sym.selected_contract);
                    return (
                    <tr key={sym.symbol} className="border-b border-border/50 last:border-0">
                      <td className="py-2 pr-4 font-medium">{sym.symbol}</td>
                      <td className="py-2 pr-4">
                        <span className={sym.price === null ? "text-muted-foreground italic" : ""}>
                          {formatPrice(sym.price)}
                        </span>
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span
                            className={cn("rounded-full px-2 py-0.5 text-xs font-medium cursor-help", getVerdictColor(sym.verdict))}
                            title={[sym.rationale?.summary ?? sym.primary_reason, sym.capital_hint ? `Band ${sym.capital_hint.band} • ${(sym.capital_hint.suggested_capital_pct * 100).toFixed(0)}% capital` : null].filter(Boolean).join(" • ")}
                          >
                            {sym.verdict}
                          </span>
                          {sym.position_open && (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/50 dark:text-amber-300" title={sym.position_reason ?? "Position open"}>
                              Position open
                            </span>
                          )}
                          {sym.capital_hint && (
                            <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground cursor-help" title={`Suggested capital: ${(sym.capital_hint.suggested_capital_pct * 100).toFixed(0)}%`}>
                              {sym.capital_hint.band}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-2 pr-4">
                        <span className={cn(
                          "font-medium",
                          sym.score >= 70 ? "text-emerald-600 dark:text-emerald-400" :
                          sym.score >= 50 ? "text-amber-600 dark:text-amber-400" :
                          "text-muted-foreground"
                        )}>
                          {sym.score}
                        </span>
                      </td>
                      <td className="py-2 pr-4 max-w-[220px]" title={sym.primary_reason}>
                        {selectedContractStr ? (
                          <span className="font-mono text-xs text-emerald-600 dark:text-emerald-400">
                            {selectedContractStr}
                          </span>
                        ) : reasonInfo.isDataIncomplete ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/50 dark:text-amber-300">
                            <AlertTriangle className="h-3 w-3" />
                            DATA_INCOMPLETE
                          </span>
                        ) : (
                          <span className="text-muted-foreground truncate block">
                            {sym.primary_reason.slice(0, 35)}{sym.primary_reason.length > 35 ? "..." : ""}
                          </span>
                        )}
                      </td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/analysis?symbol=${sym.symbol}`}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-primary hover:bg-muted"
                          >
                            <Search className="h-3 w-3" />
                            Analyze
                          </Link>
                          <button
                            onClick={() => sendToSlack(sym)}
                            disabled={slackSending === `${sym.symbol}-default`}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                          >
                            {slackSending === `${sym.symbol}-default` ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Send className="h-3 w-3" />
                            )}
                            Slack
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                  })}
              </tbody>
            </table>
          </div>
          {universeEval.counts.eligible > 10 && (
            <div className="mt-3 text-center">
              <Link to="/analytics" className="text-xs text-primary hover:underline">
                View all {universeEval.counts.eligible} eligible candidates
              </Link>
            </div>
          )}
        </section>
      )}

      {/* No eligible candidates message */}
      {mode === "LIVE" && universeEval && universeEval.evaluation_state === "COMPLETED" && universeEval.counts.eligible === 0 && (
        <section className="rounded-lg border border-border bg-card p-4" aria-label="No eligible candidates">
          <div className="flex items-center gap-3">
            <Info className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="font-medium text-foreground">No eligible candidates in last run</p>
              <p className="text-sm text-muted-foreground">
                All {universeEval.counts.evaluated} evaluated symbols were blocked or held. Check the Universe page for details.
              </p>
            </div>
          </div>
        </section>
      )}

      <TradePlanCard tradePlan={tradePlan} overview={overview ?? undefined} />

      <DailyOverviewCard overview={overview} />

      {/* Universe Summary with link */}
      {mode === "LIVE" && (
        <section className="rounded-lg border border-border bg-card p-4" aria-label="Universe summary">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">Universe Summary</h2>
            <Link
              to="/analytics"
              className="flex items-center gap-1 text-xs text-primary hover:underline"
            >
              View all symbols <ExternalLink className="h-3 w-3" />
            </Link>
          </div>
          {snapshot && (
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div title="Total symbols in universe (config/universe.csv)">
                <p className="text-xs text-muted-foreground">Total</p>
                <p className="font-medium text-foreground">{snapshot.universe.total}</p>
              </div>
              <div title="Symbols evaluated in last run">
                <p className="text-xs text-muted-foreground">Evaluated</p>
                <p className="font-medium text-foreground">{snapshot.universe.evaluated}</p>
              </div>
              <div title="Symbols eligible for trading">
                <p className="text-xs text-muted-foreground">Eligible</p>
                <p className="font-medium text-foreground">{snapshot.universe.eligible}</p>
              </div>
              <div title="Symbols shortlisted for final selection">
                <p className="text-xs text-muted-foreground">Shortlisted</p>
                <p className="font-medium text-foreground">{snapshot.universe.shortlisted}</p>
              </div>
            </div>
          )}
          {!snapshot && snapshotLoading && (
            <p className="mt-3 text-sm text-muted-foreground">Loading snapshot...</p>
          )}
          {!snapshot && snapshotError && (
            <p className="mt-3 text-sm text-destructive">{snapshotError}</p>
          )}
        </section>
      )}

      <AlertsSection alerts={alerts} />
    </div>
  );
}
