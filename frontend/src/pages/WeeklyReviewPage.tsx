/**
 * R26.4: Weekly review — weekly-summary + checklist; Mark Weekly Done; pending banner.
 * Safe labels only; no FAIL/WARN in UI.
 */
import { useMemo } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, Button } from "@/components/ui";
import {
  useOpsChecklist,
  useOpsWeeklySummary,
  useOpsChecklistMarkDone,
} from "@/api/queries";

function getISOWeekKey(date: Date): string {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  const day = d.getDay() || 7;
  const thursday = new Date(d);
  thursday.setDate(d.getDate() - day + 4);
  const year = thursday.getFullYear();
  const jan1 = new Date(year, 0, 1);
  const weekNum = Math.ceil(
    ((thursday.getTime() - jan1.getTime()) / 86400000 + jan1.getDay() + 1) / 7
  );
  return `${year}-${String(weekNum).padStart(2, "0")}`;
}

export function WeeklyReviewPage() {
  const weekKey = useMemo(() => getISOWeekKey(new Date()), []);
  const { data: checklist } = useOpsChecklist("WEEKLY", weekKey);
  const { data: summary } = useOpsWeeklySummary(weekKey);
  const markDone = useOpsChecklistMarkDone();

  const pending = (checklist?.row?.status ?? "OPEN").toUpperCase() !== "DONE";

  return (
    <div className="space-y-4">
      <PageHeader title="Weekly Review" subtext="Week summary and checklist" />
      {pending && (
        <div
          className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200"
          data-testid="weekly-pending-banner"
        >
          Weekly review checklist pending for week {weekKey}.
        </div>
      )}

      <Card data-testid="weekly-summary-card">
        <CardHeader
          title={`Week ${weekKey}`}
          description={summary ? `${summary.from_date} – ${summary.to_date}` : ""}
          actions={
            pending ? (
              <Button
                onClick={() => markDone.mutate({ kind: "WEEKLY", key: weekKey })}
                disabled={markDone.isPending}
                data-testid="weekly-mark-done"
              >
                {markDone.isPending ? "Saving…" : "Mark Weekly Done"}
              </Button>
            ) : (
              <span className="text-sm text-zinc-500">Done</span>
            )
          }
        />
        <div className="text-sm space-y-2">
          {summary && (
            <>
              <p className="text-zinc-600 dark:text-zinc-400">
                Realized P/L: ${summary.realized_pl_total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} · Trades: {summary.trade_count}
              </p>
              {summary.winners.length > 0 && (
                <p className="text-zinc-600 dark:text-zinc-400">
                  Top winners: {summary.winners.slice(0, 5).map((w) => `${w.symbol} ($${w.realized_pl.toFixed(0)})`).join(", ")}
                </p>
              )}
              {summary.losers.length > 0 && (
                <p className="text-zinc-600 dark:text-zinc-400">
                  Top losers: {summary.losers.slice(0, 5).map((l) => `${l.symbol} ($${l.realized_pl.toFixed(0)})`).join(", ")}
                </p>
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
