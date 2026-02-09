/**
 * Phase 3: Portfolio summary cards — total equity, capital in use, available, utilization %.
 */
import type { PortfolioSummary } from "@/types/portfolio";
import { cn } from "@/lib/utils";
import { DollarSign, TrendingUp, AlertTriangle } from "lucide-react";

function formatCurrency(val: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function formatPct(val: number): string {
  return `${(val * 100).toFixed(1)}%`;
}

interface PortfolioSummaryCardsProps {
  summary: PortfolioSummary;
  className?: string;
}

export function PortfolioSummaryCards({ summary, className }: PortfolioSummaryCardsProps) {
  const hasFlags = summary.risk_flags && summary.risk_flags.length > 0;

  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-4", className)}>
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <DollarSign className="h-4 w-4" />
          Total Equity
        </div>
        <p className="mt-2 text-2xl font-semibold text-foreground">
          {formatCurrency(summary.total_equity)}
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <TrendingUp className="h-4 w-4" />
          Capital In Use
        </div>
        <p className="mt-2 text-2xl font-semibold text-foreground">
          {formatCurrency(summary.capital_in_use)}
        </p>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          Available Capital
        </div>
        <p className="mt-2 text-2xl font-semibold text-foreground">
          {formatCurrency(summary.available_capital)}
        </p>
        {summary.available_capital_clamped && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
            Clamped from negative
          </p>
        )}
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          Utilization
        </div>
        <p
          className={cn(
            "mt-2 text-2xl font-semibold",
            summary.capital_utilization_pct > 0.35
              ? "text-red-600 dark:text-red-400"
              : summary.capital_utilization_pct > 0.25
              ? "text-amber-600 dark:text-amber-400"
              : "text-foreground"
          )}
        >
          {formatPct(summary.capital_utilization_pct)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {summary.open_positions_count} open positions
        </p>
      </div>

      {hasFlags && (
        <div className="col-span-full rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-destructive">
            <AlertTriangle className="h-4 w-4" />
            Risk Flags
          </div>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            {summary.risk_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className={cn(
                    "inline-block h-2 w-2 mt-1.5 rounded-full shrink-0",
                    f.severity === "error" ? "bg-red-500" : "bg-amber-500"
                  )}
                />
                {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
