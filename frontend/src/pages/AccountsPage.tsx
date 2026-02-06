/**
 * Phase 1: Accounts Page — manage brokerage accounts for capital awareness.
 * LIVE only. No broker integrations. Manual capital tracking.
 */
import { useEffect, useState, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, apiPost, apiPut, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { pushSystemNotification } from "@/lib/notifications";
import type {
  Account,
  AccountsListResponse,
  AccountPayload,
  Provider,
  AccountType,
  Strategy,
} from "@/types/accounts";
import { PROVIDERS, ACCOUNT_TYPES, STRATEGIES } from "@/types/accounts";
import { cn } from "@/lib/utils";
import { Plus, Star, Edit2, Loader2, DollarSign, Shield, Check } from "lucide-react";

function formatCurrency(val: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "short" });
  } catch {
    return iso;
  }
}

export function AccountsPage() {
  const { mode } = useDataMode();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [settingDefault, setSettingDefault] = useState<string | null>(null);

  const fetchAccounts = useCallback(async () => {
    if (mode !== "LIVE") return;
    setError(null);
    try {
      const res = await apiGet<AccountsListResponse>(ENDPOINTS.accountsList);
      setAccounts(res.accounts ?? []);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    if (mode === "MOCK") {
      setLoading(false);
      setAccounts([]);
      setError(null);
      return;
    }
    fetchAccounts();
  }, [mode, fetchAccounts]);

  const handleSetDefault = async (accountId: string) => {
    setSettingDefault(accountId);
    try {
      await apiPost(ENDPOINTS.accountSetDefault(accountId), {});
      pushSystemNotification({
        source: "system",
        severity: "info",
        title: "Default account set",
        message: `Account ${accountId} is now the default.`,
      });
      fetchAccounts();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      pushSystemNotification({ source: "system", severity: "error", title: "Error", message: msg });
    } finally {
      setSettingDefault(null);
    }
  };

  const handleEdit = (account: Account) => {
    setEditingAccount(account);
    setShowForm(true);
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditingAccount(null);
  };

  const handleFormSaved = () => {
    handleFormClose();
    fetchAccounts();
  };

  if (mode === "MOCK") {
    return (
      <div className="space-y-6 p-6">
        <PageHeader title="Accounts" subtext="Capital awareness and position sizing. Switch to LIVE to use." />
        <EmptyState title="Accounts is LIVE only" message="Switch to LIVE mode to manage accounts." />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Accounts"
        subtext="Define brokerage accounts for capital-aware position sizing. ChakraOps never places trades."
        actions={
          <button
            type="button"
            onClick={() => { setEditingAccount(null); setShowForm(true); }}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            Add account
          </button>
        }
      />

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-border bg-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-12 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading...
          </div>
        ) : accounts.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <DollarSign className="mx-auto h-8 w-8 mb-3 opacity-40" />
            <p className="font-medium">No accounts yet</p>
            <p className="mt-1 text-sm">Add an account to enable capital-aware position sizing.</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {accounts.map((a) => (
              <div
                key={a.account_id}
                className={cn(
                  "p-4 transition-colors",
                  a.is_default && "bg-primary/5 border-l-2 border-l-primary",
                  !a.active && "opacity-60"
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">{a.account_id}</span>
                      {a.is_default && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-primary/20 px-2 py-0.5 text-xs font-medium text-primary">
                          <Star className="h-3 w-3" /> Default
                        </span>
                      )}
                      {!a.active && (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                          Inactive
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted-foreground">
                      <span>
                        <span className="text-foreground font-medium">{a.provider}</span> · {a.account_type}
                      </span>
                      <span>
                        Capital: <span className="text-foreground font-medium">{formatCurrency(a.total_capital)}</span>
                      </span>
                      <span>
                        Max/trade: <span className="text-foreground">{a.max_capital_per_trade_pct}%</span>
                        {" "}({formatCurrency(a.total_capital * a.max_capital_per_trade_pct / 100)})
                      </span>
                      <span>
                        Max exposure: <span className="text-foreground">{a.max_total_exposure_pct}%</span>
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-1.5">
                      <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">
                        Strategies: {a.allowed_strategies.join(", ")}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Created {formatDate(a.created_at)} · Updated {formatDate(a.updated_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {!a.is_default && (
                      <button
                        type="button"
                        onClick={() => handleSetDefault(a.account_id)}
                        disabled={settingDefault === a.account_id}
                        className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                        title="Set as default account"
                      >
                        {settingDefault === a.account_id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Star className="h-3 w-3" />
                        )}
                        Set default
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleEdit(a)}
                      className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                      title="Edit account"
                    >
                      <Edit2 className="h-3 w-3" />
                      Edit
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {showForm && (
        <AccountFormModal
          account={editingAccount}
          onClose={handleFormClose}
          onSaved={handleFormSaved}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Account form modal (create / edit)
// ---------------------------------------------------------------------------

function AccountFormModal({
  account,
  onClose,
  onSaved,
}: {
  account: Account | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = account !== null;
  const [saving, setSaving] = useState(false);
  const [accountId, setAccountId] = useState(account?.account_id ?? "");
  const [provider, setProvider] = useState<Provider>(account?.provider ?? "Manual");
  const [accountType, setAccountType] = useState<AccountType>(account?.account_type ?? "Taxable");
  const [totalCapital, setTotalCapital] = useState(account?.total_capital?.toString() ?? "");
  const [maxPerTrade, setMaxPerTrade] = useState(account?.max_capital_per_trade_pct?.toString() ?? "5");
  const [maxExposure, setMaxExposure] = useState(account?.max_total_exposure_pct?.toString() ?? "30");
  const [strategies, setStrategies] = useState<Strategy[]>(account?.allowed_strategies ?? ["CSP"]);
  const [isDefault, setIsDefault] = useState(account?.is_default ?? false);
  const [active, setActive] = useState(account?.active ?? true);
  const [errors, setErrors] = useState<string[]>([]);

  const toggleStrategy = (s: Strategy) => {
    setStrategies((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors([]);
    setSaving(true);

    const payload: AccountPayload = {
      provider,
      account_type: accountType,
      total_capital: parseFloat(totalCapital),
      max_capital_per_trade_pct: parseFloat(maxPerTrade),
      max_total_exposure_pct: parseFloat(maxExposure),
      allowed_strategies: strategies,
      is_default: isDefault,
      active,
    };

    if (!isEdit && accountId.trim()) {
      payload.account_id = accountId.trim();
    }

    // Client-side validation
    const clientErrors: string[] = [];
    if (isNaN(payload.total_capital) || payload.total_capital <= 0) {
      clientErrors.push("Total capital must be greater than 0");
    }
    if (isNaN(payload.max_capital_per_trade_pct) || payload.max_capital_per_trade_pct < 1 || payload.max_capital_per_trade_pct > 100) {
      clientErrors.push("Max capital per trade must be between 1% and 100%");
    }
    if (isNaN(payload.max_total_exposure_pct) || payload.max_total_exposure_pct < 1 || payload.max_total_exposure_pct > 100) {
      clientErrors.push("Max total exposure must be between 1% and 100%");
    }
    if (strategies.length === 0) {
      clientErrors.push("Select at least one strategy");
    }
    if (clientErrors.length > 0) {
      setErrors(clientErrors);
      setSaving(false);
      return;
    }

    try {
      if (isEdit) {
        await apiPut(ENDPOINTS.accountUpdate(account!.account_id), payload);
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Account updated",
          message: `${account!.account_id} updated successfully.`,
        });
      } else {
        await apiPost(ENDPOINTS.accountsCreate, payload);
        pushSystemNotification({
          source: "system",
          severity: "info",
          title: "Account created",
          message: `Account created successfully.`,
        });
      }
      onSaved();
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="account-form-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-lg border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="account-form-title" className="text-lg font-semibold text-foreground">
          {isEdit ? "Edit account" : "Add account"}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Define capital limits for position sizing. ChakraOps never places trades.
        </p>

        {errors.length > 0 && (
          <div className="mt-3 rounded-md border border-destructive/50 bg-destructive/10 p-3">
            <ul className="list-inside list-disc text-sm text-destructive">
              {errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          {/* Account ID (create only) */}
          {!isEdit && (
            <div>
              <label className="block text-xs font-medium text-muted-foreground">
                Account ID <span className="text-muted-foreground/60">(optional, auto-generated if empty)</span>
              </label>
              <input
                type="text"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                placeholder="my-roth-account"
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            {/* Provider */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground">Provider</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as Provider)}
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            {/* Account type */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground">Account type</label>
              <select
                value={accountType}
                onChange={(e) => setAccountType(e.target.value as AccountType)}
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
              >
                {ACCOUNT_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Total capital */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground">Total capital (USD)</label>
            <div className="relative mt-1">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
              <input
                type="number"
                step="1"
                min="1"
                value={totalCapital}
                onChange={(e) => setTotalCapital(e.target.value)}
                placeholder="50000"
                className="w-full rounded border border-border bg-background pl-6 pr-2.5 py-1.5 text-sm"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Max capital per trade */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground">Max capital per trade (%)</label>
              <input
                type="number"
                step="0.5"
                min="1"
                max="100"
                value={maxPerTrade}
                onChange={(e) => setMaxPerTrade(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
                required
              />
            </div>

            {/* Max total exposure */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground">Max total exposure (%)</label>
              <input
                type="number"
                step="0.5"
                min="1"
                max="100"
                value={maxExposure}
                onChange={(e) => setMaxExposure(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-background px-2.5 py-1.5 text-sm"
                required
              />
            </div>
          </div>

          {/* Allowed strategies */}
          <div>
            <label className="block text-xs font-medium text-muted-foreground">Allowed strategies</label>
            <div className="mt-1.5 flex gap-2">
              {STRATEGIES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleStrategy(s)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors",
                    strategies.includes(s)
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-background text-muted-foreground hover:bg-muted"
                  )}
                >
                  {strategies.includes(s) && <Check className="h-3.5 w-3.5" />}
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Default + Active */}
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="rounded border-border"
              />
              Set as default
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
                className="rounded border-border"
              />
              Active
            </label>
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
              disabled={saving}
              className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {isEdit ? "Update" : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
