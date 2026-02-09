/**
 * Phase 2A: Top Opportunities panel — ranked decision intelligence.
 * Shows the top N opportunities sorted by band, score, and capital efficiency.
 * Each symbol appears once with its primary strategy (exclusivity rule).
 */
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { ManualExecuteModal } from "@/components/ManualExecuteModal";
import { pushSystemNotification } from "@/lib/notifications";
import type { RankedOpportunity, OpportunitiesResponse } from "@/types/opportunities";
import type { PositionStrategy } from "@/types/trackedPositions";
import { cn } from "@/lib/utils";
import { Loader2, Search, Target, TrendingUp, AlertTriangle, DollarSign, ChevronRight } from "lucide-react";

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

function formatCurrency(val: number | null): string {
  if (val == null) return "\u2014";
  if (val >= 1000) return `$${(val / 1000).toFixed(1)}k`;
  return `$${val.toFixed(0)}`;
}

function formatPct(val: number | null): string {
  if (val == null) return "\u2014";
  return `${(val * 100).toFixed(1)}%`;
}

interface TopOpportunitiesProps {
  /** Polling tick to trigger refresh */
  pollTick?: number;
}

export function TopOpportunities({ pollTick }: TopOpportunitiesProps) {
  const [data, setData] = useState<OpportunitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeOpp, setExecuteOpp] = useState<RankedOpportunity | null>(null);

  const fetchOpportunities = useCallback(async () => {
    try {
      const res = await apiGet<OpportunitiesResponse>(ENDPOINTS.dashboardOpportunities);
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

  const openExecute = (opp: RankedOpportunity) => {
    setExecuteOpp(opp);
    setExecuteModalOpen(true);
  };

  const opportunities = data?.opportunities ?? [];
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

  if (opportunities.length === 0) {
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
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
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
            <Link
              to="/analytics"
              className="flex items-center gap-0.5 text-primary hover:underline"
            >
              All <ChevronRight className="h-3 w-3" />
            </Link>
          </div>
        </div>

        {/* No account warning */}
        {hasCapitalWarning && (
          <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/5 px-4 py-2">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
            <span className="text-xs text-amber-700 dark:text-amber-300">
              No account set — capital sizing unavailable.{" "}
              <Link to="/accounts" className="font-medium underline">Add an account</Link>
            </span>
          </div>
        )}

        {/* Opportunities table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/20 text-left text-xs text-muted-foreground">
                <th className="px-4 py-2 font-medium w-8">#</th>
                <th className="px-4 py-2 font-medium">Symbol</th>
                <th className="px-4 py-2 font-medium">Strategy</th>
                <th className="px-4 py-2 font-medium">Band</th>
                <th className="px-4 py-2 font-medium">Risk</th>
                <th className="px-4 py-2 font-medium">Score</th>
                <th className="px-4 py-2 font-medium">Capital</th>
                <th className="px-4 py-2 font-medium max-w-[220px]">Why this is here</th>
                <th className="px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {opportunities.map((opp) => (
                <tr
                  key={`${opp.symbol}-${opp.strategy}`}
                  className="border-b border-border/50 last:border-0 transition-colors hover:bg-muted/30"
                >
                  {/* Rank */}
                  <td className="px-4 py-2.5">
                    <span className="text-xs font-bold text-muted-foreground">{opp.rank}</span>
                  </td>

                  {/* Symbol + price */}
                  <td className="px-4 py-2.5">
                    <div>
                      <span className="font-semibold text-foreground">{opp.symbol}</span>
                      {opp.price != null && (
                        <span className="ml-1.5 text-xs text-muted-foreground">${opp.price.toFixed(2)}</span>
                      )}
                    </div>
                    {opp.strike != null && (
                      <span className="text-xs text-muted-foreground">
                        ${opp.strike} strike{opp.expiry ? ` · ${opp.expiry}` : ""}
                      </span>
                    )}
                  </td>

                  {/* Strategy */}
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                      STRATEGY_STYLES[opp.strategy] ?? "bg-muted text-muted-foreground"
                    )}>
                      {opp.strategy}
                    </span>
                  </td>

                  {/* Band */}
                  <td className="px-4 py-2.5">
                    <span className={cn(
                      "inline-flex h-6 w-6 items-center justify-center rounded border text-xs font-bold",
                      BAND_STYLES[opp.band] ?? BAND_STYLES.C
                    )}>
                      {opp.band}
                    </span>
                  </td>

                  {/* Risk status (Phase 3) */}
                  <td className="px-4 py-2.5">
                    {opp.risk_status ? (
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                          opp.risk_status === "OK" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                          opp.risk_status === "WARN" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
                          opp.risk_status === "BLOCKED" && "bg-red-500/20 text-red-600 dark:text-red-400"
                        )}
                        title={opp.risk_status === "BLOCKED" ? (opp.risk_reasons ?? []).join(". ") : undefined}
                      >
                        {opp.risk_status}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>

                  {/* Score */}
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

                  {/* Capital */}
                  <td className="px-4 py-2.5">
                    {opp.capital_required != null ? (
                      <div>
                        <span className="text-foreground">{formatCurrency(opp.capital_required)}</span>
                        {opp.capital_pct != null && (
                          <span className={cn(
                            "ml-1 text-xs",
                            opp.capital_pct > 0.10 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                          )}>
                            ({formatPct(opp.capital_pct)})
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">\u2014</span>
                    )}
                  </td>

                  {/* Rank reason */}
                  <td className="px-4 py-2.5 max-w-[220px]">
                    <span
                      className="text-xs text-muted-foreground truncate block"
                      title={opp.rank_reason}
                    >
                      {opp.rank_reason}
                    </span>
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1">
                      <Link
                        to={`/analysis?symbol=${opp.symbol}`}
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs text-primary hover:bg-muted"
                        title="View ticker analysis"
                      >
                        <Search className="h-3 w-3" />
                        Details
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
                              : "Record manual execution"
                          }
                        >
                          <Target className="h-3 w-3" />
                          Execute
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        {data && data.total_eligible > opportunities.length && (
          <div className="border-t border-border px-4 py-2 text-center">
            <Link to="/analytics" className="text-xs text-primary hover:underline">
              View all {data.total_eligible} eligible candidates
            </Link>
          </div>
        )}
      </section>

      {/* Execute modal */}
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
            // Refresh opportunities
            fetchOpportunities();
          }}
        />
      )}
    </>
  );
}
