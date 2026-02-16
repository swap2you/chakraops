import { useState } from "react";
import { X, Copy, Check, Bookmark } from "lucide-react";
import { Button } from "@/components/ui";
import { useDefaultAccount, useManualExecute } from "@/api/queries";
import type { SymbolDiagnosticsCandidate } from "@/api/types";

interface TradeTicketDrawerProps {
  symbol: string;
  candidate: SymbolDiagnosticsCandidate;
  onClose: () => void;
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

export function TradeTicketDrawer({ symbol, candidate, onClose }: TradeTicketDrawerProps) {
  const [qty, setQty] = useState(1);
  const [copied, setCopied] = useState(false);
  const { data: accountData } = useDefaultAccount();
  const manualExecute = useManualExecute();
  const defaultAccount = accountData?.account ?? null;

  const strike = candidate.strike ?? 0;
  const notional = strike * 100 * qty;
  const credit = (candidate.credit_estimate ?? 0) * qty;

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
    manualExecute.mutate(
      {
        account_id: defaultAccount.account_id,
        symbol: symbol.toUpperCase(),
        strategy,
        contracts: qty,
        strike: candidate.strike ?? undefined,
        expiration: candidate.expiry ?? undefined,
        credit_expected: credit,
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
                onChange={(e) => setQty(Math.max(1, parseInt(e.target.value, 10) || 1))}
                className="mt-1 w-24 rounded border border-zinc-300 bg-white px-2 py-1.5 font-mono text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              />
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Notional</span>
              <p className="font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                ${notional.toLocaleString()}
              </p>
            </div>
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
              Set a default account to track positions.
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
