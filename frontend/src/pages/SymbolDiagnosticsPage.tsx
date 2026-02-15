import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Calendar, Database, Droplets } from "lucide-react";
import { useSymbolDiagnostics } from "@/api/queries";
import type { SymbolDiagnosticsResponseExtended } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";

function verdictColor(v: string | null | undefined): string {
  const s = (v ?? "").toUpperCase();
  if (s === "ELIGIBLE") return "text-green-400";
  if (s === "HOLD") return "text-yellow-400";
  if (s === "BLOCKED" || s === "UNKNOWN") return "text-red-400";
  return "text-zinc-400";
}

function regimeColor(r: string | null | undefined): string {
  const s = (r ?? "").toUpperCase();
  if (s === "UP") return "border-emerald-500/50 bg-emerald-500/10 text-emerald-400";
  if (s === "DOWN") return "border-red-500/50 bg-red-500/10 text-red-400";
  if (s === "SIDEWAYS" || s === "NEUTRAL") return "border-amber-500/50 bg-amber-500/10 text-amber-400";
  return "border-zinc-600 bg-zinc-800/50 text-zinc-400";
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

export function SymbolDiagnosticsPage() {
  const [searchParams] = useSearchParams();
  const symbolFromUrl = searchParams.get("symbol")?.trim().toUpperCase() ?? "";
  const [symbol, setSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const shouldFetch = activeSymbol != null && isValidSymbol(activeSymbol);
  const { data, isLoading, isError } = useSymbolDiagnostics(activeSymbol ?? "", shouldFetch);

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
        <ExecutionConsole data={data} />
      )}

      {!data && !isLoading && !isError && !showInvalidError && (
        <p className="text-xs text-zinc-500">Enter symbol and click Lookup.</p>
      )}
    </div>
  );
}

