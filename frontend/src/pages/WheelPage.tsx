import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Ticket, Wrench } from "lucide-react";
import {
  useWheelOverview,
  useDefaultAccount,
  useAccounts,
  useWheelAssign,
  useWheelUnassign,
  useWheelReset,
  useWheelRepair,
} from "@/api/queries";
import type { WheelOverviewRow, WheelOverviewSuggestedCandidate } from "@/api/queries";
import type { SymbolDiagnosticsCandidate } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { TradeTicketDrawer } from "@/components/TradeTicketDrawer";
import {
  Card,
  CardHeader,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  Badge,
  Button,
  EmptyState,
} from "@/components/ui";
import { formatTimestampEt } from "@/utils/formatTimestamp";

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function suggestedToCandidate(sc: WheelOverviewSuggestedCandidate | null | undefined): SymbolDiagnosticsCandidate | null {
  if (!sc) return null;
  return {
    strategy: sc.strategy ?? "CSP",
    strike: sc.strike ?? undefined,
    expiry: sc.expiry ?? undefined,
    delta: sc.delta ?? undefined,
    credit_estimate: sc.credit_estimate ?? undefined,
    max_loss: sc.max_loss ?? undefined,
    contract_key: sc.contract_key ?? undefined,
    option_symbol: sc.option_symbol ?? undefined,
  };
}

