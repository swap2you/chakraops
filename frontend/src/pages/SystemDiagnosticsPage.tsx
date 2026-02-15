import { useDataHealth } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";

export function SystemDiagnosticsPage() {
  const { data, isLoading, isError } = useDataHealth();

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
      <div className="rounded border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="block text-zinc-500">status</span>
            <p className="mt-1">
              <StatusBadge status={data.status} />
            </p>
          </div>
          <div>
            <span className="block text-zinc-500">last_success_at</span>
            <p className="mt-1 font-mono text-zinc-200">
              {data.last_success_at ?? data.effective_last_success_at ?? "—"}
            </p>
          </div>
          <div>
            <span className="block text-zinc-500">entitlement</span>
            <p className="mt-1 font-mono text-zinc-200">{data.entitlement ?? "—"}</p>
          </div>
          <div>
            <span className="block text-zinc-500">avg_latency_seconds</span>
            <p className="mt-1 font-mono text-zinc-200">
              {data.avg_latency_seconds != null ? data.avg_latency_seconds : "—"}
            </p>
          </div>
          <div>
            <span className="block text-zinc-500">provider</span>
            <p className="mt-1 font-mono text-zinc-200">{data.provider ?? "—"}</p>
          </div>
          <div>
            <span className="block text-zinc-500">last_attempt_at</span>
            <p className="mt-1 font-mono text-zinc-200">{data.last_attempt_at ?? "—"}</p>
          </div>
          <div>
            <span className="block text-zinc-500">last_error_at</span>
            <p className="mt-1 font-mono text-zinc-200">{data.last_error_at ?? "—"}</p>
          </div>
          <div>
            <span className="block text-zinc-500">last_error_reason</span>
            <p className="mt-1 text-zinc-400">{data.last_error_reason ?? "—"}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
