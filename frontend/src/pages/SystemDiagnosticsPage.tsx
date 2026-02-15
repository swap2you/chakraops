import { useUiSystemHealth } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";

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
    <div>
      <PageHeader title="System Diagnostics" />
      <div className="space-y-4">
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            API
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={api?.status ?? "—"} />
              </p>
            </div>
            <div>
              <span className="block text-zinc-500">latency_ms</span>
              <p className="mt-1 font-mono text-zinc-200">{api?.latency_ms ?? "—"}</p>
            </div>
          </div>
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            ORATS
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={orats?.status ?? "—"} />
              </p>
            </div>
            <div>
              <span className="block text-zinc-500">last_success_at</span>
              <p className="mt-1 font-mono text-zinc-200">{orats?.last_success_at ?? "—"}</p>
            </div>
            <div>
              <span className="block text-zinc-500">avg_latency_seconds</span>
              <p className="mt-1 font-mono text-zinc-200">
                {orats?.avg_latency_seconds != null ? orats.avg_latency_seconds : "—"}
              </p>
            </div>
            <div>
              <span className="block text-zinc-500">last_error_reason</span>
              <p className="mt-1 text-zinc-400">{orats?.last_error_reason ?? "—"}</p>
            </div>
          </div>
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Market
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-zinc-500">phase</span>
              <p className="mt-1 font-mono text-zinc-200">{market?.phase ?? "—"}</p>
            </div>
            <div>
              <span className="block text-zinc-500">is_open</span>
              <p className="mt-1 font-mono text-zinc-200">{market?.is_open ? "true" : "false"}</p>
            </div>
            <div>
              <span className="block text-zinc-500">timestamp</span>
              <p className="mt-1 font-mono text-zinc-200">{market?.timestamp ?? "—"}</p>
            </div>
          </div>
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Scheduler
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-zinc-500">interval_minutes</span>
              <p className="mt-1 font-mono text-zinc-200">{scheduler?.interval_minutes ?? "—"}</p>
            </div>
            <div>
              <span className="block text-zinc-500">nightly_next_at</span>
              <p className="mt-1 font-mono text-zinc-200">{scheduler?.nightly_next_at ?? "—"}</p>
            </div>
            <div>
              <span className="block text-zinc-500">eod_next_at</span>
              <p className="mt-1 font-mono text-zinc-200">{scheduler?.eod_next_at ?? "—"}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
