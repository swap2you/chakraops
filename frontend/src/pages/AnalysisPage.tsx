/**
 * Ticker — symbol diagnostics for any ticker; OUT_OF_SCOPE banner; Fetch latest data (rate-limited).
 * Progressive loading: shows cached data while fetching fresh data.
 * Send to Slack button for candidate trades.
 * 
 * IMPORTANT: Uses per-symbol AbortController.
 * Cancels ONLY when: symbol changes OR page unmounts.
 * NEVER cancels due to snapshot polling or other page activity.
 */
import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { EmptyState } from "@/components/EmptyState";
import { pushSystemNotification } from "@/lib/notifications";
import type { SymbolDiagnosticsView, SymbolDiagnosticsCandidateTrade } from "@/types/symbolDiagnostics";
import type { SlackNotifyResponse } from "@/types/universeEvaluation";
import { ManualExecuteModal } from "@/components/ManualExecuteModal";
import type { Account, AccountDefaultResponse, CspSizingResponse } from "@/types/accounts";
import type { PositionStrategy } from "@/types/trackedPositions";
import { cn } from "@/lib/utils";
import { Search, ExternalLink, CheckCircle2, XCircle, HelpCircle, TrendingUp, Shield, Option, RefreshCw, Loader2, AlertTriangle, DollarSign, BarChart3, Activity, Send, Target } from "lucide-react";

const TRADINGVIEW_BASE = "https://www.tradingview.com/symbols";
const FETCH_COOLDOWN_MS = 60_000;

// Simple in-memory cache for symbol diagnostics
const symbolCache = new Map<string, { data: SymbolDiagnosticsView; fetchedAt: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Not available";
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "Not available" : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "Not available";
  }
}

function getCachedData(sym: string): SymbolDiagnosticsView | null {
  const cached = symbolCache.get(sym);
  if (!cached) return null;
  if (Date.now() - cached.fetchedAt > CACHE_TTL_MS) {
    symbolCache.delete(sym);
    return null;
  }
  return cached.data;
}

function setCachedData(sym: string, data: SymbolDiagnosticsView): void {
  symbolCache.set(sym, { data, fetchedAt: Date.now() });
}

type LoadingPhase = "idle" | "metadata" | "summary" | "options" | "complete";

