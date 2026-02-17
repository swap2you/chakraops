import { useState } from "react";
import { useUiSystemHealth, useDiagnosticsHistory, useRunDiagnostics } from "@/api/queries";
import { formatTimestampEt, formatTimestampEtFull } from "@/utils/formatTimestamp";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, StatusBadge, Button } from "@/components/ui";

const DIAGNOSTIC_CHECKS = ["orats", "decision_store", "universe", "positions", "scheduler"] as const;

export function SystemDiagnosticsPage() {
  const { data, isLoading, isError } = useUiSystemHealth();
  const { data: historyData } = useDiagnosticsHistory(10);
  const runDiagnostics = useRunDiagnostics();
  const [selectedChecks, setSelectedChecks] = useState<Set<string>>(new Set(DIAGNOSTIC_CHECKS));
  const [latestResult, setLatestResult] = useState<typeof runDiagnostics.data | null>(null);

  const handleRunAll = () => {
    runDiagnostics.mutate(undefined, {
      onSuccess: (res) => setLatestResult(res),
    });
  };

  const handleRunSelected = () => {
    const checks = selectedChecks.size === DIAGNOSTIC_CHECKS.length
      ? undefined
      : Array.from(selectedChecks).join(",");
    runDiagnostics.mutate(checks, {
      onSuccess: (res) => setLatestResult(res),
    });
  };

  const toggleCheck = (c: string) => {
    setSelectedChecks((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  };

  const displayResult = latestResult ?? historyData?.runs?.[0];
  const runs = historyData?.runs ?? [];
  const api = data?.api;
  const decisionStore = data?.decision_store;
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
      <PageHeader title="System Status" subtext="API, Decision Store, ORATS, market, and scheduler" />
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
        <Card className={decisionStore?.status === "CRITICAL" ? "border-red-500 dark:border-red-600" : ""}>
          <CardHeader
            title="Decision Store"
            description={decisionStore?.status === "CRITICAL" ? decisionStore.reason ?? "CRITICAL" : undefined}
          />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={decisionStore?.status ?? "—"} />
              </p>
            </div>
            {decisionStore?.reason && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">reason</span>
                <p className="mt-1 text-zinc-600 dark:text-zinc-400">{decisionStore.reason}</p>
              </div>
            )}
            {decisionStore?.canonical_path && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">path</span>
                <p className="mt-1 font-mono text-xs text-zinc-600 dark:text-zinc-400 truncate" title={decisionStore.canonical_path}>
                  {decisionStore.canonical_path}
                </p>
              </div>
            )}
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
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_success_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(orats?.last_success_at)}</p>
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
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">timestamp (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(market?.timestamp)}</p>
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
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_run_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(scheduler?.last_run_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">next_run_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(scheduler?.next_run_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_result</span>
              <p className="mt-1">
                <StatusBadge status={scheduler?.last_result ?? "—"} />
              </p>
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

      {/* Sanity Checks (Phase 8.2) */}
      <Card>
        <CardHeader title="Sanity Checks" />
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="sm"
              onClick={handleRunAll}
              disabled={runDiagnostics.isPending}
            >
              {runDiagnostics.isPending ? "Running…" : "Run All"}
            </Button>
            <div className="flex flex-wrap gap-2">
              {DIAGNOSTIC_CHECKS.map((c) => (
                <label key={c} className="flex items-center gap-1 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedChecks.has(c)}
                    onChange={() => toggleCheck(c)}
                    className="rounded border-zinc-300 dark:border-zinc-600"
                  />
                  <span className="text-zinc-700 dark:text-zinc-300">{c}</span>
                </label>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRunSelected}
              disabled={runDiagnostics.isPending || selectedChecks.size === 0}
            >
              Run selected
            </Button>
          </div>

          {displayResult && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Latest run — {formatTimestampEtFull(displayResult.timestamp_utc)} · Overall: {displayResult.overall_status}
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Check</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {displayResult.checks?.map((ch, i) => (
                    <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800/50">
                      <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{ch.check}</td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={ch.status} />
                      </td>
                      <td className="py-2 text-zinc-500 dark:text-zinc-400">
                        {typeof ch.details === "object" && ch.details
                          ? JSON.stringify(ch.details)
                          : String(ch.details ?? "—")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {runs.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Last {runs.length} runs
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Timestamp (UTC)</th>
                    <th className="py-2 pr-2">Overall</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r, i) => (
                    <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800/50">
                      <td className="py-2 pr-2 font-mono text-zinc-700 dark:text-zinc-300">{formatTimestampEtFull(r.timestamp_utc)}</td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={r.overall_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
