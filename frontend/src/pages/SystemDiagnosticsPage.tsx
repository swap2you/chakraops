import { useUiSystemHealth } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, StatusBadge } from "@/components/ui";

export function SystemDiagnosticsPage() {
  const { data, isLoading, isError } = useUiSystemHealth();
  const api = data?.api;
  const orats = data?.orats;
  const market = data?.market;
  const scheduler = data?.scheduler;

  if (isLoading) {
    return (
      <div>
        <PageHeader title="System Diagnostics" />
        <p className="text-zinc-400">Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="System Diagnostics" />
        <p className="text-red-400">Failed to load system diagnostics.</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader title="System Diagnostics" />
        <p className="text-zinc-500">No data.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="System Status" subtext="API, ORATS, market, and scheduler" />
      <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
        <Card>
          <CardHeader title="API" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={api?.status ?? "—"} />
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">latency_ms</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{api?.latency_ms ?? "—"}</p>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="ORATS" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={orats?.status ?? "—"} />
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_success_at</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{orats?.last_success_at ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">avg_latency_seconds</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                {orats?.avg_latency_seconds != null ? orats.avg_latency_seconds : "—"}
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_error_reason</span>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">{orats?.last_error_reason ?? "—"}</p>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Market" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">phase</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{market?.phase ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">is_open</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{market?.is_open ? "true" : "false"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">timestamp</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{market?.timestamp ?? "—"}</p>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Scheduler" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">interval_minutes</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler?.interval_minutes ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">nightly_next_at</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler?.nightly_next_at ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">eod_next_at</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler?.eod_next_at ?? "—"}</p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
