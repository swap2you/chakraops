/**
 * R56: Strategy workspace shells — Options / Stocks / ETF-Hedge.
 * Advisory-only; no broker writes.
 */
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader } from "@/components/ui";

type WorkspaceKind = "options" | "stocks" | "etf-hedge";

const COPY: Record<WorkspaceKind, { title: string; blurb: string; testId: string }> = {
  options: {
    title: "Options workspace",
    blurb: "CSP/CC/Wheel candidates and tickets. Manual execution only. ORATS for options strategy data; Robinhood for live portfolio when healthy.",
    testId: "page-options-workspace",
  },
  stocks: {
    title: "Stocks workspace",
    blurb: "Equity holdings context and stock-level monitoring. Stay in Cash remains valid. No broker writes.",
    testId: "page-stocks-workspace",
  },
  "etf-hedge": {
    title: "ETF Hedge workspace",
    blurb: "Hedge overlays and ETF risk context. Advisory only — not automatic rebalancing.",
    testId: "page-etf-hedge-workspace",
  },
};

export function StrategyWorkspacePage({ kind }: { kind: WorkspaceKind }) {
  const c = COPY[kind];
  return (
    <div className="space-y-6" data-testid={c.testId}>
      <PageHeader title={c.title} subtext="R56 strategy workspace · manual_only · trade_execution=false" />
      <Card>
        <CardHeader title="Scope" description={c.blurb} />
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          Use Command Center / Today / Trade Ticket for actionable flow. This workspace separates strategy context without duplicating Portfolio broker truth.
        </p>
      </Card>
    </div>
  );
}

export function OptionsWorkspacePage() {
  return <StrategyWorkspacePage kind="options" />;
}
export function StocksWorkspacePage() {
  return <StrategyWorkspacePage kind="stocks" />;
}
export function EtfHedgeWorkspacePage() {
  return <StrategyWorkspacePage kind="etf-hedge" />;
}
