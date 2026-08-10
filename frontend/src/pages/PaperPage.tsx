/**
 * R27.0: Paper portfolio — open and closed paper positions. R27.1: Mark + Unrealized P/L for open. R27.2: Close modal, filters, Entry/As-of. Safe labels only.
 */
import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, Button } from "@/components/ui";
import { usePaperPositions, usePaperSummary, usePaperClose, type PaperPosition } from "@/api/queries";
import { pushSystemNotification } from "@/lib/notifications";

const TAB_OPEN = "OPEN";
const TAB_CLOSED = "CLOSED";

function formatMark(p: PaperPosition): string {
  if (p.mark_value == null) return "—";
  const src = p.mark_source || "";
  const age = p.mark_age_sec != null ? ` (${p.mark_age_sec}s)` : "";
  return `${p.mark_value.toFixed(2)} ${src}${age}`.trim();
}

function formatAsOf(p: PaperPosition): string {
  if (p.quote_ts) return (p.quote_ts as string).slice(0, 19).replace("T", " ");
  return "—";
}

function PositionTable({
  positions,
  showMarkColumns,
  onClose,
}: {
  positions: PaperPosition[];
  showMarkColumns?: boolean;
  onClose?: (p: PaperPosition) => void;
}) {
  if (positions.length === 0) {
    return <p className="text-sm text-zinc-500">No positions.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-700">
            <th className="text-left py-2 px-2">Symbol</th>
            <th className="text-left py-2 px-2">Strategy</th>
            <th className="text-right py-2 px-2">Qty</th>
            <th className="text-right py-2 px-2" data-testid="paper-th-entry">Entry</th>
            <th className="text-left py-2 px-2">Open date</th>
            {showMarkColumns && (
              <>
                <th className="text-right py-2 px-2" data-testid="paper-th-mark">Mark</th>
                <th className="text-right py-2 px-2" data-testid="paper-th-unrealized">Unrealized P/L</th>
                <th className="text-left py-2 px-2" data-testid="paper-th-asof">As-of</th>
              </>
            )}
            <th className="text-right py-2 px-2">Realized P/L</th>
            <th className="text-left py-2 px-2">Close date</th>
            {showMarkColumns && onClose && <th className="w-20 py-2 px-2" />}
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr key={p.id} className="border-b border-zinc-100 dark:border-zinc-800" data-testid="paper-position-row">
              <td className="py-2 px-2 font-mono">{p.symbol}</td>
              <td className="py-2 px-2">{p.strategy}</td>
              <td className="py-2 px-2 text-right">{p.qty}</td>
              <td className="py-2 px-2 text-right">{p.open_price}</td>
              <td className="py-2 px-2 text-zinc-600 dark:text-zinc-400">{(p.open_ts || "").slice(0, 10)}</td>
              {showMarkColumns && (
                <>
                  <td className="py-2 px-2 text-right text-zinc-600 dark:text-zinc-400" data-testid="paper-cell-mark">{formatMark(p)}</td>
                  <td className="py-2 px-2 text-right" data-testid="paper-cell-unrealized">
                    {p.unrealized_pl_usd != null ? (
                      <span className={p.unrealized_pl_usd >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                        {p.unrealized_pl_usd.toFixed(2)}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="py-2 px-2 text-zinc-500 dark:text-zinc-500 text-xs" data-testid="paper-cell-asof">{formatAsOf(p)}</td>
                </>
              )}
              <td className="py-2 px-2 text-right">
                {p.realized_pl != null ? (
                  <span className={p.realized_pl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    {p.realized_pl.toFixed(2)}
                  </span>
                ) : "—"}
              </td>
              <td className="py-2 px-2 text-zinc-600 dark:text-zinc-400">{(p.close_ts || "").slice(0, 10) || "—"}</td>
              {showMarkColumns && onClose && (
                <td className="py-2 px-2">
                  <Button variant="outline" size="sm" onClick={() => onClose(p)} data-testid="paper-close-btn">
                    Close
                  </Button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PaperPage() {
  const [tab, setTab] = useState<"OPEN" | "CLOSED">(TAB_OPEN as "OPEN");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");
  const [closeModalPosition, setCloseModalPosition] = useState<PaperPosition | null>(null);
  const month = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  })[0];

  const positionParams = {
    status: tab === TAB_OPEN ? TAB_OPEN : undefined,
    symbol: symbolFilter.trim() || undefined,
    strategy: strategyFilter.trim() || undefined,
    include_marks: true,
  };
  const openParams = { ...positionParams, status: TAB_OPEN };
  const closedParams = { ...positionParams, status: TAB_CLOSED };
  const { data: openData, isLoading: openLoading, refetch: refetchOpen } = usePaperPositions(openParams);
  const { data: closedData, isLoading: closedLoading } = usePaperPositions(closedParams);
  const { data: summary } = usePaperSummary(month);
  const closeMutation = usePaperClose();

  const openPositions = openData?.positions ?? [];
  const closedPositions = closedData?.positions ?? [];
  const positions = tab === TAB_OPEN ? openPositions : closedPositions;
  const isLoading = tab === TAB_OPEN ? openLoading : closedLoading;

  const handleCloseSubmit = async (payload: { close_price?: number; close_premium?: number; close_fees?: number; ts?: string }) => {
    if (!closeModalPosition) return;
    try {
      await closeMutation.mutateAsync({
        position_id: closeModalPosition.id,
        ...(closeModalPosition.strategy === "SHARES" ? { close_price: payload.close_price } : { close_premium: payload.close_premium }),
        close_fees: payload.close_fees ?? 0,
        ts: payload.ts || undefined,
      });
      pushSystemNotification({ source: "system", severity: "info", title: "Paper position closed", message: `${closeModalPosition.symbol} closed.` });
      setCloseModalPosition(null);
    } catch (e) {
      pushSystemNotification({ source: "system", severity: "error", title: "Close failed", message: e instanceof Error ? e.message : "Unknown error" });
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Paper Portfolio"
        subtext="SIMULATION — isolated from the live portfolio. Simulated positions and P/L (CSP/CC/SHARES). Manual only."
      />
      <div
        className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-100"
        data-testid="paper-simulation-banner"
      >
        <strong>SIMULATION</strong> — Paper results are not live account balances and do not update Portfolio cash or holdings.
      </div>
      {summary && (
        <Card data-testid="paper-summary-card">
          <CardHeader title={`Summary — ${month}`} />
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            Realized P/L: {summary.realized_pl?.toFixed(2) ?? "0.00"} · Trades: {summary.trade_count ?? 0} · Win rate: {summary.win_rate ?? 0}% · Fees: {summary.fees_total ?? 0}
          </div>
        </Card>
      )}
      <Card data-testid="paper-positions-card">
        <CardHeader
          title="Positions"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                placeholder="Symbol"
                value={symbolFilter}
                onChange={(e) => setSymbolFilter(e.target.value)}
                className="w-24 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
                data-testid="paper-filter-symbol"
              />
              <select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
                className="rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
                data-testid="paper-filter-strategy"
              >
                <option value="">All</option>
                <option value="SHARES">SHARES</option>
                <option value="CSP">CSP</option>
                <option value="CC">CC</option>
              </select>
              {tab === TAB_OPEN && (
                <Button variant="outline" size="sm" onClick={() => refetchOpen()} data-testid="paper-refresh-marks">
                  Refresh marks
                </Button>
              )}
              <Button
                variant={tab === TAB_OPEN ? "primary" : "secondary"}
                size="sm"
                onClick={() => setTab(TAB_OPEN as "OPEN")}
                data-testid="paper-tab-open"
              >
                Open
              </Button>
              <Button
                variant={tab === TAB_CLOSED ? "primary" : "secondary"}
                size="sm"
                onClick={() => setTab(TAB_CLOSED as "CLOSED")}
                data-testid="paper-tab-closed"
              >
                Closed
              </Button>
            </div>
          }
        />
        {isLoading ? (
          <p className="text-sm text-zinc-500 p-2">Loading…</p>
        ) : (
          <PositionTable
            positions={positions}
            showMarkColumns={tab === TAB_OPEN}
            onClose={tab === TAB_OPEN ? (p) => setCloseModalPosition(p) : undefined}
          />
        )}
      </Card>
      {closeModalPosition && (
        <ClosePositionModal
          position={closeModalPosition}
          onClose={() => setCloseModalPosition(null)}
          onSubmit={handleCloseSubmit}
          isPending={closeMutation.isPending}
        />
      )}
    </div>
  );
}

function ClosePositionModal({
  position,
  onClose,
  onSubmit,
  isPending,
}: {
  position: PaperPosition;
  onClose: () => void;
  onSubmit: (p: { close_price?: number; close_premium?: number; close_fees?: number; ts?: string }) => void;
  isPending: boolean;
}) {
  const isShares = (position.strategy || "").toUpperCase() === "SHARES";
  const [closePrice, setClosePrice] = useState("");
  const [closeFees, setCloseFees] = useState("0");
  const [ts, setTs] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isShares) {
      const n = parseFloat(closePrice);
      if (Number.isNaN(n)) return;
      onSubmit({ close_price: n, close_fees: parseFloat(closeFees) || 0, ts: ts.trim() || undefined });
    } else {
      const n = parseFloat(closePrice);
      if (Number.isNaN(n)) return;
      onSubmit({ close_premium: n, close_fees: parseFloat(closeFees) || 0, ts: ts.trim() || undefined });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" data-testid="paper-close-modal" role="dialog" aria-modal="true">
      <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 w-full max-w-sm">
        <h3 className="text-sm font-medium mb-3">Close paper position — {position.symbol} ({position.strategy})</h3>
        <form onSubmit={handleSubmit} className="space-y-3">
          <label className="block text-sm text-zinc-600 dark:text-zinc-400">
            {isShares ? "Close price" : "Close premium"}
            <input
              type="number"
              step="any"
              required
              value={closePrice}
              onChange={(e) => setClosePrice(e.target.value)}
              className="ml-2 w-24 rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-800"
              data-testid="paper-close-price-input"
            />
          </label>
          <label className="block text-sm text-zinc-600 dark:text-zinc-400">
            Fees
            <input
              type="number"
              step="any"
              value={closeFees}
              onChange={(e) => setCloseFees(e.target.value)}
              className="ml-2 w-20 rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-800"
            />
          </label>
          <label className="block text-sm text-zinc-600 dark:text-zinc-400">
            Close time (optional)
            <input
              type="text"
              placeholder="ISO or leave blank"
              value={ts}
              onChange={(e) => setTs(e.target.value)}
              className="ml-2 w-full rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-600 dark:bg-zinc-800"
            />
          </label>
          <div className="flex gap-2 justify-end pt-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button type="submit" size="sm" disabled={isPending} data-testid="paper-close-submit">{isPending ? "Closing…" : "Close position"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
