/**
 * Phase 7.2: Daily overview — secondary context. Read-only from DailyOverviewView.
 */
import type { DailyOverviewView } from "@/types/views";

function formatTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return "—";
  }
}

export interface DailyOverviewCardProps {
  overview: DailyOverviewView | null;
}

export function DailyOverviewCard({ overview }: DailyOverviewCardProps) {
  if (!overview) {
    return (
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium text-muted-foreground">
          Daily overview
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          No overview data.
        </p>
      </section>
    );
  }

  const blockers = overview.top_blockers ?? [];
  const evaluatedAt = overview.links?.latest_decision_ts;
  const fetchedAt = overview.fetched_at;
  return (
    <section
      className="rounded-lg border border-border bg-card p-4"
      role="region"
      aria-label="Daily overview"
    >
      <h2 className="text-sm font-medium text-muted-foreground">
        Daily overview
      </h2>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {evaluatedAt && (
          <span title="Last evaluation run (decision pipeline)">Evaluated at: {formatTs(evaluatedAt)}</span>
        )}
        {fetchedAt && (
          <span title="Last data fetched from API">Fetched at: {formatTs(fetchedAt)}</span>
        )}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <p>
          <span className="text-muted-foreground">Date</span>{" "}
          <span className="font-medium text-foreground">{overview.date}</span>
        </p>
        <p title="DRY_RUN = no trades executed, signals only">
          <span className="text-muted-foreground">Run mode</span>{" "}
          <span className="font-medium text-foreground">{overview.run_mode}</span>
        </p>
        <p title="Evaluation scope = Universe symbols">
          <span className="text-muted-foreground">Symbols evaluated</span>{" "}
          <span className="font-medium text-foreground">
            {overview.symbols_evaluated}
          </span>
        </p>
        <p>
          <span className="text-muted-foreground">Risk posture</span>{" "}
          <span className="font-medium text-foreground">
            {overview.risk_posture}
          </span>
        </p>
      </div>
      {blockers.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-muted-foreground">Evaluation constraints</p>
          <ul className="mt-1 list-inside list-disc text-sm text-foreground">
            {blockers.slice(0, 5).map((b, i) => (
              <li key={i}>
                {b.code}: {b.count}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
