/**
 * R27.9/R28.0/R28.9: Unified Positions — computed (default) or DB-first read.
 * source=recompute (default): GET /api/ui/positions/unified. source=db: GET /api/ui/positions/unified/db.
 */
import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useUnifiedPositions, useUnifiedPositionsFromDb } from "@/api/queries";
import type { UnifiedPosition } from "@/api/types";
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
  Badge,
} from "@/components/ui";

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function fmtDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const s = (ts as string).slice(0, 10);
  return s || "—";
}

export function PositionsPage() {
  const [searchParams] = useSearchParams();
  const sourceFromUrl = searchParams.get("source") ?? "recompute";
  const source = sourceFromUrl === "db" ? "db" : "recompute";
  const symbolFromUrl = searchParams.get("symbol") ?? "";
  const includePaperFromUrl = searchParams.get("include_paper");
  const initialIncludePaper = includePaperFromUrl === "true" || includePaperFromUrl === null || includePaperFromUrl === "";

  const [state, setState] = useState<"open" | "closed">("open");
  const [includePaper, setIncludePaper] = useState(initialIncludePaper);
  const [instrumentType, setInstrumentType] = useState<string>("");
  const [symbolFilter, setSymbolFilter] = useState(symbolFromUrl);

  useEffect(() => {
    if (symbolFromUrl) setSymbolFilter(symbolFromUrl);
    if (includePaperFromUrl === "true" || includePaperFromUrl === "false") setIncludePaper(includePaperFromUrl === "true");
  }, [symbolFromUrl, includePaperFromUrl]);

  const computed = useUnifiedPositions({
    state,
    include_paper: includePaper,
    instrument_type: instrumentType.trim() || null,
    symbol: symbolFilter.trim() || null,
  });
  const fromDb = useUnifiedPositionsFromDb({
    state,
    include_paper: includePaper,
    instrument_type: instrumentType.trim() || null,
    symbol: symbolFilter.trim() || null,
    limit: 500,
  });

  const { isLoading, isError } = source === "db" ? fromDb : computed;
  const positions: UnifiedPosition[] = source === "db" ? (fromDb.data?.items ?? []) : (computed.data?.positions ?? []);

  return (
    <div className="space-y-6">
      <PageHeader title="Positions" subtext="Unified view of open and closed positions (live and paper)." />
      <Card>
        <CardHeader title="Filters" />
        <div className="flex flex-wrap gap-4 p-4 border-t border-zinc-200 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-600 dark:text-zinc-400">State</span>
            <select
              value={state}
              onChange={(e) => setState(e.target.value as "open" | "closed")}
              className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-2 py-1 text-sm"
              data-testid="positions-filter-state"
            >
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includePaper}
              onChange={(e) => setIncludePaper(e.target.checked)}
              data-testid="positions-filter-paper"
            />
            Include paper
          </label>
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-600 dark:text-zinc-400">Type</span>
            <select
              value={instrumentType}
              onChange={(e) => setInstrumentType(e.target.value)}
              className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-2 py-1 text-sm"
              data-testid="positions-filter-type"
            >
              <option value="">All</option>
              <option value="SHARES">SHARES</option>
              <option value="CSP">CSP</option>
              <option value="CC">CC</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-zinc-600 dark:text-zinc-400">Symbol</span>
            <input
              type="text"
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              placeholder="e.g. AAPL"
              className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-900 px-2 py-1 text-sm w-28"
              data-testid="positions-filter-symbol"
            />
          </div>
        </div>
      </Card>
      <Card>
        <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 p-4">
          <CardHeader title={state === "open" ? "Open positions" : "Closed positions"} />
          <span className="text-sm text-zinc-500 dark:text-zinc-500" data-testid="positions-source-label">
            Source: {source === "db" ? "Stored" : "Computed"}
          </span>
        </div>
        {isLoading && (
          <div className="p-6 text-sm text-zinc-500">Loading…</div>
        )}
        {isError && (
          <div className="p-6 text-sm text-red-600 dark:text-red-400">Failed to load positions.</div>
        )}
        {!isLoading && !isError && positions.length === 0 && (
          <EmptyState
            title="No positions"
            description={state === "open" ? "No open positions match the filters." : "No closed positions match the filters."}
          />
        )}
        {!isLoading && !isError && positions.length > 0 && (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableHead>Symbol</TableHead>
                <TableHead data-testid="positions-th-source">Source</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead>Opened</TableHead>
                <TableHead className="text-right" data-testid="positions-th-mark">Mark / Unrealized</TableHead>
                <TableHead>Ticket</TableHead>
                <TableHead>Journal</TableHead>
                <TableHead>Paper</TableHead>
                {state === "closed" && (
                  <>
                    <TableHead>Closed</TableHead>
                    <TableHead className="text-right">Realized P/L</TableHead>
                  </>
                )}
              </TableHeader>
              <TableBody>
                {positions.map((p) => (
                  <TableRow key={p.id} data-testid="positions-row">
                    <TableCell className="font-mono">{p.symbol}</TableCell>
                    <TableCell data-testid="positions-cell-source">{p.is_paper ? "PAPER" : "LIVE"}</TableCell>
                    <TableCell>
                      <span className="flex items-center gap-1">
                        {p.instrument_type}
                        {p.is_paper ? (
                          <Badge variant="neutral" className="text-xs">Paper</Badge>
                        ) : null}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">{fmtNum(p.qty)}</TableCell>
                    <TableCell className="text-zinc-600 dark:text-zinc-400">{fmtDate(p.opened_ts)}</TableCell>
                    <TableCell className="text-right text-zinc-500" data-testid="positions-cell-mark">
                      {p.mark_value != null || p.unrealized_pl != null
                        ? [p.mark_value != null ? fmtNum(p.mark_value) : "", p.unrealized_pl != null ? fmtNum(p.unrealized_pl) : ""].filter(Boolean).join(" / ") || "—"
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <Link
                        to="/ticket"
                        className="text-primary hover:underline text-sm"
                        data-testid="positions-link-ticket"
                      >
                        Ticket
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link
                        to="/journal"
                        className="text-primary hover:underline text-sm"
                        data-testid="positions-link-journal"
                      >
                        Journal
                      </Link>
                    </TableCell>
                    <TableCell>
                      {p.is_paper ? (
                        <Link
                          to="/paper"
                          className="text-primary hover:underline text-sm"
                          data-testid="positions-link-paper"
                        >
                          Paper
                        </Link>
                      ) : (
                        <span className="text-zinc-400">—</span>
                      )}
                    </TableCell>
                    {state === "closed" && (
                      <>
                        <TableCell className="text-zinc-600 dark:text-zinc-400">{fmtDate(p.closed_ts)}</TableCell>
                        <TableCell className="text-right">
                          {p.realized_pl != null ? (
                            <span className={p.realized_pl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                              {fmtNum(p.realized_pl)}
                            </span>
                          ) : "—"}
                        </TableCell>
                      </>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
    </div>
  );
}
