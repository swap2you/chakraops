import { useState, useEffect, useCallback } from "react";
import type { Dispatch, SetStateAction } from "react";
import { useSearchParams } from "react-router-dom";
import { Calendar, Database, Droplets, X } from "lucide-react";
import { useSymbolDiagnostics, useRecomputeSymbolDiagnostics, useDefaultAccount, useUiSystemHealth, useUpsertSharePosition, useDeleteSharePosition, useSetDeltaOverride, useDeleteDeltaOverride } from "@/api/queries";
import type { SymbolDiagnosticsResponseExtended } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { TradeTicketDrawer } from "@/components/TradeTicketDrawer";
import { Card, CardHeader, Badge, StatusBadge, Button, Tooltip } from "@/components/ui";
import type { SymbolDiagnosticsCandidate } from "@/api/types";
import { buildReasonsFromPrimary, formatGateReason } from "@/reasons/parsePrimaryReason";

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

/** R22.4: Hold-time basis_key → user-facing label (no raw codes). */
function holdTimeBasisLabel(basisKey: string | null | undefined): string {
  const k = (basisKey ?? "").trim();
  if (k === "atr_sessions_to_target") return "Sessions to travel ATR to target";
  if (k === "default_estimate") return "Default estimate";
  return k || "—";
}

/** R22.5: why_recommended code → user-facing label (no raw FAIL_* in UI). */
function sharesWhyLabel(why: string | null | undefined): string {
  const w = (why ?? "").trim();
  if (w === "MTF_SUPPORT_REGIME_UP") return "Support level and regime UP";
  return w || "—";
}

