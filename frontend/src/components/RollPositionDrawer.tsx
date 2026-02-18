/**
 * Phase 13.0: Roll position drawer — close old + open new position with new contract identity.
 */
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useRollPosition } from "@/api/queries";
import type { PortfolioPosition } from "@/api/types";

export interface RollPositionDrawerProps {
  position: PortfolioPosition;
  onClose: () => void;
  onSuccess?: () => void;
}

export function RollPositionDrawer({ position, onClose, onSuccess }: RollPositionDrawerProps) {
  const [contractKey, setContractKey] = useState("");
  const [optionSymbol, setOptionSymbol] = useState("");
  const [strike, setStrike] = useState("");
  const [expiration, setExpiration] = useState("");
  const [contracts, setContracts] = useState(String(position.contracts ?? 1));
  const [closeDebit, setCloseDebit] = useState("");
  const [openCredit, setOpenCredit] = useState("");

  const rollPosition = useRollPosition(position.id ?? position.position_id);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cKey = contractKey.trim() || undefined;
    const oSym = optionSymbol.trim() || undefined;
    if (!cKey && !oSym) return;
    const stk = strike ? parseFloat(strike) : undefined;
    const exp = (expiration || position.expiry)?.trim() || undefined;
    const ct = contracts ? parseInt(contracts, 10) : 1;
    const cDeb = parseFloat(closeDebit);
    const oCred = parseFloat(openCredit);
    if (!Number.isFinite(cDeb) || !Number.isFinite(oCred)) return;

    rollPosition.mutate(
      {
        contract_key: cKey,
        option_symbol: oSym,
        strike: stk,
        expiration: exp,
        expiry: exp,
        contracts: ct,
        close_debit: cDeb,
        open_credit: oCred,
      },
      {
        onSuccess: () => {
          onSuccess?.();
        },
      }
    );
  };

  const canSubmit =
    (!!contractKey.trim() || !!optionSymbol.trim()) &&
    closeDebit !== "" &&
    openCredit !== "" &&
    !Number.isNaN(parseFloat(closeDebit)) &&
    !Number.isNaN(parseFloat(openCredit));

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="roll-position-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="roll-position-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Roll position — {position.symbol} {position.strategy}
        </h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Close this position and open a new one with the new contract. Provide at least contract_key or option_symbol
          for the new position.
        </p>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label htmlFor="roll-contract-key" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              New contract key (optional if option_symbol provided)
            </label>
            <input
              id="roll-contract-key"
              type="text"
              value={contractKey}
              onChange={(e) => setContractKey(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="e.g. AAPL250117C00150000"
            />
          </div>
          <div>
            <label htmlFor="roll-option-symbol" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              New option symbol (optional if contract_key provided)
            </label>
            <input
              id="roll-option-symbol"
              type="text"
              value={optionSymbol}
              onChange={(e) => setOptionSymbol(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="e.g. AAPL  250117C00150000"
            />
          </div>
          <div>
            <label htmlFor="roll-strike" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              New strike
            </label>
            <input
              id="roll-strike"
              type="number"
              step="0.01"
              min="0"
              value={strike}
              onChange={(e) => setStrike(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder={position.strike != null ? String(position.strike) : "e.g. 150"}
            />
          </div>
          <div>
            <label htmlFor="roll-expiration" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              New expiration (YYYY-MM-DD)
            </label>
            <input
              id="roll-expiration"
              type="text"
              value={expiration}
              onChange={(e) => setExpiration(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder={position.expiry ?? "e.g. 2025-03-21"}
            />
          </div>
          <div>
            <label htmlFor="roll-contracts" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Contracts
            </label>
            <input
              id="roll-contracts"
              type="number"
              min="1"
              value={contracts}
              onChange={(e) => setContracts(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            />
          </div>
          <div>
            <label htmlFor="roll-close-debit" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Close debit (total to buy back)
            </label>
            <input
              id="roll-close-debit"
              type="number"
              step="0.01"
              min="0"
              value={closeDebit}
              onChange={(e) => setCloseDebit(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="e.g. 125.00"
              required
            />
          </div>
          <div>
            <label htmlFor="roll-open-credit" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Open credit (total credit for new position)
            </label>
            <input
              id="roll-open-credit"
              type="number"
              step="0.01"
              min="0"
              value={openCredit}
              onChange={(e) => setOpenCredit(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="e.g. 200.00"
              required
            />
          </div>
          {rollPosition.isError && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {(rollPosition.error as { message?: string })?.message ?? "Failed to roll position."}
            </p>
          )}
          <div className="flex justify-end gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-700">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={rollPosition.isPending || !canSubmit}
              className="flex items-center gap-2 rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {rollPosition.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Roll position
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