export function AnalysisPage() {
  const { mode } = useDataMode();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialSymbol = searchParams.get("symbol")?.toUpperCase() || "";

  const [symbol, setSymbol] = useState(initialSymbol);
  const [inputValue, setInputValue] = useState(initialSymbol);
  const [data, setData] = useState<SymbolDiagnosticsView | null>(() => getCachedData(initialSymbol));
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState<LoadingPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fetchCooldownRemaining, setFetchCooldownRemaining] = useState(0);
  const [slackSending, setSlackSending] = useState<string | null>(null);
  // Phase 1: Manual execution state
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeTradeInfo, setExecuteTradeInfo] = useState<{
    strategy: PositionStrategy;
    strike?: number | null;
    expiration?: string | null;
    creditEstimate?: number | null;
  } | null>(null);
  const [defaultAccount, setDefaultAccount] = useState<Account | null>(null);
  const [defaultSizing, setDefaultSizing] = useState<CspSizingResponse | null>(null);
  const lastFetchTs = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentSymbolRef = useRef<string>("");
  const isMountedRef = useRef(true);

  // Phase 1: Fetch default account for capital awareness
  useEffect(() => {
    if (mode !== "LIVE") return;
    apiGet<AccountDefaultResponse>(ENDPOINTS.accountsDefault)
      .then((res) => {
        if (res.account) setDefaultAccount(res.account);
      })
      .catch(() => {
        // No default account — that's fine
      });
  }, [mode]);

  // Phase 1: Fetch CSP sizing when default account and data changes
  useEffect(() => {
    if (!defaultAccount || !data?.candidate_trades?.length) {
      setDefaultSizing(null);
      return;
    }
    // Use first CSP candidate's strike for sizing
    const cspTrade = data.candidate_trades.find((t) => t.strategy === "CSP" && t.strike);
    if (!cspTrade?.strike) {
      setDefaultSizing(null);
      return;
    }
    apiGet<CspSizingResponse>(
      `${ENDPOINTS.accountCspSizing(defaultAccount.account_id)}?strike=${cspTrade.strike}`
    )
      .then((res) => setDefaultSizing(res))
      .catch(() => setDefaultSizing(null));
  }, [defaultAccount, data?.candidate_trades]);

  // Phase 1: Open execute modal
  const openExecuteModal = useCallback((trade: SymbolDiagnosticsCandidateTrade) => {
    setExecuteTradeInfo({
      strategy: trade.strategy as PositionStrategy,
      strike: trade.strike,
      expiration: trade.expiry,
      creditEstimate: trade.credit_estimate,
    });
    setExecuteModalOpen(true);
  }, []);

  // Send to Slack
  const sendToSlack = useCallback(async (trade: SymbolDiagnosticsCandidateTrade, sym: string) => {
    const key = `${sym}-${trade.strategy}-${trade.strike}`;
    setSlackSending(key);
    try {
      const result = await apiPost<SlackNotifyResponse>(ENDPOINTS.notifySlack, {
        meta: {
          symbol: sym,
          strategy: trade.strategy,
          expiry: trade.expiry,
          strike: trade.strike,
          delta: trade.delta,
          credit_estimate: trade.credit_estimate,
          reason: trade.why_this_trade,
        },
      });
      if (result.sent) {
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Sent to Slack",
          message: result.reason ?? `${sym} ${trade.strategy} notification sent`,
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

  // Auto-fetch on initial load if symbol is provided
  useEffect(() => {
    isMountedRef.current = true;
    if (mode === "LIVE" && initialSymbol && !data) {
      fetchDiagnostics(initialSymbol);
    }
    return () => {
      isMountedRef.current = false;
    };
  }, [mode, initialSymbol]);

  const fetchDiagnostics = useCallback(async (sym: string): Promise<void> => {
    // Cancel any in-flight request for a DIFFERENT symbol
    if (abortControllerRef.current && currentSymbolRef.current !== sym) {
      abortControllerRef.current.abort();
    }
    
    // Create new controller for this symbol
    const controller = new AbortController();
    abortControllerRef.current = controller;
    currentSymbolRef.current = sym;

    setLoading(true);
    setLoadingPhase("metadata");
    setError(null);
    // wasAborted no longer used - aborts are handled silently

    // Show cached data while loading (progressive)
    const cached = getCachedData(sym);
    if (cached) {
      setData(cached);
    }

    const params = new URLSearchParams({ symbol: sym });
    
    try {
      const res = await apiGet<SymbolDiagnosticsView>(
        `${ENDPOINTS.symbolDiagnostics}?${params}`,
        { signal: controller.signal, timeoutMs: 30_000 }
      );
      
      if (!isMountedRef.current) return;
      
      if (res) {
        setData(res);
        setCachedData(sym, res);
        setLoadingPhase("complete");
      }
      lastFetchTs.current = Date.now();
    } catch (e) {
      if (!isMountedRef.current) return;
      
      // Handle abort SILENTLY - this is normal navigation behavior, not an error
      if (e instanceof Error && e.name === "AbortError") {
        // Silent return - user navigated away or changed symbol, this is expected
        // Do NOT show error banner for aborts
        return;
      }
      
      // Don't clear data on error if we have cached data (show stale)
      if (!getCachedData(sym)) {
        setData(null);
      }
      
      if (e instanceof ApiError) {
        const detail = e.body && typeof e.body === "object" && "detail" in e.body ? (e.body.detail as { reason?: string; symbol?: string }) : null;
        const reason = detail?.reason ?? (e.status === 503 ? "ORATS data unavailable for this symbol" : e.status === 404 ? "Endpoint not found (check proxy/backend)." : `${e.status}: ${e.message}`);
        setError(reason);
        pushSystemNotification({
          source: "system",
          severity: "error",
          title: e.status === 503 ? "ORATS: DOWN" : "Ticker analysis failed",
          message: reason,
        });
      } else {
        setError(e instanceof Error ? e.message : "Could not load diagnostics.");
        pushSystemNotification({
          source: "system",
          severity: "error",
          title: "Ticker analysis failed",
          message: e instanceof Error ? e.message : "Could not load diagnostics.",
        });
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
        setLoadingPhase("idle");
      }
    }
  }, []);

  const runAnalysis = useCallback(() => {
    const sym = inputValue.trim().toUpperCase();
    if (!sym) {
      setError("Enter a symbol");
      return;
    }
    setSymbol(sym);
    setSearchParams({ symbol: sym }); // Update URL
    setError(null);
    setFetchCooldownRemaining(0);
    // Don't clear data immediately — show cached if available
    const cached = getCachedData(sym);
    if (cached) {
      setData(cached);
    } else {
      setData(null);
    }
    fetchDiagnostics(sym);
  }, [inputValue, fetchDiagnostics, setSearchParams]);

  const fetchLatestData = useCallback(() => {
    if (!symbol || fetchCooldownRemaining > 0 || loading) return;
    fetchDiagnostics(symbol).then(() => {
      setFetchCooldownRemaining(Math.ceil(FETCH_COOLDOWN_MS / 1000));
      const id = setInterval(() => {
        setFetchCooldownRemaining((s) => (s <= 1 ? 0 : s - 1));
      }, 1000);
      setTimeout(() => clearInterval(id), FETCH_COOLDOWN_MS + 500);
    });
  }, [symbol, loading, fetchCooldownRemaining, fetchDiagnostics]);

  // Cleanup on unmount - abort any pending request
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const tradingViewUrl = symbol
    ? `${TRADINGVIEW_BASE}/NASDAQ-${symbol}/`
    : TRADINGVIEW_BASE;

  // Progressive loading indicator
  const loadingIndicator = useMemo(() => {
    if (!loading) return null;
    const phases: Record<LoadingPhase, string> = {
      idle: "",
      metadata: "Fetching metadata...",
      summary: "Loading summary...",
      options: "Loading options data...",
      complete: "Complete",
    };
    return phases[loadingPhase] || "Loading...";
  }, [loading, loadingPhase]);

  if (mode !== "LIVE") {
    return (
      <div className="p-6">
        <EmptyState
          title="LIVE only"
          message="Symbol analysis is available in LIVE mode. Switch to LIVE to analyze tickers against the backend universe and gates."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-2xl font-semibold text-foreground">Ticker</h1>
        <div className="flex flex-1 flex-wrap items-center gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runAnalysis()}
            placeholder="e.g. NVDA"
            className="max-w-[140px] rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Symbol"
          />
          <button
            type="button"
            onClick={runAnalysis}
            disabled={loading}
            className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {loading ? "Loading…" : "Analyze"}
          </button>
        </div>
        {/* Progressive loading indicator */}
        {loading && loadingIndicator && (
          <span className="text-xs text-muted-foreground">{loadingIndicator}</span>
        )}
      </div>

      {/* Error state — but still show cached data below if available */}
      {error && !data && (
        <EmptyState
          title="Analysis failed"
          message={error}
          action={
            <button
              type="button"
              onClick={runAnalysis}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Retry
            </button>
          }
        />
      )}

      {/* Error banner when showing stale cached data or aborted */}
      {error && data && (
        <div className="flex items-center gap-3 rounded-lg p-3 text-sm border border-destructive/30 bg-destructive/5">
          <XCircle className="h-5 w-5 shrink-0 text-destructive" />
          <div className="flex-1">
            <span className="text-destructive">
              {error}
            </span>
            {data && <span className="ml-2 text-muted-foreground">(showing cached data)</span>}
          </div>
          <button
            type="button"
            onClick={runAnalysis}
            className="rounded-md border border-border bg-secondary px-3 py-1.5 text-sm font-medium hover:bg-secondary/80"
          >
            Retry
          </button>
        </div>
      )}

      {data && !error && (
        <div className="space-y-6">
          {/* 1. Stock Snapshot */}
          {data.stock && (
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <DollarSign className="h-4 w-4" /> Stock Snapshot
              </h2>
              <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-5">
                <div>
                  <p className="text-xs text-muted-foreground">Price</p>
                  <p className="text-lg font-semibold">{data.stock.price != null ? `$${data.stock.price.toFixed(2)}` : "N/A"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Bid / Ask</p>
                  <p className="font-medium">
                    {data.stock.bid != null ? `$${data.stock.bid.toFixed(2)}` : "N/A"} / {data.stock.ask != null ? `$${data.stock.ask.toFixed(2)}` : "N/A"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Volume</p>
                  <p className="font-medium">{data.stock.volume?.toLocaleString() ?? "N/A"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Avg Volume</p>
                  <p className="font-medium">{data.stock.avg_volume?.toLocaleString() ?? "N/A"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Trend</p>
                  <p className={cn(
                    "font-medium",
                    data.stock.trend === "UP" && "text-emerald-600 dark:text-emerald-400",
                    data.stock.trend === "DOWN" && "text-destructive",
                    data.stock.trend === "NEUTRAL" && "text-muted-foreground"
                  )}>{data.stock.trend ?? "NEUTRAL"}</p>
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Data as of: {formatDate(data.fetched_at ?? data.snapshot_time)}
                {data.data_latency_seconds != null && ` (${data.data_latency_seconds}s latency)`}
              </p>
            </section>
          )}

          {/* 2. Verdict Banner (green/yellow/red) */}
          <section className={cn(
            "rounded-lg p-4",
            data.eligibility?.verdict === "ELIGIBLE" && "border border-emerald-500/30 bg-emerald-500/10",
            data.eligibility?.verdict === "HOLD" && "border border-amber-500/30 bg-amber-500/10",
            data.eligibility?.verdict === "BLOCKED" && "border border-destructive/30 bg-destructive/10",
            !data.eligibility?.verdict && "border border-muted bg-muted/30"
          )}>
            <div className="flex items-center gap-3">
              {data.eligibility?.verdict === "ELIGIBLE" && <CheckCircle2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />}
              {data.eligibility?.verdict === "HOLD" && <AlertTriangle className="h-6 w-6 text-amber-600 dark:text-amber-400" />}
              {data.eligibility?.verdict === "BLOCKED" && <XCircle className="h-6 w-6 text-destructive" />}
              {!data.eligibility?.verdict && <HelpCircle className="h-6 w-6 text-muted-foreground" />}
              <div>
                <p className={cn(
                  "text-lg font-semibold",
                  data.eligibility?.verdict === "ELIGIBLE" && "text-emerald-700 dark:text-emerald-300",
                  data.eligibility?.verdict === "HOLD" && "text-amber-700 dark:text-amber-300",
                  data.eligibility?.verdict === "BLOCKED" && "text-destructive"
                )}>
                  {data.eligibility?.verdict ?? "UNKNOWN"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {data.eligibility?.primary_reason ?? "Eligibility not determined"}
                </p>
                {data.eligibility?.confidence_score != null && (
                  <p className="text-xs text-muted-foreground">
                    Confidence: {(data.eligibility.confidence_score * 100).toFixed(0)}%
                  </p>
                )}
                {data.eligibility?.position_open && (
                  <p className="mt-1 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/50 dark:text-amber-300">
                    Position open
                    {data.eligibility.position_reason && <span className="font-normal">({data.eligibility.position_reason})</span>}
                  </p>
                )}
                {data.eligibility?.capital_hint && (
                  <p className="mt-1 inline-flex items-center gap-2">
                    <span className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      data.eligibility.capital_hint.band === "A" && "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300",
                      data.eligibility.capital_hint.band === "B" && "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300",
                      data.eligibility.capital_hint.band === "C" && "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300"
                    )} title={data.eligibility.capital_hint.band_reason ?? `Suggested capital: ${(data.eligibility.capital_hint.suggested_capital_pct * 100).toFixed(0)}% of portfolio`}>
                      Band {data.eligibility.capital_hint.band}
                    </span>
                    <span className="text-xs text-muted-foreground cursor-help" title="Suggested allocation based on confidence">
                      {(data.eligibility.capital_hint.suggested_capital_pct * 100).toFixed(0)}% capital
                    </span>
                  </p>
                )}
                {data.eligibility?.band_reason && (
                  <p className="mt-1 text-xs text-muted-foreground cursor-help" title="Why this band">
                    {data.eligibility.band_reason}
                  </p>
                )}
                {/* Run metadata */}
                {data.eligibility?.from_persisted_run && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    <span className="font-medium">From run:</span>{" "}
                    {data.eligibility.run_id ? data.eligibility.run_id.slice(-12) : "unknown"}
                    {data.eligibility.evaluated_at && (
                      <> • {formatDate(data.eligibility.evaluated_at)}</>
                    )}
                  </p>
                )}
              </div>
            </div>
            {/* Phase 3: Score breakdown and rank reasons */}
            {(data.eligibility?.score_breakdown || data.eligibility?.rank_reasons) && (
              <div className="mt-4 rounded-md border border-border bg-muted/30 p-3">
                <h3 className="text-sm font-medium text-foreground">Score breakdown & rank reasons</h3>
                {data.eligibility?.score_breakdown && (
                  <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
                    <span className="text-muted-foreground">Data quality</span>
                    <span className="font-medium">{data.eligibility.score_breakdown.data_quality_score}</span>
                    <span className="text-muted-foreground">Regime</span>
                    <span className="font-medium">{data.eligibility.score_breakdown.regime_score}</span>
                    <span className="text-muted-foreground">Options liquidity</span>
                    <span className="font-medium">{data.eligibility.score_breakdown.options_liquidity_score}</span>
                    <span className="text-muted-foreground">Strategy fit</span>
                    <span className="font-medium">{data.eligibility.score_breakdown.strategy_fit_score}</span>
                    <span className="text-muted-foreground">Capital efficiency</span>
                    <span className="font-medium">{data.eligibility.score_breakdown.capital_efficiency_score}</span>
                    <span className="text-muted-foreground">Composite</span>
                    <span className="font-semibold">{data.eligibility.score_breakdown.composite_score}</span>
                  </div>
                )}
                {(data.eligibility?.csp_notional != null || data.eligibility?.notional_pct != null) && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {data.eligibility.csp_notional != null && `CSP notional: $${data.eligibility.csp_notional.toLocaleString()}`}
                    {data.eligibility.notional_pct != null && ` • ${(data.eligibility.notional_pct * 100).toFixed(1)}% of account`}
                  </p>
                )}
                {data.eligibility?.rank_reasons && (
                  <div className="mt-2">
                    {data.eligibility.rank_reasons.reasons?.length > 0 && (
                      <p className="text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">Reasons: </span>
                        {data.eligibility.rank_reasons.reasons.join(" • ")}
                      </p>
                    )}
                    {data.eligibility.rank_reasons.penalty && (
                      <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-400">
                        <span className="font-medium">Penalty: </span>
                        {data.eligibility.rank_reasons.penalty}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
            {/* Phase 8: Why this verdict? panel */}
            {data.eligibility?.rationale && (
              <div className="mt-4 rounded-md border border-border bg-muted/30 p-3">
                <h3 className="text-sm font-medium text-foreground">Why this verdict?</h3>
                <p className="mt-1 text-sm text-muted-foreground">{data.eligibility.rationale.summary}</p>
                {data.eligibility.rationale.bullets?.length > 0 && (
                  <ul className="mt-2 list-inside list-disc text-xs text-muted-foreground">
                    {data.eligibility.rationale.bullets.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                )}
                {data.eligibility.rationale.failed_checks?.length > 0 && (
                  <ul className="mt-2 list-inside list-disc text-xs text-amber-700 dark:text-amber-400">
                    {data.eligibility.rationale.failed_checks.map((f, i) => (
                      <li key={i}>{f}</li>
                    ))}
                  </ul>
                )}
                {data.eligibility.rationale.data_warnings?.length > 0 && (
                  <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
                    {data.eligibility.rationale.data_warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {/* Fetch latest button */}
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={fetchLatestData}
                disabled={loading || fetchCooldownRemaining > 0}
                className={cn(
                  "flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm font-medium",
                  loading || fetchCooldownRemaining > 0
                    ? "cursor-not-allowed bg-muted text-muted-foreground"
                    : "bg-secondary/50 text-foreground hover:bg-secondary"
                )}
              >
                <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
                {loading ? "Loading…" : fetchCooldownRemaining > 0 ? `Retry in ${fetchCooldownRemaining}s` : "Refresh"}
              </button>
            </div>
          </section>

          {/* 3. Gates Table (PASS/FAIL) */}
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Activity className="h-4 w-4" /> Gates
            </h2>
            <p className="text-xs text-muted-foreground">All gates must PASS for eligibility</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Gate</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {data.gates.length === 0 ? (
                    <tr><td colSpan={3} className="py-4 text-center text-muted-foreground">No gate data — evaluation not run</td></tr>
                  ) : (
                    data.gates.map((g, i) => (
                      <tr key={i} className="border-b border-border/50">
                        <td className="py-2 pr-4 font-medium">{g.name}</td>
                        <td className="py-2 pr-4">
                          <span className={cn(
                            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                            (g.pass || g.status === "PASS") && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                            (!g.pass && g.status !== "PASS") && "bg-destructive/20 text-destructive"
                          )}>
                            {(g.pass || g.status === "PASS") ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                            {g.status ?? (g.pass ? "PASS" : "FAIL")}
                          </span>
                        </td>
                        <td className="py-2 text-muted-foreground">{g.reason ?? g.detail ?? "No details"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* 4. Regime & Risk */}
          <div className="grid gap-4 sm:grid-cols-2">
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <TrendingUp className="h-4 w-4" /> Market Regime
              </h2>
              <div className="mt-3 space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Regime</span>
                  <span className="font-medium">{data.regime?.market_regime ?? data.market?.regime ?? "Not evaluated"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Trading Allowed</span>
                  <span className={cn(
                    "font-medium",
                    data.regime?.allowed ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                  )}>{data.regime?.allowed ? "Yes" : "No"}</span>
                </div>
                <p className="text-xs text-muted-foreground">{data.regime?.reason ?? "No regime assessment available"}</p>
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Shield className="h-4 w-4" /> Risk Assessment
              </h2>
              <div className="mt-3 space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Posture</span>
                  <span className="font-medium">{data.risk?.posture ?? data.market?.risk_posture ?? "Not evaluated"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Trading Allowed</span>
                  <span className={cn(
                    "font-medium",
                    data.risk?.allowed ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                  )}>{data.risk?.allowed ? "Yes" : "No"}</span>
                </div>
                <p className="text-xs text-muted-foreground">{data.risk?.reason ?? "No risk assessment available"}</p>
              </div>
            </section>
          </div>

          {/* 5. Liquidity */}
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <BarChart3 className="h-4 w-4" /> Liquidity
            </h2>
            <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">Stock Liquidity</p>
                <p className={cn(
                  "font-medium",
                  data.liquidity?.stock_liquidity_ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                )}>{data.liquidity?.stock_liquidity_ok ? "OK" : "Low"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Option Liquidity</p>
                <p className={cn(
                  "font-medium",
                  data.liquidity?.option_liquidity_ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                )}>{data.liquidity?.option_liquidity_ok ? "OK" : "Low"}</p>
              </div>
              <div className="col-span-2 sm:col-span-1">
                <p className="text-xs text-muted-foreground">Assessment</p>
                <p className="text-sm text-muted-foreground">{data.liquidity?.reason ?? "No liquidity data"}</p>
              </div>
            </div>
          </section>

          {/* 6. Options + Greeks */}
          <div className="grid gap-4 sm:grid-cols-2">
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Option className="h-4 w-4" /> Options Chain
              </h2>
              <div className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Has Options</span>
                  <span className="font-medium">{data.options?.has_options ? "Yes" : "No"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Chain OK</span>
                  <span className="font-medium">{data.options?.chain_ok ? "Yes" : "No"}</span>
                </div>
                {data.options?.expirations_count != null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Expirations</span>
                    <span className="font-medium">{data.options.expirations_count}</span>
                  </div>
                )}
                {data.options?.underlying_price != null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Underlying</span>
                    <span className="font-medium">${data.options.underlying_price.toFixed(2)}</span>
                  </div>
                )}
              </div>
            </section>

            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-sm font-semibold text-foreground">Greeks Summary</h2>
              <div className="mt-3 space-y-2 text-sm">
                {data.greeks_summary?.iv_rank != null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">IV Rank</span>
                    <span className={cn(
                      "font-medium",
                      data.greeks_summary.iv_rank > 50 && "text-emerald-600 dark:text-emerald-400",
                      data.greeks_summary.iv_rank < 25 && "text-amber-600 dark:text-amber-400"
                    )}>{data.greeks_summary.iv_rank.toFixed(1)}%</span>
                  </div>
                )}
                {data.greeks_summary?.iv_percentile != null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">IV Percentile</span>
                    <span className="font-medium">{data.greeks_summary.iv_percentile.toFixed(1)}%</span>
                  </div>
                )}
                {data.greeks_summary?.delta_target_range && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Delta Target</span>
                    <span className="font-medium">{data.greeks_summary.delta_target_range}</span>
                  </div>
                )}
                {data.greeks_summary?.theta_bias && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Theta Bias</span>
                    <span className="font-medium text-xs">{data.greeks_summary.theta_bias}</span>
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* 7. Selected Contract (from 2-stage evaluation) */}
          {data.selected_contract && data.stage_reached === "STAGE2_CHAIN" && (
            <section className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">Selected Contract</h2>
                  <p className="text-xs text-emerald-600 dark:text-emerald-400">Best contract from chain evaluation (Stage 2)</p>
                </div>
                <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                  Chain Evaluated
                </span>
              </div>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-lg border border-emerald-500/20 bg-background p-3">
                  <p className="text-xs text-muted-foreground">Contract</p>
                  <p className="font-mono text-sm font-medium">
                    {data.selected_contract.contract.option_type} ${data.selected_contract.contract.strike.toFixed(0)}
                  </p>
                  <p className="text-xs text-muted-foreground">{data.selected_contract.contract.expiration} ({data.selected_contract.contract.dte} DTE)</p>
                </div>
                <div className="rounded-lg border border-emerald-500/20 bg-background p-3">
                  <p className="text-xs text-muted-foreground">Premium</p>
                  <p className="text-lg font-medium">
                    {data.selected_contract.contract.bid != null ? `$${data.selected_contract.contract.bid.toFixed(2)}` : "N/A"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Spread: {data.selected_contract.contract.spread != null ? `$${data.selected_contract.contract.spread.toFixed(2)}` : "N/A"}
                  </p>
                </div>
                <div className="rounded-lg border border-emerald-500/20 bg-background p-3">
                  <p className="text-xs text-muted-foreground">Greeks</p>
                  <p className="text-sm font-medium">
                    δ {data.selected_contract.contract.delta?.toFixed(2) ?? "N/A"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    θ {data.selected_contract.contract.theta?.toFixed(3) ?? "N/A"} |
                    IV {data.selected_contract.contract.iv != null ? `${(data.selected_contract.contract.iv * 100).toFixed(0)}%` : "N/A"}
                  </p>
                </div>
                <div className="rounded-lg border border-emerald-500/20 bg-background p-3">
                  <p className="text-xs text-muted-foreground">Liquidity</p>
                  <p className="text-sm font-medium">
                    <span className={cn(
                      "inline-flex items-center justify-center w-6 h-6 rounded text-xs font-bold",
                      data.selected_contract.contract.liquidity_grade === "A" && "bg-emerald-500 text-white",
                      data.selected_contract.contract.liquidity_grade === "B" && "bg-blue-500 text-white",
                      data.selected_contract.contract.liquidity_grade === "C" && "bg-yellow-500 text-white",
                      data.selected_contract.contract.liquidity_grade === "D" && "bg-orange-500 text-white",
                      data.selected_contract.contract.liquidity_grade === "F" && "bg-red-500 text-white",
                    )}>
                      {data.selected_contract.contract.liquidity_grade}
                    </span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    OI: {data.selected_contract.contract.open_interest?.toLocaleString() ?? "N/A"}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-xs text-emerald-600 dark:text-emerald-400">
                {data.selected_contract.selection_reason}
              </p>
            </section>
          )}

          {/* 8. Candidate Trades with Slack + Execute Buttons */}
          {data.candidate_trades && data.candidate_trades.length > 0 && (
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-sm font-semibold text-foreground">Candidate Trades</h2>
              {data.eligibility?.position_open && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">Position open — no new trade suggested. Trade suggestion CTA disabled.</p>
              )}
              <p className="text-xs text-muted-foreground">Potential trade ideas based on current analysis. Send to Slack or record a manual execution.</p>

              {/* Phase 1: Capital sizing summary */}
              {defaultAccount && defaultSizing && (
                <div className={cn(
                  "mt-2 rounded-md border p-2.5 text-xs",
                  defaultSizing.eligible
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-amber-500/30 bg-amber-500/5"
                )}>
                  <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1 font-medium">
                      <DollarSign className="h-3.5 w-3.5" />
                      {defaultAccount.account_id}
                    </span>
                    <span>Capital: ${defaultAccount.total_capital.toLocaleString()}</span>
                    <span>Max/trade: ${defaultSizing.max_capital.toLocaleString()} ({defaultAccount.max_capital_per_trade_pct}%)</span>
                    <span className="font-medium">
                      Recommended: {defaultSizing.recommended_contracts} contract{defaultSizing.recommended_contracts !== 1 ? "s" : ""}
                    </span>
                    {!defaultSizing.eligible && (
                      <span className="text-amber-600 dark:text-amber-400 font-medium">
                        Insufficient capital
                      </span>
                    )}
                  </div>
                </div>
              )}

              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Strategy</th>
                      <th className="py-2 pr-4 font-medium">Expiry</th>
                      <th className="py-2 pr-4 font-medium">Strike</th>
                      <th className="py-2 pr-4 font-medium">Delta</th>
                      <th className="py-2 pr-4 font-medium">Credit Est.</th>
                      <th className="py-2 pr-4 font-medium">Rationale</th>
                      <th className="py-2 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.candidate_trades.map((trade, i) => {
                      const slackKey = `${symbol}-${trade.strategy}-${trade.strike}`;
                      const isEligibleStrategy = trade.strategy === "CSP" || trade.strategy === "CC" || trade.strategy === "STOCK";
                      return (
                        <tr key={i} className="border-b border-border/50">
                          <td className="py-2 pr-4">
                            <span className={cn(
                              "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                              trade.strategy === "CSP" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                              trade.strategy === "CC" && "bg-blue-500/20 text-blue-600 dark:text-blue-400",
                              trade.strategy === "HOLD" && "bg-muted text-muted-foreground"
                            )}>{trade.strategy}</span>
                          </td>
                          <td className="py-2 pr-4">{trade.expiry ?? "N/A"}</td>
                          <td className="py-2 pr-4">{trade.strike != null ? `$${trade.strike}` : "N/A"}</td>
                          <td className="py-2 pr-4">{trade.delta != null ? trade.delta.toFixed(2) : "N/A"}</td>
                          <td className="py-2 pr-4">{trade.credit_estimate != null ? `$${trade.credit_estimate}` : "N/A"}</td>
                          <td className="py-2 pr-4 max-w-[200px] truncate text-xs text-muted-foreground" title={trade.why_this_trade ?? "No rationale"}>
                            {trade.why_this_trade ?? "No rationale"}
                          </td>
                          <td className="py-2">
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => sendToSlack(trade, symbol)}
                                disabled={slackSending === slackKey || data.eligibility?.position_open}
                                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
                                title={data.eligibility?.position_open ? "Position open — no new trade suggested" : "Send to Slack"}
                              >
                                {slackSending === slackKey ? (
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                ) : (
                                  <Send className="h-3 w-3" />
                                )}
                                Slack
                              </button>
                              {isEligibleStrategy && !data.eligibility?.position_open && (
                                <button
                                  onClick={() => openExecuteModal(trade)}
                                  className="flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20"
                                  title="Record manual execution"
                                >
                                  <Target className="h-3 w-3" />
                                  Execute
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Phase 1: Manual Execute Modal */}
          {executeModalOpen && executeTradeInfo && (
            <ManualExecuteModal
              symbol={symbol}
              strategy={executeTradeInfo.strategy}
              strike={executeTradeInfo.strike}
              expiration={executeTradeInfo.expiration}
              creditEstimate={executeTradeInfo.creditEstimate}
              onClose={() => { setExecuteModalOpen(false); setExecuteTradeInfo(null); }}
              onExecuted={() => {
                setExecuteModalOpen(false);
                setExecuteTradeInfo(null);
                pushSystemNotification({
                  source: "system",
                  severity: "info",
                  title: "Position recorded",
                  message: `${symbol} position tracked. Execute in your brokerage.`,
                });
              }}
            />
          )}

          {/* Blockers (if any) */}
          {data.blockers && data.blockers.length > 0 && (
            <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-destructive">
                <XCircle className="h-4 w-4" /> Blockers
              </h2>
              <ul className="mt-2 space-y-2">
                {data.blockers.map((b, i) => (
                  <li key={i} className="text-sm">
                    <span className="font-medium">{b.code}</span>: {b.message}
                    {b.impact && <p className="text-xs text-muted-foreground">{b.impact}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Notes */}
          {data.notes && data.notes.length > 0 && (
            <section className="rounded-lg border border-border bg-muted/30 p-4">
              <h2 className="text-sm font-semibold text-foreground">Notes</h2>
              <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
                {data.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </section>
          )}

          {/* TradingView link */}
          <div className="flex flex-wrap items-center justify-end gap-4 border-t border-border pt-4">
            <a
              href={tradingViewUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              Open in TradingView <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </div>
      )}

      {!data && !error && !loading && (
        <EmptyState
          title="Enter a symbol"
          message="Type a ticker (e.g. NVDA) and click Analyze to see eligibility, gates, blockers, and constraints."
        />
      )}
    </div>
  );
}
