import { useState, useEffect, useCallback } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Calendar, ChevronDown, ChevronRight, Database, Droplets, MessageSquare, X } from "lucide-react";
import { useSymbolDiagnostics, useRecomputeSymbolDiagnostics, useDefaultAccount, useUiSystemHealth, useUpsertSharePosition, useDeleteSharePosition, useCloseSharePosition, useClosedSharePositions, useSetDeltaOverride, useDeleteDeltaOverride, useActionNeeded, useJournalRecordClose } from "@/api/queries";
import type { SymbolDiagnosticsResponseExtended } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { TradeTicketDrawer } from "@/components/TradeTicketDrawer";
import { CopilotPanel } from "@/components/CopilotPanel";
import { Card, CardHeader, Badge, StatusBadge, Button, Tooltip } from "@/components/ui";
import type { SymbolDiagnosticsCandidate } from "@/api/types";
import { buildReasonsFromPrimary, formatGateReason } from "@/reasons/parsePrimaryReason";
import { constraintToLabel } from "@/utils/sizingConstraints";
import { reasonLabels } from "@/utils/reasonLabels";
import { pushSystemNotification } from "@/lib/notifications";
import { ApiError } from "@/api/client";

function regimeColor(r: string | null | undefined): string {
  const s = (r ?? "").toUpperCase();
  if (s === "UP") return "border-emerald-500/50 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400";
  if (s === "DOWN") return "border-red-500/50 bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400";
  if (s === "SIDEWAYS" || s === "NEUTRAL") return "border-amber-500/50 bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400";
  return "border-zinc-400 bg-zinc-100 text-zinc-600 dark:border-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-400";
}

function deltaInBand(delta: number | null | undefined, strategy: string): boolean {
  if (delta == null) return false;
  if ((strategy ?? "").toUpperCase() === "CSP") {
    const d = Math.abs(delta);
    return d >= 0.20 && d <= 0.35;
  }
  return false;
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function computeDte(expiry: string | null | undefined): number | null {
  if (!expiry) return null;
  try {
    const exp = new Date(String(expiry).slice(0, 10));
    const now = new Date();
    const ms = exp.getTime() - now.getTime();
    return Math.floor(ms / (1000 * 60 * 60 * 24));
  } catch {
    return null;
  }
}

function computeExpectedReturnPct(
  strike: number | null | undefined,
  credit: number | null | undefined
): number | null {
  if (strike == null || credit == null || strike <= 0) return null;
  const notional = strike * 100;
  return (credit / notional) * 100;
}

function getDefaultCapital(account: unknown): number | null {
  if (account == null || typeof account !== "object" || !("total_capital" in account)) return null;
  const tc = (account as { total_capital?: unknown }).total_capital;
  return typeof tc === "number" ? tc : null;
}

function deltaCondition(delta: number | null | undefined, strategy: string): string {
  if (delta == null) return "—";
  const d = Math.abs(delta);
  if ((strategy ?? "").toUpperCase() === "CSP") {
    if (d >= 0.20 && d <= 0.35) return "in band";
    if (d < 0.20) return "low";
    return "high";
  }
  return d.toFixed(3);
}

/** R22.4: Hold-time basis_key → user-facing label (no raw codes). */
function holdTimeBasisLabel(basisKey: string | null | undefined): string {
  const k = (basisKey ?? "").trim();
  if (k === "atr_sessions_to_target") return "Sessions to travel ATR to target";
  if (k === "default_estimate") return "Default estimate";
  return k || "—";
}

/** Optional prop for tests: force initial tab without relying on URL (e.g. ?tab=Shares). */
export function SymbolDiagnosticsPage({ initialTabForTest }: { initialTabForTest?: "Options" | "Shares" } = {}) {
  const [searchParams] = useSearchParams();
  const symbolFromUrl = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const runIdFromUrl = searchParams.get("run_id")?.trim() ?? null;
  /** R24.1: Deep-link accordion — open this section when present (e.g. trade, trade-plan). */
  const accordionFromUrl = searchParams.get("accordion")?.trim().toLowerCase() ?? null;
  const [symbol, setSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [tradeTicketCandidate, setTradeTicketCandidate] = useState<SymbolDiagnosticsCandidate | null>(null);
  const [copilotDrawerOpen, setCopilotDrawerOpen] = useState(false);

  const shouldFetch = activeSymbol != null && isValidSymbol(activeSymbol);
  const { data, isLoading, isError, error } = useSymbolDiagnostics(
    activeSymbol ?? "",
    shouldFetch,
    runIdFromUrl || undefined
  );
  const notFound = isError && error instanceof ApiError && error.status === 404;
  const recompute = useRecomputeSymbolDiagnostics();
  const { data: accountData } = useDefaultAccount();
  const { data: health } = useUiSystemHealth();
  const { data: actionNeeded } = useActionNeeded();
  const marketClosed = health?.market?.phase ? health.market.phase !== "OPEN" && health.market.phase !== "UNKNOWN" : false;

  /** R26.0: ENTRY sizing for current symbol from action-needed (if any). */
  const entrySizingItem = activeSymbol
    ? [...(actionNeeded?.top_options ?? []), ...(actionNeeded?.top_shares ?? [])].find(
        (item) => item.symbol === activeSymbol && item.next_action_code === "ENTRY" && item.sizing_recommended_by === "r260"
      )
    : null;

  const handleLookup = useCallback(() => {
    const s = symbol.trim().toUpperCase();
    if (!s) return;
    if (!isValidSymbol(s)) {
      setTouched(true);
      return;
    }
    setTouched(false);
    setActiveSymbol(s);
  }, [symbol]);

  useEffect(() => {
    if (symbolFromUrl && isValidSymbol(symbolFromUrl)) {
      setSymbol(symbolFromUrl);
      setActiveSymbol(symbolFromUrl);
    }
  }, [symbolFromUrl]);

  useEffect(() => {
    if (!copilotDrawerOpen) return;
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setCopilotDrawerOpen(false); };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [copilotDrawerOpen]);

  const showInvalidError = touched && symbol.trim().length > 0 && !isValidSymbol(symbol);

  return (
    <div className="space-y-3">
      <PageHeader title="Execution Console" />
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value.toUpperCase());
              setTouched(true);
            }}
            onKeyDown={(e) => e.key === "Enter" && handleLookup()}
            placeholder="Ticker"
            maxLength={6}
            className="w-24 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-sm text-zinc-200 uppercase placeholder:normal-case"
          />
          <button
            onClick={handleLookup}
            disabled={!symbol.trim() || isLoading}
            className="rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            Lookup
          </button>
        </div>
        {showInvalidError && (
          <p className="text-xs text-red-400">Invalid symbol. Use 1–6 uppercase letters or dots (e.g. SPY, BRK.B).</p>
        )}
      </div>

      {isLoading && <p className="text-xs text-zinc-500">Loading…</p>}
      {isError && (
        <Card data-testid="symbol-unavailable">
          <CardHeader
            title={notFound ? "Not evaluated yet" : "Diagnostics unavailable"}
            description={
              notFound
                ? `${activeSymbol ?? "This symbol"} is not in the latest evaluation store. Recompute to evaluate it now.`
                : "We could not load diagnostics for this symbol. Try recomputing or check again shortly."
            }
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => activeSymbol && recompute.mutate(activeSymbol)}
            disabled={!activeSymbol || recompute.isPending || marketClosed}
            data-testid="symbol-unavailable-recompute"
          >
            {recompute.isPending ? "Recomputing…" : "Recompute now"}
          </Button>
          {marketClosed && (
            <p className="mt-1 text-xs text-zinc-500">Market is closed — recompute is disabled to protect the canonical decision.</p>
          )}
        </Card>
      )}

      {runIdFromUrl && data && data.exact_run === false && (
        <div className="rounded border border-amber-500/50 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <strong>Exact run not available.</strong> The requested evaluation run (
          <code className="font-mono">{runIdFromUrl.slice(0, 8)}…</code>) was not found in history. Showing latest decision.
        </div>
      )}

      {data && !isLoading && (
        <>
          {/* R34.0 (H-5 cutover): canonical decision is the PRIMARY authority. */}
          {data.canonical_status === "OK" && data.canonical_decision ? (
            <Card data-testid="symbol-canonical-decision">
              <CardHeader
                title="Canonical decision"
                description="Authoritative engine decision. Manual execution only — diagnostics below are explanatory and non-authoritative."
                actions={
                  <Badge variant={data.canonical_decision.next_action_code === "ENTRY" ? "success" : data.canonical_decision.next_action_code === "BLOCKED" ? "danger" : "neutral"}>
                    {data.canonical_decision.next_action_code === "ENTRY" ? "Entry" : data.canonical_decision.next_action_code}
                  </Badge>
                }
              />
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-zinc-600 dark:text-zinc-400">
                <span className="uppercase">{data.canonical_decision.strategy}</span>
                {data.active_profile && <span>Profile: {data.active_profile}</span>}
                {data.canonical_decision.capital_required != null && (
                  <span>Capital: ${Math.round(data.canonical_decision.capital_required).toLocaleString()}</span>
                )}
                {data.canonical_decision.expected_return_pct != null && (
                  <span>Est. return: {data.canonical_decision.expected_return_pct.toFixed(1)}%</span>
                )}
                {data.canonical_decision.score != null && <span>Score: {Math.round(data.canonical_decision.score)}</span>}
              </div>
              {reasonLabels([...(data.canonical_decision.reason_codes ?? []), ...(data.canonical_decision.risk_flags ?? [])]).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1" data-testid="symbol-canonical-reasons">
                  {reasonLabels([...(data.canonical_decision.reason_codes ?? []), ...(data.canonical_decision.risk_flags ?? [])]).map((l) => (
                    <span key={l} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">{l}</span>
                  ))}
                </div>
              )}
            </Card>
          ) : (
            <Card data-testid="symbol-canonical-unavailable">
              <CardHeader
                title="Canonical decision unavailable"
                description="The authoritative engine has no current decision for this symbol. The diagnostics below are explanatory only and are not a recommendation."
              />
            </Card>
          )}
          {/* R26.0: Suggested size when this symbol has ENTRY with r260 sizing */}
          {entrySizingItem && (
            <Card data-testid="suggested-size-card">
              <CardHeader
                title="Suggested size"
                description="Portfolio-aware sizing for ENTRY (manual execution only)."
                actions={
                  <Link
                    to={`/ticket?symbol=${encodeURIComponent(activeSymbol ?? "")}&strategy=${encodeURIComponent(entrySizingItem.strategy || "SHARES")}&action=OPEN`}
                    className="text-sm text-emerald-600 hover:underline dark:text-emerald-400"
                    data-testid="suggested-size-trade-ticket-link"
                  >
                    Trade Ticket
                  </Link>
                }
              />
              <div className="text-sm text-zinc-600 dark:text-zinc-400 space-y-1">
                {entrySizingItem.recommended_contracts != null && entrySizingItem.recommended_contracts > 0 && (
                  <p>Size: {entrySizingItem.recommended_contracts} contracts</p>
                )}
                {entrySizingItem.recommended_qty != null && entrySizingItem.recommended_qty > 0 && (
                  <p>Size: {entrySizingItem.recommended_qty} shares</p>
                )}
                {entrySizingItem.recommended_notional_usd != null && entrySizingItem.recommended_notional_usd > 0 && (
                  <p>Notional: ${entrySizingItem.recommended_notional_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                )}
                {(entrySizingItem.sizing_constraints_hit?.length ?? 0) > 0 && (
                  <p>Constraints: {entrySizingItem.sizing_constraints_hit!.map((c) => constraintToLabel(c)).join(", ")}</p>
                )}
                {/* R26.1: CSP advisory */}
                {(entrySizingItem.cash_secured_available_usd != null || entrySizingItem.csp_risk_proxy_move_pct != null) && (
                  <div className="mt-1 pt-1 border-t border-zinc-200 dark:border-zinc-700" data-testid="suggested-size-csp-advisory">
                    {entrySizingItem.cash_secured_available_usd != null && (
                      <p>Cash-secured available: ${entrySizingItem.cash_secured_available_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                    )}
                    {entrySizingItem.csp_risk_proxy_move_pct != null && (
                      <p>Risk proxy move: {entrySizingItem.csp_risk_proxy_move_pct}%</p>
                    )}
                    {entrySizingItem.csp_risk_proxy_loss_per_contract_usd != null && (
                      <p>Risk proxy loss (per contract): ${entrySizingItem.csp_risk_proxy_loss_per_contract_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                    )}
                    {entrySizingItem.csp_risk_proxy_cap_contracts != null && (
                      <p>Risk proxy cap: {entrySizingItem.csp_risk_proxy_cap_contracts} contracts{entrySizingItem.csp_risk_proxy_enforced ? " (enforced)" : ""}</p>
                    )}
                  </div>
                )}
              </div>
            </Card>
          )}
          <div className="w-full max-w-full">
            <ExecutionConsole
              data={data}
              symbol={activeSymbol ?? ""}
              accountId={(accountData?.account as { account_id?: string } | undefined)?.account_id ?? "default"}
              onRecompute={() => activeSymbol && recompute.mutate(activeSymbol)}
              isRecomputing={recompute.isPending}
              isRecomputeDisabled={marketClosed}
              recomputeDisabledTooltip="Market closed: evaluation disabled to protect canonical decision. Use System Diagnostics or force to override."
              onOpenTradeTicket={(c) => setTradeTicketCandidate(c)}
              defaultCapital={getDefaultCapital(accountData?.account)}
              onOpenCopilot={() => setCopilotDrawerOpen(true)}
              initialTab={initialTabForTest ?? (searchParams.get("tab") === "Shares" ? "Shares" : "Options")}
              initialAccordionId={accordionFromUrl}
            />
          </div>
          {/* R23.4.6: Copilot as slide-over drawer, default closed */}
          {copilotDrawerOpen && (
            <>
              <div
                className="fixed inset-0 z-40 bg-black/40"
                aria-hidden
                onClick={() => setCopilotDrawerOpen(false)}
              />
              <div
                className="fixed top-0 right-0 h-full w-full max-w-md z-50 bg-zinc-900 border-l border-zinc-700 shadow-xl flex flex-col"
                role="dialog"
                aria-label="Copilot"
              >
                <div className="flex items-center justify-between p-3 border-b border-zinc-700">
                  <span className="font-semibold text-zinc-200">Copilot</span>
                  <button
                    type="button"
                    onClick={() => setCopilotDrawerOpen(false)}
                    className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                    aria-label="Close Copilot"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
                <div className="flex-1 overflow-auto">
                  <CopilotPanel
                    symbol={activeSymbol ?? ""}
                    conversationId={`copilot-${activeSymbol ?? "general"}`}
                    systemHealth={health ?? undefined}
                  />
                </div>
              </div>
            </>
          )}
        </>
      )}

      {tradeTicketCandidate && activeSymbol && (
        <TradeTicketDrawer
          symbol={activeSymbol}
          candidate={tradeTicketCandidate}
          onClose={() => setTradeTicketCandidate(null)}
        />
      )}

      {!data && !isLoading && !isError && !showInvalidError && (
        <p className="text-xs text-zinc-500">Enter symbol and click Lookup.</p>
      )}
    </div>
  );
}

