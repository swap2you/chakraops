/**
 * Phase 4: Decision Quality Summary — outcome counts, avg time in trade, capital efficiency.
 * Shows INSUFFICIENT DATA when fewer than 30 closed positions.
 */
import { useEffect, useState, useCallback } from "react";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import type { OutcomeSummary, StrategyHealth } from "@/types/decisionQuality";
import { Loader2, BarChart3 } from "lucide-react";

export function DecisionQualitySummary() {
  const [summary, setSummary] = useState<OutcomeSummary | null>(null);
  const [strategyHealth, setStrategyHealth] = useState<StrategyHealth | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [sumRes, healthRes] = await Promise.all([
        apiGet<OutcomeSummary>(ENDPOINTS.decisionQualitySummary),
        apiGet<StrategyHealth>(ENDPOINTS.decisionQualityStrategyHealth),
      ]);
      setSummary(sumRes);
      setStrategyHealth(healthRes);
    } catch (e) {
      if (e instanceof ApiError) {
        setSummary({ status: "ERROR", error: e.message });
        setStrategyHealth({ status: "ERROR", error: e.message });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading decision quality...
      </div>
    );
  }

  const isInsufficient =
    summary?.status === "INSUFFICIENT DATA" || strategyHealth?.status === "INSUFFICIENT DATA";
  const closedCount = summary?.total_closed ?? strategyHealth?.total_closed ?? 0;

  return (
    <section className="space-y-4">
      <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <BarChart3 className="h-4 w-4" />
        Decision Quality
      </h2>

      {isInsufficient ? (
        <div className="rounded-lg border border-border bg-muted/20 p-6 text-center text-sm text-muted-foreground">
          INSUFFICIENT DATA — minimum 30 closed positions required. ({closedCount} closed)
        </div>
      ) : summary?.status === "ERROR" ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {summary.error ?? "Failed to load decision quality"}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="rounded-lg border border-border p-4">
              <div className="text-xs text-muted-foreground">Wins</div>
              <div className="text-2xl font-semibold text-emerald-600">{summary?.win_count ?? "—"}</div>
            </div>
            <div className="rounded-lg border border-border p-4">
              <div className="text-xs text-muted-foreground">Scratches</div>
              <div className="text-2xl font-semibold text-amber-600">{summary?.scratch_count ?? "—"}</div>
            </div>
            <div className="rounded-lg border border-border p-4">
              <div className="text-xs text-muted-foreground">Losses</div>
              <div className="text-2xl font-semibold text-red-600">{summary?.loss_count ?? "—"}</div>
            </div>
            <div className="rounded-lg border border-border p-4">
              <div className="text-xs text-muted-foreground">UNKNOWN (insufficient risk def.)</div>
              <div className="text-2xl font-semibold text-muted-foreground">
                {summary?.unknown_risk_definition_count ?? 0}
              </div>
            </div>
            <div className="rounded-lg border border-border p-4">
              <div className="text-xs text-muted-foreground">Avg Days in Trade</div>
              <div className="text-2xl font-semibold">
                {summary?.avg_time_in_trade_days != null ? summary.avg_time_in_trade_days.toFixed(1) : "—"}
              </div>
            </div>
          </div>

          {strategyHealth?.strategies && Object.keys(strategyHealth.strategies).length > 0 && (
            <div className="rounded-lg border border-border overflow-hidden">
              <h3 className="px-4 py-2 text-xs font-medium text-muted-foreground bg-muted/30">
                Strategy Health
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
                    <th className="p-3 font-medium">Strategy</th>
                    <th className="p-3 font-medium">Win %</th>
                    <th className="p-3 font-medium">Loss %</th>
                    <th className="p-3 font-medium">Avg Duration</th>
                    <th className="p-3 font-medium">Abort %</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(strategyHealth.strategies).map(([strat, data]) => (
                    <tr key={strat} className="border-b border-border hover:bg-muted/30">
                      <td className="p-3 font-medium">{strat}</td>
                      <td className="p-3 text-emerald-600">{data.win_pct}%</td>
                      <td className="p-3 text-red-600">{data.loss_pct}%</td>
                      <td className="p-3">
                        {data.avg_duration_days != null ? `${data.avg_duration_days}d` : "—"}
                      </td>
                      <td className="p-3">{data.abort_pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
