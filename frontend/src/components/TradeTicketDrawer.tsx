import { useState } from "react";
import { X, Copy, Check, Bookmark } from "lucide-react";
import { Button } from "@/components/ui";
import { useDefaultAccount, useManualExecute, useSavePaperPosition, useUiTrackedPositions } from "@/api/queries";
import type { SymbolDiagnosticsCandidate } from "@/api/types";
import type { DecisionRef } from "@/api/queries";

interface TradeTicketDrawerProps {
  symbol: string;
  candidate: SymbolDiagnosticsCandidate;
  onClose: () => void;
  /** Phase 11.0: Decision reference for save payload */
  decisionRef?: DecisionRef | null;
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

const defaultCredit = (c: SymbolDiagnosticsCandidate, q: number) =>
  (c.credit_estimate ?? 0) * q;

export function TradeTicketDrawer({ symbol, candidate, onClose, decisionRef }: TradeTicketDrawerProps) {
  const [qty, setQty] = useState(1);
  const [entryCredit, setEntryCredit] = useState(defaultCredit(candidate, 1));
  const [copied, setCopied] = useState(false);
  const { data: accountData } = useDefaultAccount();
  const { data: positionsData } = useUiTrackedPositions();
  const manualExecute = useManualExecute();
  const savePaperPosition = useSavePaperPosition();
  const defaultAccount = accountData?.account ?? null;

  const strike = candidate.strike ?? 0;
  const notional = strike * 100 * qty;
  const collateral = notional;
  const credit = entryCredit;
  const capitalDeployed = positionsData?.capital_deployed ?? 0;
  const openCount = positionsData?.open_positions_count ?? 0;
  const maxPerTrade = (defaultAccount as { max_collateral_per_trade?: number } | null)?.max_collateral_per_trade;
  const maxTotal = (defaultAccount as { max_total_collateral?: number } | null)?.max_total_collateral;
  const maxPositions = (defaultAccount as { max_positions_open?: number } | null)?.max_positions_open;
  const remainingCapacity = maxTotal != null ? Math.max(0, maxTotal - capitalDeployed) : null;

  const orderText = [
    `Symbol: ${symbol}`,
    `Strategy: ${candidate.strategy ?? "CSP"}`,
    `Expiry: ${candidate.expiry ?? "—"}`,
    `Strike: ${fmt(candidate.strike)}`,
    `Delta: ${candidate.delta != null ? candidate.delta.toFixed(3) : "—"}`,
    `Quantity: ${qty} contract(s)`,
    `Credit: $${fmt(credit)}`,
    `Notional: $${notional.toLocaleString()}`,
    `Max loss: $${fmt((candidate.max_loss ?? 0) * qty)}`,
  ].join("\n");

  const handleCopy = async () => {
    await navigator.clipboard.writeText(orderText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleMarkAsTracked = () => {
    if (!defaultAccount?.account_id) return;
    const strategy = (candidate.strategy ?? "CSP").toUpperCase();
    const fillCredit = Number.isFinite(credit) ? credit : defaultCredit(candidate, qty);
    manualExecute.mutate(
      {
        account_id: defaultAccount.account_id,
        symbol: symbol.toUpperCase(),
        strategy,
        contracts: qty,
        strike: candidate.strike ?? undefined,
        expiration: candidate.expiry ?? undefined,
        credit_expected: fillCredit,
        entry_credit: fillCredit,
      },
      {
        onSuccess: () => onClose(),
        onError: () => {},
      }
    );
  };

  const handleSavePosition = () => {
    const strategy = (candidate.strategy ?? "CSP").toUpperCase();
    const fillCredit = Number.isFinite(credit) ? credit : defaultCredit(candidate, qty);
    const exp = candidate.expiry ?? undefined;
    const stk = candidate.strike ?? undefined;
    const contractKey =
      candidate.contract_key ??
      (stk && exp && strategy ? `${stk}-${String(exp).slice(0, 10)}-${strategy === "CSP" ? "PUT" : "CALL"}` : undefined);
    savePaperPosition.mutate(
      {
        symbol: symbol.toUpperCase(),
        strategy,
        contracts: qty,
        strike: stk,
        expiration: exp,
        credit_expected: fillCredit,
        open_credit: fillCredit,
        max_loss: candidate.max_loss != null ? candidate.max_loss * qty : undefined,
        contract_key: contractKey,
        decision_ref: decisionRef ?? undefined,
      },
      {
        onSuccess: () => onClose(),
        onError: () => {},
      }
    );
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30 transition-opacity"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-950"
        role="dialog"
        aria-label="Trade ticket"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 p-4 dark:border-zinc-800">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">Trade Ticket</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-5">
          <div className="space-y-4">
            <div>
              <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-500">Contract</span>
              <p className="font-mono text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                {symbol} · {(candidate.strategy ?? "CSP").toUpperCase()} {fmt(candidate.strike)} {candidate.expiry ?? ""} · {qty} contract{qty !== 1 ? "s" : ""}
              </p>
            </div>
            <div>
              <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-500">Underlying</span>
              <p className="font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-100">{symbol}</p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Strategy</span>
                <p className="font-mono text-zinc-900 dark:text-zinc-200">{candidate.strategy ?? "CSP"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Expiry</span>
                <p className="font-mono text-zinc-900 dark:text-zinc-200">{candidate.expiry ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Strike</span>
                <p className="font-mono text-zinc-900 dark:text-zinc-200">{fmt(candidate.strike)}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Delta</span>
                <p className="font-mono text-zinc-900 dark:text-zinc-200">
                  {candidate.delta != null ? candidate.delta.toFixed(3) : "—"}
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Credit / contract</span>
                <p className="font-mono text-zinc-900 dark:text-zinc-200">${fmt(candidate.credit_estimate)}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Max loss / contract</span>
                <p className="font-mono text-zinc-900 dark:text-zinc-200">${fmt(candidate.max_loss)}</p>
              </div>
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-500">Quantity</label>
              <input
                type="number"
                min={1}
                max={100}
                value={qty}
                onChange={(e) => {
                  const nextQty = Math.max(1, parseInt(e.target.value, 10) || 1);
                  setQty(nextQty);
                  setEntryCredit(defaultCredit(candidate, nextQty));
                }}
                className="mt-1 w-24 rounded border border-zinc-300 bg-white px-2 py-1.5 font-mono text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 dark:text-zinc-500">Entry credit (actual fill)</label>
              <input
                type="number"
                step={0.01}
                min={0}
                value={entryCredit}
                onChange={(e) => setEntryCredit(parseFloat(e.target.value) || 0)}
                className="mt-1 w-28 rounded border border-zinc-300 bg-white px-2 py-1.5 font-mono text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              />
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Notional / Collateral</span>
              <p className="font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                ${notional.toLocaleString()}
              </p>
            </div>
            {(maxPerTrade != null || maxTotal != null || maxPositions != null) && (
              <div className="space-y-1 rounded border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-700 dark:bg-zinc-900/50">
                <span className="block font-medium text-zinc-600 dark:text-zinc-400">Sizing</span>
                {maxPerTrade != null && (
                  <p>
                    Max per trade: ${maxPerTrade.toLocaleString()}
                    {collateral > maxPerTrade && (
                      <span className="ml-1 text-red-600 dark:text-red-400">(exceeded)</span>
                    )}
                  </p>
                )}
                {maxTotal != null && (
                  <p>
                    Remaining capacity: ${(remainingCapacity ?? 0).toLocaleString()}
                    {remainingCapacity != null && collateral > remainingCapacity && (
                      <span className="ml-1 text-red-600 dark:text-red-400">(exceeded)</span>
                    )}
                  </p>
                )}
                {maxPositions != null && (
                  <p>
                    Open positions: {openCount} / {maxPositions}
                    {openCount >= maxPositions && (
                      <span className="ml-1 text-red-600 dark:text-red-400">(limit reached)</span>
                    )}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="space-y-2 border-t border-zinc-200 p-4 dark:border-zinc-800">
          <Button
            variant="primary"
            className="w-full"
            onClick={handleCopy}
          >
            {copied ? (
              <>
                <Check className="mr-2 h-4 w-4" />
                Copied
              </>
            ) : (
              <>
                <Copy className="mr-2 h-4 w-4" />
                Copy order
              </>
            )}
          </Button>
          <Button
            variant="primary"
            className="w-full"
            onClick={handleSavePosition}
            disabled={savePaperPosition.isPending}
          >
            <Bookmark className="mr-2 h-4 w-4" />
            {savePaperPosition.isPending ? "Saving…" : "Save Position"}
          </Button>
          <Button
            variant="secondary"
            className="w-full"
            onClick={handleMarkAsTracked}
            disabled={!defaultAccount?.account_id || manualExecute.isPending}
          >
            <Bookmark className="mr-2 h-4 w-4" />
            {manualExecute.isPending ? "Saving…" : "Mark as tracked"}
          </Button>
          {!defaultAccount?.account_id && (
            <p className="text-center text-xs text-zinc-500 dark:text-zinc-400">
              Set a default account to track positions (Mark as tracked).
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
