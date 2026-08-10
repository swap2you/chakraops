/**
 * R25.6: Universe Health — total symbols, recently added/removed, warnings. Safe labels only.
 */
import { useUniverseHealth } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader } from "@/components/ui";
import { Loader2 } from "lucide-react";

export function UniverseHealthPage() {
  const { data, isLoading, isError, error } = useUniverseHealth();

  return (
    <div className="space-y-6 p-6" data-testid="page-universe-health">
      <PageHeader
        title="Universe Health"
        subtext="Summary of universe size, recent changes, and data status."
      />

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
          {error instanceof Error ? error.message : "Unable to load universe health."}
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-zinc-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading…
        </div>
      )}

      {!isLoading && !isError && data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
              Total symbols
            </CardHeader>
            <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{data.total_symbols}</p>
          </Card>
          <Card>
            <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
              Base count
            </CardHeader>
            <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{data.base_count}</p>
          </Card>
          <Card>
            <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
              Warnings (data issues)
            </CardHeader>
            <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{data.warnings_count}</p>
          </Card>
          {data.earnings_upcoming != null && (
            <Card>
              <CardHeader className="pb-1 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                Earnings upcoming
              </CardHeader>
              <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{data.earnings_upcoming}</p>
            </Card>
          )}
        </div>
      )}

      {!isLoading && !isError && data && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Recently added (last 30 days)
            </CardHeader>
            <div className="flex flex-wrap gap-2">
              {(data.recently_added ?? []).length === 0 ? (
                <span className="text-zinc-500">None</span>
              ) : (
                (data.recently_added ?? []).map((s) => (
                  <span key={s} className="rounded bg-emerald-100 px-2 py-0.5 text-sm dark:bg-emerald-900/40">{s}</span>
                ))
              )}
            </div>
          </Card>
          <Card>
            <CardHeader className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Recently removed (last 30 days)
            </CardHeader>
            <div className="flex flex-wrap gap-2">
              {(data.recently_removed ?? []).length === 0 ? (
                <span className="text-zinc-500">None</span>
              ) : (
                (data.recently_removed ?? []).map((s) => (
                  <span key={s} className="rounded bg-red-100 px-2 py-0.5 text-sm dark:bg-red-900/40">{s}</span>
                ))
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