function ExecutionConsole({ data }: { data: SymbolDiagnosticsResponseExtended }) {
  const comp = data.computed;
  const ep = data.exit_plan;
  const candidates = data.candidates ?? [];
  const liq = data.liquidity;
  const sel = data.symbol_eligibility;

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {/* Left column */}
      <div className="space-y-3">
        {/* 1. Top Thesis */}
        <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Thesis
          </h3>
          <div className="flex flex-wrap items-baseline gap-4">
            <div>
              <span className="block text-xs text-zinc-500">verdict</span>
              <span className={`text-xl font-bold ${verdictColor(data.verdict)}`}>
                {data.verdict ?? "—"}
              </span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">score</span>
              <span className="font-mono text-2xl font-semibold text-zinc-300">
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
            <p className="mt-2 text-xs text-zinc-500">{data.band_reason}</p>
          )}
        </section>

        {/* 2. Technical Context Grid */}
        <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Technical
          </h3>
          <div className="grid grid-cols-3 gap-x-6 gap-y-2 text-sm">
            <Kv label="RSI" value={fmt(comp?.rsi)} />
            <Kv label="ATR" value={fmt(comp?.atr)} />
            <Kv label="ATR%" value={comp?.atr_pct != null ? fmtPct(comp.atr_pct) : "—"} />
            <Kv label="support" value={fmt(comp?.support_level)} />
            <Kv label="resistance" value={fmt(comp?.resistance_level)} />
            <div>
              <span className="block text-zinc-500">regime</span>
              <span
                className={`inline-flex rounded border px-2 py-0.5 text-sm font-medium ${regimeColor(data.regime)}`}
              >
                {data.regime ?? "—"}
              </span>
            </div>
          </div>
        </section>

        {/* 3. Candidate Table */}
        <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Candidates
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-700 text-left text-zinc-500">
                  <th className="py-2 pr-2">strategy</th>
                  <th className="py-2 pr-2">strike</th>
                  <th className="py-2 pr-2">expiry</th>
                  <th className="py-2 pr-2">DTE</th>
                  <th className="py-2 pr-2">delta</th>
                  <th className="py-2 pr-2">credit</th>
                  <th className="py-2 pr-2">max_loss</th>
                  <th className="py-2 pr-2">ret%</th>
                  <th className="py-2">why</th>
                </tr>
              </thead>
              <tbody>
                {candidates.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-3 text-zinc-500">
                      No candidates.
                    </td>
                  </tr>
                ) : (
                  candidates.map((c, i) => {
                    const dte = computeDte(c.expiry);
                    const retPct = computeExpectedReturnPct(c.strike ?? undefined, c.credit_estimate ?? undefined);
                    const inBand = deltaInBand(c.delta ?? undefined, c.strategy ?? "");
                    return (
                      <tr
                        key={i}
                        className={`border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30 ${
                          i % 2 === 1 ? "bg-zinc-900/30" : ""
                        }`}
                      >
                        <td className="py-2 pr-2 font-mono">{c.strategy ?? "—"}</td>
                        <td className="py-2 pr-2 font-mono font-bold text-zinc-100">
                          {fmt(c.strike)}
                        </td>
                        <td className="py-2 pr-2 font-mono">{c.expiry ?? "—"}</td>
                        <td className="py-2 pr-2">{dte != null ? dte : "—"}</td>
                        <td
                          className={`py-2 pr-2 font-mono ${
                            inBand ? "text-emerald-400 font-semibold" : ""
                          }`}
                        >
                          {c.delta != null ? c.delta.toFixed(3) : "—"}
                        </td>
                        <td className="py-2 pr-2">{fmt(c.credit_estimate)}</td>
                        <td className="py-2 pr-2">{fmt(c.max_loss)}</td>
                        <td className="py-2 pr-2">{retPct != null ? retPct.toFixed(2) + "%" : "—"}</td>
                        <td
                          className="py-2 truncate max-w-[120px] text-zinc-400"
                          title={c.why_this_trade ?? ""}
                        >
                          {c.why_this_trade ?? "—"}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Right column */}
      <div className="space-y-3">
        {/* 4. Exit Plan Card */}
        <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Exit Plan
          </h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500">T1</span>
              <span className="font-mono text-zinc-300">{fmt(ep?.t1)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">T2</span>
              <span className="font-mono text-zinc-300">{fmt(ep?.t2)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">T3</span>
              <span className="font-mono text-zinc-300">{fmt(ep?.t3)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">stop</span>
              <span className="font-mono font-semibold text-red-400">{fmt(ep?.stop)}</span>
            </div>
          </div>
        </section>

        {/* 5. Risk Flags */}
        <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Risk Flags
          </h3>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <RiskFlag
              icon={<Calendar className="h-4 w-4" />}
              label="earnings days"
              value="—"
              status="neutral"
            />
            <RiskFlag
              icon={<Calendar className="h-4 w-4" />}
              label="earnings block"
              value="—"
              status="neutral"
            />
            <RiskFlag
              icon={<Droplets className="h-4 w-4" />}
              label="stock liq"
              value={
                liq?.stock_liquidity_ok == null
                  ? "—"
                  : liq.stock_liquidity_ok
                    ? "OK"
                    : "FAIL"
              }
              status={
                liq?.stock_liquidity_ok == null
                  ? "neutral"
                  : liq.stock_liquidity_ok
                    ? "ok"
                    : "fail"
              }
            />
            <RiskFlag
              icon={<Droplets className="h-4 w-4" />}
              label="option liq"
              value={
                liq?.option_liquidity_ok == null
                  ? "—"
                  : liq.option_liquidity_ok
                    ? "OK"
                    : "FAIL"
              }
              status={
                liq?.option_liquidity_ok == null
                  ? "neutral"
                  : liq.option_liquidity_ok
                    ? "ok"
                    : "fail"
              }
            />
            <RiskFlag
              icon={<Database className="h-4 w-4" />}
              label="data status"
              value={sel?.status ?? "—"}
              status={
                sel?.status === "PASS"
                  ? "ok"
                  : sel?.status === "FAIL"
                    ? "fail"
                    : "neutral"
              }
            />
            <div className="col-span-2 flex items-start gap-2">
              <Database className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
              <div>
                <span className="block text-xs text-zinc-500">missing</span>
                <span className="font-mono text-zinc-300">
                  {sel?.required_data_missing?.join(", ") ?? "—"}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Gates (compact) */}
        <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Gates
          </h3>
          <div className="space-y-1 text-xs">
            {data.gates?.length ? (
              data.gates.map((g, i) => (
                <div key={i} className="flex items-center justify-between gap-2">
                  <span className="truncate text-zinc-300">{g.name}</span>
                  <StatusBadge status={g.status} />
                  <span className="truncate text-zinc-500">{g.reason}</span>
                </div>
              ))
            ) : (
              <span className="text-zinc-500">No gates.</span>
            )}
          </div>
        </section>
      </div>
    </div>
  );
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
      <span className="text-zinc-500">{label}</span>
      <div className="font-mono text-zinc-200">{value}</div>
    </div>
  );
}
