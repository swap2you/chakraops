import { useState } from "react";
import { useArtifactList, useDecision } from "@/api/queries";
import type { DecisionMode } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";

export function DashboardPage() {
  const [mode, setMode] = useState<DecisionMode>("LIVE");
  const [filename, setFilename] = useState<string>("decision_latest.json");

  const { data: files, isError: filesError, isLoading: filesLoading } = useArtifactList(mode);
  const { data: decision, isError: decisionError, isLoading: decisionLoading } = useDecision(
    mode,
    filename
  );

  const isLoading = filesLoading || decisionLoading;
  const isError = filesError || decisionError;

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Dashboard" />
        <p className="text-zinc-400">Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Dashboard" />
        <p className="text-red-400">Failed to load decision data.</p>
      </div>
    );
  }

  const snapshot = decision?.decision_snapshot;
  const stats = snapshot?.stats;
  const executionPlan = decision?.execution_plan;
  const executionGate = decision?.execution_gate;
  const metadata = decision?.metadata;

  return (
    <div>
      <PageHeader title="Dashboard" />
      <div className="mb-4 flex items-center gap-4">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as DecisionMode)}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-200"
        >
          <option value="LIVE">LIVE</option>
          <option value="MOCK">MOCK</option>
        </select>
        <select
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-200"
        >
          {files?.files.map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-4">
        <section>
          <h2 className="mb-2 text-sm font-medium text-zinc-400">Stats</h2>
          <div className="grid grid-cols-3 gap-2 rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <div>
              <span className="text-zinc-500">symbols_evaluated</span>
              <p className="font-mono">{stats?.symbols_evaluated ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">total_candidates</span>
              <p className="font-mono">{stats?.total_candidates ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">selected_count</span>
              <p className="font-mono">{stats?.selected_count ?? "—"}</p>
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-zinc-400">Execution Gate</h2>
          <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="flex items-center gap-2">
              <StatusBadge status={executionGate?.allowed ? "ALLOWED" : "BLOCKED"} />
              <span className="text-zinc-400">
                {executionGate?.reasons?.join("; ") ?? "—"}
              </span>
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-zinc-400">Execution Plan</h2>
          <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <div className="flex items-center gap-2">
              <StatusBadge status={executionPlan?.allowed ? "ALLOWED" : "BLOCKED"} />
              <span className="text-zinc-400">{executionPlan?.blocked_reason ?? "—"}</span>
              <span className="text-zinc-500">orders: {executionPlan?.orders?.length ?? 0}</span>
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-zinc-400">Selected Signals</h2>
          <div className="overflow-x-auto rounded border border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/50">
                  <th className="px-3 py-2 text-left text-zinc-400">Symbol</th>
                  <th className="px-3 py-2 text-left text-zinc-400">Verdict</th>
                  <th className="px-3 py-2 text-left text-zinc-400">Strategy</th>
                  <th className="px-3 py-2 text-left text-zinc-400">Strike</th>
                  <th className="px-3 py-2 text-left text-zinc-400">Delta</th>
                </tr>
              </thead>
              <tbody>
                {snapshot?.selected_signals?.map((s, i) => (
                  <tr key={i} className="border-b border-zinc-800/50 last:border-0">
                    <td className="px-3 py-2 font-mono">{s.symbol}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={s.verdict} />
                    </td>
                    <td className="px-3 py-2">{s.candidate?.strategy ?? "—"}</td>
                    <td className="px-3 py-2 font-mono">{s.candidate?.strike ?? "—"}</td>
                    <td className="px-3 py-2 font-mono">{s.candidate?.delta ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(!snapshot?.selected_signals?.length) && (
              <p className="p-4 text-zinc-500">No selected signals.</p>
            )}
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium text-zinc-400">Metadata</h2>
          <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <p>
              <span className="text-zinc-500">data_source</span>{" "}
              <span className="font-mono">{metadata?.data_source ?? "—"}</span>
            </p>
            <p>
              <span className="text-zinc-500">pipeline_timestamp</span>{" "}
              <span className="font-mono">{metadata?.pipeline_timestamp ?? "—"}</span>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
