import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Calendar, ChevronDown, ChevronRight, Database, Droplets, X } from "lucide-react";
import { useSymbolDiagnostics, useRecomputeSymbolDiagnostics, useDefaultAccount, useUiSystemHealth } from "@/api/queries";
import type { SymbolDiagnosticsResponseExtended } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { TradeTicketDrawer } from "@/components/TradeTicketDrawer";
import { Card, CardHeader, Badge, StatusBadge, Button, Tooltip } from "@/components/ui";
import type { SymbolDiagnosticsCandidate } from "@/api/types";

function verdictColor(v: string | null | undefined): string {
  const s = (v ?? "").toUpperCase();
  if (s === "ELIGIBLE") return "text-emerald-600 dark:text-emerald-400";
  if (s === "HOLD") return "text-amber-600 dark:text-amber-400";
  if (s === "BLOCKED" || s === "UNKNOWN") return "text-red-600 dark:text-red-400";
  return "text-zinc-600 dark:text-zinc-400";
}

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

export function SymbolDiagnosticsPage() {
  const [searchParams] = useSearchParams();
  const symbolFromUrl = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const [symbol, setSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [tradeTicketCandidate, setTradeTicketCandidate] = useState<SymbolDiagnosticsCandidate | null>(null);

  const shouldFetch = activeSymbol != null && isValidSymbol(activeSymbol);
  const { data, isLoading, isError } = useSymbolDiagnostics(activeSymbol ?? "", shouldFetch);
  const recompute = useRecomputeSymbolDiagnostics();
  const { data: accountData } = useDefaultAccount();
  const { data: health } = useUiSystemHealth();
  const marketClosed = health?.market?.phase ? health.market.phase !== "OPEN" && health.market.phase !== "UNKNOWN" : false;

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
      {isError && <p className="text-xs text-red-400">Failed to load.</p>}

      {data && !isLoading && (
        <ExecutionConsole
          data={data}
          symbol={activeSymbol ?? ""}
          onRecompute={() => activeSymbol && recompute.mutate(activeSymbol)}
          isRecomputing={recompute.isPending}
          isRecomputeDisabled={marketClosed}
          recomputeDisabledTooltip="Market closed: evaluation disabled to protect canonical decision. Use System Diagnostics or force to override."
          onOpenTradeTicket={(c) => setTradeTicketCandidate(c)}
          defaultCapital={getDefaultCapital(accountData?.account)}
        />
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
  Provider: "Data provider status. NO_CHAIN: No option chain expirations for this symbol. NOT_FOUND: Symbol or quote not found.",
  support: "Technical support level from eligibility trace.",
  resistance: "Technical resistance level from eligibility trace.",
  regime: "Market regime: UP, DOWN, or SIDEWAYS/NEUTRAL from evaluation.",
};

function ExecutionConsole({
  data,
  onRecompute,
  isRecomputing,
  isRecomputeDisabled,
  recomputeDisabledTooltip,
  onOpenTradeTicket,
  defaultCapital,
}: {
  data: SymbolDiagnosticsResponseExtended;
  symbol: string;
  onRecompute?: () => void;
  isRecomputing?: boolean;
  isRecomputeDisabled?: boolean;
  recomputeDisabledTooltip?: string;
  onOpenTradeTicket: (c: SymbolDiagnosticsCandidate) => void;
  defaultCapital?: number | null;
}) {
  const [infoDrawerKey, setInfoDrawerKey] = useState<string | null>(null);
  const comp = data.computed;
  const ep = data.exit_plan;
  const candidates = data.candidates ?? [];
  const liq = data.liquidity;
  const sel = data.symbol_eligibility;
  const expl = data.explanation;
  const price = data.stock && typeof data.stock === "object" && "price" in data.stock ? (data.stock as { price?: number }).price : null;
  const providerStatus = data.provider_status ?? "OK";
  const totalCapital = defaultCapital ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Symbol header */}
      <Card className="lg:col-span-2">
        <CardHeader
          title={data.symbol ?? "—"}
          description={price != null ? `$${price.toFixed(2)}` : undefined}
          actions={
            onRecompute ? (
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
            ) : undefined
          }
        />
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={data.verdict ?? "—"} />
          <span
            title={
              data.score_caps?.applied_caps?.length
                ? `Raw: ${data.score_caps.applied_caps[0].before} → Final: ${data.score_caps.applied_caps[0].after} (${data.score_caps.applied_caps[0].reason})`
                : undefined
            }
          >
            <Badge variant="default">
              <span className="font-mono">
                {data.score_caps?.applied_caps?.length ? "Final score " : "Score "}
                {fmt(data.composite_score)}
                {data.score_caps?.applied_caps?.length ? (
                  <span className="ml-1 text-xs opacity-80">
                    (capped from {data.raw_score ?? data.score_caps.applied_caps[0].before})
                  </span>
                ) : null}
              </span>
            </Badge>
          </span>
          <Badge variant={data.confidence_band === "A" ? "success" : data.confidence_band === "B" ? "warning" : "neutral"}>
            Band {data.confidence_band ?? "—"}
          </Badge>
          <Badge variant="default" className={regimeColor(data.regime)}>
            Regime {data.regime ?? "—"}
          </Badge>
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
      </Card>
      {/* Gate Summary: same "why" as Universe */}
      <Card className="lg:col-span-2 w-full">
        <CardHeader title="Gate Summary" />
        <div className="space-y-3 text-sm">
          <div>
            <span className="block text-xs text-zinc-500 dark:text-zinc-500">Primary reason</span>
            <p className="mt-0.5 text-zinc-700 dark:text-zinc-300">{data.primary_reason ?? "—"}</p>
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
                    <td className="py-2 text-zinc-500 dark:text-zinc-400">{g.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-zinc-500 dark:text-zinc-500">No gates evaluated.</p>
          )}
        </div>
      </Card>

      {/* Candidates: full width, same as header */}
      <Card className="lg:col-span-2 w-full">
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
      {/* Left column */}
      <div className="space-y-4">
        <Card>
          <CardHeader title="Thesis" />
          <div className="flex flex-wrap items-baseline gap-4">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">verdict</span>
              <span className={`text-xl font-bold ${verdictColor(data.verdict)}`}>
                {data.verdict ?? "—"}
              </span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">score</span>
              <span className="font-mono text-2xl font-semibold text-zinc-700 dark:text-zinc-300">
                {fmt(data.composite_score)}
              </span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">band</span>
              <span
                className={`inline-flex rounded border px-2 py-0.5 font-semibold ${
                  data.confidence_band === "A"
                    ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400"
                    : data.confidence_band === "B"
                      ? "border-amber-500/50 bg-amber-500/10 text-amber-400"
                      : data.confidence_band === "C"
                        ? "border-zinc-500/50 bg-zinc-500/10 text-zinc-400"
                        : "border-zinc-600 bg-zinc-800/50 text-zinc-400"
                }`}
              >
                {data.confidence_band ?? "—"}
              </span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">cap%</span>
              <span className="font-mono text-sm text-zinc-300">
                {fmtPct(data.suggested_capital_pct ?? undefined)}
              </span>
            </div>
          </div>
          {data.band_reason && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-500">{data.band_reason}</p>
          )}
        </Card>

        <Card>
          <CardHeader title="Technical" />
          <div className="grid grid-cols-3 gap-x-6 gap-y-2 text-sm">
            <LabelKv label="RSI" value={fmt(comp?.rsi)} onLabelClick={() => setInfoDrawerKey("RSI")} />
            <LabelKv label="ATR" value={fmt(comp?.atr)} onLabelClick={() => setInfoDrawerKey("ATR")} />
            <Kv label="ATR%" value={comp?.atr_pct != null ? fmtPct(comp.atr_pct) : "—"} />
            <LabelKv label="support" value={fmt(comp?.support_level)} onLabelClick={() => setInfoDrawerKey("support")} />
            <LabelKv label="resistance" value={fmt(comp?.resistance_level)} onLabelClick={() => setInfoDrawerKey("resistance")} />
            <div>
              <button
                type="button"
                onClick={() => setInfoDrawerKey("regime")}
                className="text-left hover:opacity-80"
              >
                <span className="block text-zinc-500 dark:text-zinc-500">regime</span>
                <span className={`inline-flex rounded border px-2 py-0.5 text-sm font-medium ${regimeColor(data.regime)}`}>
                  {data.regime ?? "—"}
                </span>
              </button>
            </div>
          </div>
        </Card>

      </div>

      {/* Right column */}
      <div className="space-y-4">
        <Card>
          <CardHeader title="Exit Plan" />
          <div className="flex flex-wrap gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">T1</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(ep?.t1)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">T2</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(ep?.t2)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">T3</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmt(ep?.t3)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">stop</span>
              <span className="font-mono font-semibold text-red-600 dark:text-red-400">{fmt(ep?.stop)}</span>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Risk Flags" />
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <RiskFlag
              icon={<Calendar className="h-4 w-4" />}
              label="earnings days"
              value={earningsDaysReason(undefined)}
              status="neutral"
            />
            <RiskFlag
              icon={<Calendar className="h-4 w-4" />}
              label="earnings block"
              value={earningsBlockReason(undefined)}
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
              value={sel?.status ?? "Not evaluated"}
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
          </div>
        </Card>

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
    </div>
  );
}

function earningsDaysReason(_value: unknown): string {
  return "Not evaluated";
}

function earningsBlockReason(_value: unknown): string {
  return "Not evaluated";
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
