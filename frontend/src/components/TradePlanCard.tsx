/**
 * Trade plan card — prominent, status badge, key metrics, Why this trade, "Why only this symbol?" modal.
 */
import { useState } from "react";
import type { TradePlanView, DailyOverviewView } from "@/types/views";
import { cn } from "@/lib/utils";
import { WhyOnlyThisSymbolModal } from "@/components/WhyOnlyThisSymbolModal";

export interface TradePlanCardProps {
  tradePlan: TradePlanView | null;
  overview?: DailyOverviewView | null;
  onPrimaryAction?: () => void;
}

function formatCurrency(val: number | undefined | null): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

export function TradePlanCard({
  tradePlan,
  overview,
  onPrimaryAction,
}: TradePlanCardProps) {
  const [whyModalOpen, setWhyModalOpen] = useState(false);

  if (!tradePlan) {
    return (
      <section className="rounded-lg border border-border bg-card p-5">
        <h2 className="text-sm font-medium text-muted-foreground">Trade plan</h2>
        <p className="mt-2 text-sm text-muted-foreground">No trade plan available.</p>
      </section>
    );
  }

  const status = (tradePlan.execution_status ?? "BLOCKED").toUpperCase();
  const isReady = status === "READY";
  const proposal = tradePlan.proposal as Record<string, unknown> | undefined;
  const creditEst = proposal?.credit_estimate ?? tradePlan.computed_targets?.t1;
  const maxLoss = proposal?.max_loss;
  const targets = tradePlan.computed_targets ?? {};
  const expiry = typeof proposal?.expiry === "string" ? proposal.expiry : undefined;

  const regime = overview?.regime ?? null;
  const riskPosture = overview?.risk_posture ?? null;
  const gatesPassed: string[] = [];
  if (regime && regime !== "RISK_OFF") gatesPassed.push("Regime allowed");
  if (riskPosture) gatesPassed.push(`Risk posture: ${riskPosture}`);
  if (isReady && !(tradePlan.blockers?.length)) gatesPassed.push("Execution gate passed");
  const topGates = gatesPassed.slice(0, 3);

  return (
    <section className="rounded-lg border border-border bg-card p-5" role="region" aria-label="Trade plan">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium text-muted-foreground">Trade plan</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                isReady ? "bg-emerald-500/20 text-emerald-400" : "bg-muted text-muted-foreground"
              )}
            >
              {status}
            </span>
            <span className="text-lg font-semibold text-foreground">{tradePlan.symbol}</span>
            <span className="text-sm text-muted-foreground">{tradePlan.strategy_type}</span>
            <button
              type="button"
              onClick={() => setWhyModalOpen(true)}
              className="text-xs font-medium text-primary hover:underline"
            >
              Why only this symbol?
            </button>
          </div>
        </div>
        {isReady && (
          <button
            type="button"
            onClick={onPrimaryAction}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-ring"
          >
            Review plan
          </button>
        )}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Credit est.</dt>
          <dd className="font-medium text-foreground">{formatCurrency(creditEst as number)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Max loss</dt>
          <dd className="font-medium text-foreground">{formatCurrency(maxLoss as number)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Targets (T1/T2/T3)</dt>
          <dd className="font-medium text-foreground">
            {formatCurrency(targets.t1)} / {formatCurrency(targets.t2)} / {formatCurrency(targets.t3)}
          </dd>
        </div>
        {expiry && (
          <div>
            <dt className="text-muted-foreground">Expiry</dt>
            <dd className="font-medium text-foreground">{expiry}</dd>
          </div>
        )}
      </dl>

      {isReady && (regime || riskPosture || topGates.length > 0) && (
        <div className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-sm">
          <h3 className="font-medium text-foreground">Why this trade</h3>
          <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-muted-foreground">
            {regime && <li>Market regime: {regime}</li>}
            {topGates.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
            {riskPosture && !topGates.some((g) => g.includes(riskPosture)) && (
              <li>Risk posture alignment: {riskPosture}</li>
            )}
          </ul>
        </div>
      )}

      {tradePlan.blockers && tradePlan.blockers.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">Constraints: {tradePlan.blockers.join(", ")}</p>
      )}

      <WhyOnlyThisSymbolModal
        open={whyModalOpen}
        onClose={() => setWhyModalOpen(false)}
        overview={overview ?? null}
        symbol={tradePlan.symbol}
      />
    </section>
  );
}