export function WheelPage() {
  const { data: accountsData } = useAccounts();
  const { data: defaultAccountData } = useDefaultAccount();
  const accounts = accountsData?.accounts ?? [];
  const defaultAccount = defaultAccountData?.account;
  const selectedAccount = defaultAccount ?? (accounts.length > 0 ? accounts[0] : null);
  const accountId = (selectedAccount as { account_id?: string })?.account_id ?? null;

  const { data, isLoading, isError } = useWheelOverview(accountId, !!selectedAccount);
  const [openTicket, setOpenTicket] = useState<{ symbol: string; row: WheelOverviewRow } | null>(null);
  const [repairConfirmed, setRepairConfirmed] = useState(false);
  const wheelAssign = useWheelAssign();
  const wheelUnassign = useWheelUnassign();
  const wheelReset = useWheelReset();
  const wheelRepair = useWheelRepair();

  const symbols = data?.symbols ?? {};
  const rows = Object.values(symbols);
  const riskStatus = data?.risk_status ?? "PASS";
  const runId = data?.run_id ?? null;
  const wheelIntegrity = data?.wheel_integrity;
  const integrityFail = wheelIntegrity?.status === "FAIL";
  const repairEnabled = integrityFail || repairConfirmed;

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Wheel" subtext="Lifecycle automation" />
        <Card>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
        </Card>
      </div>
    );
  }

  if (isError || data?.error) {
    return (
      <div>
        <PageHeader title="Wheel" />
        <p className="text-red-500 dark:text-red-400">{data?.error ?? "Failed to load wheel overview."}</p>
      </div>
    );
  }

  const candidate = openTicket ? suggestedToCandidate(openTicket.row.suggested_candidate) : null;
  const canOpenTicket = candidate && (openTicket?.row.next_action.suggested_contract_key || candidate.contract_key);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Wheel"
        subtext={`${rows.length} symbol(s) · Risk: ${riskStatus}`}
      />

      {/* Phase 20.0: Repair wheel state — enabled when integrity FAIL or user confirms */}
      <Card>
        <CardHeader
          title="Wheel state"
          description={integrityFail ? (wheelIntegrity?.recommended_action ?? "Wheel state does not match open positions.") : "Repair rebuilds wheel_state from open positions and recent actions."}
        />
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
            <input
              type="checkbox"
              checked={repairConfirmed}
              onChange={(e) => setRepairConfirmed(e.target.checked)}
              className="rounded border-zinc-300 dark:border-zinc-600"
            />
            Run repair anyway (even if integrity is PASS)
          </label>
          <Button
            variant="outline"
            size="sm"
            disabled={!repairEnabled || wheelRepair.isPending}
            onClick={() => wheelRepair.mutate()}
            className="gap-1"
          >
            <Wrench className="h-4 w-4" />
            Repair wheel state
          </Button>
          {wheelRepair.isError && (
            <span className="text-sm text-red-500 dark:text-red-400">{String(wheelRepair.error)}</span>
          )}
          {wheelRepair.data && (
            <span className="text-sm text-emerald-600 dark:text-emerald-400">
              Repaired: {wheelRepair.data.repaired_symbols?.length ?? 0}, removed: {wheelRepair.data.removed_symbols?.length ?? 0}
            </span>
          )}
        </div>
      </Card>

      {rows.length === 0 ? (
        <Card>
          <EmptyState
            title="No wheel symbols"
            description="Add positions or run evaluation to populate wheel state."
          />
        </Card>
      ) : (
        <Card>
          <CardHeader title="Symbols" description="Wheel state, next action, and suggested contract" />
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableHead>Symbol</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead>Open Position</TableHead>
                <TableHead>Next Action</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Score</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableHeader>
              <TableBody>
                {rows.map((row) => {
                  const actionType = row.next_action.action_type ?? "NONE";
                  const canOpen = (actionType === "OPEN_TICKET" || actionType === "REASSIGN") && !row.next_action.blocked_by?.length;
                  const pos = row.open_position;
                  const symbolLink = runId
                    ? `/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}&run_id=${encodeURIComponent(runId)}`
                    : `/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`;
                  const portfolioLink = pos?.position_id ? `/portfolio` : null;

                  return (
                    <TableRow key={row.symbol}>
                      <TableCell>
                        <Link
                          to={symbolLink}
                          className="font-mono font-medium text-emerald-600 hover:underline dark:text-emerald-400"
                        >
                          {row.symbol}
                        </Link>
                        {runId && (
                          <Link
                            to={symbolLink}
                            className="ml-1 inline-block text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
                            aria-label="Symbol diagnostics"
                          >
                            <ExternalLink className="h-3 w-3" />
                          </Link>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={row.wheel_state === "OPEN" ? "success" : row.wheel_state === "CLOSED" ? "neutral" : "warning"}>
                          {row.wheel_state}
                        </Badge>
                        {row.manual_override && (
                          <span className="ml-1 text-xs text-zinc-500 dark:text-zinc-400" title="Manual override">(manual)</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          {row.last_updated_utc ? formatTimestampEt(row.last_updated_utc) : "—"}
                        </span>
                      </TableCell>
                      <TableCell>
                        {pos ? (
                          portfolioLink ? (
                            <Link to={portfolioLink} className="font-mono text-sm text-zinc-700 hover:underline dark:text-zinc-300">
                              {pos.contract_key ?? pos.position_id ?? "—"}
                            </Link>
                          ) : (
                            <span className="font-mono text-sm">{pos.contract_key ?? pos.position_id ?? "—"}</span>
                          )
                        ) : (
                          <span className="text-zinc-400">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <span className="text-sm">{actionType}</span>
                          {row.next_action.reasons?.length ? (
                            <span className="text-xs text-zinc-500 dark:text-zinc-400">
                              {row.next_action.reasons[0]}
                            </span>
                          ) : null}
                          {row.next_action.blocked_by?.length ? (
                            <div className="flex flex-wrap gap-1 mt-0.5">
                              {row.next_action.blocked_by.map((b) => (
                                <Badge key={b} variant="danger" className="text-xs">
                                  {b}
                                </Badge>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={row.risk_status === "PASS" ? "success" : row.risk_status === "WARN" ? "warning" : "danger"}>
                          {row.risk_status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="font-mono text-sm">{row.last_decision_score != null ? fmt(row.last_decision_score) : "—"}</span>
                        {row.last_decision_band && (
                          <Badge variant="neutral" className="ml-1">
                            {row.last_decision_band}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap justify-end gap-1">
                          {/* Phase 20.0: Assign when EMPTY; Unassign when ASSIGNED; Reset when CLOSED or any */}
                          {row.wheel_state === "EMPTY" && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={wheelAssign.isPending}
                              onClick={() => wheelAssign.mutate(row.symbol)}
                            >
                              Assign
                            </Button>
                          )}
                          {(row.wheel_state === "ASSIGNED" || row.wheel_state === "OPEN") && (
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={wheelUnassign.isPending}
                              onClick={() => wheelUnassign.mutate(row.symbol)}
                            >
                              Unassign
                            </Button>
                          )}
                          {(row.wheel_state === "CLOSED" || row.wheel_state === "ASSIGNED" || row.wheel_state === "OPEN") && (
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={wheelReset.isPending}
                              onClick={() => wheelReset.mutate(row.symbol)}
                              className="text-zinc-500"
                            >
                              Reset
                            </Button>
                          )}
                          {canOpen && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setOpenTicket({ symbol: row.symbol, row })}
                              className="gap-1"
                            >
                              <Ticket className="h-4 w-4" />
                              Open ticket
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      )}

      {openTicket && candidate && canOpenTicket && (
        <TradeTicketDrawer
          symbol={openTicket.symbol}
          candidate={candidate}
          onClose={() => setOpenTicket(null)}
          decisionRef={runId ? { run_id: runId } : undefined}
        />
      )}
    </div>
  );
}
