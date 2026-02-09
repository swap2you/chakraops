/**
 * Phase 5: Ranked Universe Table — sortable, filterable, persisted.
 * Fully sortable headers; filters + sort persist in localStorage.
 * Row actions: View Ticker, Execute (Manual).
 * UNKNOWN states shown explicitly.
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
import { Loader2, Search, Target, ArrowUpDown, ArrowUp, ArrowDown, Filter, TrendingUp } from "lucide-react";

const STORAGE_KEY = "chakraops-ranked-universe";

type SortField = "rank" | "band" | "score" | "strategy" | "capital_required" | "capital_pct" | "risk_status";
type SortDir = "asc" | "desc";

const BAND_PRIORITY: Record<string, number> = { A: 0, B: 1, C: 2 };
const RISK_PRIORITY: Record<string, number> = { OK: 0, WARN: 1, BLOCKED: 2, UNKNOWN: 3 };

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

function loadPersisted(): { sortField: SortField; sortDir: SortDir; bandFilter: string; strategyFilter: string; riskFilter: string; maxCapFilter: string } {
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (!s) return getDefaults();
    const parsed = JSON.parse(s);
    return {
      sortField: typeof parsed.sortField === "string" ? parsed.sortField : "rank",
      sortDir: parsed.sortDir === "desc" ? "desc" : "asc",
      bandFilter: typeof parsed.bandFilter === "string" ? parsed.bandFilter : "ALL",
      strategyFilter: typeof parsed.strategyFilter === "string" ? parsed.strategyFilter : "ALL",
      riskFilter: typeof parsed.riskFilter === "string" ? parsed.riskFilter : "ALL",
      maxCapFilter: typeof parsed.maxCapFilter === "string" ? parsed.maxCapFilter : "",
    };
  } catch {
    return getDefaults();
  }
}

function getDefaults() {
  return {
    sortField: "rank" as SortField,
    sortDir: "asc" as SortDir,
    bandFilter: "ALL",
    strategyFilter: "ALL",
    riskFilter: "ALL",
    maxCapFilter: "",
  };
}

function savePersisted(state: ReturnType<typeof loadPersisted>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

function usePersistedFilters() {
  const [filters] = useState(() => loadPersisted());
  return filters;
}

export function RankedTable() {
  const initialFilters = usePersistedFilters();
  const [data, setData] = useState<OpportunitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>(initialFilters.sortField);
  const [sortDir, setSortDir] = useState<SortDir>(initialFilters.sortDir);
  const [bandFilter, setBandFilter] = useState<string>(initialFilters.bandFilter);
  const [strategyFilter, setStrategyFilter] = useState<string>(initialFilters.strategyFilter);
  const [riskFilter, setRiskFilter] = useState<string>(initialFilters.riskFilter);
  const [maxCapFilter, setMaxCapFilter] = useState<string>(initialFilters.maxCapFilter);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeOpp, setExecuteOpp] = useState<RankedOpportunity | null>(null);

  const persist = useCallback(() => {
    savePersisted({ sortField, sortDir, bandFilter, strategyFilter, riskFilter, maxCapFilter });
  }, [sortField, sortDir, bandFilter, strategyFilter, riskFilter, maxCapFilter]);

  useEffect(() => {
    persist();
  }, [persist]);

  const fetchAll = useCallback(async () => {
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
    fetchAll();
  }, [fetchAll]);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "score" ? "desc" : "asc");
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 opacity-30" />;
    return sortDir === "asc"
      ? <ArrowUp className="h-3 w-3 text-primary" />
      : <ArrowDown className="h-3 w-3 text-primary" />;
  };

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

    const dir = sortDir === "asc" ? 1 : -1;
    return [...items].sort((a, b) => {
      switch (sortField) {
        case "rank":
          return (a.rank - b.rank) * dir;
        case "band":
          return ((BAND_PRIORITY[a.band] ?? 99) - (BAND_PRIORITY[b.band] ?? 99)) * dir;
        case "score":
          return (a.score - b.score) * dir;
        case "strategy":
          return a.strategy.localeCompare(b.strategy) * dir;
        case "capital_required":
          return ((a.capital_required ?? 0) - (b.capital_required ?? 0)) * dir;
        case "capital_pct":
          return ((a.capital_pct ?? 0) - (b.capital_pct ?? 0)) * dir;
        case "risk_status": {
          const ra = RISK_PRIORITY[a.risk_status ?? "UNKNOWN"] ?? 99;
          const rb = RISK_PRIORITY[b.risk_status ?? "UNKNOWN"] ?? 99;
          return (ra - rb) * dir;
        }
        default:
          return 0;
      }
    });
  }, [data, bandFilter, strategyFilter, riskFilter, maxCapFilter, sortField, sortDir]);

  const openExecute = (opp: RankedOpportunity) => {
    setExecuteOpp(opp);
    setExecuteModalOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading ranked universe...
      </div>
    );
  }

  if (error) {
    return <p className="py-4 text-sm text-destructive">{error}</p>;
  }

  return (
    <>
      <section className="rounded-lg border border-border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">Ranked Universe</h2>
            <span className="text-xs text-muted-foreground">
              {filtered.length} of {data?.total_eligible ?? 0} eligible
            </span>
          </div>

          <div className="flex items-center gap-2">
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
              className="w-20 rounded border border-border bg-background px-2 py-1 text-xs"
              min="1"
              max="100"
              aria-label="Max capital percentage"
            />
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground text-sm">
            No opportunities match the current filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/20 text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("rank")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      # <SortIcon field="rank" />
                    </button>
                  </th>
                  <th className="px-4 py-2 font-medium">Symbol</th>
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("strategy")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      Strategy <SortIcon field="strategy" />
                    </button>
                  </th>
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("band")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      Band <SortIcon field="band" />
                    </button>
                  </th>
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("risk_status")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      Risk <SortIcon field="risk_status" />
                    </button>
                  </th>
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("score")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      Score <SortIcon field="score" />
                    </button>
                  </th>
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("capital_required")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      Capital <SortIcon field="capital_required" />
                    </button>
                  </th>
                  <th className="px-4 py-2">
                    <button onClick={() => toggleSort("capital_pct")} className="flex items-center gap-1 font-medium hover:text-foreground">
                      Cap % <SortIcon field="capital_pct" />
                    </button>
                  </th>
                  <th className="px-4 py-2 font-medium">Reason</th>
                  <th className="px-4 py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((opp) => (
                  <tr
                    key={`${opp.symbol}-${opp.strategy}`}
                    className="border-b border-border/50 last:border-0 transition-colors hover:bg-muted/30"
                  >
                    <td className="px-4 py-2">
                      <span className="text-xs font-bold text-muted-foreground">{opp.rank}</span>
                    </td>
                    <td className="px-4 py-2">
                      <span className="font-semibold text-foreground">{opp.symbol}</span>
                      {opp.price != null && (
                        <span className="ml-1 text-xs text-muted-foreground">${opp.price.toFixed(2)}</span>
                      )}
                      {opp.price == null && (
                        <span className="ml-1 text-xs text-muted-foreground">(UNKNOWN)</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                        STRATEGY_STYLES[opp.strategy] ?? "bg-muted text-muted-foreground"
                      )}>{opp.strategy}</span>
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn(
                        "inline-flex h-6 w-6 items-center justify-center rounded border text-xs font-bold",
                        BAND_STYLES[opp.band] ?? BAND_STYLES.C
                      )}>{opp.band}</span>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={cn(
                          "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                          opp.risk_status === "OK" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                          opp.risk_status === "WARN" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
                          opp.risk_status === "BLOCKED" && "bg-red-500/20 text-red-600 dark:text-red-400",
                          !opp.risk_status && "bg-muted text-muted-foreground"
                        )}
                        title={opp.risk_status === "BLOCKED" ? (opp.risk_reasons ?? []).join("; ") : opp.risk_status == null ? "Risk status not available" : undefined}
                      >
                        {riskLabel(opp.risk_status)}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn(
                        "font-semibold tabular-nums",
                        opp.score >= 78 ? "text-emerald-600 dark:text-emerald-400" :
                        opp.score >= 60 ? "text-blue-600 dark:text-blue-400" :
                        "text-muted-foreground"
                      )}>{opp.score}</span>
                    </td>
                    <td className="px-4 py-2">
                      <span className={opp.capital_required != null ? "" : "text-muted-foreground"}>
                        {formatCurrency(opp.capital_required)}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <span className={cn(
                        opp.capital_pct != null ? "" : "text-muted-foreground",
                        opp.capital_pct != null && opp.capital_pct > 0.10 ? "text-amber-600 dark:text-amber-400 font-medium" : ""
                      )}>{formatPct(opp.capital_pct)}</span>
                    </td>
                    <td className="px-4 py-2 max-w-[180px]">
                      <span className="text-xs text-muted-foreground truncate block" title={opp.rank_reason || "—"}>
                        {opp.rank_reason || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2">
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
            fetchAll();
          }}
        />
      )}
    </>
  );
}
