import { useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Activity, Droplets, Zap } from "lucide-react";
import { useArtifactList, useDecision, useUniverse, useUiSystemHealth, useUiTrackedPositions } from "@/api/queries";
import type { DecisionMode } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";

function fmtTs(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return s;
  }
}

export function DashboardPage() {
  const [mode, setMode] = useState<DecisionMode>("LIVE");
  const [filename, setFilename] = useState<string>("decision_latest.json");

  const { data: files } = useArtifactList(mode);
  const { data: decision } = useDecision(mode, filename);
  useUniverse();
  const { data: health } = useUiSystemHealth();
  const { data: positionsRes } = useUiTrackedPositions();

  const isLoading = !decision;

  if (isLoading || !decision) {
    return (
      <div className="space-y-3">
        <PageHeader title="Command Center" />
        <p className="text-sm text-zinc-500">Loading…</p>
      </div>
    );
  }

  const snapshot = decision.decision_snapshot;
  const metadata = decision.metadata;
  const selectedSignals = snapshot?.selected_signals ?? [];
  const positions = positionsRes?.positions ?? [];
  const openPositions = positions.filter((p) => (p.status ?? "").toUpperCase() === "OPEN" || (p.status ?? "").toUpperCase() === "PARTIAL_EXIT");
  const capitalDeployed = openPositions.reduce((sum, p) => sum + (p.notional ?? 0), 0);

  const marketPhase = health?.market?.phase ?? "—";
  const oratsStatus = health?.orats?.status ?? "—";
  const lastEvalTs = metadata?.pipeline_timestamp ?? health?.market?.timestamp;

  return (
    <div className="space-y-3">
      <PageHeader title="Command Center" />
      <div className="mb-2 flex items-center gap-4">
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
          {(files?.files ?? []).map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
      </div>

      {/* 1. Top Strip */}
      <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
        <div className="flex flex-wrap items-center gap-6 text-sm">
          <div>
            <span className="block text-xs text-zinc-500">Mode</span>
            <span className="font-mono font-medium text-zinc-200">{mode}</span>
          </div>
          <div>
            <span className="block text-xs text-zinc-500">Market</span>
            <span className="font-mono text-zinc-300">{marketPhase}</span>
          </div>
          <div>
            <span className="block text-xs text-zinc-500">Last eval</span>
            <span className="font-mono text-zinc-300">{fmtTs(lastEvalTs)}</span>
          </div>
          <div>
            <span className="block text-xs text-zinc-500">ORATS</span>
            <span
              className={
                oratsStatus === "OK"
                  ? "font-mono text-emerald-400"
                  : oratsStatus === "WARN"
                    ? "font-mono text-amber-400"
                    : "font-mono text-zinc-400"
              }
            >
              {oratsStatus}
            </span>
          </div>
        </div>
      </section>

      {/* 2. Main: Candidates + Positions */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {/* Left: Candidate list from selected_signals */}
        <div className="space-y-3 lg:col-span-2">
          <CandidatePanel signals={selectedSignals} />
        </div>

        {/* Right column */}
        <div className="space-y-3">
          <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Positions
            </h3>
            <p className="font-mono text-lg font-semibold text-zinc-200">{openPositions.length}</p>
            <p className="text-xs text-zinc-500">{positions.length} total</p>
            {positions.length > 0 && (
              <div className="mt-2 space-y-1">
                {positions.slice(0, 5).map((p, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <Link
                      to={`/symbol-diagnostics?symbol=${encodeURIComponent(p.symbol)}`}
                      className="font-mono text-zinc-300 hover:text-zinc-100"
                    >
                      {p.symbol}
                    </Link>
                    <span className="font-mono text-zinc-500">
                      {p.contracts != null ? `${p.contracts}×` : p.qty != null ? `${p.qty}` : ""}{" "}
                      {p.notional != null ? `$${p.notional.toLocaleString()}` : ""}
                    </span>
                  </div>
                ))}
                {positions.length > 5 && (
                  <p className="text-xs text-zinc-500">+{positions.length - 5} more</p>
                )}
              </div>
            )}
          </section>
          <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Capital Deployed
            </h3>
            <p className="font-mono text-lg font-semibold text-zinc-200">
              ${capitalDeployed.toLocaleString()}
            </p>
          </section>
          <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Earnings Alerts
            </h3>
            <p className="text-sm text-zinc-400">—</p>
          </section>
          <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Data Freshness
            </h3>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-zinc-300">{health?.orats?.status ?? "—"}</span>
            </div>
            <p className="mt-1 text-xs text-zinc-500">
              {health?.orats?.last_success_at ? fmtTs(health.orats.last_success_at) : "—"}
            </p>
          </section>
        </div>
      </div>

      {/* 3. Bottom: System health tiles (api / orats / market) */}
      <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          System Health
        </h3>
        <div className="flex flex-wrap gap-4 text-sm">
          <div className="flex items-center gap-2">
            <Activity
              className={`h-4 w-4 ${health?.api?.status === "OK" ? "text-emerald-400" : "text-red-400"}`}
            />
            <span className="text-zinc-500">API</span>
            <span className={health?.api?.status === "OK" ? "text-emerald-400" : "text-red-400"}>
              {health?.api?.status ?? "—"}
            </span>
            {health?.api?.latency_ms != null && (
              <span className="text-zinc-500">{health.api.latency_ms}ms</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Droplets
              className={
                health?.orats?.status === "OK"
                  ? "h-4 w-4 text-emerald-400"
                  : health?.orats?.status === "WARN"
                    ? "h-4 w-4 text-amber-400"
                    : "h-4 w-4 text-zinc-500"
              }
            />
            <span className="text-zinc-500">ORATS</span>
            <span
              className={
                health?.orats?.status === "OK"
                  ? "text-emerald-400"
                  : health?.orats?.status === "WARN"
                    ? "text-amber-400"
                    : "text-zinc-400"
              }
            >
              {health?.orats?.status ?? "—"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Zap
              className={`h-4 w-4 ${health?.market?.is_open ? "text-emerald-400" : "text-zinc-500"}`}
            />
            <span className="text-zinc-500">Market</span>
            <span className="text-zinc-400">{health?.market?.phase ?? "—"}</span>
          </div>
        </div>
      </section>
    </div>
  );
}

function CandidatePanel({ signals }: { signals: Array<{ symbol: string; verdict?: string; candidate?: { strategy?: string; strike?: number; delta?: number; credit_estimate?: number; max_loss?: number; expiry?: string } }> }) {
  return (
    <section className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Candidates
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-700 text-left text-zinc-500">
              <th className="py-2 pr-2">symbol</th>
              <th className="py-2 pr-2">verdict</th>
              <th className="py-2 pr-2">strategy</th>
              <th className="py-2 pr-2">strike</th>
              <th className="py-2 pr-2">delta</th>
              <th className="py-2 w-16"></th>
            </tr>
          </thead>
          <tbody>
            {signals.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-2 text-zinc-500">
                  None
                </td>
              </tr>
            ) : (
              signals.map((s) => (
                <tr key={s.symbol} className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30">
                  <td className="py-2 pr-2 font-mono font-medium text-zinc-200">{s.symbol}</td>
                  <td className="py-2 pr-2">
                    <span
                      className={
                        (s.verdict ?? "").toUpperCase() === "ELIGIBLE"
                          ? "text-emerald-400"
                          : (s.verdict ?? "").toUpperCase() === "HOLD"
                            ? "text-amber-400"
                            : "text-zinc-400"
                      }
                    >
                      {s.verdict ?? "—"}
                    </span>
                  </td>
                  <td className="py-2 pr-2 font-mono text-zinc-300">{s.candidate?.strategy ?? "—"}</td>
                  <td className="py-2 pr-2 font-mono text-zinc-300">{s.candidate?.strike ?? "—"}</td>
                  <td className="py-2 pr-2 font-mono text-zinc-300">{s.candidate?.delta != null ? s.candidate.delta.toFixed(3) : "—"}</td>
                  <td className="py-2">
                    <Link
                      to={`/symbol-diagnostics?symbol=${encodeURIComponent(s.symbol)}`}
                      className="inline-flex items-center gap-1 rounded border border-zinc-600 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-700"
                    >
                      Open
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
