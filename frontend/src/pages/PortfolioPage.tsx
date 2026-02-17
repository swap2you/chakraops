import { useState } from "react";
import { Link } from "react-router-dom";
import { usePortfolio, useAccounts, useDefaultAccount, useClosePosition, useDeletePosition } from "@/api/queries";
import type { PortfolioPosition } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { ClosePositionDrawer } from "@/components/ClosePositionDrawer";
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
  const { data: accountsData } = useAccounts();
  const { data: defaultAccountData } = useDefaultAccount();
  const deletePosition = useDeletePosition();
  const [closeDrawerPosition, setCloseDrawerPosition] = useState<PortfolioPosition | null>(null);

  const positions = data?.positions ?? [];
  const capitalDeployed = data?.capital_deployed ?? 0;
  const openPositionsCount = data?.open_positions_count ?? positions.filter((p) => (p.status ?? "").toUpperCase() === "OPEN" || (p.status ?? "").toUpperCase() === "PARTIAL_EXIT").length;

  const accounts = accountsData?.accounts ?? [];
  const defaultAccount = defaultAccountData?.account;
  const selectedAccount = defaultAccount ?? (accounts.length > 0 ? accounts[0] : null);
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

      <Card>
        <CardHeader title="Positions" />
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
              <TableHead>Premium captured</TableHead>
              <TableHead>DTE</TableHead>
              <TableHead>Status</TableHead>
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
                  <TableCell numeric className="font-mono">
                    {fmtPct(row.premium_captured_pct)}
                  </TableCell>
                  <TableCell numeric className="font-mono">
                    {row.dte != null && typeof row.dte === "number" ? String(row.dte) : "n/a"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="neutral">{row.status ?? "OPEN"}</Badge>
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
                    <span className="flex flex-wrap gap-1">
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
    </div>
  );
}
