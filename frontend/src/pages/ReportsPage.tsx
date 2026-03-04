/**
 * R25.5: Monthly report — realized P/L, counts, winners/losers.
 * R26.5: Monthly close pack — generate and download.
 * Uses /api/ui/reports/monthly. Safe labels only (no raw codes).
 */
import { useState } from "react";
import {
  useReportsMonthly,
  useMonthlyCloseFiles,
  useMonthlyCloseGenerate,
  downloadMonthlyCloseFile,
} from "@/api/queries";
import type { MonthlyReportResponse } from "@/api/queries";
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
} from "@/components/ui";

function formatCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);
}

function currentMonth(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

export function ReportsPage() {
  const [month, setMonth] = useState(currentMonth());
  const [includePaper, setIncludePaper] = useState(false);
  const { data, isLoading, isError, error } = useReportsMonthly(month, includePaper);
  const { data: closeFilesLive, isLoading: closeFilesLiveLoading } = useMonthlyCloseFiles(month, "live");
  const { data: closeFilesPaper, isLoading: closeFilesPaperLoading } = useMonthlyCloseFiles(month, "paper");
  const generateClose = useMonthlyCloseGenerate();
  const closeFilesLoading = closeFilesLiveLoading || closeFilesPaperLoading;

  const report = data as MonthlyReportResponse | undefined;
  const hasData = report && (report.trade_count > 0 || report.total_realized_pl !== 0 || report.fees_total !== 0);
  const modeLabel = report?.mode === "PAPER_ONLY" ? "Paper only" : report?.mode === "MIXED" ? "Mixed" : "Live only";

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Monthly report"
        subtext="Realized P/L, trade counts, and top winners and losers by month."
      />

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          Month
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value || currentMonth())}
            className="rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400" data-testid="reports-include-paper">
          <input
            type="checkbox"
            checked={includePaper}
            onChange={(e) => setIncludePaper(e.target.checked)}
            className="rounded border-zinc-300 dark:border-zinc-600"
          />
          Include paper
        </label>
        {report && (
          <span className="text-sm text-zinc-600 dark:text-zinc-400" data-testid="reports-mode-label">
            Mode: {modeLabel}
          </span>
        )}
      </div>

      {/* R26.5: Monthly Close pack. R27.1: live vs paper pack */}
      <Card data-testid="monthly-close-panel">
        <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Monthly close
        </CardHeader>
        <div className="space-y-3 pt-2">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Generate a close pack (JSON, CSV, journal export, summary) for the selected month. data/reports/{month}/live/ or .../paper/.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => generateClose.mutate({ month, include_paper: false })}
              disabled={generateClose.isPending || !month}
              className="rounded bg-zinc-800 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-700 dark:hover:bg-zinc-600"
              data-testid="monthly-close-generate-live"
            >
              {generateClose.isPending ? "Generating…" : "Generate live pack"}
            </button>
            <button
              type="button"
              onClick={() => generateClose.mutate({ month, include_paper: true })}
              disabled={generateClose.isPending || !month}
              className="rounded border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700 disabled:opacity-50"
              data-testid="monthly-close-generate-paper"
            >
              {generateClose.isPending ? "Generating…" : "Generate paper pack"}
            </button>
          </div>
          {closeFilesLoading && <p className="text-sm text-zinc-500">Loading…</p>}
          {!closeFilesLoading && (
            <>
              {closeFilesLive?.generated_ts && (
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  Live pack: {new Date(closeFilesLive.generated_ts).toLocaleString()}
                </p>
              )}
              {(closeFilesLive?.files?.length ?? 0) > 0 && (
                <div className="flex flex-wrap gap-2">
                  {(closeFilesLive?.files ?? []).map((f) => (
                    <button
                      key={`live-${f.name}`}
                      type="button"
                      onClick={() => downloadMonthlyCloseFile(month, f.name, "live")}
                      className="rounded border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
                      data-testid={`monthly-close-download-live-${f.name.replace(".", "-")}`}
                    >
                      Download {f.name} (live)
                    </button>
                  ))}
                </div>
              )}
              {closeFilesPaper?.generated_ts && (
                <p className="text-sm text-zinc-600 dark:text-zinc-400">
                  Paper pack: {new Date(closeFilesPaper.generated_ts).toLocaleString()}
                </p>
              )}
              {(closeFilesPaper?.files?.length ?? 0) > 0 && (
                <div className="flex flex-wrap gap-2">
                  {(closeFilesPaper?.files ?? []).map((f) => (
                    <button
                      key={`paper-${f.name}`}
                      type="button"
                      onClick={() => downloadMonthlyCloseFile(month, f.name, "paper")}
                      className="rounded border border-zinc-300 bg-white px-2 py-1 text-sm text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
                      data-testid={`monthly-close-download-paper-${f.name.replace(".", "-")}`}
                    >
                      Download {f.name} (paper)
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </Card>

      {isLoading && (
        <div className="rounded-lg border border-zinc-200 bg-zinc-50/50 p-8 text-center text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/50">
          Loading report…
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
          {error instanceof Error ? error.message : "Unable to load report."}
        </div>
      )}

      {!isLoading && !isError && !hasData && (
        <EmptyState
          title="No data for this month"
          message="Add journal entries with realized P/L to see summary and winners/losers here."
        />
      )}

      {!isLoading && !isError && hasData && report && (
        <div className="space-y-6">
          {/* R27.2: Split Live / Paper totals when include_paper enabled */}
          {report.live_totals != null && report.paper_totals != null && (
            <Card data-testid="reports-split-totals">
              <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Split totals (Live vs Paper)
              </CardHeader>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 pt-2">
                <div className="rounded border border-zinc-200 p-3 dark:border-zinc-700">
                  <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">Live</p>
                  <p className={report.live_totals.total_realized_pl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    {formatCurrency(report.live_totals.total_realized_pl)}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {report.live_totals.trade_count} trades · Win rate {report.live_totals.win_rate}%
                  </p>
                </div>
                <div className="rounded border border-zinc-200 p-3 dark:border-zinc-700">
                  <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">Paper</p>
                  <p className={report.paper_totals.total_realized_pl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    {formatCurrency(report.paper_totals.total_realized_pl)}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {report.paper_totals.trade_count} trades · Win rate {report.paper_totals.win_rate}%
                  </p>
                </div>
              </div>
            </Card>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                Total realized P/L
              </CardHeader>
              <p className={report.total_realized_pl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                {formatCurrency(report.total_realized_pl)}
              </p>
            </Card>
            <Card>
              <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                Trades / Wins / Losses
              </CardHeader>
              <p className="text-zinc-900 dark:text-zinc-100">
                {report.trade_count} / {report.win_count} / {report.loss_count}
              </p>
            </Card>
            <Card>
              <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                Win rate
              </CardHeader>
              <p className="text-zinc-900 dark:text-zinc-100">{report.win_rate}%</p>
            </Card>
            <Card>
              <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                Fees total
              </CardHeader>
              <p className="text-zinc-900 dark:text-zinc-100">{formatCurrency(report.fees_total)}</p>
            </Card>
          </div>

          {Object.keys(report.by_strategy ?? {}).length > 0 && (
            <Card>
              <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Realized P/L by strategy
              </CardHeader>
              <div className="flex flex-wrap gap-4 pt-2">
                {Object.entries(report.by_strategy).map(([strat, pl]) => (
                  <span key={strat} className={pl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                    {strat}: {formatCurrency(pl)}
                  </span>
                ))}
              </div>
            </Card>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Top winners
              </CardHeader>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Strategy</TableHead>
                    <TableHead className="text-right">P/L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(report.top_winners ?? []).length === 0 ? (
                    <TableRow>
                      <td colSpan={3} className="py-3 pr-2 text-center text-zinc-500">
                        None
                      </td>
                    </TableRow>
                  ) : (
                    (report.top_winners ?? []).map((r, i) => (
                      <TableRow key={`w-${i}-${r.symbol}`}>
                        <TableCell className="font-medium">{r.symbol}</TableCell>
                        <TableCell>{r.strategy}</TableCell>
                        <TableCell className="text-right text-emerald-600 dark:text-emerald-400">
                          {formatCurrency(r.realized_pl)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Card>
            <Card>
              <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Top losers
              </CardHeader>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Strategy</TableHead>
                    <TableHead className="text-right">P/L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(report.top_losers ?? []).length === 0 ? (
                    <TableRow>
                      <td colSpan={3} className="py-3 pr-2 text-center text-zinc-500">
                        None
                      </td>
                    </TableRow>
                  ) : (
                    (report.top_losers ?? []).map((r, i) => (
                      <TableRow key={`l-${i}-${r.symbol}`}>
                        <TableCell className="font-medium">{r.symbol}</TableCell>
                        <TableCell>{r.strategy}</TableCell>
                        <TableCell className="text-right text-red-600 dark:text-red-400">
                          {formatCurrency(r.realized_pl)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
