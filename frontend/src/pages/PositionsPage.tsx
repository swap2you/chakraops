/**
 * R27.9/R28.0/R28.9/R29.0/R29.1/R29.2: Unified Positions — Integrity strip; Compare Stored vs Computed when symbol set.
 * R29.2: Compare panel (symbol set): Stored vs Computed columns, diff summary/details, sanitized display.
 */
import { useState, useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  useUnifiedPositions,
  useUnifiedPositionsFromDb,
  useUiSystemHealth,
  usePositionsUnifiedRebuild,
  useReconcileDiff,
} from "@/api/queries";
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
  Button,
} from "@/components/ui";

const STALENESS_HOURS = 6;

/** R29.0: Stale if rebuild block missing, finished_at_utc missing, or finished_at_utc older than 6h (UTC). */
function useStoredPositionsStale(): boolean {
  const { data: health } = useUiSystemHealth();
  return useMemo(() => {
    const block = health?.positions_unified_rebuild;
    if (!block) return true;
    const finished = block.finished_at_utc ?? block.last_rebuild_at_utc ?? null;
    if (!finished || typeof finished !== "string") return true;
    try {
      const dt = new Date(finished);
      if (Number.isNaN(dt.getTime())) return true;
      const now = Date.now();
      const ageMs = now - dt.getTime();
      return ageMs > STALENESS_HOURS * 60 * 60 * 1000;
    } catch {
      return true;
    }
  }, [health?.positions_unified_rebuild]);
}

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

/** R29.2: Sanitize for compare display — no raw FAIL/WARN/PASS or FAIL_/WARN_ in UI. */
function sanitizeCompareDisplay(val: string | null | undefined): string {
  if (val == null) return "—";
  let s = String(val).trim();
  s = s.replace(/\bFAIL\b/gi, "—").replace(/\bWARN\b/gi, "Review").replace(/\bPASS\b/gi, "OK");
  s = s.replace(/FAIL_/g, "").replace(/WARN_/g, "");
  return s || "—";
}