export function SymbolDiagnosticsPage() {
  const [searchParams] = useSearchParams();
  const symbolFromUrl = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const runIdFromUrl = searchParams.get("run_id")?.trim() ?? null;
  const [symbol, setSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [tradeTicketCandidate, setTradeTicketCandidate] = useState<SymbolDiagnosticsCandidate | null>(null);

  const shouldFetch = activeSymbol != null && isValidSymbol(activeSymbol);
  const { data, isLoading, isError } = useSymbolDiagnostics(
    activeSymbol ?? "",
    shouldFetch,
    runIdFromUrl || undefined
  );
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

      {runIdFromUrl && data && data.exact_run === false && (
        <div className="rounded border border-amber-500/50 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <strong>Exact run not available.</strong> The requested evaluation run (
          <code className="font-mono">{runIdFromUrl.slice(0, 8)}…</code>) was not found in history. Showing latest decision.
        </div>
      )}

      {data && !isLoading && (
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
  accountId = "default",
}: {
  data: SymbolDiagnosticsResponseExtended;
  symbol: string;
  accountId?: string | null;
  onRecompute?: () => void;
  isRecomputing?: boolean;
  isRecomputeDisabled?: boolean;
  recomputeDisabledTooltip?: string;
  onOpenTradeTicket: (c: SymbolDiagnosticsCandidate) => void;
  defaultCapital?: number | null;
}) {
  const [infoDrawerKey, setInfoDrawerKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"Options" | "Shares">("Options");
  const [sharesModalOpen, setSharesModalOpen] = useState(false);
  const [sharesForm, setSharesForm] = useState({ quantity: "", avg_cost: "", opened_at: "" });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const bandMin = data.delta_diagnostics?.band_min ?? data.computed_values?.delta_band?.[0] ?? 0.25;
  const bandMax = data.delta_diagnostics?.band_max ?? data.computed_values?.delta_band?.[1] ?? 0.35;
  const [deltaOverrideForm, setDeltaOverrideForm] = useState({ delta_lo: data.delta_override?.delta_lo ?? bandMin, delta_hi: data.delta_override?.delta_hi ?? bandMax });
  useEffect(() => {
    setDeltaOverrideForm({ delta_lo: data.delta_override?.delta_lo ?? bandMin, delta_hi: data.delta_override?.delta_hi ?? bandMax });
  }, [data.delta_override?.delta_lo, data.delta_override?.delta_hi, bandMin, bandMax]);
  const upsertSharePosition = useUpsertSharePosition(data.symbol);
  const deleteSharePosition = useDeleteSharePosition();
  const setDeltaOverride = useSetDeltaOverride(data.symbol);
  const deleteDeltaOverride = useDeleteDeltaOverride(data.symbol);
  const comp = data.computed;
  const cv = data.computed_values;
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
          description={price != null ? `$${price.toFixed(2)}` : "—"}
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
        {price == null && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Price unavailable</p>
        )}
        {data.stock && typeof data.stock === "object" && "quote_as_of" in data.stock && (data.stock as { quote_as_of?: string }).quote_as_of && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Quote as of {(data.stock as { quote_as_of: string }).quote_as_of}</p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={data.verdict ?? "—"} />
          <span
            title={
              data.score_caps?.applied_caps?.length
                ? `Raw: ${data.raw_score ?? data.score_caps.applied_caps[0].before} → Final: ${data.final_score ?? data.composite_score ?? data.score_caps.applied_caps[0].after} (${(data.score_caps.applied_caps[0] as { reason_code?: string; reason?: string }).reason_code ?? (data.score_caps.applied_caps[0] as { reason?: string }).reason ?? "cap"})`
                : undefined
            }
          >
            <Badge variant="default">
              <span className="font-mono">
                {data.score_caps?.applied_caps?.length ? "Final score " : "Score "}
                {fmt(data.final_score ?? data.composite_score)}
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
        {/* R22.7: As-of / Inputs — verify Universe eval vs Recompute use same pipeline */}
        {data.as_of_inputs && (data.as_of_inputs.pipeline_timestamp ?? data.as_of_inputs.evaluation_run_id) && (
          <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
            <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">As-of / Inputs</span>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono text-zinc-600 dark:text-zinc-300">
              {data.as_of_inputs.evaluation_run_id != null && (
                <div><span className="text-zinc-500 dark:text-zinc-500">run_id</span> {String(data.as_of_inputs.evaluation_run_id).slice(0, 8)}…</div>
              )}
              {data.as_of_inputs.pipeline_timestamp != null && (
                <div><span className="text-zinc-500 dark:text-zinc-500">pipeline</span> {new Date(data.as_of_inputs.pipeline_timestamp).toLocaleString()}</div>
              )}
              {data.as_of_inputs.quote_as_of != null && (
                <div><span className="text-zinc-500 dark:text-zinc-500">quote_as_of</span> {data.as_of_inputs.quote_as_of}</div>
              )}
              {data.as_of_inputs.config_hash != null && (
                <div><span className="text-zinc-500 dark:text-zinc-500">config_hash</span> {data.as_of_inputs.config_hash}</div>
              )}
            </div>
          </div>
        )}
        {/* R23.0: Options | Shares tab */}
        <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700 flex gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("Options")}
            className={`px-3 py-1.5 rounded text-sm font-medium ${activeTab === "Options" ? "bg-zinc-700 text-white dark:bg-zinc-500 dark:text-zinc-900" : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"}`}
          >
            Options
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("Shares")}
            className={`px-3 py-1.5 rounded text-sm font-medium ${activeTab === "Shares" ? "bg-zinc-700 text-white dark:bg-zinc-500 dark:text-zinc-900" : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"}`}
          >
            Shares
          </button>
        </div>
      </Card>
      {activeTab === "Options" ? (
      <>
      {/* R23.1/R23.2: Delta reject diagnostics — best delta, miss vs band, best candidate; optional override (Advanced) */}
      {(data.delta_diagnostics || data.delta_override) && (
        <Card className="lg:col-span-2 w-full">
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
      {/* Gate Summary: reasons_explained from backend; fallback to primary_reason mapping (rejected_due_to_delta=N → rejected_count) */}
      <Card className="lg:col-span-2 w-full">
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
                <span className="mt-1 block text-xs text-zinc-400 dark:text-zinc-500 cursor-help">Debug: raw reason</span>
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

        {/* R22.9: Score breakdown panel (request-time only; from diagnostics/summary) */}
        {(data.score_breakdown || data.score_caps?.applied_caps?.length) ? (
          <Card data-testid="score-breakdown-panel">
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
            {data.score_caps?.applied_caps?.length ? (
              <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
                <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-2">Applied caps</span>
                <ul className="space-y-1 text-xs font-mono text-zinc-600 dark:text-zinc-300">
                  {data.score_caps.applied_caps.map((cap, i) => (
                    <li key={i}>
                      {(cap as { reason_code?: string }).reason_code ?? (cap as { reason?: string }).reason ?? "CAP"}: {fmt((cap as { before?: number }).before)} → {fmt((cap as { after?: number }).after)} (cap={fmt((cap as { cap_value?: number }).cap_value)})
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>
        ) : null}

        <div data-testid="technical-details-panel">
          <Card>
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
                    <th className="py-2 pr-2">bar_count</th>
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

        {/* R22.4: Targets, invalidation, hold-time estimate */}
        {(data.targets || data.invalidation != null || data.hold_time_estimate) ? (
          <Card>
            <CardHeader title="Targets & hold-time" />
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {data.targets && (
                <>
                  <Kv label="T1" value={fmt(data.targets.t1)} />
                  <Kv label="T2" value={fmt(data.targets.t2)} />
                  <Kv label="T3" value={fmt(data.targets.t3)} />
                </>
              )}
              {data.invalidation != null && <Kv label="Invalidation" value={fmt(data.invalidation)} />}
              {data.hold_time_estimate && (
                <div className="col-span-2">
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Hold-time estimate</span>
                  <p className="mt-1 text-zinc-700 dark:text-zinc-300">
                    {data.hold_time_estimate.sessions ?? "—"} sessions · {holdTimeBasisLabel(data.hold_time_estimate.basis_key)}
                  </p>
                </div>
              )}
            </div>
          </Card>
        ) : null}

        {/* R22.5/R23.3: Shares plan (recommendation only) */}
        {data.shares_plan ? (
          <Card>
            <CardHeader title="Shares plan" description="BUY SHARES recommendation only; no order placement" />
            <div className="space-y-2 text-sm">
              <p><span className="text-zinc-500 dark:text-zinc-500">Entry zone:</span> {fmt(data.shares_plan.entry_zone?.low)} – {fmt(data.shares_plan.entry_zone?.high)}</p>
              <p><span className="text-zinc-500 dark:text-zinc-500">Stop:</span> {fmt(typeof data.shares_plan.stop === "object" && data.shares_plan.stop && "price" in data.shares_plan.stop ? (data.shares_plan.stop as { price?: number | null }).price ?? null : typeof data.shares_plan.stop === "number" ? data.shares_plan.stop : null)}</p>
              <p><span className="text-zinc-500 dark:text-zinc-500">Targets:</span> T1 {fmt(data.shares_plan.targets?.t1)} · T2 {fmt(data.shares_plan.targets?.t2)} · T3 {fmt(data.shares_plan.targets?.t3)}</p>
              <p><span className="text-zinc-500 dark:text-zinc-500">Invalidation:</span> {fmt(data.shares_plan.invalidation)}</p>
              <p><span className="text-zinc-500 dark:text-zinc-500">Hold-time:</span> {data.shares_plan.hold_time?.sessions_to_t1 ?? data.shares_plan.hold_time_estimate?.sessions ?? "—"} sessions · {holdTimeBasisLabel(data.shares_plan.hold_time_estimate?.basis_key)}</p>
              {data.shares_plan.confidence_score != null && <p><span className="text-zinc-500 dark:text-zinc-500">Confidence:</span> {data.shares_plan.confidence_score}</p>}
              <p><span className="text-zinc-500 dark:text-zinc-500">Why:</span> {(data.shares_plan.reason_codes?.length ? data.shares_plan.reason_codes.map(sharesReasonCodeToLabel).join("; ") : sharesWhyLabel(data.shares_plan.why_recommended)) || "—"}</p>
            </div>
          </Card>
        ) : null}

      </div>

      {/* Right column */}
      <div className="space-y-4">
        <Card>
          <CardHeader title="Exit Plan" />
          {ep?.status === "NOT_AVAILABLE" && ep?.reason ? (
            <p className="text-sm text-amber-700 dark:text-amber-400">{ep.reason}</p>
          ) : null}
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
      </> ) : (
        <SharesTabContent
          data={data}
          accountId={accountId ?? ""}
          upsertSharePosition={upsertSharePosition}
          deleteSharePosition={deleteSharePosition}
          sharesModalOpen={sharesModalOpen}
          setSharesModalOpen={setSharesModalOpen}
          sharesForm={sharesForm}
          setSharesForm={setSharesForm}
        />
      )}
    </div>
  );
}

function earningsDaysReason(_value: unknown): string {
  return "Not evaluated";
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

/** R23.0/R23.3: Shares tab — Plan view: eligibility badge, Why list, plan card (spot, entry zone, stop, targets, hold-time, sizing), Your Shares Position. */
function SharesTabContent({
  data,
  accountId,
  upsertSharePosition,
  deleteSharePosition,
  sharesModalOpen,
  setSharesModalOpen,
  sharesForm,
  setSharesForm,
}: {
  data: SymbolDiagnosticsResponseExtended;
  accountId: string;
  upsertSharePosition: ReturnType<typeof useUpsertSharePosition>;
  deleteSharePosition: ReturnType<typeof useDeleteSharePosition>;
  sharesModalOpen: boolean;
  setSharesModalOpen: (v: boolean) => void;
  sharesForm: { quantity: string; avg_cost: string; opened_at: string };
  setSharesForm: Dispatch<SetStateAction<{ quantity: string; avg_cost: string; opened_at: string }>>;
}) {
  const pos = data.shares_position;
  const plan = data.shares_plan;
  const eligibleLabel = plan?.eligible ? "Eligible" : "Not eligible";
  const reasonCodes = plan?.reason_codes ?? plan?.eligibility_codes ?? [];
  const stopObj = plan?.stop && typeof plan.stop === "object" && "price" in plan.stop ? plan.stop : { price: typeof plan?.stop === "number" ? plan.stop : null, basis: "" };
  const stopPrice = stopObj?.price ?? (typeof plan?.stop === "number" ? plan.stop : null);
  const hasPlan = plan && (plan.spot != null || plan.entry_zone?.low != null || stopPrice != null || plan.targets?.t1 != null || plan.sizing);
  return (
    <div className="space-y-4 lg:col-span-2">
      <Card>
        <CardHeader title="Shares" description="BUY SHARES recommendation only; no order placement." />
        <div className="space-y-3 text-sm">
          <p><span className="text-zinc-500 dark:text-zinc-400">Eligibility:</span> <span className={plan?.eligible ? "text-emerald-600 dark:text-emerald-400 font-medium" : "text-zinc-600 dark:text-zinc-400"}>{eligibleLabel}</span>
            {reasonCodes.includes("SHARES_UAT_FORCED") && (
              <Badge variant="warning" className="ml-2">UAT forced</Badge>
            )}
          </p>
          {reasonCodes.length > 0 && (
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Why</span>
              <ul className="list-disc pl-4 space-y-0.5 text-zinc-700 dark:text-zinc-300">
                {reasonCodes.map((c, i) => (
                  <li key={i}>{sharesReasonCodeToLabel(c)}</li>
                ))}
              </ul>
            </div>
          )}
          {hasPlan && (
            <div className="pt-2 border-t border-zinc-200 dark:border-zinc-700 space-y-2">
              <span className="block text-xs font-medium text-zinc-600 dark:text-zinc-300">Shares Plan</span>
              {plan.spot != null && <p><span className="text-zinc-500 dark:text-zinc-400">Spot:</span> <span className="font-mono">{plan.spot}</span></p>}
              {plan.entry_zone && (plan.entry_zone.low != null || plan.entry_zone.high != null) && (
                <p>
                  <span className="text-zinc-500 dark:text-zinc-400">Entry zone:</span> {fmt(plan.entry_zone.low)} – {fmt(plan.entry_zone.high)}
                  <Tooltip content={plan.entry_zone.basis ? `Based on ${plan.entry_zone.basis.replace(/_/g, " ").toLowerCase()}` : "Range around support"} className="ml-1 inline">
                    <span className="cursor-help text-zinc-400 dark:text-zinc-500" aria-label="Entry zone basis">ⓘ</span>
                  </Tooltip>
                </p>
              )}
              {stopPrice != null && (
                <p>
                  <span className="text-zinc-500 dark:text-zinc-400">Stop:</span> <span className="font-mono">{stopPrice}</span>
                  <Tooltip content="Stop below support (ATR-based)" className="ml-1 inline">
                    <span className="cursor-help text-zinc-400 dark:text-zinc-500" aria-label="Stop basis">ⓘ</span>
                  </Tooltip>
                </p>
              )}
              {plan.targets && (plan.targets.t1 != null || plan.targets.t2 != null) && (
                <p><span className="text-zinc-500 dark:text-zinc-400">Targets:</span> T1 {fmt(plan.targets.t1)} · T2 {fmt(plan.targets.t2)}</p>
              )}
              {plan.hold_time?.sessions_to_t1 != null && (
                <p>
                  <span className="text-zinc-500 dark:text-zinc-400">Hold-time estimate:</span> {plan.hold_time.sessions_to_t1} sessions
                  <Tooltip content={plan.hold_time.method === "ATR_DISTANCE" ? "Estimated sessions to T1 using ATR distance" : "Default or ATR-based estimate"} className="ml-1 inline">
                    <span className="cursor-help text-zinc-400 dark:text-zinc-500" aria-label="Hold-time method">ⓘ</span>
                  </Tooltip>
                </p>
              )}
              {plan.sizing && (
                <div className="pt-1">
                  <span className="block text-xs text-zinc-500 dark:text-zinc-400 mb-0.5">Sizing</span>
                  {plan.sizing.basis === "INSUFFICIENT_DATA" ? (
                    <p className="text-zinc-500 dark:text-zinc-400">Insufficient data (set account balances for suggested size)</p>
                  ) : (
                    <>
                      <p><span className="text-zinc-500 dark:text-zinc-400">Suggested shares:</span> <span className="font-mono font-medium">{plan.sizing.suggested_shares ?? "—"}</span></p>
                      {plan.sizing.suggested_cost != null && <p><span className="text-zinc-500 dark:text-zinc-400">Suggested cost:</span> <span className="font-mono">${plan.sizing.suggested_cost.toFixed(2)}</span></p>}
                      {plan.sizing.max_loss != null && <p><span className="text-zinc-500 dark:text-zinc-400">Max loss:</span> <span className="font-mono">${plan.sizing.max_loss.toFixed(2)}</span></p>}
                      <Tooltip content="Risk budget from account value × risk %; size = budget / stop distance" className="inline">
                        <span className="cursor-help text-zinc-400 dark:text-zinc-500" aria-label="Sizing method">ⓘ</span>
                      </Tooltip>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
          {data.mtf_levels && (data.mtf_levels.daily || data.mtf_levels.weekly || data.mtf_levels.monthly) && !hasPlan && (
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Multi-timeframe levels</span>
              <p className="text-zinc-700 dark:text-zinc-300">See Options tab for M/W/D support and resistance.</p>
            </div>
          )}
        </div>
      </Card>
      <Card>
        <CardHeader title="Your Shares Position" />
        {pos ? (
          <div className="space-y-2 text-sm">
            <p><span className="text-zinc-500 dark:text-zinc-400">Quantity:</span> <span className="font-mono font-medium">{pos.quantity}</span></p>
            {pos.avg_cost != null && <p><span className="text-zinc-500 dark:text-zinc-400">Avg cost:</span> <span className="font-mono">${pos.avg_cost.toFixed(2)}</span></p>}
            <p><span className="text-zinc-500 dark:text-zinc-400">Last updated:</span> {pos.updated_at ? new Date(pos.updated_at).toLocaleString() : "—"}</p>
            <div className="flex gap-2 pt-2">
              <Button size="sm" variant="secondary" onClick={() => { setSharesForm({ quantity: String(pos.quantity), avg_cost: pos.avg_cost != null ? String(pos.avg_cost) : "", opened_at: "" }); setSharesModalOpen(true); }}>
                Update
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={deleteSharePosition.isPending}
                onClick={() => { if (window.confirm(`Remove shares position for ${data.symbol}?`)) deleteSharePosition.mutate({ accountId, symbol: data.symbol }); }}
              >
                {deleteSharePosition.isPending ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-zinc-500 dark:text-zinc-400">No shares position recorded.</p>
        )}
        {!pos && (
          <Button size="sm" className="mt-2" onClick={() => { setSharesForm({ quantity: "", avg_cost: "", opened_at: "" }); setSharesModalOpen(true); }}>
            Add Shares Position
          </Button>
        )}
      </Card>
      {sharesModalOpen && (
        <Card className="border-zinc-400 dark:border-zinc-500">
          <CardHeader title="Add / Update Shares Position" />
          <div className="grid grid-cols-1 gap-3 max-w-xs">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Quantity (required)</label>
              <input
                type="number"
                min="1"
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={sharesForm.quantity}
                onChange={(e) => setSharesForm((p) => ({ ...p, quantity: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Avg cost (optional)</label>
              <input
                type="number"
                step="0.01"
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={sharesForm.avg_cost}
                onChange={(e) => setSharesForm((p) => ({ ...p, avg_cost: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Opened date (optional)</label>
              <input
                type="date"
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={sharesForm.opened_at || ""}
                onChange={(e) => setSharesForm((p) => ({ ...p, opened_at: e.target.value || "" }))}
              />
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => {
                  const qty = parseInt(sharesForm.quantity, 10);
                  if (!Number.isNaN(qty) && qty >= 0) {
                    upsertSharePosition.mutate({
                      account_id: accountId,
                      quantity: qty,
                      avg_cost: sharesForm.avg_cost.trim() ? parseFloat(sharesForm.avg_cost) : null,
                      opened_at: sharesForm.opened_at.trim() || null,
                    });
                    setSharesModalOpen(false);
                  }
                }}
                disabled={upsertSharePosition.isPending}
              >
                {upsertSharePosition.isPending ? "Saving…" : "Save"}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setSharesModalOpen(false)}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
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
