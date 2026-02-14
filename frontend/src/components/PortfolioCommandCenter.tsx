/**
 * Phase 8.4 – Portfolio Dashboard (Read-Only Command Center)
 * Read-only command center. No trading logic mutation.
 */
import { useEffect, useState, useCallback } from "react";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import type {
  PortfolioDashboardResponse,
  PortfolioDashboardSnapshot,
  PortfolioDashboardStressScenario,
} from "@/types/portfolio";
import { Loader2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

const TARGET_MAX_EXPOSURE_PCT = 35;

function formatCurrency(n: number | null | undefined): string {
  if (n == null) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function formatPct(n: number | null | undefined): string {
  if (n == null) return "N/A";
  return `${n.toFixed(1)}%`;
}

function exposureStatusColor(exposurePct: number | null | undefined): "green" | "yellow" | "red" | "muted" {
  if (exposurePct == null) return "muted";
  const target = TARGET_MAX_EXPOSURE_PCT;
  const pctOfTarget = exposurePct / target;
  if (pctOfTarget < 0.7) return "green";
  if (pctOfTarget < 1) return "yellow";
  return "red";
}

function survivalStatusStyle(s: string): string {
  switch (s?.toUpperCase()) {
    case "OK": return "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400";
    case "TIGHT": return "bg-amber-500/20 text-amber-600 dark:text-amber-400";
    case "CRITICAL": return "bg-red-500/20 text-red-600 dark:text-red-400";
    default: return "bg-muted text-muted-foreground";
  }
}

export function PortfolioCommandCenter() {
  const [data, setData] = useState<PortfolioDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    setError(null);
    try {
      const res = await apiGet<PortfolioDashboardResponse>(ENDPOINTS.portfolioDashboard);
      setData(res);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 p-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading command center...
      </div>
    );
  }

  if (error || data?.error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
        {error || data?.error}
      </div>
    );
  }

  const snapshot: PortfolioDashboardSnapshot = data?.snapshot ?? {};
  const stress = data?.stress ?? {};
  const scenarios: PortfolioDashboardStressScenario[] = stress.scenarios ?? [];
  const worstShock = stress.worst_case?.shock_pct;

  const equity = snapshot.portfolio_equity_usd ?? (scenarios[0]?.starting_equity ?? null);
  const exposurePct = snapshot.exposure_pct;
  const expStatus = exposureStatusColor(exposurePct);

  return (
    <div className="space-y-6">
      {/* Section 1: Overview Cards */}
      <section>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Overview</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Total Equity</p>
            <p className="text-lg font-semibold mt-1">{formatCurrency(equity)}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Exposure %</p>
            <p className="text-lg font-semibold mt-1">{formatPct(exposurePct)}</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Target Exposure %</p>
            <p className="text-lg font-semibold mt-1">{TARGET_MAX_EXPOSURE_PCT}%</p>
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <p className="text-xs text-muted-foreground">Exposure Status</p>
            <span
              className={cn(
                "inline-flex mt-1 rounded-full px-2 py-0.5 text-xs font-medium",
                expStatus === "green" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                expStatus === "yellow" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
                expStatus === "red" && "bg-red-500/20 text-red-600 dark:text-red-400",
                expStatus === "muted" && "bg-muted text-muted-foreground"
              )}
            >
              {exposurePct == null ? "N/A" : expStatus === "green" ? "GREEN" : expStatus === "yellow" ? "YELLOW" : "RED"}
            </span>
          </div>
        </div>
      </section>

      {/* Section 2: Position Summary */}
      <section>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Position Summary</h3>
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b border-border">
                <td className="p-3 text-muted-foreground">Open CSP</td>
                <td className="p-3 font-medium">{snapshot.open_csp_count ?? 0}</td>
              </tr>
              <tr className="border-b border-border">
                <td className="p-3 text-muted-foreground">Open CC</td>
                <td className="p-3 font-medium">{snapshot.open_cc_count ?? 0}</td>
              </tr>
              <tr className="border-b border-border">
                <td className="p-3 text-muted-foreground">CSP Reserved Cash</td>
                <td className="p-3 font-medium">{scenarios[0] ? formatCurrency(scenarios[0].csp_reserved_cash) : "N/A"}</td>
              </tr>
              <tr>
                <td className="p-3 text-muted-foreground">CC Equity Notional</td>
                <td className="p-3 font-medium">{scenarios[0] ? formatCurrency(scenarios[0].cc_equity_notional) : "N/A"}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Section 3: Concentration */}
      <section>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Concentration</h3>
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                <th className="p-3 font-medium">Symbol</th>
                <th className="p-3 font-medium">$ Committed</th>
                <th className="p-3 font-medium">% of Portfolio</th>
              </tr>
            </thead>
            <tbody>
              {(snapshot.symbol_concentration?.top_symbols ?? []).slice(0, 5).map((t) => (
                <tr key={t.symbol} className="border-b border-border hover:bg-muted/50">
                  <td className="p-3 font-medium">{t.symbol}</td>
                  <td className="p-3">{formatCurrency(t.committed)}</td>
                  <td className="p-3">{t.pct_of_committed?.toFixed(1) ?? "0"}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="p-3 border-t border-border flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Cluster Risk Level:</span>
            <span
              className={cn(
                "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                (snapshot.cluster_risk_level ?? "").toUpperCase() === "HIGH" && "bg-red-500/20 text-red-600 dark:text-red-400",
                (snapshot.cluster_risk_level ?? "").toUpperCase() === "MEDIUM" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
                (snapshot.cluster_risk_level ?? "").toUpperCase() === "LOW" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                !["HIGH", "MEDIUM", "LOW"].includes((snapshot.cluster_risk_level ?? "").toUpperCase()) && "bg-muted text-muted-foreground"
              )}
            >
              {snapshot.cluster_risk_level ?? "UNKNOWN"}
            </span>
          </div>
        </div>
      </section>

      {/* Section 4: Dynamic Stress Table */}
      <section>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Dynamic Stress</h3>
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                <th className="p-3 font-medium">Shock %</th>
                <th className="p-3 font-medium">Assignments</th>
                <th className="p-3 font-medium">Capital Required</th>
                <th className="p-3 font-medium">Drawdown</th>
                <th className="p-3 font-medium">Post-Shock Exposure %</th>
                <th className="p-3 font-medium">Survival Status</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr
                  key={s.shock_pct}
                  className={cn(
                    "border-b border-border hover:bg-muted/50",
                    s.shock_pct === worstShock && "bg-amber-500/10"
                  )}
                >
                  <td className="p-3 font-medium">{s.shock_pct != null ? Math.round(s.shock_pct * 100) : "?"}%</td>
                  <td className="p-3">{s.estimated_assignments ?? 0}</td>
                  <td className="p-3">{formatCurrency(s.assignment_capital_required)}</td>
                  <td className="p-3">{formatCurrency(s.estimated_unrealized_drawdown)}</td>
                  <td className="p-3">{formatPct(s.post_shock_exposure_pct)}</td>
                  <td className="p-3">
                    <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-medium", survivalStatusStyle(s.survival_status ?? ""))}>
                      {s.survival_status ?? "UNKNOWN"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {scenarios.length === 0 && (
            <p className="p-6 text-center text-muted-foreground text-sm">No stress scenarios.</p>
          )}
        </div>
      </section>

      {/* Section 5: Notes / Warnings */}
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <AlertTriangle className="h-4 w-4" />
          Notes & Warnings
        </h3>
        <div className="rounded-lg border border-border p-4 space-y-2">
          {[
            ...(snapshot.warnings ?? []),
            ...(stress.warnings ?? []),
          ].length === 0 ? (
            <p className="text-sm text-muted-foreground">No warnings.</p>
          ) : (
            <ul className="text-sm list-disc list-inside space-y-1 text-muted-foreground">
              {[...(snapshot.warnings ?? []), ...(stress.warnings ?? [])].map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
