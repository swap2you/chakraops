import { useState } from "react";
import { Link } from "react-router-dom";
import {
  usePortfolio,
  usePortfolioMetrics,
  usePortfolioRisk,
  useRefreshMarks,
  useAccounts,
  useDefaultAccount,
  useDeletePosition,
  useAccountSummary,
  useAccountHoldings,
  useSetBalances,
  useUpsertHolding,
  useDeleteHolding,
} from "@/api/queries";
import type { PortfolioPosition, AccountHolding, SharePositionSummary, OptionsPositionSummary } from "@/api/types";
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
  const { data: accountSummary } = useAccountSummary();
  const { data: accountHoldingsData } = useAccountHoldings();
  const setBalances = useSetBalances();
  const upsertHolding = useUpsertHolding();
  const deleteHolding = useDeleteHolding();
  const deletePosition = useDeletePosition();
  const [closeDrawerPosition, setCloseDrawerPosition] = useState<PortfolioPosition | null>(null);
  const [detailDrawerPosition, setDetailDrawerPosition] = useState<PortfolioPosition | null>(null);
  const [balancesEdit, setBalancesEdit] = useState<{ cash: string; buying_power: string } | null>(null);
  const [holdingForm, setHoldingForm] = useState<{ symbol: string; shares: string; avg_cost: string } | null>(null);
  const [sharesFilter, setSharesFilter] = useState<"all" | "cc_eligible">("all");

  const positions = data?.positions ?? [];
  const capitalDeployed = data?.capital_deployed ?? 0;
  const sharesPositions = data?.shares_positions ?? [];
  const optionsPositions = data?.options_positions ?? [];
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
  // R36.3: display stored account buying_power; never invent from totalCapital - deployed.
  const buyingPower = accountSummary?.buying_power ?? null;

  const isOpen = (p: PortfolioPosition) => {
    const s = (p.status ?? "").toUpperCase();
    return s === "OPEN" || s === "PARTIAL_EXIT";
  };
  const canDelete = (p: PortfolioPosition) =>
    p.is_test === true || (p.status ?? "").toUpperCase() === "CLOSED" || (p.status ?? "").toUpperCase() === "ABORTED";

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Account & Portfolio" subtext="Tracked positions" />
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
        </Card>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Account & Portfolio" />
        <p className="text-red-500 dark:text-red-400">Failed to load portfolio.</p>
      </div>
    );
  }

  const holdings = accountHoldingsData?.holdings ?? [];
  const summary = accountSummary;

  return (
    <div className="space-y-8" data-testid="page-portfolio">
      <PageHeader title="Account & Portfolio" subtext={`${positions.length} position(s) · ${fmtCurrency(capitalDeployed)} deployed`} />

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

      <Card>
        <CardHeader
          title="Balances (manual)"
          description="Manual portfolio snapshot — cash and buying power are user-entered, not broker-synced. Used for CC eligibility and display."
        />
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400" data-testid="portfolio-provenance">
          Provenance: Manual portfolio snapshot · not broker-synced
        </p>
        {summary ? (
          balancesEdit ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 max-w-md">
              <div>
                <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Cash</label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                  value={balancesEdit.cash}
                  onChange={(e) => setBalancesEdit((p) => (p ? { ...p, cash: e.target.value } : null))}
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Buying power</label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                  value={balancesEdit.buying_power}
                  onChange={(e) => setBalancesEdit((p) => (p ? { ...p, buying_power: e.target.value } : null))}
                />
              </div>
              <div className="sm:col-span-2 flex gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    const cash = parseFloat(balancesEdit.cash);
                    const bp = parseFloat(balancesEdit.buying_power);
                    if (!Number.isNaN(cash) && !Number.isNaN(bp)) {
                      setBalances.mutate({ cash, buying_power: bp });
                      setBalancesEdit(null);
                    }
                  }}
                  disabled={setBalances.isPending}
                >
                  {setBalances.isPending ? "Saving…" : "Save"}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setBalancesEdit(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Cash</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtCurrency(summary.cash)}</span>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-400">Buying power</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{fmtCurrency(summary.buying_power)}</span>
              </div>
              <div>
                <Button size="sm" variant="secondary" onClick={() => setBalancesEdit({ cash: String(summary.cash), buying_power: String(summary.buying_power) })}>
                  Edit
                </Button>
              </div>
            </div>
          )
        ) : (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading balances…</p>
        )}
      </Card>

      <Card>
        <CardHeader title="Holdings" description="Manual equity holdings (used for CC eligibility: ≥100 shares)." />
        {holdingForm ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4 max-w-2xl mb-4">
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Symbol</label>
              <input
                type="text"
                placeholder="e.g. AAPL"
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={holdingForm.symbol}
                onChange={(e) => setHoldingForm((p) => (p ? { ...p, symbol: e.target.value.toUpperCase() } : null))}
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Shares</label>
              <input
                type="number"
                min="1"
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={holdingForm.shares}
                onChange={(e) => setHoldingForm((p) => (p ? { ...p, shares: e.target.value } : null))}
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-400 mb-1">Avg cost (optional)</label>
              <input
                type="number"
                step="0.01"
                placeholder="—"
                className="w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-600 dark:bg-zinc-800"
                value={holdingForm.avg_cost}
                onChange={(e) => setHoldingForm((p) => (p ? { ...p, avg_cost: e.target.value } : null))}
              />
            </div>
            <div className="flex items-end gap-2">
              <Button
                size="sm"
                onClick={() => {
                  const symbol = holdingForm.symbol.trim();
                  const shares = parseInt(holdingForm.shares, 10);
                  if (symbol && !Number.isNaN(shares) && shares >= 1) {
                    const avgCost = holdingForm.avg_cost.trim() ? parseFloat(holdingForm.avg_cost) : undefined;
                    upsertHolding.mutate({ symbol, shares, avg_cost: avgCost ?? undefined });
                    setHoldingForm(null);
                  }
                }}
                disabled={upsertHolding.isPending}
              >
                {upsertHolding.isPending ? "Saving…" : "Add"}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setHoldingForm(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="mb-4">
            <Button size="sm" variant="secondary" onClick={() => setHoldingForm({ symbol: "", shares: "", avg_cost: "" })}>
              Add holding
            </Button>
          </div>
        )}
        {holdings.length === 0 ? (
          <EmptyState title="No holdings" message="Add equity holdings for covered-call eligibility (≥100 shares)." />
        ) : (
          <Table>
            <TableHeader>
              <TableHead>Symbol</TableHead>
              <TableHead>Shares</TableHead>
              <TableHead>Avg cost</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead>Actions</TableHead>
            </TableHeader>
            <TableBody>
              {holdings.map((h: AccountHolding) => (
                <TableRow key={h.symbol}>
                  <TableCell className="font-mono font-medium">{h.symbol}</TableCell>
                  <TableCell numeric className="font-mono">{h.shares}</TableCell>
                  <TableCell numeric className="font-mono">{h.avg_cost != null ? fmtNum(h.avg_cost) : "—"}</TableCell>
                  <TableCell className="text-zinc-500 dark:text-zinc-400 text-sm">{h.updated_at ? new Date(h.updated_at).toLocaleString() : "—"}</TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={deleteHolding.isPending}
                      onClick={() => {
                        if (window.confirm(`Remove holding ${h.symbol}?`)) deleteHolding.mutate(h.symbol);
                      }}
                    >
                      Remove
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {sharesPositions.length > 0 && (
        <Card>
          <CardHeader
            title="Shares Positions"
            description="R27.4: Mark and Unrealized P/L. R27.7: CC eligible badge and filter; link to Ticket (CC) when eligible."
            actions={
              <div className="flex gap-1 rounded border border-zinc-200 dark:border-zinc-700 p-0.5">
                <button
                  type="button"
                  onClick={() => setSharesFilter("all")}
                  className={`rounded px-2 py-1 text-sm ${sharesFilter === "all" ? "bg-zinc-200 dark:bg-zinc-700 font-medium" : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"}`}
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setSharesFilter("cc_eligible")}
                  className={`rounded px-2 py-1 text-sm ${sharesFilter === "cc_eligible" ? "bg-zinc-200 dark:bg-zinc-700 font-medium" : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"}`}
                >
                  CC eligible
                </button>
              </div>
            }
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Qty</TableHead>
                <TableHead>Avg cost</TableHead>
                <TableHead>Mark</TableHead>
                <TableHead>Last price</TableHead>
                <TableHead>Market value</TableHead>
                <TableHead>Unrealized P/L</TableHead>
                <TableHead>Unrealized %</TableHead>
                <TableHead>CC</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sharesPositions
                .filter((row: SharePositionSummary) => sharesFilter === "all" || row.cc_eligible === true)
                .map((row: SharePositionSummary) => {
                  const unrealizedPl = row.unrealized_pl ?? row.unrealized_pnl;
                  const markStr =
                    row.mark_value != null
                      ? [fmtCurrency(row.mark_value), row.mark_source ?? "", row.mark_age_sec != null ? `(${row.mark_age_sec}s)` : ""].filter(Boolean).join(" ")
                      : "—";
                  return (
                    <TableRow key={row.symbol}>
                      <TableCell>
                        <Link
                          to={`/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`}
                          className="font-mono font-medium text-zinc-900 dark:text-zinc-200 hover:underline"
                        >
                          {row.symbol}
                        </Link>
                      </TableCell>
                      <TableCell numeric className="font-mono">{row.quantity}</TableCell>
                      <TableCell numeric className="font-mono">{row.avg_cost != null ? fmtNum(row.avg_cost) : "—"}</TableCell>
                      <TableCell className="font-mono text-zinc-700 dark:text-zinc-300">{markStr}</TableCell>
                      <TableCell numeric className="font-mono">{row.last_price != null ? fmtNum(row.last_price) : "—"}</TableCell>
                      <TableCell numeric className="font-mono">{row.market_value != null ? fmtCurrency(row.market_value) : "—"}</TableCell>
                      <TableCell
                        numeric
                        className={`font-mono ${unrealizedPl != null ? (unrealizedPl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400") : ""}`}
                      >
                        {unrealizedPl != null ? fmtCurrency(unrealizedPl) : "—"}
                      </TableCell>
                      <TableCell
                        numeric
                        className={`font-mono ${row.pct_return != null ? (row.pct_return >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400") : ""}`}
                      >
                        {row.pct_return != null ? fmtPct(row.pct_return) : "—"}
                      </TableCell>
                      <TableCell>
                        {row.cc_eligible === true ? (
                          <Badge variant="success">Eligible</Badge>
                        ) : (
                          <span className="text-zinc-400 dark:text-zinc-500 text-xs">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {row.cc_eligible === true ? (
                          <Link
                            to={`/ticket?symbol=${encodeURIComponent(row.symbol)}&strategy=CC&action=OPEN`}
                            className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
                          >
                            Open CC ticket
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </Card>
      )}

      {optionsPositions.length > 0 && (
        <Card>
          <CardHeader
            title="Options Positions"
            description="R27.8: Enriched option positions (mark/source/age, DTE, max profit %, lifecycle recommend+reason)."
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Strategy</TableHead>
                <TableHead>Strike</TableHead>
                <TableHead>Expiry</TableHead>
                <TableHead>DTE</TableHead>
                <TableHead>Mark</TableHead>
                <TableHead>Unrealized P/L</TableHead>
                <TableHead>Max profit %</TableHead>
                <TableHead>Recommend</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {optionsPositions.map((row: OptionsPositionSummary) => {
                const markStr =
                  row.mark_value != null
                    ? [fmtCurrency(row.mark_value), row.mark_source ?? "", row.mark_age_sec != null ? `(${row.mark_age_sec}s)` : ""].filter(Boolean).join(" ")
                    : "—";
                return (
                  <TableRow key={row.position_id}>
                    <TableCell>
                      <Link
                        to={`/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`}
                        className="font-mono font-medium text-zinc-900 dark:text-zinc-200 hover:underline"
                      >
                        {row.symbol}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono">{row.strategy ?? "—"}</TableCell>
                    <TableCell numeric className="font-mono">{row.strike != null ? fmtNum(row.strike) : "—"}</TableCell>
                    <TableCell className="font-mono text-zinc-700 dark:text-zinc-300">{row.expiration ?? "—"}</TableCell>
                    <TableCell numeric className="font-mono">{row.dte != null ? row.dte : "—"}</TableCell>
                    <TableCell className="font-mono text-zinc-700 dark:text-zinc-300">{markStr}</TableCell>
                    <TableCell
                      numeric
                      className={`font-mono ${row.unrealized_pnl != null ? (row.unrealized_pnl >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400") : ""}`}
                    >
                      {row.unrealized_pnl != null ? fmtCurrency(row.unrealized_pnl) : "—"}
                    </TableCell>
                    <TableCell numeric className="font-mono">{row.pct_max_profit != null ? fmtPct(row.pct_max_profit) : "—"}</TableCell>
                    <TableCell>
                      <Badge variant={row.lifecycle_recommend === "Close" ? "danger" : row.lifecycle_recommend === "Roll" ? "warning" : "neutral"}>
                        {row.lifecycle_recommend ?? "—"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-zinc-600 dark:text-zinc-400 text-sm">{row.lifecycle_reason ?? "—"}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Link
                          to={`/ticket?symbol=${encodeURIComponent(row.symbol)}&strategy=${encodeURIComponent(row.strategy || "CSP")}&action=CLOSE`}
                          className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
                        >
                          Open Ticket
                        </Link>
                        <Link
                          to={`/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`}
                          className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
                        >
                          Open Symbol
                        </Link>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      {accounts.length > 0 && (
        <Card>
          <CardHeader
            title="Account"
            description="Manual portfolio snapshot — balances are user-entered; Robinhood sync is NO-GO (not broker-synced)."
          />
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Account</span>
              <span className="font-mono font-medium text-zinc-900 dark:text-zinc-200">{selectedAccount ? (selectedAccount as { account_id?: string }).account_id : "—"}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">Source</span>
              <span className="text-zinc-700 dark:text-zinc-300">Manual portfolio snapshot</span>
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
                {riskData.status === "PASS" ? "Passed" : riskData.status === "WARN" ? "Degraded" : "Blocked"}
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
          <>
            <EmptyState
              title="No positions"
              message="Track positions via Trade Ticket (Symbol page) or manual execution."
            />
            {(accounts.length > 0 || (accountHoldingsData?.holdings?.length ?? 0) > 0) && (
              <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400 rounded border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/50 px-3 py-2">
                <strong>Data reset likely.</strong> Positions are empty. If you deleted state files, re-add positions via Trade Ticket or import. See docs for cleanup policy.
              </p>
            )}
          </>
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
