/**
 * Phase 10.0: Close position drawer — captures close price and submits close endpoint.
 */
import { useState } from "react";
import { useClosePosition } from "@/api/queries";
import type { PortfolioPosition } from "@/api/types";
import { Loader2 } from "lucide-react";

export interface ClosePositionDrawerProps {
  position: PortfolioPosition;
  onClose: () => void;
  onClosed: () => void;
}

export function ClosePositionDrawer({ position, onClose, onClosed }: ClosePositionDrawerProps) {
  const [closePrice, setClosePrice] = useState("");
  const [closeFees, setCloseFees] = useState("");
  const closePosition = useClosePosition();
  const posId = position.id ?? position.position_id;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const price = parseFloat(closePrice);
    if (Number.isNaN(price) || price < 0) return;
    const fees = closeFees ? parseFloat(closeFees) : undefined;
    closePosition.mutate(
      { positionId: posId, close_price: price, close_fees: fees },
      {
        onSuccess: () => {
          onClosed();
        },
      }
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="close-position-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-full max-w-md rounded-lg border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="close-position-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
          Close position — {position.symbol} {position.strategy}
        </h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Enter the debit price per share to buy back the option.
        </p>
        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label htmlFor="close-price" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Close price (required)
            </label>
            <input
              id="close-price"
              type="number"
              step="0.01"
              min="0"
              value={closePrice}
              onChange={(e) => setClosePrice(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="e.g. 1.25"
              required
            />
          </div>
          <div>
            <label htmlFor="close-fees" className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Close fees (optional)
            </label>
            <input
              id="close-fees"
              type="number"
              step="0.01"
              min="0"
              value={closeFees}
              onChange={(e) => setCloseFees(e.target.value)}
              className="mt-1 w-full rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
              placeholder="e.g. 0.65"
            />
          </div>
          {closePosition.isError && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {(closePosition.error as { message?: string })?.message ?? "Failed to close position."}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-3 border-t border-zinc-200 dark:border-zinc-700">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={closePosition.isPending || !closePrice}
              className="flex items-center gap-2 rounded bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {closePosition.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Close position
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