export function PositionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sourceFromUrl = searchParams.get("source") ?? "db";
  const source = sourceFromUrl === "db" ? "db" : "recompute";
  const symbolFromUrl = searchParams.get("symbol") ?? "";
  const includePaperFromUrl = searchParams.get("include_paper");
  const initialIncludePaper = includePaperFromUrl === "true" || includePaperFromUrl === null || includePaperFromUrl === "";

  const [state, setState] = useState<"open" | "closed">("open");
  const [includePaper, setIncludePaper] = useState(initialIncludePaper);
  const [instrumentType, setInstrumentType] = useState<string>("");
  const [symbolFilter, setSymbolFilter] = useState(symbolFromUrl);
  const [showRebuildConfirm, setShowRebuildConfirm] = useState(false);
  const [integrityDiffExpanded, setIntegrityDiffExpanded] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);

  const hasSymbolFilter = !!symbolFilter.trim();
  const computedEnabled = source === "recompute" || (compareOpen && hasSymbolFilter);
  const fromDbEnabled = source === "db" || (compareOpen && hasSymbolFilter);

  const isStale = useStoredPositionsStale();
  const rebuildUnified = usePositionsUnifiedRebuild();
  const { data: health } = useUiSystemHealth();
  const reconcileStatus = (health?.positions_unified_reconcile?.status ?? "OK") as "OK" | "Review";
  const reconcileCounts = health?.positions_unified_reconcile;
  const needReconcileDiff = source === "db" && reconcileStatus === "Review";
  const { data: reconcileDiff } = useReconcileDiff({
    include_paper: includePaper,
    symbol: symbolFilter.trim() || null,
    limit: 200,
    enabled: needReconcileDiff,
  });
  const { data: compareDiff } = useReconcileDiff({
    include_paper: includePaper,
    symbol: symbolFilter.trim() || null,
    limit: 200,
    enabled: compareOpen && hasSymbolFilter,
  });

  useEffect(() => {
    if (symbolFromUrl) setSymbolFilter(symbolFromUrl);
    if (includePaperFromUrl === "true" || includePaperFromUrl === "false") setIncludePaper(includePaperFromUrl === "true");
  }, [symbolFromUrl, includePaperFromUrl]);

  const computed = useUnifiedPositions({
    state,
    include_paper: includePaper,
    instrument_type: instrumentType.trim() || null,
    symbol: symbolFilter.trim() || null,
    enabled: computedEnabled,
  });
  const fromDb = useUnifiedPositionsFromDb({
    state,
    include_paper: includePaper,
    instrument_type: instrumentType.trim() || null,
    symbol: symbolFilter.trim() || null,
    limit: 500,
    enabled: fromDbEnabled,
  });

  const { isLoading, isError } = source === "db" ? fromDb : computed;
  const positions: UnifiedPosition[] = source === "db" ? (fromDb.data?.items ?? []) : (computed.data?.positions ?? []);

  const setSource = (s: "db" | "recompute") => {
    const next = new URLSearchParams(searchParams);
    next.set("source", s === "db" ? "db" : "recompute");
    setSearchParams(next);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Positions" subtext="Unified view of open and closed positions (live and paper)." />

      {/* R29.1: Integrity strip — reconcile status + diff summary + actions when Stored; minimal note when Computed */}
      <Card className="border-zinc-200 dark:border-zinc-700" data-testid="positions-integrity-strip">
        <div className="p-4">
          <h3 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">Integrity</h3>
          {source === "db" ? (
            <>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                <span className="text-zinc-600 dark:text-zinc-400">
                  Reconcile: <span data-testid="positions-integrity-status">{reconcileStatus === "Review" ? "Review" : "OK"}</span>
                </span>
                {reconcileCounts != null && (
                  <span className="text-zinc-500 dark:text-zinc-500">
                    (open: {reconcileCounts.paper_open_count ?? "—"} paper, {reconcileCounts.unified_open_paper_count ?? "—"} unified)
                  </span>
                )}
              </div>
              {reconcileStatus === "Review" && (
                <>
                  {reconcileDiff != null && (
                    <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-zinc-600 dark:text-zinc-400">
                      <span data-testid="positions-integrity-diff-counts">
                        missing: {reconcileDiff.missing_count}, extra: {reconcileDiff.extra_count}, mismatched: {reconcileDiff.mismatched_count}
                      </span>
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setIntegrityDiffExpanded((e) => !e)}
                      data-testid="positions-integrity-view-diff-details"
                    >
                      {integrityDiffExpanded ? "Hide diff details" : "View diff details"}
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => setShowRebuildConfirm(true)}
                      disabled={rebuildUnified.isPending}
                      data-testid="positions-integrity-rebuild-btn"
                    >
                      {rebuildUnified.isPending ? "Rebuild running" : "Rebuild unified positions"}
                    </Button>
                    <button
                      type="button"
                      onClick={() => setSource("recompute")}
                      className="text-sm text-blue-600 hover:underline dark:text-blue-400"
                      data-testid="positions-integrity-switch-to-computed"
                    >
                      Switch to Computed
                    </button>
                  </div>
                  {integrityDiffExpanded && reconcileDiff?.items != null && reconcileDiff.items.length > 0 && (
                    <ul className="mt-3 max-h-60 list-none space-y-1 overflow-y-auto rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900/50" data-testid="positions-integrity-diff-list">
                      {reconcileDiff.items.map((item, i) => (
                        <li key={`${item.id}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-zinc-200 py-1.5 last:border-0 dark:border-zinc-700">
                          <span className="font-medium text-zinc-700 dark:text-zinc-300">{item.kind}</span>
                          <span className="font-mono text-zinc-600 dark:text-zinc-400">{item.symbol ?? item.id}</span>
                          {item.instrument_type != null && (
                            <span className="text-zinc-500 dark:text-zinc-500">{item.instrument_type}</span>
                          )}
                          <span className="text-zinc-400 dark:text-zinc-500">{item.id}</span>
                          {item.fields_diff != null && item.fields_diff.length > 0 && (
                            <span className="text-zinc-500 dark:text-zinc-500">({item.fields_diff.join(", ")})</span>
                          )}
                          <Link
                            to={`/positions?symbol=${encodeURIComponent(item.symbol ?? "")}&include_paper=${includePaper}&source=db`}
                            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
                            data-testid="positions-integrity-view-positions-link"
                          >
                            View positions
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </>
          ) : (
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
              <span className="text-zinc-600 dark:text-zinc-400" data-testid="positions-integrity-computed-note">
                Integrity: Computed (authoritative)
              </span>
              <button
                type="button"
                onClick={() => setSource("db")}
                className="text-blue-600 hover:underline dark:text-blue-400"
                data-testid="positions-integrity-switch-to-stored"
              >
                Switch to Stored
              </button>
            </div>
          )}
        </div>
      </Card>

      {/* R29.2: Compare Stored vs Computed — only when symbol filter set */}
      {hasSymbolFilter && (
        <Card className="border-zinc-200 dark:border-zinc-700" data-testid="positions-compare-panel">
          <div className="p-4">
            <h3 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">Compare</h3>
            <div className="mt-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setCompareOpen((o) => !o)}
                data-testid="positions-compare-toggle-btn"
              >
                {compareOpen ? "Hide stored vs computed" : "Compare stored vs computed"}
              </Button>
            </div>
            {compareOpen && (
              <>
                {compareDiff != null && (
                  <div className="mt-3 text-sm text-zinc-600 dark:text-zinc-400" data-testid="positions-compare-diff-summary">
                    missing_in_stored: {compareDiff.missing_count}, extra_in_stored: {compareDiff.extra_count}, mismatched: {compareDiff.mismatched_count}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap gap-4">
                  <div className="min-w-0 flex-1 rounded border border-zinc-200 bg-zinc-50/50 p-2 dark:border-zinc-700 dark:bg-zinc-900/30">
                    <p className="text-xs font-medium text-zinc-500 dark:text-zinc-500">Stored</p>
                    <ul className="mt-1 max-h-48 list-none space-y-0.5 overflow-y-auto text-xs">
                      {(fromDb.data?.items ?? []).map((p) => (
                        <li key={p.id} className="flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-zinc-700 dark:text-zinc-300">
                          <span>{sanitizeCompareDisplay(p.id)}</span>
                          <span>{sanitizeCompareDisplay(p.instrument_type)}</span>
                          <span>qty: {fmtNum(p.qty)}</span>
                          <span>{fmtDate(p.opened_ts)}</span>
                          {p.expiry != null && <span>exp: {sanitizeCompareDisplay(String(p.expiry))}</span>}
                          {p.strike != null && <span>strike: {fmtNum(p.strike)}</span>}
                          {p.right != null && <span>{sanitizeCompareDisplay(String(p.right))}</span>}
                          <span>{p.is_paper ? "paper" : "live"}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="min-w-0 flex-1 rounded border border-zinc-200 bg-zinc-50/50 p-2 dark:border-zinc-700 dark:bg-zinc-900/30">
                    <p className="text-xs font-medium text-zinc-500 dark:text-zinc-500">Computed</p>
                    <ul className="mt-1 max-h-48 list-none space-y-0.5 overflow-y-auto text-xs">
                      {(computed.data?.positions ?? []).map((p) => (
                        <li key={p.id} className="flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-zinc-700 dark:text-zinc-300">
                          <span>{sanitizeCompareDisplay(p.id)}</span>
                          <span>{sanitizeCompareDisplay(p.instrument_type)}</span>
                          <span>qty: {fmtNum(p.qty)}</span>
                          <span>{fmtDate(p.opened_ts)}</span>
                          {p.expiry != null && <span>exp: {sanitizeCompareDisplay(String(p.expiry))}</span>}
                          {p.strike != null && <span>strike: {fmtNum(p.strike)}</span>}
                          {p.right != null && <span>{sanitizeCompareDisplay(String(p.right))}</span>}
                          <span>{p.is_paper ? "paper" : "live"}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                {compareDiff?.items != null && compareDiff.items.length > 0 && (
                  <ul className="mt-3 max-h-40 list-none space-y-1 overflow-y-auto rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900/50" data-testid="positions-compare-diff-details">
                    {compareDiff.items.map((item, i) => (
                      <li key={`${item.id}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-b border-zinc-200 py-1 last:border-0 dark:border-zinc-700">
                        <span className="font-medium text-zinc-700 dark:text-zinc-300">
                          {item.kind === "missing" ? "Missing" : item.kind === "extra" ? "Extra" : "Mismatch"}
                        </span>
                        <span className="font-mono text-zinc-600 dark:text-zinc-400">{sanitizeCompareDisplay(item.id)}</span>
                        {item.instrument_type != null && <span className="text-zinc-500">{sanitizeCompareDisplay(item.instrument_type)}</span>}
                        {item.fields_diff != null && item.fields_diff.length > 0 && (
                          <span className="text-zinc-500">({item.fields_diff.map((f) => sanitizeCompareDisplay(f)).join(", ")})</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                  <Link to="/system" className="text-blue-600 hover:underline dark:text-blue-400" data-testid="positions-compare-view-diff-diagnostics">
                    View diff in diagnostics
                  </Link>
                  <Button variant="primary" size="sm" onClick={() => setShowRebuildConfirm(true)} disabled={rebuildUnified.isPending} data-testid="positions-compare-rebuild-btn">
                    {rebuildUnified.isPending ? "Rebuild running" : "Rebuild unified positions"}
                  </Button>
                </div>
              </>
            )}
          </div>
        </Card>
      )}

      {source === "db" && isStale && (
        <Card className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40">
          <div className="p-4">
            <p className="font-medium text-amber-800 dark:text-amber-200" data-testid="positions-stale-banner-title">
              Stored positions may be stale — Review
            </p>
            <p className="mt-1 text-sm text-amber-700 dark:text-amber-300" data-testid="positions-stale-banner-subtext">
              Rebuild unified positions to refresh stored data from authoritative sources.
            </p>
            <div className="mt-3 flex items-center gap-3">
              <Button
                variant="primary"
                onClick={() => setShowRebuildConfirm(true)}
                disabled={rebuildUnified.isPending}
                data-testid="positions-stale-rebuild-btn"
              >
                {rebuildUnified.isPending ? "Rebuild running" : "Rebuild unified positions"}
              </Button>
            </div>
          </div>
        </Card>
      )}

      {showRebuildConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" data-testid="positions-rebuild-confirm-modal">
          <Card className="max-w-md p-6">
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              This will rebuild the unified positions DB from authoritative sources. Manual action. Continue?
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowRebuildConfirm(false)} data-testid="positions-rebuild-confirm-cancel">
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  rebuildUnified.mutate({ include_paper: includePaper }, { onSuccess: () => setShowRebuildConfirm(false) });
                }}
                disabled={rebuildUnified.isPending}
                data-testid="positions-rebuild-confirm-ok"
              >
                Continue
              </Button>
            </div>
          </Card>
        </div>
      )}

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
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 dark:border-zinc-800 p-4">
          <CardHeader title={state === "open" ? "Open positions" : "Closed positions"} />
          <div className="flex items-center gap-3" role="radiogroup" aria-label="Data source">
            <span className="text-sm text-zinc-500 dark:text-zinc-500" data-testid="positions-source-label">
              Source: {source === "db" ? "Stored" : "Computed"}
            </span>
            <label className="flex cursor-pointer items-center gap-1.5 text-sm">
              <input
                type="radio"
                name="positions-source"
                checked={source === "db"}
                onChange={() => setSource("db")}
                className="rounded-full border-zinc-400 text-zinc-600 focus:ring-zinc-500 dark:border-zinc-500 dark:text-zinc-400"
                data-testid="positions-source-radio-stored"
              />
              Stored
            </label>
            <label className="flex cursor-pointer items-center gap-1.5 text-sm">
              <input
                type="radio"
                name="positions-source"
                checked={source === "recompute"}
                onChange={() => setSource("recompute")}
                className="rounded-full border-zinc-400 text-zinc-600 focus:ring-zinc-500 dark:border-zinc-500 dark:text-zinc-400"
                data-testid="positions-source-radio-computed"
              />
              Computed
            </label>
          </div>
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
