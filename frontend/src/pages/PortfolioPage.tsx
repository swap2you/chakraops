/**
 * Phase 3: Portfolio dashboard — summary cards, exposure tables, risk profile editor.
 */
import { useEffect, useState, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { PortfolioSummaryCards } from "@/components/PortfolioSummaryCards";
import { ExposureTable } from "@/components/ExposureTable";
import { RiskProfileForm } from "@/components/RiskProfileForm";
import { pushSystemNotification } from "@/lib/notifications";
import type {
  PortfolioSummary,
  PortfolioExposureResponse,
  ExposureItem,
} from "@/types/portfolio";
import type { TrackedPosition, TrackedPositionsListResponse } from "@/types/trackedPositions";
import { Loader2, PieChart, Settings2, Target } from "lucide-react";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, string> = {
  OPEN: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
  PARTIAL_EXIT: "bg-amber-500/20 text-amber-600 dark:text-amber-400",
  CLOSED: "bg-muted text-muted-foreground",
  ABORTED: "bg-red-500/20 text-red-600 dark:text-red-400",
};

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "\u2014";
  return `$${Number(val).toFixed(2)}`;
}

export function PortfolioPage() {
  const { mode } = useDataMode();
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [exposureBySymbol, setExposureBySymbol] = useState<ExposureItem[]>([]);
  const [exposureBySector, setExposureBySector] = useState<ExposureItem[]>([]);
  const [positions, setPositions] = useState<TrackedPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"exposure" | "positions" | "risk">("exposure");

  const fetchAll = useCallback(async () => {
    if (mode !== "LIVE") return;
    setError(null);
    try {
      const [sumRes, expSymRes, expSecRes, posRes] = await Promise.all([
        apiGet<PortfolioSummary>(ENDPOINTS.portfolioSummary),
        apiGet<PortfolioExposureResponse>(ENDPOINTS.portfolioExposure("symbol")),
        apiGet<PortfolioExposureResponse>(ENDPOINTS.portfolioExposure("sector")),
        apiGet<TrackedPositionsListResponse>(ENDPOINTS.trackedPositions),
      ]);
      setSummary(sumRes);
      setExposureBySymbol(expSymRes.items ?? []);
      setExposureBySector(expSecRes.items ?? []);
      setPositions(posRes.positions ?? []);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Portfolio fetch failed",
        message: msg,
      });
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    if (mode === "MOCK") {
      setLoading(false);
      setSummary(null);
      setExposureBySymbol([]);
      setExposureBySector([]);
      setPositions([]);
      setError(null);
      return;
    }
    fetchAll();
  }, [mode, fetchAll]);

  if (mode === "MOCK") {
    return (
      <div className="space-y-6 p-6">
        <PageHeader title="Portfolio" subtext="Portfolio & risk intelligence. Switch to LIVE to use." />
        <EmptyState
          title="Portfolio is LIVE only"
          message="Switch to LIVE mode to view portfolio and risk metrics."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <PageHeader title="Portfolio" subtext="Portfolio & risk intelligence." />
        <div className="flex items-center justify-center gap-2 p-12 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading portfolio...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Portfolio"
        subtext="Portfolio visibility and risk-aware controls. Manual execution only."
      />

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {summary && (
        <section>
          <h2 className="mb-4 flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <PieChart className="h-4 w-4" />
            Summary
          </h2>
          <PortfolioSummaryCards summary={summary} />
        </section>
      )}

      <section>
        <div className="mb-4 flex gap-2">
          {(["exposure", "positions", "risk"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                activeTab === tab
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              {tab === "exposure" ? "Exposure" : tab === "positions" ? "Positions" : "Risk Profile"}
            </button>
          ))}
        </div>

        {activeTab === "exposure" && (
          <div className="space-y-6">
            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">By Symbol</h3>
              <ExposureTable items={exposureBySymbol} groupBy="symbol" />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-medium text-muted-foreground">By Sector</h3>
              <ExposureTable items={exposureBySector} groupBy="sector" />
            </div>
          </div>
        )}

        {activeTab === "positions" && (
          <div className="rounded-lg border border-border overflow-hidden">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Target className="h-4 w-4" />
              Open Positions
            </h3>
            {positions.filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT").length ===
            0 ? (
              <p className="p-6 text-center text-muted-foreground text-sm">
                No open positions. Track positions from the Ticker page.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                    <th className="p-3 font-medium">Symbol</th>
                    <th className="p-3 font-medium">Strategy</th>
                    <th className="p-3 font-medium">Contracts</th>
                    <th className="p-3 font-medium">Status</th>
                    <th className="p-3 font-medium">Lifecycle</th>
                    <th className="p-3 font-medium">Last Directive</th>
                  </tr>
                </thead>
                <tbody>
                  {positions
                    .filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT")
                    .map((p) => (
                      <tr key={p.position_id} className="border-b border-border hover:bg-muted/50">
                        <td className="p-3 font-medium">{p.symbol}</td>
                        <td className="p-3">{p.strategy}</td>
                        <td className="p-3">{p.contracts}</td>
                        <td className="p-3">
                          <span
                            className={cn(
                              "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                              STATUS_STYLES[p.status] ?? "bg-muted text-muted-foreground"
                            )}
                          >
                            {p.status}
                          </span>
                        </td>
                        <td className="p-3 text-muted-foreground">{p.lifecycle_state ?? "\u2014"}</td>
                        <td className="p-3 text-muted-foreground truncate max-w-[180px]">
                          {p.last_directive ?? "\u2014"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {activeTab === "risk" && (
          <div className="rounded-lg border border-border p-6">
            <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Settings2 className="h-4 w-4" />
              Risk Profile
            </h3>
            <RiskProfileForm />
          </div>
        )}
      </section>
    </div>
  );
}
