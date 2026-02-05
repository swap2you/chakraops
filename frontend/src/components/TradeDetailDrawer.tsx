/**
 * Trade Journal: detail drawer for a single trade — fields, fills, add/delete fill, export, edit/delete trade.
 */
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import type { JournalTrade, FillPayload, TradePayload } from "@/types/journal";
import { apiPost, apiPut, apiDelete, ApiError, getResolvedUrl } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { pushSystemNotification } from "@/lib/notifications";
import { X, Plus, Trash2, Download, Pencil, Loader2 } from "lucide-react";

export interface TradeDetailDrawerProps {
  trade: JournalTrade | null;
  open: boolean;
  onClose: () => void;
  /** Call when trade or fills changed; pass updated trade if available so parent can refresh selection */
  onUpdated: (updatedTrade?: JournalTrade) => void;
  onDeleted: () => void;
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function TradeDetailDrawer({
  trade,
  open,
  onClose,
  onUpdated,
  onDeleted,
}: TradeDetailDrawerProps) {
  const [addFillOpen, setAddFillOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingFillId, setDeletingFillId] = useState<string | null>(null);

  if (!trade) return null;

  const handleExportCsv = async () => {
    try {
      const url = getResolvedUrl(ENDPOINTS.tradeExportCsv(trade.trade_id));
      const res = await fetch(url, { method: "GET" });
      if (!res.ok) throw new Error(`${res.status}`);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `trade_${trade.trade_id}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      pushSystemNotification({ source: "system", severity: "info", title: "Exported", message: "Trade CSV downloaded." });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      pushSystemNotification({ source: "system", severity: "error", title: "Export failed", message: msg });
    }
  };

  const handleDeleteTrade = async () => {
    if (!confirm(`Delete trade ${trade.symbol} (${trade.trade_id})?`)) return;
    setSaving(true);
    try {
      await apiDelete<{ deleted: boolean }>(ENDPOINTS.tradeDelete(trade.trade_id));
      pushSystemNotification({ source: "system", severity: "info", title: "Deleted", message: "Trade removed." });
      onDeleted();
      onClose();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      pushSystemNotification({ source: "system", severity: "error", title: "Delete failed", message: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteFill = async (fillId: string) => {
    if (!confirm("Remove this fill?")) return;
    setDeletingFillId(fillId);
    try {
      const updated = await apiDelete<JournalTrade>(ENDPOINTS.tradeFillDelete(trade.trade_id, fillId));
      pushSystemNotification({ source: "system", severity: "info", title: "Fill removed", message: "" });
      onUpdated(updated);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      pushSystemNotification({ source: "system", severity: "error", title: "Delete fill failed", message: msg });
    } finally {
      setDeletingFillId(null);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            role="presentation"
            className="fixed inset-0 z-40 bg-black/50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />
          <motion.aside
            className="fixed right-0 top-0 z-50 h-full w-full max-w-lg border-l border-border bg-card shadow-xl"
            role="dialog"
            aria-label="Trade detail"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
          >
            <div className="flex h-full flex-col p-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h2 className="text-lg font-semibold text-foreground">
                  {trade.symbol} — {trade.strategy}
                </h2>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setEditOpen(true)}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label="Edit trade"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={handleExportCsv}
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label="Export CSV"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>

              <div className="mt-4 flex-1 space-y-4 overflow-y-auto text-sm">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-muted-foreground">Trade ID</p>
                    <p className="font-mono text-xs text-foreground">{trade.trade_id}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Opened</p>
                    <p className="text-foreground">{formatDate(trade.opened_at)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Expiry</p>
                    <p className="text-foreground">{trade.expiry ?? "—"}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Strike</p>
                    <p className="text-foreground">{trade.strike != null ? trade.strike : "—"}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Contracts</p>
                    <p className="text-foreground">{trade.contracts}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Remaining</p>
                    <p className="text-foreground">{trade.remaining_qty}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Avg entry</p>
                    <p className="text-foreground">{trade.avg_entry != null ? formatCurrency(trade.avg_entry) : "—"}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Avg exit</p>
                    <p className="text-foreground">{trade.avg_exit != null ? formatCurrency(trade.avg_exit) : "—"}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Realized PnL</p>
                    <p className={`font-medium ${(trade.realized_pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                      {trade.realized_pnl != null ? formatCurrency(trade.realized_pnl) : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Stop / Targets</p>
                    <p className="text-foreground">
                      {trade.stop_level != null ? `Stop ${trade.stop_level}` : "—"}
                      {trade.target_levels?.length ? ` · ${trade.target_levels.join(", ")}` : ""}
                    </p>
                  </div>
                  {trade.next_action && (
                    <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3">
                      <p className="text-xs font-medium text-amber-700 dark:text-amber-400">Next action (EOD rules)</p>
                      <p className="mt-1 text-sm text-foreground">{trade.next_action.message}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{trade.next_action.action}</p>
                    </div>
                  )}
                </div>
                {trade.notes && (
                  <div>
                    <p className="text-muted-foreground">Notes</p>
                    <p className="text-foreground">{trade.notes}</p>
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium text-foreground">Fills</h3>
                    <button
                      type="button"
                      onClick={() => setAddFillOpen(true)}
                      className="flex items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-1 text-sm hover:bg-muted"
                    >
                      <Plus className="h-3.5 w-3.5" /> Add fill
                    </button>
                  </div>
                  {trade.fills.length === 0 ? (
                    <p className="mt-2 text-muted-foreground">No fills yet.</p>
                  ) : (
                    <div className="mt-2 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b border-border text-muted-foreground">
                            <th className="p-2 text-left">Date</th>
                            <th className="p-2 text-left">Action</th>
                            <th className="p-2 text-right">Qty</th>
                            <th className="p-2 text-right">Price</th>
                            <th className="p-2 text-right">Fees</th>
                            <th className="p-2 w-8" />
                          </tr>
                        </thead>
                        <tbody>
                          {trade.fills.map((f) => (
                            <tr key={f.fill_id} className="border-b border-border/50">
                              <td className="p-2">{formatDate(f.filled_at)}</td>
                              <td className="p-2">{f.action}</td>
                              <td className="p-2 text-right">{f.qty}</td>
                              <td className="p-2 text-right">{formatCurrency(f.price)}</td>
                              <td className="p-2 text-right">{formatCurrency(f.fees)}</td>
                              <td className="p-2">
                                <button
                                  type="button"
                                  onClick={() => handleDeleteFill(f.fill_id)}
                                  disabled={deletingFillId === f.fill_id}
                                  className="rounded p-1 text-muted-foreground hover:bg-destructive/20 hover:text-destructive disabled:opacity-50"
                                  aria-label="Remove fill"
                                >
                                  {deletingFillId === f.fill_id ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Trash2 className="h-3.5 w-3.5" />
                                  )}
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div className="border-t border-border pt-3">
                  <button
                    type="button"
                    onClick={handleDeleteTrade}
                    disabled={saving}
                    className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/20 disabled:opacity-50"
                  >
                    {saving ? "Deleting…" : "Delete trade"}
                  </button>
                </div>
              </div>
            </div>
          </motion.aside>

          {addFillOpen && (
            <AddFillModal
              tradeId={trade.trade_id}
              onClose={() => setAddFillOpen(false)}
              onAdded={(updatedTrade) => {
                setAddFillOpen(false);
                onUpdated(updatedTrade);
              }}
            />
          )}
          {editOpen && (
            <EditTradeModal
              trade={trade}
              onClose={() => setEditOpen(false)}
              onSaved={(updatedTrade) => {
                setEditOpen(false);
                onUpdated(updatedTrade);
              }}
            />
          )}
        </>
      )}
    </AnimatePresence>
  );
}

function AddFillModal({
  tradeId,
  onClose,
  onAdded,
}: {
  tradeId: string;
  onClose: () => void;
  onAdded: (updatedTrade: JournalTrade) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [filledAt, setFilledAt] = useState(() => new Date().toISOString().slice(0, 16));
  const [action, setAction] = useState<FillPayload["action"]>("CLOSE");
  const [qty, setQty] = useState(1);
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const priceNum = parseFloat(price);
    if (Number.isNaN(priceNum)) return;
    setSaving(true);
    try {
      const payload: FillPayload = {
        filled_at: new Date(filledAt).toISOString(),
        action,
        qty,
        price: priceNum,
        fees: parseFloat(fees) || 0,
      };
      const updated = await apiPost<JournalTrade>(ENDPOINTS.tradeFillsCreate(tradeId), payload);
      pushSystemNotification({ source: "system", severity: "info", title: "Fill added", message: "" });
      onAdded(updated);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
      pushSystemNotification({ source: "system", severity: "error", title: "Add fill failed", message: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-fill-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-full max-w-sm rounded-lg border border-border bg-card p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="add-fill-title" className="text-lg font-semibold text-foreground">
          Add fill
        </h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block text-xs text-muted-foreground">Date & time</label>
            <input
              type="datetime-local"
              value={filledAt}
              onChange={(e) => setFilledAt(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Action</label>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as FillPayload["action"])}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            >
              <option value="OPEN">OPEN</option>
              <option value="CLOSE">CLOSE</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Qty</label>
            <input
              type="number"
              min={1}
              value={qty}
              onChange={(e) => setQty(parseInt(e.target.value, 10) || 1)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Price</label>
            <input
              type="number"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Fees</label>
            <input
              type="number"
              step="0.01"
              value={fees}
              onChange={(e) => setFees(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50">
              {saving ? "Saving…" : "Add"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditTradeModal({
  trade,
  onClose,
  onSaved,
}: {
  trade: JournalTrade;
  onClose: () => void;
  onSaved: (updatedTrade: JournalTrade) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [symbol, setSymbol] = useState(trade.symbol);
  const [strategy, setStrategy] = useState(trade.strategy);
  const [openedAt, setOpenedAt] = useState(trade.opened_at.slice(0, 16));
  const [expiry, setExpiry] = useState(trade.expiry != null ? String(trade.expiry) : "");
  const [strike, setStrike] = useState(trade.strike != null ? String(trade.strike) : "");
  const [contracts, setContracts] = useState(trade.contracts);
  const [entryMidEst, setEntryMidEst] = useState(trade.entry_mid_est != null ? String(trade.entry_mid_est) : "");
  const [notes, setNotes] = useState(trade.notes ?? "");
  const [stopLevel, setStopLevel] = useState(trade.stop_level != null ? String(trade.stop_level) : "");
  const [targetLevels, setTargetLevels] = useState(trade.target_levels?.join(", ") ?? "");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload: TradePayload = {
        symbol,
        strategy,
        opened_at: new Date(openedAt).toISOString(),
        expiry: expiry || null,
        strike: strike === "" ? null : parseFloat(strike),
        contracts,
        entry_mid_est: entryMidEst === "" ? null : parseFloat(entryMidEst),
        notes: notes || null,
        stop_level: stopLevel === "" ? null : parseFloat(stopLevel),
        target_levels: targetLevels
          ? targetLevels
              .split(/[\s,]+/)
              .map((s) => parseFloat(s.trim()))
              .filter((n) => !Number.isNaN(n))
          : [],
      };
      const updated = await apiPut<JournalTrade>(ENDPOINTS.tradeUpdate(trade.trade_id), payload);
      pushSystemNotification({ source: "system", severity: "info", title: "Trade updated", message: "" });
      onSaved(updated);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
      pushSystemNotification({ source: "system", severity: "error", title: "Update failed", message: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-trade-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-auto rounded-lg border border-border bg-card p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="edit-trade-title" className="text-lg font-semibold text-foreground">
          Edit trade
        </h2>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block text-xs text-muted-foreground">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground">Strategy</label>
            <input
              type="text"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              placeholder="CSP, CC, …"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              required
            />
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
              min={0}
              value={contracts}
              onChange={(e) => setContracts(parseInt(e.target.value, 10) || 0)}
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
            <button type="button" onClick={onClose} className="rounded-md border border-border px-3 py-1.5 text-sm">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-50">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
