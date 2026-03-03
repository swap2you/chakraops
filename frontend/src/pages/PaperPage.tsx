/**
 * R27.0: Paper portfolio — open and closed paper positions. R27.1: Mark + Unrealized P/L for open. Safe labels only.
 */
import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, Button } from "@/components/ui";
import { usePaperPositions, usePaperSummary, type PaperPosition } from "@/api/queries";

const TAB_OPEN = "OPEN";
const TAB_CLOSED = "CLOSED";

function formatMark(p: PaperPosition): string {
  if (p.mark_value == null) return "—";
  const src = p.mark_source || "";
  const age = p.mark_age_sec != null ? ` (${p.mark_age_sec}s)` : "";
  return `${p.mark_value.toFixed(2)} ${src}${age}`.trim();
}

function PositionTable({ positions, showMarkColumns }: { positions: PaperPosition[]; showMarkColumns?: boolean }) {
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
            <th className="text-right py-2 px-2">Open price</th>
            <th className="text-left py-2 px-2">Open date</th>
            {showMarkColumns && (
              <>
                <th className="text-right py-2 px-2" data-testid="paper-th-mark">Mark</th>
                <th className="text-right py-2 px-2" data-testid="paper-th-unrealized">Unrealized P/L</th>
              </>
            )}
            <th className="text-right py-2 px-2">Realized P/L</th>
            <th className="text-left py-2 px-2">Close date</th>
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PaperPage() {
  const [tab, setTab] = useState<"OPEN" | "CLOSED">(TAB_OPEN as "OPEN");
  const month = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  })[0];

  const { data: openData, isLoading: openLoading } = usePaperPositions({ status: TAB_OPEN });
  const { data: closedData, isLoading: closedLoading } = usePaperPositions({ status: TAB_CLOSED });
  const { data: summary } = usePaperSummary(month);

  const openPositions = openData?.positions ?? [];
  const closedPositions = closedData?.positions ?? [];
  const positions = tab === TAB_OPEN ? openPositions : closedPositions;
  const isLoading = tab === TAB_OPEN ? openLoading : closedLoading;

  return (
    <div className="space-y-4">
      <PageHeader title="Paper Portfolio" subtext="Simulated positions and P/L (CSP/CC/SHARES). Manual only." />
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
            <div className="flex gap-2">
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
          <PositionTable positions={positions} showMarkColumns={tab === TAB_OPEN} />
        )}
      </Card>
    </div>
  );
}
