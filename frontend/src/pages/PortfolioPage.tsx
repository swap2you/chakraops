import { useState } from "react";
import { Link } from "react-router-dom";
import { usePortfolio, usePortfolioMetrics, usePortfolioRisk, useRefreshMarks, useAccounts, useDefaultAccount, useDeletePosition } from "@/api/queries";
import type { PortfolioPosition } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { ClosePositionDrawer } from "@/components/ClosePositionDrawer";
import { PortfolioPositionDetailDrawer } from "@/components/PortfolioPositionDetailDrawer";
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

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "n/a";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "n/a";
  return n.toFixed(1) + "%";
}

function alertBadgeVariant(flag: string): "success" | "warning" | "danger" | "neutral" {
  const f = flag.toUpperCase();
  if (f === "T3") return "success";
  if (f === "T2" || f === "T1") return "warning";
  if (f === "STOP" || f === "DTE_RISK") return "danger";
  return "neutral";
}

function fmtCurrency(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function PortfolioPage() {
  const { data, isLoading, isError } = usePortfolio();
  const { data: metrics } = usePortfolioMetrics();
  const { data: accountsData } = useAccounts();
  const { data: defaultAccountData } = useDefaultAccount();
  const deletePosition = useDeletePosition();
  const [closeDrawerPosition, setCloseDrawerPosition] = useState<PortfolioPosition | null>(null);
  const [detailDrawerPosition, setDetailDrawerPosition] = useState<PortfolioPosition | null>(null);

  const positions = data?.positions ?? [];
  const capitalDeployed = data?.capital_deployed ?? 0;
  const openPositionsCount = data?.open_positions_count ?? positions.filter((p) => (p.status ?? "").toUpperCase() === "OPEN" || (p.status ?? "").toUpperCase() === "PARTIAL_EXIT").length;

  const accounts = accountsData?.accounts ?? [];
  const defaultAccount = defaultAccountData?.account;
  const selectedAccount = defaultAccount ?? (accounts.length > 0 ? accounts[0] : null);
  const accountId = (selectedAccount as { account_id?: string })?.account_id ?? null;
  const { data: riskData } = usePortfolioRisk(accountId, !!selectedAccount);
  const refreshMarks = useRefreshMarks(accountId);
  const totalCapital = (selectedAccount as { total_capital?: number })?.total_capital ?? 0;
  const maxCapitalPct = (selectedAccount as { max_capital_per_trade_pct?: number })?.max_capital_per_trade_pct ?? 5;
  const riskPerTrade = totalCapital > 0 ? (totalCapital * maxCapitalPct) / 100 : 0;
  const buyingPower = totalCapital > 0 ? totalCapital - capitalDeployed : 0;

  const isOpen = (p: PortfolioPosition) => {
    const s = (p.status ?? "").toUpperCase();
    return s === "OPEN" || s === "PARTIAL_EXIT";
  };
  const canDelete = (p: PortfolioPosition) =>
    p.is_test === true || (p.status ?? "").toUpperCase() === "CLOSED" || (p.status ?? "").toUpperCase() === "ABORTED";

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Portfolio" subtext="Tracked positions" />
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
        </Card>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Portfolio" />
        <p className="text-red-500 dark:text-red-400">Failed to load portfolio.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader title="Portfolio" subtext={`${positions.length} position(s) · ${fmtCurrency(capitalDeployed)} deployed`} />

      {metrics && (
        <Card>
          <CardHeader title="Portfolio Metrics" />
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4 lg:grid-cols-6">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Open positions</span>
              <span className="font-mono font-medium text-zinc-900 dark:text-zinc-200">{metrics.open_positions_count}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Capital deployed</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtCurrency(metrics.capital_deployed)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Realized PnL total</span>
              <span className={`font-mono font-medium ${(metrics.realized_pnl_total ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                {fmtCurrency(metrics.realized_pnl_total)}
              </span>
            </div>
            {metrics.win_rate != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Win rate</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{(metrics.win_rate * 100).toFixed(1)}%</span>
              </div>
            )}
            {metrics.avg_pnl != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Avg PnL</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtCurrency(metrics.avg_pnl)}</span>
              </div>
            )}
            {metrics.avg_dte_at_entry != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Avg DTE at entry</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{metrics.avg_dte_at_entry.toFixed(1)}</span>
              </div>
            )}
          </div>
        </Card>
      )}

      {accounts.length > 0 && (
        <Card>
          <CardHeader title="Account" />
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Account</span>
              <span className="font-mono font-medium text-zinc-900 dark:text-zinc-200">{selectedAccount ? (selectedAccount as { account_id?: string }).account_id : "—"}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Buying power</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtCurrency(buyingPower)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Risk per trade</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtCurrency(riskPerTrade)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Open positions</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{openPositionsCount}</span>
            </div>
          </div>
        </Card>
      )}

      {riskData && (
        <Card className={riskData.status === "FAIL" ? "border-red-500 dark:border-red-600" : riskData.status === "WARN" ? "border-amber-500 dark:border-amber-600" : ""}>
          <CardHeader
            title="Risk (Phase 14.0)"
            description={riskData.status === "FAIL" ? "Limit breach" : riskData.status === "WARN" ? "Warning" : undefined}
          />
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Status</span>
              <Badge variant={riskData.status === "PASS" ? "success" : riskData.status === "WARN" ? "warning" : "danger"}>
                {riskData.status}
              </Badge>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Deployed %</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">
                {riskData.metrics?.deployed_pct != null ? (riskData.metrics.deployed_pct * 100).toFixed(1) + "%" : "—"}
              </span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Top symbol</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">
                {riskData.metrics?.top_symbol ?? "—"} {riskData.metrics?.top_symbol_collateral != null ? `(${fmtCurrency(riskData.metrics.top_symbol_collateral)})` : ""}
              </span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Near expiry (DTE≤7)</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{riskData.metrics?.near_expiry_count ?? 0}</span>
            </div>
          </div>
          {(riskData.breaches ?? []).length > 0 && (
            <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-700">
              <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-2">Breaches</span>
              <ul className="space-y-1 text-sm text-red-600 dark:text-red-400">
                {riskData.breaches.map((b, i) => (
                  <li key={i}>{b.message}</li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      <Card>
        <CardHeader
          title="Positions"
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => refreshMarks.mutate()}
              disabled={refreshMarks.isPending}
            >
              {refreshMarks.isPending ? "Refreshing…" : "Refresh marks"}
            </Button>
          }
        />
        {positions.length === 0 ? (
          <EmptyState
            title="No positions"
            message="Track positions via Trade Ticket (Symbol page) or manual execution."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableHead>Symbol</TableHead>
              <TableHead>Strategy</TableHead>
              <TableHead>Entry credit</TableHead>
              <TableHead>Mark</TableHead>
              <TableHead>Unrealized PnL</TableHead>
              <TableHead>Premium captured</TableHead>
              <TableHead>DTE</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Realized PnL</TableHead>
              <TableHead>Alert</TableHead>
              <TableHead>Actions</TableHead>
            </TableHeader>
            <TableBody>
              {positions.map((row: PortfolioPosition) => (
                <TableRow key={row.position_id}>
                  <TableCell>
                    <Link
                      to={`/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`}
                      className="font-mono font-medium text-zinc-900 dark:text-zinc-200 hover:underline"
                    >
                      {row.symbol}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-zinc-700 dark:text-zinc-300">
                    {row.strategy ?? "n/a"}
                  </TableCell>
                  <TableCell numeric className="font-mono">
                    {row.entry_credit != null ? fmtNum(row.entry_credit) : "n/a"}
                  </TableCell>
                  <TableCell numeric className="font-mono">
                    {row.mark != null ? fmtNum(row.mark) : "n/a"}
                  </TableCell>
                  <TableCell
                    numeric
                    className={
                      isOpen(row) && row.unrealized_pnl != null
                        ? `font-mono ${(row.unrealized_pnl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`
                        : "font-mono text-zinc-500 dark:text-zinc-400"
                    }
                  >
                    {isOpen(row) ? (row.unrealized_pnl != null ? fmtCurrency(row.unrealized_pnl) : "—") : "—"}
                  </TableCell>
                  <TableCell numeric className="font-mono">
                    {fmtPct(row.premium_captured_pct)}
                  </TableCell>
                  <TableCell numeric className="font-mono">
                    {row.dte != null && typeof row.dte === "number" ? String(row.dte) : "n/a"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="neutral">{row.status ?? "OPEN"}</Badge>
                  </TableCell>
                  <TableCell numeric className="font-mono">
                    {(row.status ?? "").toUpperCase() === "CLOSED" || (row.status ?? "").toUpperCase() === "ABORTED"
                      ? fmtCurrency(row.realized_pnl)
                      : "—"}
                  </TableCell>
                  <TableCell>
                    {(row.alert_flags ?? []).length === 0 ? (
                      "n/a"
                    ) : (
                      <span className="flex flex-wrap gap-1">
                        {(row.alert_flags ?? []).map((flag) => (
                          <Badge key={flag} variant={alertBadgeVariant(flag)}>
                            {flag}
                          </Badge>
                        ))}
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-wrap items-center gap-1">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setDetailDrawerPosition(row)}
                      >
                        View
                      </Button>
                      <Link
                        to={
                          row.decision_ref?.run_id
                            ? `/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}&run_id=${encodeURIComponent(row.decision_ref.run_id)}`
                            : `/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`
                        }
                        className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                        title={
                          row.decision_ref?.run_id
                            ? `Decision (run_id ${row.decision_ref.run_id.slice(0, 8)}…)`
                            : "Decision (latest — run not traced)"
                        }
                      >
                        {row.decision_ref?.run_id
                          ? `Decision (run ${row.decision_ref.run_id.slice(0, 8)}…)`
                          : "Decision (latest)"}
                      </Link>
                      {!row.decision_ref?.run_id && (
                        <Badge variant="warning" className="shrink-0">
                          no run
                        </Badge>
                      )}
                      {isOpen(row) && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setCloseDrawerPosition(row)}
                        >
                          Close
                        </Button>
                      )}
                      {canDelete(row) && (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={deletePosition.isPending}
                          onClick={() => {
                            if (window.confirm(`Delete position ${row.symbol} ${row.strategy}?`)) {
                              deletePosition.mutate(row.position_id);
                            }
                          }}
                        >
                          Delete
                        </Button>
                      )}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {closeDrawerPosition && (
        <ClosePositionDrawer
          position={closeDrawerPosition}
          onClose={() => setCloseDrawerPosition(null)}
          onClosed={() => setCloseDrawerPosition(null)}
        />
      )}

      <PortfolioPositionDetailDrawer
        position={detailDrawerPosition}
        open={!!detailDrawerPosition}
        onClose={() => setDetailDrawerPosition(null)}
        onClosed={() => setDetailDrawerPosition(null)}
      />
    </div>
  );
}
