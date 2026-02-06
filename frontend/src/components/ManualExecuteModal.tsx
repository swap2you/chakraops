/**
 * Phase 1: Manual Execute Modal — records a manual execution as a tracked position.
 * 
 * IMPORTANT: This does NOT place a trade. It records the user's intention to execute.
 * The user must execute the actual trade in their brokerage account.
 */
import { useState, useEffect, useCallback } from "react";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { pushSystemNotification } from "@/lib/notifications";
import type { Account, AccountsListResponse, CspSizingResponse } from "@/types/accounts";
import type { ManualExecutePayload, PositionStrategy } from "@/types/trackedPositions";
import { cn } from "@/lib/utils";
import { Loader2, AlertTriangle, Target, DollarSign } from "lucide-react";

export interface ManualExecuteModalProps {
  /** Symbol being executed */
  symbol: string;
  /** Strategy type */
  strategy: PositionStrategy;
  /** Strike price (for CSP/CC) */
  strike?: number | null;
  /** Expiration date YYYY-MM-DD (for CSP/CC) */
  expiration?: string | null;
  /** Expected credit per contract */
  creditEstimate?: number | null;
  /** Called when modal should close */
  onClose: () => void;
  /** Called after successful execution */
  onExecuted: () => void;
}

export function ManualExecuteModal({
  symbol,
  strategy,
  strike,
  expiration,
  creditEstimate,
  onClose,
  onExecuted,
}: ManualExecuteModalProps) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [contracts, setContracts] = useState(1);
  const [quantity, setQuantity] = useState(100);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [sizing, setSizing] = useState<CspSizingResponse | null>(null);
  const [sizingLoading, setSizingLoading] = useState(false);

  // Fetch accounts on mount
  useEffect(() => {
    let cancelled = false;
    const fetchAccounts = async () => {
      try {
        const res = await apiGet<AccountsListResponse>(ENDPOINTS.accountsList);
        if (cancelled) return;
        const active = (res.accounts ?? []).filter((a) => a.active);
        setAccounts(active);
        // Auto-select default account
        const defaultAcct = active.find((a) => a.is_default);
        if (defaultAcct) {
          setSelectedAccountId(defaultAcct.account_id);
        } else if (active.length > 0) {
          setSelectedAccountId(active[0].account_id);
        }
      } catch (e) {
        if (!cancelled) {
          setErrors(["Failed to load accounts. Create an account first."]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchAccounts();
    return () => { cancelled = true; };
  }, []);

  // Fetch CSP sizing when account or strike changes
  const fetchSizing = useCallback(async () => {
    if (!selectedAccountId || !strike || strategy === "STOCK") {
      setSizing(null);
      return;
    }
    setSizingLoading(true);
    try {
      const res = await apiGet<CspSizingResponse>(
        `${ENDPOINTS.accountCspSizing(selectedAccountId)}?strike=${strike}`
      );
      setSizing(res);
      // Auto-set recommended contracts
      if (res.recommended_contracts > 0) {
        setContracts(res.recommended_contracts);
      }
    } catch {
      setSizing(null);
    } finally {
      setSizingLoading(false);
    }
  }, [selectedAccountId, strike, strategy]);

  useEffect(() => {
    fetchSizing();
  }, [fetchSizing]);

  const selectedAccount = accounts.find((a) => a.account_id === selectedAccountId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors([]);
    setSaving(true);

    const payload: ManualExecutePayload = {
      account_id: selectedAccountId,
      symbol,
      strategy,
      notes: notes.trim() || undefined,
    };

    if (strategy === "STOCK") {
      payload.quantity = quantity;
    } else {
      payload.contracts = contracts;
      payload.strike = strike;
      payload.expiration = expiration;
      payload.credit_expected = creditEstimate;
    }

    try {
      await apiPost(ENDPOINTS.manualExecute, payload);
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: "Position recorded",
        message: `${symbol} ${strategy} recorded. Execute the trade in your brokerage.`,
      });
      onExecuted();
    } catch (err) {
      if (err instanceof ApiError && err.body && typeof err.body === "object" && "errors" in (err.body as Record<string, unknown>)) {
        setErrors((err.body as { errors: string[] }).errors);
      } else {
        const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
        setErrors([msg]);
      }
    } finally {
      setSaving(false);
    }
  };

  const capitalRequired = strategy !== "STOCK" && strike
    ? strike * 100 * contracts
    : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="execute-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-auto rounded-lg border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2">
          <Target className="h-5 w-5 text-primary" />
          <h2 id="execute-title" className="text-lg font-semibold text-foreground">
            Execute (Manual)
          </h2>
        </div>

        {/* Warning banner */}
        <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
          <AlertTriangle className="h-4 w-4 mt-0.5 text-amber-600 dark:text-amber-400 shrink-0" />
          <div className="text-xs text-amber-700 dark:text-amber-300">
            <p className="font-medium">This does NOT place a trade.</p>
            <p className="mt-0.5">It records your intention. You must execute the trade manually in your brokerage.</p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading accounts...
          </div>
        ) : accounts.length === 0 ? (
          <div className="py-6 text-center">
            <DollarSign className="mx-auto h-8 w-8 mb-2 text-muted-foreground opacity-40" />
            <p className="text-sm font-medium text-muted-foreground">No accounts found</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Create an account on the Accounts page first.
            </p>
            <button
              type="button"
              onClick={onClose}
              className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
            >
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-4 space-y-3">
            {errors.length > 0 && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
                <ul className="list-inside list-disc text-sm text-destructive">
                  {errors.map((err, i) => <li key={i}>{err}</li>)}
                </ul>
              </div>
            )}

            {/* Trade summary */}
            <div className="rounded-md bg-muted/50 p-3">
              <div className="grid grid-cols-2 gap-y-1 text-sm">
                <span className="text-muted-foreground">Symbol</span>
                <span className="font-medium text-foreground">{symbol}</span>
                <span className="text-muted-foreground">Strategy</span>
                <span className={cn(
                  "font-medium",
                  strategy === "CSP" && "text-emerald-600 dark:text-emerald-400",
                  strategy === "CC" && "text-blue-600 dark:text-blue-400",
                  strategy === "STOCK" && "text-purple-600 dark:text-purple-400"
                )}>{strategy}</span>
                {strike != null && (
                  <>
                    <span className="text-muted-foreground">Strike</span>
                    <span className="font-medium text-foreground">${strike}</span>
                  </>
                )}
                {expiration && (
                  <>
                    <span className="text-muted-foreground">Expiration</span>
                    <span className="text-foreground">{expiration}</span>
                  </>
                )}
                {creditEstimate != null && (
                  <>
                    <span className="text-muted-foreground">Credit Est.</span>
                    <span className="text-foreground">${creditEstimate}</span>
                  </>
                )}
              </div>
            </div>

            {/* Account selector */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground">Account</label>
              <select
                value={selectedAccountId}
                onChange={(e) => setSelectedAccountId(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
              >
                {accounts.map((a) => (
                  <option key={a.account_id} value={a.account_id}>
                    {a.account_id} ({a.provider} · {a.account_type} · ${a.total_capital.toLocaleString()})
                    {a.is_default ? " [DEFAULT]" : ""}
                  </option>
                ))}
              </select>
            </div>

            {/* CSP Sizing info */}
            {sizing && strategy !== "STOCK" && (
              <div className={cn(
                "rounded-md border p-3 text-sm",
                sizing.eligible
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-amber-500/30 bg-amber-500/5"
              )}>
                <div className="flex items-center gap-1.5 font-medium">
                  <DollarSign className="h-3.5 w-3.5" />
                  Capital Sizing
                  {sizingLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-y-0.5 text-xs">
                  <span className="text-muted-foreground">Max capital/trade</span>
                  <span>${sizing.max_capital.toLocaleString()}</span>
                  <span className="text-muted-foreground">CSP notional/contract</span>
                  <span>${sizing.csp_notional.toLocaleString()}</span>
                  <span className="text-muted-foreground">Recommended contracts</span>
                  <span className="font-medium">{sizing.recommended_contracts}</span>
                </div>
                {!sizing.eligible && (
                  <p className="mt-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
                    {sizing.reason}
                  </p>
                )}
              </div>
            )}

            {/* Contracts / Quantity */}
            {strategy === "STOCK" ? (
              <div>
                <label className="block text-xs font-medium text-muted-foreground">Shares</label>
                <input
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(e) => setQuantity(parseInt(e.target.value, 10) || 1)}
                  className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
                  required
                />
              </div>
            ) : (
              <div>
                <label className="block text-xs font-medium text-muted-foreground">Contracts</label>
                <input
                  type="number"
                  min={1}
                  value={contracts}
                  onChange={(e) => setContracts(parseInt(e.target.value, 10) || 1)}
                  className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
                  required
                />
                {capitalRequired != null && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Capital required: ${capitalRequired.toLocaleString()}
                    {selectedAccount && (
                      <> ({((capitalRequired / selectedAccount.total_capital) * 100).toFixed(1)}% of account)</>
                    )}
                  </p>
                )}
              </div>
            )}

            {/* Notes */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground">Notes (optional)</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="e.g., Placed via Robinhood app"
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
              />
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !selectedAccountId}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Record Execution
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
