/**
 * R53: Broker live portfolio panel — Robinhood MCP read-only snapshot (masked).
 * Manual edit controls must not appear here.
 */
import { useBrokerAccounts, useBrokerSnapshot, useBrokerStatus } from "@/api/queries";
import { Badge, Button, Card, CardHeader, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, EmptyState } from "@/components/ui";

function fmtMoney(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function BrokerLivePanel() {
  const { data: status, isLoading: stLoading, refetch: refetchStatus } = useBrokerStatus();
  const { data: accountsData, refetch: refetchAccounts } = useBrokerAccounts();
  const { data: snapData, isLoading: snapLoading, refetch: refetchSnap } = useBrokerSnapshot("acct_individual", false);

  const statusCode = status?.status ?? "UNKNOWN";
  const available = Boolean(status?.ROBINHOOD_MCP_READ_ONLY_AVAILABLE);
  const snap = snapData?.snapshot;
  const balances = snap?.balances;
  const equities = snap?.equity_positions ?? [];
  const options = snap?.option_positions ?? [];
  const stale = Boolean(snapData?.stale ?? snap?.stale);

  return (
    <div className="space-y-4" data-testid="broker-live-panel">
      <Card data-testid="broker-live-status">
        <CardHeader
          title="Live broker portfolio (Robinhood MCP read-only)"
          description="Primary live source when authenticated. Manual balances below are not live. No broker writes."
        />
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge variant={available ? "success" : "warning"} data-testid="broker-status-badge">
            {statusCode}
          </Badge>
          {stale ? <Badge variant="warning" data-testid="broker-stale-badge">STALE</Badge> : null}
          <span className="text-xs text-zinc-500 dark:text-zinc-400" data-testid="broker-status-reason">
            {status?.reason ?? (stLoading ? "Loading…" : "—")}
          </span>
          <Button
            variant="secondary"
            size="sm"
            data-testid="broker-refresh-btn"
            onClick={() => {
              void refetchStatus();
              void refetchAccounts();
              void refetchSnap();
            }}
          >
            Refresh status
          </Button>
        </div>
        {!available && (
          <p className="mt-3 text-xs text-amber-700 dark:text-amber-300" data-testid="broker-auth-blocker">
            Runtime OAuth token not configured ({status?.blocker ?? "ROBINHOOD_RUNTIME_AUTH_EXTERNAL_BLOCKER"}).
            Last-good snapshot shown when present. Cursor MCP auth ≠ production token.
          </p>
        )}
      </Card>

      <Card data-testid="broker-accounts-card">
        <CardHeader title="Accounts (masked)" description="Aliases only — full account numbers never shown." />
        {(accountsData?.accounts?.length ?? 0) === 0 ? (
          <EmptyState title="No broker accounts loaded" description="Authenticate read-only MCP or use last-good snapshot." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alias</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Masked #</TableHead>
                <TableHead>Name</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(accountsData?.accounts ?? []).map((a) => (
                <TableRow key={a.alias}>
                  <TableCell className="font-mono">{a.alias}</TableCell>
                  <TableCell>{a.account_type}</TableCell>
                  <TableCell className="font-mono">{a.masked_account_number}</TableCell>
                  <TableCell>{a.display_name}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Card data-testid="broker-snapshot-card">
        <CardHeader
          title="acct_individual snapshot"
          description={snapLoading ? "Loading…" : `Fetched ${snap?.fetched_at ?? "—"} · completeness ${snap?.completeness ?? "—"}`}
        />
        <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4" data-testid="broker-balances">
          <div>
            <span className="block text-xs text-zinc-500">Cash</span>
            <span className="font-mono font-medium">{fmtMoney(balances?.cash)}</span>
          </div>
          <div>
            <span className="block text-xs text-zinc-500">Buying power</span>
            <span className="font-mono font-medium">{fmtMoney(balances?.buying_power)}</span>
          </div>
          <div>
            <span className="block text-xs text-zinc-500">Equity</span>
            <span className="font-mono font-medium">{fmtMoney(balances?.equity)}</span>
          </div>
          <div>
            <span className="block text-xs text-zinc-500">Market value</span>
            <span className="font-mono font-medium">{fmtMoney(balances?.market_value)}</span>
          </div>
        </div>

        <h3 className="mt-4 text-sm font-medium text-zinc-800 dark:text-zinc-200">Equity holdings</h3>
        {equities.length === 0 ? (
          <p className="text-xs text-zinc-500" data-testid="broker-equities-empty">No equity positions in snapshot (zero remains zero).</p>
        ) : (
          <Table data-testid="broker-equities-table">
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Qty</TableHead>
                <TableHead>Avg cost</TableHead>
                <TableHead>Mkt value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {equities.map((p) => (
                <TableRow key={`${p.symbol}-${p.quantity}`}>
                  <TableCell className="font-mono">{p.symbol}</TableCell>
                  <TableCell className="font-mono">{p.quantity}</TableCell>
                  <TableCell className="font-mono">{fmtMoney(p.average_cost)}</TableCell>
                  <TableCell className="font-mono">{fmtMoney(p.market_value)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <h3 className="mt-4 text-sm font-medium text-zinc-800 dark:text-zinc-200">Option positions</h3>
        {options.length === 0 ? (
          <p className="text-xs text-zinc-500" data-testid="broker-options-empty">No option positions in snapshot.</p>
        ) : (
          <Table data-testid="broker-options-table">
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Strike</TableHead>
                <TableHead>Qty</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {options.map((p, i) => (
                <TableRow key={`${p.symbol}-${p.strike}-${i}`}>
                  <TableCell className="font-mono">{p.symbol}</TableCell>
                  <TableCell>{p.option_type}</TableCell>
                  <TableCell className="font-mono">{p.strike ?? "—"}</TableCell>
                  <TableCell className="font-mono">{p.quantity}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
