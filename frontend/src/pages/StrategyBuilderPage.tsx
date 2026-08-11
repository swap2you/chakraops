/**
 * R68: Guarded Strategy Builder — Stay in Cash valid; never promises returns.
 */
import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Button, Card, CardHeader } from "@/components/ui";
import { apiPost } from "@/api/client";

type BuilderPlan = {
  primary_recommendation?: string;
  stay_in_cash?: boolean;
  return_guarantee?: boolean;
  recommendations?: Array<{ label: string; rationale?: string }>;
  disclaimer?: string;
};

type CspPayoff = {
  breakeven?: number;
  max_profit?: number;
  max_loss?: number;
  collateral?: number;
};

export function StrategyBuilderPage() {
  const [capital, setCapital] = useState("0");
  const [account, setAccount] = useState("acct_individual");
  const [horizonMonths, setHorizonMonths] = useState("12");
  const [maxDd, setMaxDd] = useState("20");
  const [comfort, setComfort] = useState("medium");
  const [target, setTarget] = useState("");
  const [plan, setPlan] = useState<BuilderPlan | null>(null);
  const [payoff, setPayoff] = useState<CspPayoff | null>(null);
  const [strike, setStrike] = useState("100");
  const [credit, setCredit] = useState("1.50");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runBuilder() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        capital: Number(capital) || 0,
        account_alias: account,
        horizon_months: Number(horizonMonths) || 12,
        max_drawdown_pct: Number(maxDd) || 20,
        assignment_comfort: comfort,
      };
      if (target.trim()) body.target_return_pct = Number(target);
      const res = await apiPost<BuilderPlan>("/api/ui/golive/strategy/builder", body);
      setPlan(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Builder failed");
    } finally {
      setBusy(false);
    }
  }

  async function runPayoff() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiPost<CspPayoff>("/api/ui/golive/strategy/csp-payoff", {
        strike: Number(strike) || 0,
        credit: Number(credit) || 0,
        spot: Number(strike) || 0,
      });
      setPayoff(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Payoff failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6" data-testid="page-strategy-builder">
      <PageHeader
        title="Strategy Builder"
        subtext="Advisory plan only · Stay in Cash is valid · never a return guarantee"
      />

      <Card>
        <CardHeader title="Inputs" description="Target return is a goal label only — not a promise." />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          <label className="block">
            <span className="text-xs text-zinc-500">Capital</span>
            <input className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={capital} onChange={(e) => setCapital(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Account</span>
            <select className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={account} onChange={(e) => setAccount(e.target.value)}>
              <option value="acct_individual">acct_individual</option>
              <option value="acct_ira_roth">acct_ira_roth</option>
              <option value="acct_agentic">acct_agentic (no execution)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Horizon (months)</span>
            <input className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={horizonMonths} onChange={(e) => setHorizonMonths(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Max drawdown %</span>
            <input className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={maxDd} onChange={(e) => setMaxDd(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Assignment comfort</span>
            <select className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={comfort} onChange={(e) => setComfort(e.target.value)}>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Target return % (goal only)</span>
            <input className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="optional" />
          </label>
        </div>
        <div className="mt-4">
          <Button data-testid="strategy-builder-run" disabled={busy} onClick={() => void runBuilder()}>
            Build advisory plan
          </Button>
        </div>
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        {plan ? (
          <div className="mt-4 space-y-2 text-sm" data-testid="strategy-builder-result">
            <p>
              Primary: <strong>{plan.primary_recommendation ?? "—"}</strong>
            </p>
            <p>Return guarantee: {String(plan.return_guarantee ?? false)}</p>
            <ul className="list-disc pl-5">
              {(plan.recommendations ?? []).map((r) => (
                <li key={r.label}>
                  {r.label}
                  {r.rationale ? ` — ${r.rationale}` : ""}
                </li>
              ))}
            </ul>
            <p className="text-xs text-zinc-500">{plan.disclaimer}</p>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardHeader title="Visual Options Lab — CSP payoff" description="Breakeven / max profit for a manually selected short put." />
        <div className="grid gap-3 sm:grid-cols-2 max-w-md text-sm">
          <label className="block">
            <span className="text-xs text-zinc-500">Strike</span>
            <input className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={strike} onChange={(e) => setStrike(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Credit</span>
            <input className="mt-1 w-full rounded border px-2 py-1.5 dark:border-zinc-600 dark:bg-zinc-900" value={credit} onChange={(e) => setCredit(e.target.value)} />
          </label>
        </div>
        <div className="mt-4">
          <Button variant="secondary" data-testid="csp-payoff-run" disabled={busy} onClick={() => void runPayoff()}>
            Calculate CSP payoff
          </Button>
        </div>
        {payoff ? (
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4" data-testid="csp-payoff-result">
            <div>
              <span className="block text-xs text-zinc-500">Breakeven</span>
              <span className="font-mono">{payoff.breakeven ?? "—"}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">Max profit</span>
              <span className="font-mono">{payoff.max_profit ?? "—"}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">Max loss</span>
              <span className="font-mono">{payoff.max_loss ?? "—"}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">Collateral</span>
              <span className="font-mono">{payoff.collateral ?? "—"}</span>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
