/**
 * R27.5: Journal-driven backtest replay. Date range, live/paper/mixed; summary + trades; download JSON/CSV.
 * Safe labels only (no FAIL/WARN).
 */
import { useState } from "react";
import {
  useBacktestRuns,
  useBacktestRun,
  downloadBacktestFile,
} from "@/api/queries";
import type { BacktestRunResponse } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import {
  Card,
  CardHeader,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  EmptyState,
  Button,
} from "@/components/ui";

function formatCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);
}

function dateRangeLastDays(days: number): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

const MODE_LABELS: Record<string, string> = {
  live: "Live only",
  paper: "Paper only",
  mixed: "Mixed",
};

export function BacktestPage() {
  const { start: defaultStart, end: defaultEnd } = dateRangeLastDays(7);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [includePaper, setIncludePaper] = useState(false);
  const [paperOnly, setPaperOnly] = useState(false);
  const [lastResult, setLastResult] = useState<BacktestRunResponse | null>(null);

  const runMutation = useBacktestRun();
  const { data: runsData } = useBacktestRuns(20, 0);
  const runs = runsData?.runs ?? [];

  const handleRun = () => {
    runMutation.mutate(
      { start_date: startDate, end_date: endDate, include_paper: includePaper, paper_only: paperOnly },
      {
        onSuccess: (data) => {
          setLastResult(data);
        },
      }
    );
  };

  const metrics = lastResult?.metrics;
  const trades = lastResult?.trades ?? [];
  const modeLabel = metrics ? MODE_LABELS[metrics.mode] ?? metrics.mode : "";

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Backtest"
        subtext="Replay journal entries for a date range. Deterministic summary and trades."
      />

      <Card>
        <CardHeader title="Run backtest" />
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
            Start date
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value.slice(0, 10))}
              className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
              data-testid="backtest-start-date"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
            End date
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value.slice(0, 10))}
              className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
              data-testid="backtest-end-date"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400" data-testid="backtest-include-paper">
            <input
              type="checkbox"
              checked={includePaper}
              onChange={(e) => {
                setIncludePaper(e.target.checked);
                if (!e.target.checked) setPaperOnly(false);
              }}
              className="rounded border-zinc-300 dark:border-zinc-600"
            />
            Include paper
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400" data-testid="backtest-paper-only">
            <input
              type="checkbox"
              checked={paperOnly}
              onChange={(e) => setPaperOnly(e.target.checked)}
              disabled={!includePaper}
              className="rounded border-zinc-300 dark:border-zinc-600 disabled:opacity-50"
            />
            Paper only
          </label>
          <Button
            size="sm"
            onClick={handleRun}
            disabled={runMutation.isPending || !startDate || !endDate}
            data-testid="backtest-run-btn"
          >
            {runMutation.isPending ? "Running…" : "Run"}
          </Button>
        </div>
      </Card>

      {runMutation.isError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {runMutation.error instanceof Error ? runMutation.error.message : "Run failed"}
        </p>
      )}

      {metrics && (
        <>
          <Card data-testid="backtest-results">
            <CardHeader title="Results" description={`Mode: ${modeLabel}`} />
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4 lg:grid-cols-6">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Realized P/L</span>
                <span className={`font-mono font-medium ${(metrics.total_realized_pl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                  {formatCurrency(metrics.total_realized_pl)}
                </span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Fees</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{formatCurrency(metrics.total_fees)}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Trades</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{metrics.trade_count}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Win rate</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{metrics.win_rate != null ? `${metrics.win_rate}%` : "—"}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Drawdown (proxy)</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">
                  {metrics.max_drawdown_proxy != null ? formatCurrency(metrics.max_drawdown_proxy) : "—"}
                </span>
              </div>
            </div>
            {lastResult?.run_id && (
              <div className="mt-4 flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => downloadBacktestFile(lastResult.run_id, "summary_json")}
                  data-testid="backtest-download-json"
                >
                  Download JSON
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => downloadBacktestFile(lastResult.run_id, "trades_csv")}
                  data-testid="backtest-download-csv"
                >
                  Download CSV
                </Button>
              </div>
            )}
          </Card>

          {metrics.by_strategy && Object.keys(metrics.by_strategy).length > 0 && (
            <Card>
              <CardHeader title="By strategy" />
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Strategy</TableHead>
                    <TableHead className="text-right">Realized P/L</TableHead>
                    <TableHead className="text-right">Trades</TableHead>
                    <TableHead className="text-right">Wins</TableHead>
                    <TableHead className="text-right">Losses</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(metrics.by_strategy).map(([strat, v]) => (
                    <TableRow key={strat}>
                      <TableCell className="font-medium">{strat}</TableCell>
                      <TableCell className="text-right font-mono">{formatCurrency(v.realized_pl)}</TableCell>
                      <TableCell className="text-right font-mono">{v.trades}</TableCell>
                      <TableCell className="text-right font-mono">{v.wins}</TableCell>
                      <TableCell className="text-right font-mono">{v.losses}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}

          {trades.length > 0 && (
            <Card>
              <CardHeader title="Trades" />
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Strategy</TableHead>
                      <TableHead>Action</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">Price</TableHead>
                      <TableHead className="text-right">Premium</TableHead>
                      <TableHead className="text-right">Fees</TableHead>
                      <TableHead className="text-right">Realized P/L</TableHead>
                      <TableHead>Paper</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {trades.slice(0, 200).map((t, i) => (
                      <TableRow key={i}>
                        <TableCell className="text-sm">{t.trade_date ?? "—"}</TableCell>
                        <TableCell className="font-mono">{t.symbol ?? "—"}</TableCell>
                        <TableCell>{t.strategy ?? "—"}</TableCell>
                        <TableCell>{t.action ?? "—"}</TableCell>
                        <TableCell className="text-right font-mono">{t.qty ?? "—"}</TableCell>
                        <TableCell className="text-right font-mono">{t.price != null ? formatCurrency(t.price) : "—"}</TableCell>
                        <TableCell className="text-right font-mono">{t.premium != null ? formatCurrency(t.premium) : "—"}</TableCell>
                        <TableCell className="text-right font-mono">{t.fees != null ? formatCurrency(t.fees) : "—"}</TableCell>
                        <TableCell className={`text-right font-mono ${(t.realized_pl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                          {t.realized_pl != null ? formatCurrency(t.realized_pl) : "—"}
                        </TableCell>
                        <TableCell>{t.is_paper ? "Yes" : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {trades.length > 200 && <p className="text-xs text-zinc-500 mt-2">Showing first 200 of {trades.length} trades.</p>}
            </Card>
          )}
        </>
      )}

      {!metrics && !runMutation.isPending && (
        <EmptyState
          title="No results yet"
          message="Set date range and toggles, then click Run to replay journal entries."
        />
      )}

      <Card>
        <CardHeader title="History" />
        {runs.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No past runs.</p>
        ) : (
          <ul className="space-y-2">
            {runs.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="text-zinc-700 dark:text-zinc-300">
                  {r.start_date} → {r.end_date} ({MODE_LABELS[r.mode] ?? r.mode}) — {new Date(r.created_ts).toLocaleString()}
                </span>
                <span className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => downloadBacktestFile(r.id, "summary_json")}
                    className="text-emerald-600 hover:underline dark:text-emerald-400"
                  >
                    JSON
                  </button>
                  <span className="text-zinc-400">|</span>
                  <button
                    type="button"
                    onClick={() => downloadBacktestFile(r.id, "trades_csv")}
                    className="text-emerald-600 hover:underline dark:text-emerald-400"
                  >
                    CSV
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
