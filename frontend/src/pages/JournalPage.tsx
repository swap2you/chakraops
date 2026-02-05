/**
 * Trade Journal: list trades, add/edit/delete, fills, PnL, CSV export.
 * LIVE only: uses /api/trades endpoints.
 */
import { useEffect, useState, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { usePolling } from "@/context/PollingContext";
import { apiGet, apiPost, ApiError, getResolvedUrl } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { TradeDetailDrawer } from "@/components/TradeDetailDrawer";
import { pushSystemNotification } from "@/lib/notifications";
import type { JournalTrade, TradesListResponse, TradePayload } from "@/types/journal";
import { cn } from "@/lib/utils";
import { Plus, Download, Loader2 } from "lucide-react";

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "short" });
  } catch {
    return iso;
  }
}

export function JournalPage() {
  const { mode } = useDataMode();
  const polling = usePolling();
  const pollTick = polling?.pollTick ?? 0;
  const [trades, setTrades] = useState<JournalTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTrade, setSelectedTrade] = useState<JournalTrade | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [addTradeOpen, setAddTradeOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  const fetchTrades = useCallback(async () => {
    if (mode !== "LIVE") return;
    setError(null);
    try {
      const res = await apiGet<TradesListResponse>(ENDPOINTS.tradesList);
      setTrades(res.trades ?? []);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
      setTrades([]);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Journal fetch failed",
        message: msg,
      });
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    if (mode === "MOCK") {
      setLoading(false);
      setTrades([]);
      setError(null);
      return;
    }
    if (mode !== "LIVE") return;
    fetchTrades();
  }, [mode, fetchTrades, mode === "LIVE" ? pollTick : 0]);

  const handleExportAllCsv = async () => {
    setExporting(true);
    try {
      const url = getResolvedUrl(ENDPOINTS.tradesExportCsv);
      const res = await fetch(url, { method: "GET" });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "trades_export.csv";
      a.click();
      URL.revokeObjectURL(a.href);
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: "Exported",
        message: "All trades CSV downloaded.",
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Export failed",
        message: msg,
      });
    } finally {
      setExporting(false);
    }
  };

  const openTrade = (t: JournalTrade) => {
    setSelectedTrade(t);
    setDrawerOpen(true);
  };

  const handleTradeUpdated = (updatedTrade?: JournalTrade) => {
    fetchTrades();
    if (updatedTrade) {
      setSelectedTrade(updatedTrade);
    }
  };

  const handleTradeDeleted = () => {
    setSelectedTrade(null);
    setDrawerOpen(false);
    fetchTrades();
  };

  if (mode === "MOCK") {
    return (
      <div className="space-y-6 p-6">
        <PageHeader
          title="Journal"
          subtext="Trade journal and execution tracking. Switch to LIVE to use."
        />
        <EmptyState
          title="Journal is LIVE only"
          message="Switch to LIVE mode to record trades, add fills, and export CSV."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Journal"
        subtext="Track trades, fills, PnL, and export to CSV."
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExportAllCsv}
              disabled={exporting || trades.length === 0}
              className="flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
            >
              {exporting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Export CSV
            </button>
            <button
              type="button"
              onClick={() => setAddTradeOpen(true)}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" />
              Add trade
            </button>
          </div>
        }
      />

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-border bg-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-12 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading…
          </div>
        ) : trades.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            No trades yet. Add a trade to start your journal.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                  <th className="p-3 font-medium">Symbol</th>
                  <th className="p-3 font-medium">Strategy</th>
                  <th className="p-3 font-medium">Opened</th>
                  <th className="p-3 font-medium">Contracts</th>
                  <th className="p-3 font-medium">Remaining</th>
                  <th className="p-3 font-medium">Avg entry</th>
                  <th className="p-3 font-medium">Realized PnL</th>
                  <th className="p-3 font-medium">Next action</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr
                    key={t.trade_id}
                    role="button"
                    tabIndex={0}
                    onClick={() => openTrade(t)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openTrade(t);
                      }
                    }}
                    className={cn(
                      "border-b border-border transition-colors cursor-pointer",
                      "hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset"
                    )}
                  >
                    <td className="p-3 font-medium">{t.symbol}</td>
                    <td className="p-3">{t.strategy}</td>
                    <td className="p-3">{formatDate(t.opened_at)}</td>
                    <td className="p-3">{t.contracts}</td>
                    <td className="p-3">{t.remaining_qty}</td>
                    <td className="p-3">{t.avg_entry != null ? formatCurrency(t.avg_entry) : "—"}</td>
                    <td
                      className={cn(
                        "p-3 font-medium",
                        (t.realized_pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
                      )}
                    >
                      {t.realized_pnl != null ? formatCurrency(t.realized_pnl) : "—"}
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {t.next_action?.message ?? (t.next_action?.action ? t.next_action.action : "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <TradeDetailDrawer
        trade={selectedTrade}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onUpdated={handleTradeUpdated}
        onDeleted={handleTradeDeleted}
      />

      {addTradeOpen && (
        <AddTradeModal
          onClose={() => setAddTradeOpen(false)}
          onAdded={() => {
            setAddTradeOpen(false);
            fetchTrades();
          }}
        />
      )}
    </div>
  );
}

function AddTradeModal({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("CSP");
  const [openedAt, setOpenedAt] = useState(() => new Date().toISOString().slice(0, 16));
  const [expiry, setExpiry] = useState("");
  const [strike, setStrike] = useState("");
  const [contracts, setContracts] = useState(1);
  const [entryMidEst, setEntryMidEst] = useState("");
  const [notes, setNotes] = useState("");
  const [stopLevel, setStopLevel] = useState("");
  const [targetLevels, setTargetLevels] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: TradePayload = {
        symbol: symbol.trim(),
        strategy: strategy.trim(),
        opened_at: new Date(openedAt).toISOString(),
        expiry: expiry.trim() || null,
        strike: strike === "" ? null : parseFloat(strike),
        contracts,
        entry_mid_est: entryMidEst === "" ? null : parseFloat(entryMidEst),
        notes: notes.trim() || null,
        stop_level: stopLevel === "" ? null : parseFloat(stopLevel),
        target_levels: targetLevels
          ? targetLevels
              .split(/[\s,]+/)
              .map((s) => parseFloat(s.trim()))
              .filter((n) => !Number.isNaN(n))
          : [],
      };
      await apiPost<JournalTrade>(ENDPOINTS.tradesCreate, payload);
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: "Trade added",
        message: `${symbol} ${strategy}`,
      });
      onAdded();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Create failed",
        message: msg,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-trade-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-auto rounded-lg border border-border bg-card p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="add-trade-title" className="text-lg font-semibold text-foreground">
          Add trade
        </h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block text-xs text-muted-foreground">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="SPY"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            >
              <option value="CSP">CSP</option>
              <option value="CC">CC</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Opened at</label>
            <input
              type="datetime-local"
              value={openedAt}
              onChange={(e) => setOpenedAt(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-muted-foreground">Expiry</label>
              <input
                type="text"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
                placeholder="YYYY-MM-DD"
                className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground">Strike</label>
              <input
                type="number"
                step="0.01"
                value={strike}
                onChange={(e) => setStrike(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Contracts</label>
            <input
              type="number"
              min={1}
              value={contracts}
              onChange={(e) => setContracts(parseInt(e.target.value, 10) || 1)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Entry mid (est)</label>
            <input
              type="number"
              step="0.01"
              value={entryMidEst}
              onChange={(e) => setEntryMidEst(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Stop level</label>
            <input
              type="number"
              step="0.01"
              value={stopLevel}
              onChange={(e) => setStopLevel(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Target levels (comma-separated)</label>
            <input
              type="text"
              value={targetLevels}
              onChange={(e) => setTargetLevels(e.target.value)}
              placeholder="0.5, 0.25"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-border px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50"
            >
              {saving ? "Saving…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