const INFO_DRAWER_CONTENT: Record<string, string> = {
  RSI: "Relative Strength Index (14). Overbought >70, oversold <30. Used for regime context.",
  ATR: "Average True Range (14). Volatility measure. ATR% = ATR/price.",
  "ATR%": "ATR as percentage of price. Higher values mean more volatility.",
  Provider: "Data provider status. NO_CHAIN: No option chain expirations for this symbol. NOT_FOUND: Symbol or quote not found.",
  support: "Technical support level (nearest cluster below spot). Used for stop and entry zone.",
  resistance: "Technical resistance level (nearest cluster above spot). Used for targets.",
  regime: "Market regime: UP, DOWN, or SIDEWAYS/NEUTRAL from evaluation.",
  "Delta band": "Target delta range for CSP (e.g. 0.25–0.35). Contracts outside this may be rejected.",
  "bar_count": "Candles sampled for this timeframe S/R calculation.",
  "Hold-time estimate":
    "A session means one trading day. Hold-time is a rough estimate of how many trading days it might take for price to reach T1 if it moved about 1 ATR per day (based on distance to T1 and ATR). It is not a promise. Formula: Sessions to T1 = ceil(|T1-Spot| / ATR).",
  "ATR-based hold time":
    "A session means one trading day. Hold-time is a rough estimate of how many trading days to reach T1 if price moves ~1 ATR per day; it is not a promise. Formula: Sessions to T1 = ceil(|T1-Spot| / ATR). Uses Spot, T1, and ATR; when available, Distance = |T1-Spot|.",
  "Targets basis": "SR_LEVEL: targets from support/resistance. ATR_FALLBACK: from ATR when no valid S/R met distance.",
  Invalidation: "Price level that invalidates the structure (e.g. stop below support).",
};

