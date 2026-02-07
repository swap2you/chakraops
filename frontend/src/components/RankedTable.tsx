/**
 * Phase 2A: Full Ranked Table — sortable, filterable universe view.
 * Shows all ranked opportunities with sorting and filtering controls.
 * No charts. Tables first. Clarity > beauty.
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

type SortField = "rank" | "band" | "score" | "strategy" | "capital_required" | "capital_pct";
type SortDir = "asc" | "desc";

const BAND_PRIORITY: Record<string, number> = { A: 0, B: 1, C: 2 };

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

export function RankedTable() {
  const [data, setData] = useState<OpportunitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>("rank");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [bandFilter, setBandFilter] = useState<string>("ALL");
  const [strategyFilter, setStrategyFilter] = useState<string>("ALL");
  const [maxCapFilter, setMaxCapFilter] = useState<string>("");
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeOpp, setExecuteOpp] = useState<RankedOpportunity | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      // Fetch up to 50 for the full table
      const res = await apiGet<OpportunitiesResponse>(
        `${ENDPOINTS.dashboardOpportunities}?limit=50`
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

  // Filter and sort
  const filtered = useMemo(() => {
    let items = data?.opportunities ?? [];

    if (bandFilter !== "ALL") {
      items = items.filter((o) => o.band === bandFilter);
    }
    if (strategyFilter !== "ALL") {
      items = items.filter((o) => o.strategy === strategyFilter);
    }
    if (maxCapFilter) {
      const maxPct = parseFloat(maxCapFilter) / 100;
      if (!isNaN(maxPct)) {
        items = items.filter((o) => o.capital_pct == null || o.capital_pct <= maxPct);
      }
    }

    // Sort
    const sorted = [...items].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
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
        default:
          return 0;
      }
    });

    return sorted;
  }, [data, bandFilter, strategyFilter, maxCapFilter, sortField, sortDir]);

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
        {/* Header + filters */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">Ranked Opportunities</h2>
            <span className="text-xs text-muted-foreground">
              {filtered.length} of {data?.total_eligible ?? 0} eligible
            </span>
          </div>

          {/* Filters */}
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

        {/* Table */}
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
                  <th className="px-4 py-2 font-medium">Strike / Expiry</th>
                  <th className="px-4 py-2 font-medium max-w-[180px]">Reason</th>
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
                      <span className={cn(
                        "font-semibold tabular-nums",
                        opp.score >= 78 ? "text-emerald-600 dark:text-emerald-400" :
                        opp.score >= 60 ? "text-blue-600 dark:text-blue-400" :
                        "text-muted-foreground"
                      )}>{opp.score}</span>
                    </td>
                    <td className="px-4 py-2">
                      {opp.capital_required != null
                        ? <span>{formatCurrency(opp.capital_required)}</span>
                        : <span className="text-xs text-muted-foreground">\u2014</span>}
                    </td>
                    <td className="px-4 py-2">
                      {opp.capital_pct != null ? (
                        <span className={cn(
                          "tabular-nums",
                          opp.capital_pct > 0.10 ? "text-amber-600 dark:text-amber-400 font-medium" : ""
                        )}>{formatPct(opp.capital_pct)}</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">\u2014</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">
                      {opp.strike != null && <span>${opp.strike}</span>}
                      {opp.expiry && <span className="ml-1">{opp.expiry}</span>}
                      {opp.strike == null && opp.expiry == null && "\u2014"}
                    </td>
                    <td className="px-4 py-2 max-w-[180px]">
                      <span className="text-xs text-muted-foreground truncate block" title={opp.rank_reason}>
                        {opp.rank_reason}
                      </span>
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1">
                        <Link
                          to={`/analysis?symbol=${opp.symbol}`}
                          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-primary hover:bg-muted"
                        >
                          <Search className="h-3 w-3" />
                        </Link>
                        {!opp.position_open && (
                          <button
                            onClick={() => openExecute(opp)}
                            className="flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20"
                          >
                            <Target className="h-3 w-3" />
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
              message: `${executeOpp.symbol} ${executeOpp.strategy} tracked.`,
            });
            fetchAll();
          }}
        />
      )}
    </>
  );
}
