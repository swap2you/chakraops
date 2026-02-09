/**
 * Phase 5: Top Opportunities — Dashboard truthfulness & UX.
 * Shows top N opportunities (default 7, configurable).
 * Columns: Band, Risk Status, Strategy, Score, Capital Required, Capital % of Equity, Reason.
 * Sort: Band (A→D) → Risk (OK→WARN→BLOCKED) → Capital% asc → Score desc.
 * Filters: Band, Strategy, Risk Status, Max Capital %.
 * UNKNOWN states shown explicitly (never blanks).
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { ManualExecuteModal } from "@/components/ManualExecuteModal";
import { pushSystemNotification } from "@/lib/notifications";
import type { RankedOpportunity, OpportunitiesResponse } from "@/types/opportunities";
import type { PositionStrategy } from "@/types/trackedPositions";
import { cn } from "@/lib/utils";
import { Loader2, Search, Target, TrendingUp, AlertTriangle, DollarSign, ChevronRight, Filter } from "lucide-react";

const BAND_STYLES: Record<string, string> = {
  A: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
  B: "bg-blue-500/20 text-blue-700 dark:text-blue-400 border-blue-500/30",
  C: "bg-muted text-muted-foreground border-border",
};

const STRATEGY_STYLES: Record<string, string> = {
  CSP: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  CC: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  STOCK: "bg-purple-500/15 text-purple-700 dark:text-purple-400",
};

const RISK_PRIORITY: Record<string, number> = { OK: 0, WARN: 1, BLOCKED: 2 };

function formatCurrency(val: number | null): string {
  if (val == null) return "UNKNOWN";
  if (val >= 1000) return `$${(val / 1000).toFixed(1)}k`;
  return `$${val.toFixed(0)}`;
}

function formatPct(val: number | null): string {
  if (val == null) return "UNKNOWN";
  return `${(val * 100).toFixed(1)}%`;
}

function riskLabel(status: string | null | undefined): string {
  if (status === "OK" || status === "WARN" || status === "BLOCKED") return status;
  return "UNKNOWN";
}

interface TopOpportunitiesProps {
  pollTick?: number;
  defaultLimit?: number;
}

export function TopOpportunities({ pollTick, defaultLimit = 7 }: TopOpportunitiesProps) {
  const [data, setData] = useState<OpportunitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeOpp, setExecuteOpp] = useState<RankedOpportunity | null>(null);
  const [limit, setLimit] = useState(defaultLimit);
  const [bandFilter, setBandFilter] = useState<string>("ALL");
  const [strategyFilter, setStrategyFilter] = useState<string>("ALL");
  const [riskFilter, setRiskFilter] = useState<string>("ALL");
  const [maxCapFilter, setMaxCapFilter] = useState<string>("");

  const fetchOpportunities = useCallback(async () => {
    try {
      const res = await apiGet<OpportunitiesResponse>(
        `${ENDPOINTS.dashboardOpportunities}?limit=50&include_blocked=true`
      );
      setData(res);
      setError(null);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities, pollTick]);

  const filtered = useMemo(() => {
    let items = data?.opportunities ?? [];
    if (bandFilter !== "ALL") items = items.filter((o) => o.band === bandFilter);
    if (strategyFilter !== "ALL") items = items.filter((o) => o.strategy === strategyFilter);
    if (riskFilter !== "ALL") {
      if (riskFilter === "UNKNOWN") {
        items = items.filter((o) => !o.risk_status || (o.risk_status !== "OK" && o.risk_status !== "WARN" && o.risk_status !== "BLOCKED"));
      } else {
        items = items.filter((o) => o.risk_status === riskFilter);
      }
    }
    if (maxCapFilter) {
      const maxPct = parseFloat(maxCapFilter) / 100;
      if (!isNaN(maxPct)) {
        items = items.filter((o) => o.capital_pct == null || o.capital_pct <= maxPct);
      }
    }
    const sorted = [...items].sort((a, b) => {
      const bandA = { A: 0, B: 1, C: 2 }[a.band] ?? 99;
      const bandB = { A: 0, B: 1, C: 2 }[b.band] ?? 99;
      if (bandA !== bandB) return bandA - bandB;
      const riskA = RISK_PRIORITY[a.risk_status ?? ""] ?? 3;
      const riskB = RISK_PRIORITY[b.risk_status ?? ""] ?? 3;
      if (riskA !== riskB) return riskA - riskB;
      const capA = a.capital_pct ?? 1;
      const capB = b.capital_pct ?? 1;
      if (capA !== capB) return capA - capB;
      return (b.score ?? 0) - (a.score ?? 0);
    });
    return sorted.slice(0, limit);
  }, [data, bandFilter, strategyFilter, riskFilter, maxCapFilter, limit]);

  const openExecute = (opp: RankedOpportunity) => {
    setExecuteOpp(opp);
    setExecuteModalOpen(true);
  };

  const opportunities = filtered;
  const hasCapitalWarning = data?.account_equity == null && opportunities.length > 0;

  if (loading) {
    return (
      <section className="rounded-lg border border-border bg-card p-4" aria-label="Top opportunities">
        <h2 className="text-sm font-medium text-muted-foreground">Top Opportunities</h2>
        <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading ranked opportunities...
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-lg border border-border bg-card p-4" aria-label="Top opportunities">
        <h2 className="text-sm font-medium text-muted-foreground">Top Opportunities</h2>
        <p className="mt-2 text-sm text-destructive">{error}</p>
      </section>
    );
  }

  if (opportunities.length === 0 && !data?.opportunities?.length) {
    return (
      <section className="rounded-lg border border-border bg-card p-4" aria-label="Top opportunities">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Top Opportunities</h2>
          {data?.evaluated_at && (
            <span className="text-xs text-muted-foreground">
              {new Date(data.evaluated_at).toLocaleTimeString()}
            </span>
          )}
        </div>
        <div className="py-6 text-center text-muted-foreground">
          <TrendingUp className="mx-auto h-6 w-6 mb-2 opacity-40" />
          <p className="text-sm">No ranked opportunities available.</p>
          <p className="mt-1 text-xs">
            {data?.evaluation_id
              ? `${data.total_eligible} eligible in last run — none passed ranking filters.`
              : "No evaluation run found. Trigger one from the dashboard."}
          </p>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="rounded-lg border border-border bg-card" aria-label="Top opportunities">
        <div className="flex flex-col gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold text-foreground">Top Opportunities</h2>
              <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                {opportunities.length} of {data?.total_eligible ?? 0}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {data?.account_equity != null && (
                <span className="flex items-center gap-1">
                  <DollarSign className="h-3 w-3" />
                  ${data.account_equity.toLocaleString()}
                </span>
              )}
              {data?.evaluated_at && (
                <span>{new Date(data.evaluated_at).toLocaleTimeString()}</span>
              )}
              <Link to="/analytics" className="flex items-center gap-0.5 text-primary hover:underline">
                All <ChevronRight className="h-3 w-3" />
              </Link>
            </div>
          </div>

          {/* Filters + limit */}
          <div className="flex flex-wrap items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={bandFilter}
              onChange={(e) => setBandFilter(e.target.value)}
              className="rounded border border-border bg-background px-2 py-1 text-xs"
              aria-label="Filter by band"
            >
              <option value="ALL">All bands</option>
              <option value="A">Band A</option>
              <option value="B">Band B</option>
              <option value="C">Band C</option>
            </select>
            <select
              value={strategyFilter}
              onChange={(e) => setStrategyFilter(e.target.value)}
              className="rounded border border-border bg-background px-2 py-1 text-xs"
              aria-label="Filter by strategy"
            >
              <option value="ALL">All strategies</option>
              <option value="CSP">CSP</option>
              <option value="CC">CC</option>
              <option value="STOCK">STOCK</option>
            </select>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="rounded border border-border bg-background px-2 py-1 text-xs"
              aria-label="Filter by risk status"
            >
              <option value="ALL">All risk</option>
              <option value="OK">OK</option>
              <option value="WARN">WARN</option>
              <option value="BLOCKED">BLOCKED</option>
              <option value="UNKNOWN">UNKNOWN</option>
            </select>
            <input
              type="number"
              placeholder="Max cap %"
              value={maxCapFilter}
              onChange={(e) => setMaxCapFilter(e.target.value)}
              className="w-18 rounded border border-border bg-background px-2 py-1 text-xs"
              min="1"
              max="100"
              aria-label="Max capital percentage"
            />
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded border border-border bg-background px-2 py-1 text-xs"
              aria-label="Number to show"
            >
              {[5, 7, 10, 15, 20].map((n) => (
                <option key={n} value={n}>Show {n}</option>
              ))}
            </select>
          </div>
        </div>

        {hasCapitalWarning && (
          <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/5 px-4 py-2">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            <span className="text-xs text-amber-700 dark:text-amber-300">
              Account equity UNKNOWN — capital sizing unavailable.{" "}
              <Link to="/accounts" className="font-medium underline">Add an account</Link>
            </span>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/20 text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium w-8">#</th>
                <th className="px-4 py-2 font-medium">Symbol</th>
                <th className="px-4 py-2 font-medium">Band</th>
                <th className="px-4 py-2 font-medium">Risk Status</th>
                <th className="px-4 py-2 font-medium">Strategy</th>
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Capital Required</th>
                <th className="px-4 py-2 font-medium">Capital % of Equity</th>
                <th className="px-4 py-2 font-medium max-w-[200px]">Reason</th>
                <th className="px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {opportunities.map((opp, idx) => (
                <tr
                  key={`${opp.symbol}-${opp.strategy}`}
                  className="border-b border-border/50 last:border-0 transition-colors hover:bg-muted/30"
                >
                  <td className="px-4 py-2.5">
                    <span className="text-xs font-bold text-muted-foreground">{idx + 1}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div>
                      <span className="font-semibold text-foreground">{opp.symbol}</span>
                      {opp.price != null && (
                        <span className="ml-1.5 text-xs text-muted-foreground">${opp.price.toFixed(2)}</span>
                      )}
                      {opp.price == null && (
                        <span className="ml-1.5 text-xs text-muted-foreground">(Price UNKNOWN)</span>
                      )}
                    </div>
                    {opp.strike != null && (
                      <span className="text-xs text-muted-foreground">
                        ${opp.strike} strike{opp.expiry ? ` · ${opp.expiry}` : ""}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      "inline-flex h-6 w-6 items-center justify-center rounded border text-xs font-bold",
                      BAND_STYLES[opp.band] ?? BAND_STYLES.C
                    )}>
                      {opp.band}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                        opp.risk_status === "OK" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                        opp.risk_status === "WARN" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
                        opp.risk_status === "BLOCKED" && "bg-red-500/20 text-red-600 dark:text-red-400",
                        !opp.risk_status && "bg-muted text-muted-foreground"
                      )}
                      title={opp.risk_status === "BLOCKED" ? (opp.risk_reasons ?? []).join(". ") : opp.risk_status == null ? "Risk status not available from API" : undefined}
                    >
                      {riskLabel(opp.risk_status)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                      STRATEGY_STYLES[opp.strategy] ?? "bg-muted text-muted-foreground"
                    )}>
                      {opp.strategy}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      "font-semibold tabular-nums",
                      opp.score >= 78 ? "text-emerald-600 dark:text-emerald-400" :
                      opp.score >= 60 ? "text-blue-600 dark:text-blue-400" :
                      "text-muted-foreground"
                    )}>
                      {opp.score}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={opp.capital_required != null ? "text-foreground" : "text-muted-foreground"}>
                      {formatCurrency(opp.capital_required)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      opp.capital_pct != null ? "" : "text-muted-foreground",
                      opp.capital_pct != null && opp.capital_pct > 0.10 ? "text-amber-600 dark:text-amber-400" : ""
                    )}>
                      {formatPct(opp.capital_pct)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 max-w-[200px]">
                    <span
                      className="text-xs text-muted-foreground truncate block"
                      title={opp.rank_reason || "No reason provided"}
                    >
                      {opp.rank_reason || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1">
                      <Link
                        to={`/analysis?symbol=${opp.symbol}`}
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs text-primary hover:bg-muted"
                        title="View ticker analysis"
                      >
                        <Search className="h-3 w-3" />
                        View Ticker
                      </Link>
                      {!opp.position_open && (
                        <button
                          onClick={() => opp.risk_status !== "BLOCKED" && openExecute(opp)}
                          disabled={opp.risk_status === "BLOCKED"}
                          className={cn(
                            "flex items-center gap-1 rounded px-2 py-1 text-xs font-medium",
                            opp.risk_status === "BLOCKED"
                              ? "cursor-not-allowed bg-muted text-muted-foreground"
                              : "bg-primary/10 text-primary hover:bg-primary/20"
                          )}
                          title={
                            opp.risk_status === "BLOCKED"
                              ? `Why blocked: ${(opp.risk_reasons ?? []).join("; ")}`
                              : "Record manual execution (log intent only)"
                          }
                        >
                          <Target className="h-3 w-3" />
                          Execute (Manual)
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data && data.total_eligible > opportunities.length && (
          <div className="border-t border-border px-4 py-2 text-center">
            <Link to="/analytics" className="text-xs text-primary hover:underline">
              View all {data.total_eligible} eligible candidates
            </Link>
          </div>
        )}
      </section>

      {executeModalOpen && executeOpp && (
        <ManualExecuteModal
          symbol={executeOpp.symbol}
          strategy={executeOpp.strategy as PositionStrategy}
          strike={executeOpp.strike}
          expiration={executeOpp.expiry}
          creditEstimate={executeOpp.credit_estimate}
          onClose={() => { setExecuteModalOpen(false); setExecuteOpp(null); }}
          onExecuted={() => {
            setExecuteModalOpen(false);
            setExecuteOpp(null);
            pushSystemNotification({
              source: "system",
              severity: "info",
              title: "Position recorded",
              message: `${executeOpp.symbol} ${executeOpp.strategy} tracked. Execute in your brokerage.`,
            });
            fetchOpportunities();
          }}
        />
      )}
    </>
  );
}