function ExecutionConsole({
  data,
  onRecompute,
  isRecomputing,
  isRecomputeDisabled,
  recomputeDisabledTooltip,
  onOpenTradeTicket,
  onOpenCopilot,
  defaultCapital,
  accountId = "default",
  initialTab = "Options",
  initialAccordionId,
}: {
  data: SymbolDiagnosticsResponseExtended;
  symbol: string;
  accountId?: string | null;
  onRecompute?: () => void;
  isRecomputing?: boolean;
  isRecomputeDisabled?: boolean;
  recomputeDisabledTooltip?: string;
  onOpenTradeTicket: (c: SymbolDiagnosticsCandidate) => void;
  onOpenCopilot?: () => void;
  defaultCapital?: number | null;
  /** When tab=Shares in URL, open Shares tab by default. */
  initialTab?: "Options" | "Shares";
  /** R24.1: When accordion= in URL, open this section (e.g. trade, trade-plan). */
  initialAccordionId?: string | null;
}) {
  const [infoDrawerKey, setInfoDrawerKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"Options" | "Shares">(initialTab);
  const [sharesModalOpen, setSharesModalOpen] = useState(false);
  const [sharesForm, setSharesForm] = useState({ quantity: "", avg_cost: "", opened_at: "", target_price: "", stop_price: "" });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const openByAccordionId = initialAccordionId ?? null;
  const [tradeAccordionOpen, setTradeAccordionOpen] = useState(openByAccordionId === "trade" || !openByAccordionId);
  const [technicalsAccordionOpen, setTechnicalsAccordionOpen] = useState(openByAccordionId === "technicals");
  const [riskAccordionOpen, setRiskAccordionOpen] = useState(openByAccordionId === "risk");
  const [recordCloseModalOpen, setRecordCloseModalOpen] = useState(false);
  const [recordCloseForm, setRecordCloseForm] = useState({ action: "CLOSE_CSP" as "CLOSE_CSP" | "CLOSE_CC" | "ROLL", strategy: "CSP" as "CSP" | "CC", qty: "1", premium: "", fees: "", contract_key: "", expiry: "", strike: "", right: "P", notes: "", trade_date: new Date().toISOString().slice(0, 10) });
  const bandMin = data.delta_diagnostics?.band_min ?? data.computed_values?.delta_band?.[0] ?? 0.25;
  const bandMax = data.delta_diagnostics?.band_max ?? data.computed_values?.delta_band?.[1] ?? 0.35;
  const [deltaOverrideForm, setDeltaOverrideForm] = useState({ delta_lo: data.delta_override?.delta_lo ?? bandMin, delta_hi: data.delta_override?.delta_hi ?? bandMax });
  useEffect(() => {
    setDeltaOverrideForm({ delta_lo: data.delta_override?.delta_lo ?? bandMin, delta_hi: data.delta_override?.delta_hi ?? bandMax });
  }, [data.delta_override?.delta_lo, data.delta_override?.delta_hi, bandMin, bandMax]);
  const upsertSharePosition = useUpsertSharePosition(data.symbol);
  const deleteSharePosition = useDeleteSharePosition();
  const closeSharePosition = useCloseSharePosition(data.symbol);
  const journalRecordClose = useJournalRecordClose();
  const setDeltaOverride = useSetDeltaOverride(data.symbol);
  const deleteDeltaOverride = useDeleteDeltaOverride(data.symbol);
  const comp = data.computed;
  const cv = data.computed_values;
  const ep = data.exit_plan;
  const candidates = data.candidates ?? [];
  const liq = data.liquidity;
  const sel = data.symbol_eligibility;
  const expl = data.explanation;
  const stockObj = data.stock && typeof data.stock === "object" ? data.stock as { price?: number | null; spot?: number | null; underlying_price?: number | null; quote_as_of?: string | null } : null;
  const price = stockObj != null
    ? (stockObj.spot ?? stockObj.price ?? stockObj.underlying_price ?? null)
    : null;
  const providerStatus = data.provider_status ?? "OK";
  const totalCapital = defaultCapital ?? null;
  const primaryReasons = (data.reasons_explained?.length ? data.reasons_explained : buildReasonsFromPrimary(data.primary_reason)).slice(0, 2).map((r) => r.message);

  return (
    <div className="w-full max-w-full space-y-4">
      {/* R23.4.6: Hero header — symbol, price, quote_as_of, verdict, score, band, regime, primary reason(s) */}
      <Card className="w-full">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-zinc-800 dark:text-zinc-100">{data.symbol ?? "—"}</h1>
            <div className="mt-1 flex items-baseline gap-3 flex-wrap">
              {price != null ? (
                <span className="text-xl font-mono font-semibold text-zinc-700 dark:text-zinc-200">${price.toFixed(2)}</span>
              ) : (
                <span className="text-sm text-zinc-500 dark:text-zinc-400">Not available</span>
              )}
              {stockObj?.quote_as_of != null && (
                <span className="text-xs text-zinc-500 dark:text-zinc-400">as of {stockObj.quote_as_of}</span>
              )}
            </div>
            {primaryReasons.length > 0 && (
              <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400 max-w-2xl">{primaryReasons.join(" · ")}</p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusBadge status={data.verdict ?? "—"} />
              <Badge variant="default">
                <span className="font-mono text-sm">
                  {data.score_caps?.applied_caps?.length ? "Final " : ""}Score {fmt(data.final_score ?? data.composite_score)}
                  {data.score_caps?.applied_caps?.length ? ` (capped)` : ""}
                </span>
              </Badge>
              <Badge variant={data.confidence_band === "A" ? "success" : data.confidence_band === "B" ? "warning" : "neutral"}>
                Band {data.confidence_band ?? "—"}
              </Badge>
              <Badge variant="default" className={regimeColor(data.regime)}>
                Regime {data.regime ?? "—"}
              </Badge>
              {data.next_action_code && data.next_action_code !== "NONE" && (
                <Badge variant={data.next_action_code === "ENTRY" ? "success" : data.next_action_code === "CLOSE" ? "danger" : "neutral"} data-testid="next-action-badge">
                  {data.next_action_code === "ENTRY" ? "Entry" : data.next_action_code === "CLOSE" ? "Close" : data.next_action_code}
                </Badge>
              )}
              {earningsPillLabel(data.earnings) && (
                <Badge variant="warning" className="border-amber-500/50 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-200" data-testid="earnings-advisory-pill">
                  {earningsPillLabel(data.earnings)}
                </Badge>
              )}
              {providerStatus !== "OK" && (
                <button
                  type="button"
                  onClick={() => setInfoDrawerKey("Provider")}
                  className="text-xs text-amber-600 dark:text-amber-400 hover:underline"
                  title={data.provider_message ?? ""}
                >
                  Provider: {providerStatus}
                </button>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {onRecompute && (
              <Tooltip content={isRecomputeDisabled ? recomputeDisabledTooltip : undefined}>
                <span className="inline-block">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={isRecomputing || isRecomputeDisabled}
                    onClick={onRecompute}
                  >
                    {isRecomputing ? "Recomputing…" : "Recompute now"}
                  </Button>
                </span>
              </Tooltip>
            )}
            {onOpenCopilot && (
              <Button size="sm" variant="secondary" onClick={onOpenCopilot} className="gap-1.5">
                <MessageSquare className="h-4 w-4" />
                Copilot
              </Button>
            )}
          </div>
        </div>
        {/* Options | Shares tab */}
        <div className="mt-4 pt-4 border-t border-zinc-200 dark:border-zinc-700 flex gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("Options")}
            className={`px-3 py-1.5 rounded text-sm font-medium ${activeTab === "Options" ? "bg-zinc-700 text-white dark:bg-zinc-500 dark:text-zinc-900" : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"}`}
          >
            Options
          </button>
            <button
              type="button"
              data-testid="tab-shares"
              onClick={() => setActiveTab("Shares")}
              className={`px-3 py-1.5 rounded text-sm font-medium ${activeTab === "Shares" ? "bg-zinc-700 text-white dark:bg-zinc-500 dark:text-zinc-900" : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"}`}
            >
              Shares
            </button>
        </div>
      </Card>
      {activeTab === "Options" ? (
      <div className="w-full space-y-2">
      {/* R25.3: Options lifecycle strip (tracked position) — concise; safe labels only */}
      {data.options_lifecycle && (
        <Card className="w-full" data-testid="options-lifecycle-strip">
          <CardHeader title="Position lifecycle" description="Request-time only; not persisted." />
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-zinc-500 dark:text-zinc-400">Recommend: </span>
              <span className="font-medium text-zinc-800 dark:text-zinc-200">
                {data.options_lifecycle.recommended_action_code === "CLOSE" ? "Close" : data.options_lifecycle.recommended_action_code === "ROLL" ? "Roll" : data.options_lifecycle.recommended_action_code === "HOLD" ? "Hold" : data.options_lifecycle.recommended_action_code ?? "—"}
              </span>
            </p>
            {data.options_lifecycle.pct_max_profit != null && (
              <p><span className="text-zinc-500 dark:text-zinc-400">Profit: </span>{data.options_lifecycle.pct_max_profit}%</p>
            )}
            {data.options_lifecycle.dte != null && (
              <p><span className="text-zinc-500 dark:text-zinc-400">DTE: </span>{data.options_lifecycle.dte}</p>
            )}
            {data.options_lifecycle.mark_value != null && (
              <p>
                <span className="text-zinc-500 dark:text-zinc-400">Mark: </span>
                ${data.options_lifecycle.mark_value.toFixed(2)}
                {(data.options_lifecycle.mark_source || data.options_lifecycle.mark_age_sec != null) && (
                  <span className="text-zinc-500 dark:text-zinc-400">
                    {" "}({[data.options_lifecycle.mark_source, data.options_lifecycle.mark_age_sec != null ? `${data.options_lifecycle.mark_age_sec}s ago` : null].filter(Boolean).join(", ")})
                  </span>
                )}
              </p>
            )}
            {data.options_lifecycle.recommended_action_code === "ROLL" && data.options_lifecycle.roll_reason_codes?.length ? (
              <p><span className="text-zinc-500 dark:text-zinc-400">Reason: </span>DTE window</p>
            ) : data.options_lifecycle.recommended_action_code === "CLOSE" && (data.options_lifecycle.pct_max_profit ?? 0) >= 50 ? (
              <p><span className="text-zinc-500 dark:text-zinc-400">Reason: </span>Profit target hit</p>
            ) : data.options_lifecycle.assignment_risk?.active ? (
              <p><span className="text-zinc-500 dark:text-zinc-400">Reason: </span>Assignment risk</p>
            ) : null}
            <div className="pt-2">
              <Button size="sm" variant="secondary" onClick={() => setRecordCloseModalOpen(true)} data-testid="record-close-btn">Record close</Button>
            </div>
          </div>
        </Card>
      )}
      {/* R23.4.6: Accordion 1 — Trade (Candidates, Exit Plan, Targets); default open */}
      <details open={tradeAccordionOpen} onToggle={(e) => setTradeAccordionOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {tradeAccordionOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Trade
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3 space-y-4">
      {/* R23.1/R23.2: Delta reject diagnostics */}
      {(data.delta_diagnostics || data.delta_override) && (
        <Card className="w-full">
          <CardHeader
            title="Delta band (rejected)"
            description={data.delta_override ? "Closest contract missed the target delta range. Override active." : "Closest contract missed the target delta range."}
          />
          {data.delta_override && (
            <div className="mb-3">
              <Badge variant="warning">Override active</Badge>
              <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                Band: {data.delta_override.delta_lo} – {data.delta_override.delta_hi}
              </span>
            </div>
          )}
          {data.delta_diagnostics && (
            <div className="space-y-2 text-sm">
              <p><span className="text-zinc-500 dark:text-zinc-400">Best available delta:</span> <span className="font-mono font-medium">{data.delta_diagnostics.best_delta}</span></p>
              <p><span className="text-zinc-500 dark:text-zinc-400">Distance to band:</span> <span className="font-mono">{data.delta_diagnostics.miss}</span> ({data.delta_diagnostics.direction === "BELOW_BAND" ? "below band" : data.delta_diagnostics.direction === "ABOVE_BAND" ? "above band" : "in band"})</p>
              <p><span className="text-zinc-500 dark:text-zinc-400">Target band:</span> {data.delta_diagnostics.band_min} – {data.delta_diagnostics.band_max}</p>
              {data.delta_diagnostics.best_candidate && (data.delta_diagnostics.best_candidate.strike != null || data.delta_diagnostics.best_candidate.expiry) && (
                <div className="pt-2 border-t border-zinc-200 dark:border-zinc-700">
                  <span className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Closest contract</span>
                  <p className="font-mono text-xs">
                    Strike {data.delta_diagnostics.best_candidate.strike ?? "—"} · Exp {data.delta_diagnostics.best_candidate.expiry ?? "—"}
                    {data.delta_diagnostics.best_candidate.bid != null && ` · Bid $${data.delta_diagnostics.best_candidate.bid}`}
                    {data.delta_diagnostics.best_candidate.ask != null && ` · Ask $${data.delta_diagnostics.best_candidate.ask}`}
                  </p>
                </div>
              )}
            </div>
          )}
          {/* R23.2: Adjust delta band (Advanced) — only when Show Advanced is enabled */}
          <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
            <button
              type="button"
              onClick={() => setShowAdvanced((a) => !a)}
              className="text-xs text-zinc-500 dark:text-zinc-400 hover:underline"
            >
              {showAdvanced ? "Hide Advanced" : "Show Advanced"}
            </button>
            {showAdvanced && (
              <div className="mt-3 space-y-2">
                <span className="block text-xs font-medium text-zinc-600 dark:text-zinc-300">Adjust delta band (Advanced)</span>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="text-xs text-zinc-500 dark:text-zinc-400">
                    delta_lo
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      className="ml-1 w-20 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                      value={deltaOverrideForm.delta_lo}
                      onChange={(e) => setDeltaOverrideForm((p) => ({ ...p, delta_lo: parseFloat(e.target.value) || 0 }))}
                    />
                  </label>
                  <label className="text-xs text-zinc-500 dark:text-zinc-400">
                    delta_hi
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      max="1"
                      className="ml-1 w-20 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                      value={deltaOverrideForm.delta_hi}
                      onChange={(e) => setDeltaOverrideForm((p) => ({ ...p, delta_hi: parseFloat(e.target.value) || 0 }))}
                    />
                  </label>
                  <Button
                    size="sm"
                    disabled={setDeltaOverride.isPending}
                    onClick={() => setDeltaOverride.mutate({ delta_lo: deltaOverrideForm.delta_lo, delta_hi: deltaOverrideForm.delta_hi })}
                  >
                    {setDeltaOverride.isPending ? "Saving…" : "Save override"}
                  </Button>
                  {data.delta_override && (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={deleteDeltaOverride.isPending}
                      onClick={() => deleteDeltaOverride.mutate()}
                    >
                      {deleteDeltaOverride.isPending ? "Removing…" : "Reset override"}
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        </Card>
      )}
      {/* Gate Summary */}
      <Card className="w-full">
        <CardHeader title="Gate Summary" />
        <div className="space-y-3 text-sm">
          <div>
            <span className="block text-xs text-zinc-500 dark:text-zinc-500">Reasons</span>
            {(() => {
              const reasons = (data.reasons_explained?.length ? data.reasons_explained : buildReasonsFromPrimary(data.primary_reason));
              if (!reasons.length) {
                return <p className="mt-0.5 text-zinc-700 dark:text-zinc-300">{data.primary_reason ?? "—"}</p>;
              }
              return (
                <>
                  <ul className="mt-1 list-disc pl-4 text-zinc-700 dark:text-zinc-300 space-y-0.5">
                    {(reasons.length > 3 ? reasons.slice(0, 3) : reasons).map((r, i) => (
                      <li key={i}>{r.message}</li>
                    ))}
                  </ul>
                  {reasons.length > 3 ? (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-zinc-500 dark:text-zinc-400">Show more…</summary>
                      <ul className="mt-1 list-disc pl-4 text-zinc-600 dark:text-zinc-400 space-y-0.5">
                        {reasons.slice(3).map((r, i) => (
                          <li key={i}>{r.message}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </>
              );
            })()}
            {data.primary_reason ? (
              <Tooltip content={data.primary_reason} className="max-w-sm">
                <span className="mt-1 block text-xs text-zinc-400 dark:text-zinc-500 cursor-help">Debug: raw reason (see Details)</span>
              </Tooltip>
            ) : null}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Required data missing</span>
              <p className="mt-0.5 font-mono text-zinc-700 dark:text-zinc-300">
                {sel?.required_data_missing?.length ? sel.required_data_missing.join(", ") : "None"}
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Required data stale</span>
              <p className="mt-0.5 font-mono text-zinc-700 dark:text-zinc-300">
                {sel?.required_data_stale?.length ? sel.required_data_stale.join(", ") : "None"}
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Optional missing</span>
              <p className="mt-0.5 font-mono text-zinc-700 dark:text-zinc-300">
                {sel?.optional_missing?.length ? sel.optional_missing.join(", ") : "None"}
              </p>
            </div>
          </div>
          {data.gates?.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                  <th className="py-2 pr-2">Gate</th>
                  <th className="py-2 pr-2">Status</th>
                  <th className="py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {data.gates.map((g, i) => (
                  <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800/50">
                    <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{g.name}</td>
                    <td className="py-2 pr-2">
                      <StatusBadge status={g.status} />
                    </td>
                    <td className="py-2 text-zinc-500 dark:text-zinc-400">{formatGateReason(g.reason) || g.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-zinc-500 dark:text-zinc-500">No gates evaluated.</p>
          )}
        </div>
      </Card>

      {/* R24.0: Options position sizing (request-time only) */}
      {data.options_sizing && (
        <Card className="w-full" data-testid="options-sizing-block">
          <CardHeader title="Options sizing" description="Conservative cash-secured suggestion; not an order." />
          {data.options_sizing.basis !== "OK" ? (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {data.options_sizing.basis === "INSUFFICIENT_DATA"
                ? "Account data is not available. Set up default account and balances to see sizing."
                : "No selected option candidate for this symbol."}
            </p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Suggested contracts</span>
                <span className="font-mono font-medium text-zinc-800 dark:text-zinc-200">{data.options_sizing.suggested_contracts ?? "—"}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Required cash</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{data.options_sizing.required_cash != null ? `$${data.options_sizing.required_cash.toFixed(2)}` : "—"}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Credit estimate</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{data.options_sizing.credit_estimate != null ? `$${data.options_sizing.credit_estimate.toFixed(2)}` : "—"}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Risk % used</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{data.options_sizing.risk_pct_used != null ? fmtPct(data.options_sizing.risk_pct_used) : "—"}</span>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Candidates */}
      <Card className="w-full">
        <CardHeader
          title="Candidates"
          actions={
            candidates.length > 0 ? (
              <Button variant="primary" size="sm" onClick={() => onOpenTradeTicket(candidates[0])}>
                Open Trade Ticket
              </Button>
            ) : null
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                <th className="py-2 pr-2">strategy</th>
                <th className="py-2 pr-2">strike</th>
                <th className="py-2 pr-2">expiry</th>
                <th className="py-2 pr-2">DTE</th>
                <th className="py-2 pr-2">delta</th>
                <th className="py-2 pr-2">credit</th>
                <th className="py-2 pr-2">max_loss</th>
                <th className="py-2 pr-2">ret%</th>
                <th className="py-2 pr-2">cap util %</th>
                <th className="py-2 pr-2 max-w-[100px]">regime</th>
                <th className="py-2 pr-2 max-w-[100px]">support</th>
                <th className="py-2 pr-2 max-w-[100px]">liquidity</th>
                <th className="py-2 pr-2 max-w-[100px]">iv</th>
                <th className="py-2 pr-2">delta cond</th>
              </tr>
            </thead>
            <tbody>
              {candidates.length === 0 ? (
                <tr>
                  <td colSpan={14} className="py-3 text-zinc-500">No candidates.</td>
                </tr>
              ) : (
                candidates.map((c, i) => {
                  const dte = computeDte(c.expiry);
                  const retPct = computeExpectedReturnPct(c.strike ?? undefined, c.credit_estimate ?? undefined);
                  const inBand = deltaInBand(c.delta ?? undefined, c.strategy ?? "");
                  const maxLoss = c.max_loss ?? 0;
                  const capUtilPct = totalCapital != null && totalCapital > 0 && maxLoss > 0
                    ? (maxLoss / totalCapital) * 100
                    : null;
                  return (
                    <tr
                      key={i}
                      className={`border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800/50 dark:hover:bg-zinc-800/30 ${
                        i % 2 === 1 ? "bg-zinc-50/50 dark:bg-zinc-900/30" : ""
                      }`}
                    >
                      <td className="py-2 pr-2 font-mono text-zinc-700 dark:text-zinc-300">{c.strategy ?? "—"}</td>
                      <td className="py-2 pr-2 font-mono font-bold text-zinc-900 dark:text-zinc-100 text-right tabular-nums">{fmt(c.strike)}</td>
                      <td className="py-2 pr-2 font-mono">{c.expiry ?? "—"}</td>
                      <td className="py-2 pr-2">{dte != null ? dte : "—"}</td>
                      <td className={`py-2 pr-2 font-mono ${inBand ? "text-emerald-400 font-semibold" : ""}`}>
                        {c.delta != null ? c.delta.toFixed(3) : "—"}
                      </td>
                      <td className="py-2 pr-2">{fmt(c.credit_estimate)}</td>
                      <td className="py-2 pr-2">{fmt(c.max_loss)}</td>
                      <td className="py-2 pr-2">{retPct != null ? retPct.toFixed(2) + "%" : "—"}</td>
                      <td className="py-2 pr-2 font-mono">{capUtilPct != null ? capUtilPct.toFixed(2) + "%" : "—"}</td>
                      <td className="py-2 pr-2 max-w-[100px] truncate text-zinc-600 dark:text-zinc-400" title={expl?.stock_regime_reason ?? ""}>
                        {expl?.stock_regime_reason ?? "—"}
                      </td>
                      <td className="py-2 pr-2 max-w-[100px] truncate text-zinc-600 dark:text-zinc-400" title={expl?.support_condition ?? ""}>
                        {expl?.support_condition ?? "—"}
                      </td>
                      <td className="py-2 pr-2 max-w-[100px] truncate text-zinc-600 dark:text-zinc-400" title={expl?.liquidity_condition ?? ""}>
                        {expl?.liquidity_condition ?? "—"}
                      </td>
                      <td className="py-2 pr-2 max-w-[100px] truncate text-zinc-600 dark:text-zinc-400" title={expl?.iv_condition ?? ""}>
                        {expl?.iv_condition ?? "—"}
                      </td>
                      <td className="py-2 pr-2">{deltaCondition(c.delta ?? undefined, c.strategy ?? "")}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
      {/* Exit Plan + Targets inside Trade accordion */}
      <Card className="w-full">
        <CardHeader title="Exit Plan" />
        {ep?.status === "NOT_AVAILABLE" && ep?.reason ? (
          <p className="text-sm text-amber-700 dark:text-amber-400">{ep.reason}</p>
        ) : null}
        <div className="flex flex-wrap gap-4 text-sm">
          {ep?.t1 != null && (<div><span className="block text-xs text-zinc-500 dark:text-zinc-500">T1</span><span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(ep.t1)}</span></div>)}
          {ep?.t2 != null && (<div><span className="block text-xs text-zinc-500 dark:text-zinc-500">T2</span><span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(ep.t2)}</span></div>)}
          {ep?.t3 != null && (<div><span className="block text-xs text-zinc-500 dark:text-zinc-500">T3</span><span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(ep.t3)}</span></div>)}
          {ep?.stop != null && (<div><span className="block text-xs text-zinc-500 dark:text-zinc-500">stop</span><span className="font-mono font-semibold text-red-600 dark:text-red-400">{fmt(ep.stop)}</span></div>)}
        </div>
      </Card>
      {(data.targets || data.invalidation != null || data.hold_time_estimate) && (
        <Card className="w-full">
          <CardHeader title="Targets & hold-time" description="Targets from next resistances above spot (passed levels skipped). Hold-time: rough estimate of how many trading days to T1 if price moves ~1 ATR per day (one session = one trading day); not a promise." />
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            {data.targets && (<>{data.targets.t1 != null && <Kv label="T1" value={fmt(data.targets.t1)} />}{data.targets.t2 != null && <Kv label="T2" value={fmt(data.targets.t2)} />}{data.targets.t3 != null && <Kv label="T3" value={fmt(data.targets.t3)} />}</>)}
            {data.invalidation != null && <Kv label="Invalidation" value={fmt(data.invalidation)} />}
            {data.targets && (data.targets.target_basis != null || data.targets.level_source_timeframe != null) && (
              <div className="col-span-2" data-testid="target-basis-label">
                <span className="text-xs text-zinc-500 dark:text-zinc-500">Basis: {data.targets.target_basis === "SR_LEVEL" ? "SR level used" : data.targets.target_basis === "ATR_FALLBACK" ? "ATR fallback used" : data.targets.target_basis ?? "—"}{data.targets.level_source_timeframe ? ` · ${data.targets.level_source_timeframe}` : ""}</span>
                <Tooltip content={data.targets.target_basis === "SR_LEVEL" ? "Targets from support/resistance level." : "Targets from ATR when no valid S/R level met distance threshold."} className="ml-1 inline"><span aria-hidden>(?)</span></Tooltip>
              </div>
            )}
            {(data.targets?.targets_already_exceeded === true || (typeof data.stock?.price === "number" && typeof data.targets?.t1 === "number" && data.stock.price >= data.targets.t1)) && (
              <div className="col-span-2" data-testid="target-already-exceeded-badge">
                <Badge variant="warning">Target already exceeded (price above T1)</Badge>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Targets already exceeded at snapshot; recompute for updated levels.</p>
              </div>
            )}
            {data.hold_time_estimate && (
              <div className="col-span-2" data-testid="hold-time-block">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">
                  Hold-time estimate{" "}
                  <button type="button" onClick={() => setInfoDrawerKey(data.hold_time_estimate?.hold_time_atr != null ? "ATR-based hold time" : "Hold-time estimate")} className="inline cursor-help underline decoration-dotted">
                    (?)
                  </button>
                </span>
                {(data.hold_time_estimate.hold_time_atr != null && data.hold_time_estimate.hold_time_distance_to_t1 != null) && (
                  <>
                    <p className="mt-1 text-sm font-medium text-zinc-700 dark:text-zinc-300" data-testid="hold-time-formula">
                      Sessions to T1 = ceil(|T1-Spot| / ATR)
                    </p>
                    <p className="mt-0.5 text-xs text-zinc-600 dark:text-zinc-400">
                      Spot {fmt(price ?? data.computed?.support_level)} · T1 {fmt(data.targets?.t1)} · ATR {fmt(data.hold_time_estimate.hold_time_atr)} · Distance {fmt(data.hold_time_estimate.hold_time_distance_to_t1)}
                    </p>
                  </>
                )}
                <p className="mt-1 text-zinc-700 dark:text-zinc-300">
                  {data.hold_time_estimate.sessions != null ? data.hold_time_estimate.sessions : "Not available"} sessions · {holdTimeBasisLabel(data.hold_time_estimate.basis_key)}
                </p>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400" data-testid="hold-time-plain-english">
                  One session = one trading day. Rough estimate of days to T1 if price moves ~1 ATR per day; not a promise.
                </p>
              </div>
            )}
          </div>
        </Card>
      )}
        </div>
      </details>

      {/* Accordion 2: Technicals */}
      <details open={technicalsAccordionOpen} onToggle={(e) => setTechnicalsAccordionOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {technicalsAccordionOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Technicals
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3 space-y-4">
        <div data-testid="technical-details-panel">
          <Card className="w-full">
            <CardHeader title="Technical details" />
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
            <LabelKv label="RSI" value={fmt(cv?.rsi ?? comp?.rsi)} onLabelClick={() => setInfoDrawerKey("RSI")} />
            <Kv
              label="RSI range"
              value={
                cv?.rsi_range?.length === 2
                  ? `${cv.rsi_range[0]} – ${cv.rsi_range[1]}`
                  : "—"
              }
            />
            <LabelKv label="ATR" value={fmt(cv?.atr ?? comp?.atr)} onLabelClick={() => setInfoDrawerKey("ATR")} />
            <Kv label="ATR%" value={(cv?.atr_pct ?? comp?.atr_pct) != null ? fmtPct(cv?.atr_pct ?? comp?.atr_pct) : "—"} />
            <LabelKv label="Support" value={fmt(cv?.support_level ?? comp?.support_level)} onLabelClick={() => setInfoDrawerKey("support")} />
            <LabelKv label="Resistance" value={fmt(cv?.resistance_level ?? comp?.resistance_level)} onLabelClick={() => setInfoDrawerKey("resistance")} />
            <div>
              <button
                type="button"
                onClick={() => setInfoDrawerKey("regime")}
                className="text-left hover:opacity-80"
              >
                <span className="block text-zinc-500 dark:text-zinc-500">Regime</span>
                <span className={`inline-flex rounded border px-2 py-0.5 text-sm font-medium ${regimeColor(cv?.regime ?? data.regime)}`}>
                  {cv?.regime ?? data.regime ?? "—"}
                </span>
              </button>
            </div>
            <Kv
              label="Delta band"
              value={
                cv?.delta_band?.length === 2
                  ? `${cv.delta_band[0]} – ${cv.delta_band[1]}`
                  : "—"
              }
            />
            <Kv label="Rejected count" value={cv?.rejected_count != null ? String(cv.rejected_count) : "—"} />
          </div>
          </Card>
        </div>

        {/* R22.7: Multi-timeframe levels from resampled OHLC (request-time only) */}
        {data.mtf_levels && (data.mtf_levels.monthly || data.mtf_levels.weekly || data.mtf_levels.daily || data.mtf_levels["4h"]) ? (
          <Card data-testid="mtf-levels-panel">
            <CardHeader title="Multi-timeframe levels" description="Support and resistance by timeframe (request-time; not persisted)" />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Timeframe</th>
                    <th className="py-2 pr-2">Support</th>
                    <th className="py-2 pr-2">Resistance</th>
                    <th className="py-2 pr-2">
                      <Tooltip content="Candles sampled for this timeframe S/R calculation.">bar_count</Tooltip>
                    </th>
                    <th className="py-2 pr-2">as_of</th>
                    <th className="py-2 pr-2">method</th>
                  </tr>
                </thead>
                <tbody>
                  {(["monthly", "weekly", "daily", "4h"] as const).map((tf) => {
                    const row = data.mtf_levels?.[tf] as { support?: number | null; resistance?: number | null; as_of?: string; method?: string; bar_count?: number | null; status_code?: string } | undefined;
                    if (!row) return null;
                    if ((row as { status_code?: string }).status_code === "INSUFFICIENT_HISTORY") {
                      return (
                        <tr key={tf} className="border-b border-zinc-100 dark:border-zinc-800/50">
                          <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{tf}</td>
                          <td colSpan={5} className="py-2 pr-2 text-zinc-500 dark:text-zinc-400">INSUFFICIENT_HISTORY</td>
                        </tr>
                      );
                    }
                    if (row.support == null && row.resistance == null) return null;
                    return (
                      <tr key={tf} className="border-b border-zinc-100 dark:border-zinc-800/50">
                        <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{tf}</td>
                        <td className="py-2 pr-2 font-mono">{fmt(row.support)}</td>
                        <td className="py-2 pr-2 font-mono">{fmt(row.resistance)}</td>
                        <td className="py-2 pr-2 text-zinc-500 dark:text-zinc-400">{row.bar_count != null ? String(row.bar_count) : "—"}</td>
                        <td className="py-2 pr-2 text-zinc-500 dark:text-zinc-400">{row.as_of ? new Date(row.as_of).toLocaleString() : "—"}</td>
                        <td className="py-2 pr-2 text-zinc-500 dark:text-zinc-400">{row.method ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {(() => {
              const m = data.mtf_levels?.monthly as { support?: number; resistance?: number; bar_count?: number } | undefined;
              const w = data.mtf_levels?.weekly as { support?: number; resistance?: number; bar_count?: number } | undefined;
              const d = data.mtf_levels?.daily as { support?: number; resistance?: number; bar_count?: number } | undefined;
              const sameLevels = m && w && d
                && m.support === w.support && w.support === d.support
                && m.resistance === w.resistance && w.resistance === d.resistance;
              const differentBars = sameLevels && (m.bar_count !== w.bar_count || w.bar_count !== d.bar_count);
              return differentBars ? (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">Levels coincide across timeframes; bar_count differs by resolution.</p>
              ) : null;
            })()}
            {data.methodology && (
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-500">
                Methodology: {data.methodology.candles_source ?? "—"} · window {data.methodology.window ?? "—"} · tolerance {data.methodology.clustering_tolerance_pct ?? "—"}% · {data.methodology.active_criteria ?? "—"}
              </p>
            )}
          </Card>
        ) : null}
        </div>
      </details>

      {/* R23.4.6: Accordion 3 — Risk & Details; collapsed by default */}
      <details open={riskAccordionOpen} onToggle={(e) => setRiskAccordionOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {riskAccordionOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Risk & Details
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3 space-y-4">
        {(data.score_breakdown || data.score_caps?.applied_caps?.length) ? (
          <Card data-testid="score-breakdown-panel" className="w-full">
            <CardHeader title="Score breakdown" />
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
              {data.score_breakdown?.data_quality_score != null && <Kv label="Data quality" value={fmt(data.score_breakdown.data_quality_score)} />}
              {data.score_breakdown?.regime_score != null && <Kv label="Regime" value={fmt(data.score_breakdown.regime_score)} />}
              {data.score_breakdown?.options_liquidity_score != null && <Kv label="Options liquidity" value={fmt(data.score_breakdown.options_liquidity_score)} />}
              {data.score_breakdown?.strategy_fit_score != null && <Kv label="Strategy fit" value={fmt(data.score_breakdown.strategy_fit_score)} />}
              {data.score_breakdown?.capital_efficiency_score != null && <Kv label="Capital efficiency" value={fmt(data.score_breakdown.capital_efficiency_score)} />}
              {data.score_breakdown?.composite_score != null && <Kv label="Composite" value={fmt(data.score_breakdown.composite_score)} />}
              <Kv label="Raw score" value={fmt(data.raw_score ?? data.score_breakdown?.raw_score)} />
              <Kv label="Final score" value={fmt(data.final_score ?? data.composite_score ?? data.score_breakdown?.final_score)} />
            </div>
            <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1" data-testid="score-used-line">
                {data.score_caps?.applied_caps?.length
                  ? "Score used: Final score (capped)"
                  : "Score used: Raw score (uncapped)"}
              </p>
              <p className="text-xs text-zinc-600 dark:text-zinc-400 mb-3">
                {data.score_caps?.applied_caps?.length
                  ? "Regime or other caps limit the final score even when the raw score is high (e.g. from liquidity or strategy fit)."
                  : "Final score equals raw score; no caps were applied."}
              </p>
              <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-2">Capped by</span>
              {data.score_caps?.applied_caps?.length ? (
                <>
                  <p className="text-sm text-zinc-700 dark:text-zinc-300 mb-2" data-testid="capped-by-summary">
                    {(data.score_caps.applied_caps[0] as { reason_code?: string }).reason_code ?? (data.score_caps.applied_caps[0] as { reason?: string }).reason ?? "Cap"} (cap={fmt((data.score_caps.applied_caps[0] as { cap_value?: number }).cap_value)}): {fmt((data.score_caps.applied_caps[0] as { before?: number }).before)}→{fmt((data.score_caps.applied_caps[0] as { after?: number }).after)}
                  </p>
                  <ul className="space-y-1 text-xs font-mono text-zinc-600 dark:text-zinc-300">
                    {data.score_caps.applied_caps.map((cap, i) => (
                      <li key={i}>
                        {(cap as { reason_code?: string }).reason_code ?? (cap as { reason?: string }).reason ?? "CAP"}: {fmt((cap as { before?: number }).before)} → {fmt((cap as { after?: number }).after)} (cap={fmt((cap as { cap_value?: number }).cap_value)})
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-sm text-zinc-500 dark:text-zinc-400" data-testid="no-caps-applied">No caps applied.</p>
              )}
            </div>
          </Card>
        ) : null}
        <Card className="w-full">
          <CardHeader title="Risk Flags" />
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <RiskFlag
              icon={<Calendar className="h-4 w-4" />}
              label="earnings days"
              value={earningsDaysReason(data.earnings)}
              status="neutral"
            />
            <RiskFlag
              icon={<Calendar className="h-4 w-4" />}
              label="earnings block"
              value={earningsBlockReason(data.earnings)}
              status="neutral"
            />
            <RiskFlag
              icon={<Droplets className="h-4 w-4" />}
              label="stock liq"
              value={liqReason(liq?.stock_liquidity_ok, liq?.reason, "stock", liq?.liquidity_evaluated)}
              status={
                liq?.liquidity_evaluated === false
                  ? "neutral"
                  : liq?.stock_liquidity_ok == null
                    ? "neutral"
                    : liq.stock_liquidity_ok
                      ? "ok"
                      : "fail"
              }
            />
            <RiskFlag
              icon={<Droplets className="h-4 w-4" />}
              label="option liq"
              value={liqReason(liq?.option_liquidity_ok, liq?.reason, "option", liq?.liquidity_evaluated)}
              status={
                liq?.liquidity_evaluated === false
                  ? "neutral"
                  : liq?.option_liquidity_ok == null
                    ? "neutral"
                    : liq.option_liquidity_ok
                      ? "ok"
                      : "fail"
              }
            />
            <RiskFlag
              icon={<Database className="h-4 w-4" />}
              label="data status"
              value={sel?.status === "PASS" ? "Passed" : sel?.status === "FAIL" ? "Blocked" : sel?.status === "WARN" ? "Degraded" : (sel?.status ?? "Unavailable")}
              status={
                sel?.status === "PASS" ? "ok" : sel?.status === "FAIL" ? "fail" : "neutral"
              }
            />
            <div className="col-span-2 flex items-start gap-2">
              <Database className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500 dark:text-zinc-500" />
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">missing</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">
                  {sel?.required_data_missing?.length ? sel.required_data_missing.join(", ") : "None"}
                </span>
              </div>
            </div>
            {data.earnings && data.earnings.earnings_data_status === "OK" && (data.earnings.earnings_next_date != null || data.earnings.earnings_days != null) && (
              <div className="col-span-2 flex items-start gap-2">
                <Calendar className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500 dark:text-zinc-500" />
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">earnings advisory</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {data.earnings.earnings_next_date != null && String(data.earnings.earnings_next_date).slice(0, 10) !== "0000-00-00" ? `Next: ${data.earnings.earnings_next_date}` : ""}
                    {data.earnings.earnings_days != null && Number.isInteger(data.earnings.earnings_days) ? ` · ${data.earnings.earnings_days}d` : ""}
                    {data.earnings.implied_earnings_move_pct != null && typeof data.earnings.implied_earnings_move_pct === "number" ? ` · Implied move ${data.earnings.implied_earnings_move_pct.toFixed(2)}%` : ""}
                  </span>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Advisory only. Earnings do not block options or shares eligibility.</p>
                </div>
              </div>
            )}
          </div>
        </Card>
        <details className="rounded border border-zinc-200 dark:border-zinc-700 p-3" open={detailsOpen} onToggle={(e) => setDetailsOpen((e.target as HTMLDetailsElement).open)}>
          <summary className="cursor-pointer text-xs font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300 list-none">Details (as-of / inputs, debug)</summary>
          <div className="mt-2 space-y-2">
            {data.as_of_inputs && (data.as_of_inputs.pipeline_timestamp ?? data.as_of_inputs.evaluation_run_id) && (
              <div>
                <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">As-of / Inputs</span>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono text-zinc-600 dark:text-zinc-300">
                  {data.as_of_inputs.evaluation_run_id != null && <div><span className="text-zinc-500 dark:text-zinc-500">run_id</span> {String(data.as_of_inputs.evaluation_run_id).slice(0, 8)}…</div>}
                  {data.as_of_inputs.pipeline_timestamp != null && <div><span className="text-zinc-500 dark:text-zinc-500">pipeline</span> {new Date(data.as_of_inputs.pipeline_timestamp).toLocaleString()}</div>}
                  {data.as_of_inputs.quote_as_of != null && <div><span className="text-zinc-500 dark:text-zinc-500">quote_as_of</span> {data.as_of_inputs.quote_as_of}</div>}
                  {data.as_of_inputs.config_hash != null && <div><span className="text-zinc-500 dark:text-zinc-500">config_hash</span> {data.as_of_inputs.config_hash}</div>}
                </div>
              </div>
            )}
            {data.primary_reason && (
              <Tooltip content={data.primary_reason} className="max-w-sm"><span className="block text-xs text-zinc-400 dark:text-zinc-500 cursor-help">Debug: raw reason</span></Tooltip>
            )}
            {data.earnings && (
              <div className="text-xs text-zinc-500 dark:text-zinc-400">
                <span className="font-medium text-zinc-600 dark:text-zinc-300">Earnings (debug):</span>{" "}
                {data.earnings.earnings_data_status ?? "—"} · as_of {data.earnings.earnings_as_of ?? "—"}
              </div>
            )}
          </div>
        </details>
        {infoDrawerKey && (
          <Card className="border-zinc-300 dark:border-zinc-600">
            <div className="flex items-center justify-between border-b border-zinc-200 pb-2 dark:border-zinc-700">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">{infoDrawerKey}</span>
              <button
                type="button"
                onClick={() => setInfoDrawerKey(null)}
                className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {INFO_DRAWER_CONTENT[infoDrawerKey] ?? "No explanation available."}
            </p>
          </Card>
        )}
        </div>
      </details>
      </div>
      ) : (
        <SharesTabContent
          data={data}
          accountId={accountId ?? ""}
          setInfoDrawerKey={setInfoDrawerKey}
          upsertSharePosition={upsertSharePosition}
          deleteSharePosition={deleteSharePosition}
          closeSharePosition={closeSharePosition}
          sharesModalOpen={sharesModalOpen}
          setSharesModalOpen={setSharesModalOpen}
          sharesForm={sharesForm}
          setSharesForm={setSharesForm}
          initialOpenAccordionId={initialAccordionId}
        />
      )}

      {recordCloseModalOpen && (
        <Card className="fixed inset-0 z-50 m-4 max-h-[90vh] overflow-auto border-amber-200 dark:border-amber-800 bg-white dark:bg-zinc-900" data-testid="record-close-modal">
          <CardHeader title="Record options close / roll" />
          <div className="grid grid-cols-1 gap-3 max-w-sm p-4">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Symbol</label>
              <input type="text" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={data.symbol} readOnly />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Strategy</label>
              <select className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.strategy} onChange={(e) => setRecordCloseForm((f) => ({ ...f, strategy: e.target.value as "CSP" | "CC" }))}>
                <option value="CSP">CSP</option>
                <option value="CC">CC</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Action</label>
              <select className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.action} onChange={(e) => setRecordCloseForm((f) => ({ ...f, action: e.target.value as "CLOSE_CSP" | "CLOSE_CC" | "ROLL" }))}>
                <option value="CLOSE_CSP">CLOSE_CSP</option>
                <option value="CLOSE_CC">CLOSE_CC</option>
                <option value="ROLL">ROLL</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Qty (required)</label>
              <input type="number" min="1" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.qty} onChange={(e) => setRecordCloseForm((f) => ({ ...f, qty: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Premium (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.premium} onChange={(e) => setRecordCloseForm((f) => ({ ...f, premium: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Fees (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.fees} onChange={(e) => setRecordCloseForm((f) => ({ ...f, fees: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Contract key (optional)</label>
              <input type="text" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.contract_key} onChange={(e) => setRecordCloseForm((f) => ({ ...f, contract_key: e.target.value }))} placeholder="OCC symbol" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Expiry (optional)</label>
              <input type="text" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.expiry} onChange={(e) => setRecordCloseForm((f) => ({ ...f, expiry: e.target.value }))} placeholder="YYYY-MM-DD" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Strike (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.strike} onChange={(e) => setRecordCloseForm((f) => ({ ...f, strike: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Right (optional)</label>
              <select className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.right} onChange={(e) => setRecordCloseForm((f) => ({ ...f, right: e.target.value }))}>
                <option value="P">P</option>
                <option value="C">C</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Trade date</label>
              <input type="date" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.trade_date} onChange={(e) => setRecordCloseForm((f) => ({ ...f, trade_date: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Notes (optional)</label>
              <input type="text" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={recordCloseForm.notes} onChange={(e) => setRecordCloseForm((f) => ({ ...f, notes: e.target.value }))} placeholder="Optional" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" data-testid="record-close-submit" disabled={journalRecordClose.isPending} onClick={() => { const qty = parseInt(recordCloseForm.qty, 10); if (!Number.isNaN(qty) && qty > 0) { journalRecordClose.mutate({ symbol: data.symbol, strategy: recordCloseForm.strategy, action: recordCloseForm.action, qty, premium: recordCloseForm.premium.trim() ? parseFloat(recordCloseForm.premium) : undefined, fees: recordCloseForm.fees.trim() ? parseFloat(recordCloseForm.fees) : undefined, contract_key: recordCloseForm.contract_key.trim() || undefined, expiry: recordCloseForm.expiry.trim() || undefined, strike: recordCloseForm.strike.trim() ? parseFloat(recordCloseForm.strike) : undefined, right: recordCloseForm.right || undefined, notes: recordCloseForm.notes.trim() || undefined, trade_date: recordCloseForm.trade_date || undefined }, { onSuccess: () => { pushSystemNotification({ source: "system", severity: "info", title: "Journal entry created", message: "Options close/roll recorded." }); setRecordCloseModalOpen(false); } }); } }}>{journalRecordClose.isPending ? "Saving…" : "Save"}</Button>
              <Button size="sm" variant="secondary" onClick={() => setRecordCloseModalOpen(false)}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

/** R24.5/R24.5.1: Earnings advisory — safe labels only (no FAIL_/WARN_). Never show "Earnings: 00" or 0000-00-00. */
function earningsPillLabel(earnings: SymbolDiagnosticsResponseExtended["earnings"]): string | null {
  if (!earnings || earnings.earnings_data_status !== "OK" || earnings.earnings_days == null) return null;
  const d = earnings.earnings_next_date;
  if (!d || d.slice(0, 10) === "0000-00-00") return null;
  const annc = earnings.earnings_annc_tod && earnings.earnings_annc_tod !== "Unknown" ? ` (${earnings.earnings_annc_tod})` : "";
  const days = earnings.earnings_days;
  if (days === 0) return `Earnings: Today${annc}`;
  if (days === 1) return `Earnings: 1d${annc}`;
  try {
    const parts = d.slice(0, 10).split("-");
    const dayNum = parseInt(parts[2], 10);
    if (dayNum < 1 || dayNum > 31) return null; // R24.5.1: avoid "Earnings: 00" or bogus day
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const month = monthNames[parseInt(parts[1], 10) - 1] ?? parts[1];
    return `Earnings: ${month} ${dayNum}${annc}`;
  } catch {
    return null;
  }
}

function earningsDaysReason(earnings: SymbolDiagnosticsResponseExtended["earnings"]): string {
  if (!earnings) return "Unavailable";
  if (earnings.earnings_data_status !== "OK") return earnings.note ?? "Unavailable";
  if (earnings.earnings_days != null) return `${earnings.earnings_days}d`;
  if (earnings.earnings_next_date) return `Next: ${earnings.earnings_next_date}`;
  return earnings.note ?? "Unavailable";
}

/** R23.3: Map shares reason_codes to safe UI labels (no raw FAIL_/WARN_). */
function sharesReasonCodeToLabel(code: string): string {
  const m: Record<string, string> = {
    SHARES_ELIGIBLE: "Meets all shares eligibility rules",
    SHARES_UAT_FORCED: "UAT forced",
    NOT_STOCK_QUALITY: "Stock quality (Stage 1) did not pass",
    REGIME_NOT_PREFERRED: "Regime not preferred for shares (UP required)",
    NOT_NEAR_SUPPORT: "Price not near daily/weekly support",
    NO_SUPPORT_OR_SPOT: "No support or spot price available",
    RSI_OUT_OF_RANGE: "RSI outside preferred range",
    DATA_STALE: "Data missing or stale",
  };
  return m[code] ?? code.replace(/_/g, " ").toLowerCase();
}

/** R23.5.0: Shares tab — Trade Plan view with accordions: Trade Plan, Technicals, Risk & Details, Position. */
function SharesTabContent({
  data,
  accountId,
  setInfoDrawerKey,
  upsertSharePosition,
  deleteSharePosition,
  closeSharePosition,
  sharesModalOpen,
  setSharesModalOpen,
  sharesForm,
  setSharesForm,
  initialOpenAccordionId,
}: {
  data: SymbolDiagnosticsResponseExtended;
  accountId: string;
  setInfoDrawerKey: (k: string | null) => void;
  upsertSharePosition: ReturnType<typeof useUpsertSharePosition>;
  deleteSharePosition: ReturnType<typeof useDeleteSharePosition>;
  closeSharePosition: ReturnType<typeof useCloseSharePosition>;
  sharesModalOpen: boolean;
  setSharesModalOpen: (v: boolean) => void;
  sharesForm: { quantity: string; avg_cost: string; opened_at: string; target_price: string; stop_price: string };
  setSharesForm: Dispatch<SetStateAction<{ quantity: string; avg_cost: string; opened_at: string; target_price: string; stop_price: string }>>;
  /** R24.1: Open this accordion when present (trade-plan, technicals, risk, position). */
  initialOpenAccordionId?: string | null;
}) {
  const aid = (initialOpenAccordionId ?? "").toLowerCase();
  const [tradePlanOpen, setTradePlanOpen] = useState(aid === "trade-plan" || !aid);
  const [technicalsOpen, setTechnicalsOpen] = useState(aid === "technicals");
  const [riskOpen, setRiskOpen] = useState(aid === "risk");
  const [positionOpen, setPositionOpen] = useState(aid === "position");
  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [closeForm, setCloseForm] = useState({ exit_price: "", exit_date: new Date().toISOString().slice(0, 10), fees: "", notes: "" });

  const pos = data.shares_position;
  const plan = data.shares_plan;
  const { data: closedData } = useClosedSharePositions(accountId || null);
  const closedList = closedData?.positions ?? [];
  const cv = data.computed_values;
  const comp = data.computed;
  const reasonCodes = plan?.reason_codes ?? plan?.eligibility_codes ?? [];
  const stopObj = plan?.stop && typeof plan.stop === "object" && "price" in plan.stop ? plan.stop : { price: typeof plan?.stop === "number" ? plan.stop : null, basis: "" };
  const stopPrice = stopObj?.price ?? (typeof plan?.stop === "number" ? plan.stop : null);
  const invalidation = plan?.invalidation ?? data.invalidation;
  const holdTimeEst = plan?.hold_time_estimate ?? data.hold_time_estimate;
  const targets = plan?.targets ?? data.targets;
  const price = (data.stock && typeof data.stock === "object" && (data.stock as { price?: number; spot?: number }).spot) ?? (data.stock as { price?: number })?.price ?? null;

  return (
    <div className="space-y-4 lg:col-span-2" data-testid="shares-tab-content">
      {/* Accordion 1: Trade Plan — R24.1 deep-link id: trade-plan */}
      <details open={tradePlanOpen} onToggle={(e) => setTradePlanOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60" data-testid="shares-accordion-trade-plan">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {tradePlanOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Trade Plan
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3 space-y-4">
          <Card data-testid="shares-trade-plan-card">
            <CardHeader title="Trade Plan" description="BUY SHARES recommendation only; no order placement." />
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
              {plan?.spot != null && <Kv label="Spot" value={fmt(plan.spot)} />}
              {plan?.entry_zone?.low != null && plan?.entry_zone?.high != null && (
                <div className="col-span-2 sm:col-span-1">
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Entry zone</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(plan.entry_zone.low)} – {fmt(plan.entry_zone.high)}</span>
                  {plan.entry_zone.basis && (
                    <button type="button" onClick={() => setInfoDrawerKey("Targets basis")} className="ml-1 cursor-help underline decoration-dotted">(?)</button>
                  )}
                </div>
              )}
              {stopPrice != null && <Kv label="Stop" value={fmt(stopPrice)} />}
              {targets?.t1 != null && <Kv label="T1" value={fmt(targets.t1)} />}
              {targets?.t2 != null && <Kv label="T2" value={fmt(targets.t2)} />}
              {targets?.t3 != null && <Kv label="T3" value={fmt(targets.t3)} />}
              {invalidation != null && <Kv label="Invalidation" value={fmt(invalidation)} />}
            </div>
            {(holdTimeEst?.hold_time_atr != null && holdTimeEst?.hold_time_distance_to_t1 != null) && (
              <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700" data-testid="shares-hold-time-block">
                <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Sessions to T1 = ceil(|T1-Spot| / ATR)</p>
                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-0.5">Spot {fmt(typeof (price ?? comp?.support_level) === "number" ? (price ?? comp?.support_level) as number : null)} · T1 {fmt(typeof targets?.t1 === "number" ? targets.t1 : null)} · ATR {fmt(typeof holdTimeEst.hold_time_atr === "number" ? holdTimeEst.hold_time_atr : null)} · Distance {fmt(typeof holdTimeEst.hold_time_distance_to_t1 === "number" ? holdTimeEst.hold_time_distance_to_t1 : null)}</p>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">One session = one trading day. Rough estimate of days to T1 if price moves ~1 ATR per day; not a promise.</p>
                <button type="button" onClick={() => setInfoDrawerKey(holdTimeEst.hold_time_atr != null ? "ATR-based hold time" : "Hold-time estimate")} className="mt-1 text-xs cursor-help underline decoration-dotted">(?)</button>
              </div>
            )}
            {holdTimeEst?.sessions != null && (holdTimeEst.hold_time_atr == null || holdTimeEst.hold_time_distance_to_t1 == null) && (
              <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{holdTimeEst.sessions} sessions</p>
            )}
            {/* Why eligible / Why not checklist */}
            <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
              <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-2">{plan?.eligible ? "Why eligible" : "Why not"}</span>
              <ul className="space-y-1 text-sm" data-testid="shares-why-checklist">
                {reasonCodes.map((c, i) => (
                  <li key={i} className="flex items-center gap-2">
                    {plan?.eligible && c === "SHARES_ELIGIBLE" ? <span className="text-emerald-600" aria-hidden>✓</span> : (plan?.eligible ? null : <span className="text-zinc-400" aria-hidden>✗</span>)}
                    <span className={plan?.eligible && c === "SHARES_ELIGIBLE" ? "text-emerald-700 dark:text-emerald-400" : "text-zinc-600 dark:text-zinc-400"}>{sharesReasonCodeToLabel(c)}</span>
                  </li>
                ))}
              </ul>
            </div>
            {plan?.sizing && (
              <div className="mt-2 text-sm">
                {plan.sizing.basis === "INSUFFICIENT_DATA" ? (
                  <p className="text-zinc-500 dark:text-zinc-400">Insufficient data (set account balances for suggested size)</p>
                ) : (
                  <>
                    <span className="text-zinc-500 dark:text-zinc-400">Suggested shares:</span> <span className="font-mono font-medium">{plan.sizing.suggested_shares ?? "—"}</span>
                  </>
                )}
              </div>
            )}
          </Card>
        </div>
      </details>

      {/* Accordion 2: Technicals (reuse) */}
      <details open={technicalsOpen} onToggle={(e) => setTechnicalsOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {technicalsOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Technicals
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3">
          <Card>
            <CardHeader title="Technical details" />
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
              <Kv label="RSI" value={fmt(cv?.rsi ?? comp?.rsi)} />
              <Kv label="ATR" value={fmt(cv?.atr ?? comp?.atr)} />
              <Kv label="Support" value={fmt(cv?.support_level ?? comp?.support_level)} />
              <Kv label="Resistance" value={fmt(cv?.resistance_level ?? comp?.resistance_level)} />
            </div>
          </Card>
          {data.mtf_levels && (data.mtf_levels.daily || data.mtf_levels.weekly || data.mtf_levels.monthly) && (
            <Card className="mt-3">
              <CardHeader title="Multi-timeframe levels" />
              <p className="text-sm text-zinc-600 dark:text-zinc-400">Daily / Weekly / Monthly support and resistance. See Options tab for full table.</p>
            </Card>
          )}
        </div>
      </details>

      {/* Accordion 3: Risk & Details (reuse) */}
      <details open={riskOpen} onToggle={(e) => setRiskOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {riskOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Risk & Details
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3">
          {(data.score_breakdown || data.score_caps?.applied_caps?.length) ? (
            <Card className="mb-3">
              <CardHeader title="Score breakdown" />
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <Kv label="Raw score" value={fmt(data.raw_score ?? data.score_breakdown?.raw_score)} />
                <Kv label="Final score" value={fmt(data.final_score ?? data.composite_score)} />
              </div>
            </Card>
          ) : null}
          <Card>
            <CardHeader title="Risk flags" />
            <p className="text-sm text-zinc-600 dark:text-zinc-400">Data status, liquidity, and other risk flags. See Options tab for full Risk & Details.</p>
          </Card>
        </div>
      </details>

      {/* Accordion 4: Position */}
      <details open={positionOpen} onToggle={(e) => setPositionOpen((e.target as HTMLDetailsElement).open)} className="group rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
          {positionOpen ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          Position
        </summary>
        <div className="border-t border-zinc-200 dark:border-zinc-700 px-4 pb-4 pt-3 space-y-4">
          {/* R25.2: Close recommendation banner when target/stop hit (safe labels only) */}
          {(data.shares_exit_hit_type === "TARGET" || data.shares_exit_hit_type === "STOP") && data.shares_exit_reason_safe && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/30 px-4 py-3 text-sm" data-testid="shares-exit-recommend-banner">
              <p className="font-medium text-amber-800 dark:text-amber-200">Recommend: Close</p>
              <p className="text-amber-700 dark:text-amber-300">Reason: {data.shares_exit_reason_safe}</p>
              {data.shares_exit_last_price != null && <p className="mt-1 text-zinc-600 dark:text-zinc-400">Last price: ${data.shares_exit_last_price.toFixed(2)}</p>}
              {(data.shares_exit_target_price != null || data.shares_exit_stop_price != null) && (
                <p className="text-zinc-600 dark:text-zinc-400">
                  {data.shares_exit_target_price != null && `Target: $${data.shares_exit_target_price.toFixed(2)}`}
                  {data.shares_exit_target_price != null && data.shares_exit_stop_price != null && " · "}
                  {data.shares_exit_stop_price != null && `Stop: $${data.shares_exit_stop_price.toFixed(2)}`}
                </p>
              )}
            </div>
          )}
          <Card data-testid="shares-position-card">
            <CardHeader title="Your Shares Position" />
            {pos ? (
              <div className="space-y-2 text-sm">
                <p><span className="text-zinc-500 dark:text-zinc-400">Quantity:</span> <span className="font-mono font-medium">{pos.quantity}</span></p>
                {pos.avg_cost != null && <p><span className="text-zinc-500 dark:text-zinc-400">Avg cost:</span> <span className="font-mono">${pos.avg_cost.toFixed(2)}</span></p>}
                {(pos.target_price != null || pos.stop_price != null) && (
                  <p className="text-zinc-600 dark:text-zinc-400">
                    {pos.target_price != null && <>Target: <span className="font-mono">${pos.target_price.toFixed(2)}</span></>}
                    {pos.target_price != null && pos.stop_price != null && " · "}
                    {pos.stop_price != null && <>Stop: <span className="font-mono">${pos.stop_price.toFixed(2)}</span></>}
                  </p>
                )}
                {(pos as { last_price?: number }).last_price != null && (
                  <p><span className="text-zinc-500 dark:text-zinc-400">Unrealized P/L:</span> <span className={`font-mono font-medium ${((pos as { unrealized_pnl?: number }).unrealized_pnl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>${((pos as { unrealized_pnl?: number }).unrealized_pnl ?? 0).toFixed(2)}</span></p>
                )}
                <p><span className="text-zinc-500 dark:text-zinc-400">Last updated:</span> {pos.updated_at ? new Date(pos.updated_at).toLocaleString() : "—"}</p>
                <div className="flex flex-wrap gap-2 pt-2">
                  <Button size="sm" variant="secondary" onClick={() => { setSharesForm({ quantity: String(pos.quantity), avg_cost: pos.avg_cost != null ? String(pos.avg_cost) : "", opened_at: pos.opened_at ?? "", target_price: pos.target_price != null ? String(pos.target_price) : "", stop_price: pos.stop_price != null ? String(pos.stop_price) : "" }); setSharesModalOpen(true); }}>Update</Button>
                  <Button size="sm" variant="secondary" disabled={closeSharePosition.isPending} onClick={() => setCloseModalOpen(true)} data-testid="close-position-open-btn">Close position</Button>
                  <Button size="sm" variant="secondary" disabled={deleteSharePosition.isPending} onClick={() => { if (window.confirm(`Remove shares position for ${data.symbol}?`)) deleteSharePosition.mutate({ accountId, symbol: data.symbol }); }}>{deleteSharePosition.isPending ? "Deleting…" : "Delete"}</Button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-zinc-500 dark:text-zinc-400">No shares position recorded.</p>
                <Button size="sm" className="mt-2" onClick={() => { setSharesForm({ quantity: "", avg_cost: "", opened_at: "", target_price: "", stop_price: "" }); setSharesModalOpen(true); }}>Add Shares Position</Button>
              </>
            )}
          </Card>
          {closedList.length > 0 && (
            <Card>
              <CardHeader title="Closed positions (this symbol)" />
              <ul className="space-y-2 text-sm">
                {closedList.filter((c) => c.symbol.toUpperCase() === data.symbol?.toUpperCase()).slice(0, 5).map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono font-medium">{c.symbol}</span>
                    <span className={c.realized_pnl != null && c.realized_pnl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>Realized P/L: ${(c.realized_pnl ?? 0).toFixed(2)}</span>
                    <span className="text-zinc-500 dark:text-zinc-400 text-xs">Closed {c.closed_at ? new Date(c.closed_at).toLocaleDateString() : ""}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </details>

      {sharesModalOpen && (
        <Card className="border-zinc-400 dark:border-zinc-500">
          <CardHeader title="Add / Update Shares Position" />
          <div className="grid grid-cols-1 gap-3 max-w-xs">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Quantity (required)</label>
              <input type="number" min="1" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={sharesForm.quantity} onChange={(e) => setSharesForm((p) => ({ ...p, quantity: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Avg cost (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={sharesForm.avg_cost} onChange={(e) => setSharesForm((p) => ({ ...p, avg_cost: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Opened date (optional)</label>
              <input type="date" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={sharesForm.opened_at || ""} onChange={(e) => setSharesForm((p) => ({ ...p, opened_at: e.target.value || "" }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Target price (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={sharesForm.target_price || ""} onChange={(e) => setSharesForm((p) => ({ ...p, target_price: e.target.value }))} placeholder="e.g. 150" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Stop price (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={sharesForm.stop_price || ""} onChange={(e) => setSharesForm((p) => ({ ...p, stop_price: e.target.value }))} placeholder="e.g. 130" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => { const qty = parseInt(sharesForm.quantity, 10); if (!Number.isNaN(qty) && qty >= 0) { upsertSharePosition.mutate({ account_id: accountId, quantity: qty, avg_cost: sharesForm.avg_cost.trim() ? parseFloat(sharesForm.avg_cost) : null, opened_at: sharesForm.opened_at.trim() || null, target_price: sharesForm.target_price.trim() ? parseFloat(sharesForm.target_price) : null, stop_price: sharesForm.stop_price.trim() ? parseFloat(sharesForm.stop_price) : null }); setSharesModalOpen(false); } }} disabled={upsertSharePosition.isPending}>{upsertSharePosition.isPending ? "Saving…" : "Save"}</Button>
              <Button size="sm" variant="secondary" onClick={() => setSharesModalOpen(false)}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}

      {closeModalOpen && pos && (
        <Card className="border-amber-200 dark:border-amber-800" data-testid="close-position-modal">
          <CardHeader title="Close position" />
          <div className="grid grid-cols-1 gap-3 max-w-xs">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Exit price (required)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={closeForm.exit_price} onChange={(e) => setCloseForm((f) => ({ ...f, exit_price: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Exit date (default today)</label>
              <input type="date" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={closeForm.exit_date} onChange={(e) => setCloseForm((f) => ({ ...f, exit_date: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Fees (optional)</label>
              <input type="number" step="0.01" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={closeForm.fees} onChange={(e) => setCloseForm((f) => ({ ...f, fees: e.target.value }))} placeholder="0" />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Notes (optional)</label>
              <input type="text" className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800" value={closeForm.notes} onChange={(e) => setCloseForm((f) => ({ ...f, notes: e.target.value }))} placeholder="Optional notes" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" data-testid="close-position-submit" onClick={() => { const ex = parseFloat(closeForm.exit_price); if (!Number.isNaN(ex) && ex > 0) { const feesNum = closeForm.fees.trim() ? parseFloat(closeForm.fees) : 0; closeSharePosition.mutate({ account_id: accountId, exit_price: ex, exit_date: closeForm.exit_date ? new Date(closeForm.exit_date).toISOString() : null, fees: Number.isNaN(feesNum) ? undefined : feesNum, notes: closeForm.notes.trim() || null }, { onSuccess: () => { pushSystemNotification({ source: "system", severity: "info", title: "Position closed", message: `${data.symbol} shares closed. Journal entry created.` }); } }); setCloseModalOpen(false); setCloseForm({ exit_price: "", exit_date: new Date().toISOString().slice(0, 10), fees: "", notes: "" }); } }} disabled={closeSharePosition.isPending}>{closeSharePosition.isPending ? "Closing…" : "Close"}</Button>
              <Button size="sm" variant="secondary" onClick={() => setCloseModalOpen(false)}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function earningsBlockReason(earnings: SymbolDiagnosticsResponseExtended["earnings"]): string {
  if (!earnings) return "Unavailable";
  if (earnings.earnings_data_status !== "OK") return earnings.note ?? "Unavailable";
  if (earnings.earnings_block === true) return "Blocked";
  return "Advisory only (does not block)";
}

function liqReason(
  ok: boolean | null | undefined,
  reason: string | null | undefined,
  kind: string,
  liquidityEvaluated?: boolean
): string {
  if (liquidityEvaluated === false) return "Not evaluated";
  if (ok == null) return "Data not available";
  if (ok) return "OK";
  return reason && reason.trim() ? reason.trim() : `${kind} liquidity failed`;
}

function RiskFlag({
  icon,
  label,
  value,
  status = "neutral",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  status?: "ok" | "fail" | "neutral";
}) {
  const valueColor =
    status === "ok"
      ? "text-emerald-400"
      : status === "fail"
        ? "text-red-400"
        : "text-zinc-300";
  const iconColor =
    status === "ok"
      ? "text-emerald-400"
      : status === "fail"
        ? "text-red-400"
        : "text-zinc-500";
  return (
    <div className="flex items-start gap-2">
      <span className={`mt-0.5 shrink-0 ${iconColor}`}>{icon}</span>
      <div>
        <span className="block text-xs text-zinc-500">{label}</span>
        <span className={`font-mono font-medium ${valueColor}`}>{value}</span>
      </div>
    </div>
  );
}

const SYMBOL_REGEX = /^[A-Z.]{1,6}$/;

function isValidSymbol(s: string): boolean {
  return SYMBOL_REGEX.test((s || "").trim().toUpperCase());
}

function Kv({
  label,
  value,
  className = "",
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <span className="text-zinc-500 dark:text-zinc-500">{label}</span>
      <div className="font-mono text-zinc-700 dark:text-zinc-200">{value}</div>
    </div>
  );
}

function LabelKv({
  label,
  value,
  onLabelClick,
  className = "",
}: {
  label: string;
  value: React.ReactNode;
  onLabelClick?: () => void;
  className?: string;
}) {
  return (
    <div className={className}>
      {onLabelClick ? (
        <button type="button" onClick={onLabelClick} className="text-left hover:opacity-80">
          <span className="text-zinc-500 dark:text-zinc-500 hover:underline">{label}</span>
        </button>
      ) : (
        <span className="text-zinc-500 dark:text-zinc-500">{label}</span>
      )}
      <div className="font-mono text-zinc-700 dark:text-zinc-200">{value}</div>
    </div>
  );
}
