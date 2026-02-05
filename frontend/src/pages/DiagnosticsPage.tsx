/**
 * Diagnostics page — lightweight view for system state, ORATS health, warnings/errors.
 * Shows snapshot_phase, pipeline_steps, invariant warnings, and actionable error codes.
 * Replaces "UNKNOWN" with reasoned states explaining WHY something is in that state.
 */
import { SystemDiagnosticsPanel } from "@/components/SystemDiagnosticsPanel";
import { useDataMode } from "@/context/DataModeContext";
import { useApiSnapshot, hasSnapshotErrors, hasSnapshotWarnings, type PipelineStep } from "@/hooks/useApiSnapshot";
import { useApiDataHealth } from "@/hooks/useApiDataHealth";
import { useApiOpsStatus } from "@/hooks/useApiOpsStatus";
import { cn } from "@/lib/utils";
import { AlertTriangle, XCircle, CheckCircle2, Clock, HelpCircle, Loader2 } from "lucide-react";

function formatIsoDate(iso: string | null | undefined, reason?: string): string {
  if (!iso) return reason ?? "Not available yet";
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? (reason ?? "Invalid date") : d.toLocaleString();
  } catch {
    return reason ?? "Invalid date";
  }
}

function formatSeconds(seconds: number | null | undefined, reason?: string): string {
  if (seconds == null) return reason ?? "Not measured";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function PipelineStepIcon({ status }: { status: PipelineStep["status"] }) {
  switch (status) {
    case "OK": return <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />;
    case "WARN": return <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />;
    case "ERROR": return <XCircle className="h-4 w-4 text-destructive" />;
    case "NOT_RUN": return <Clock className="h-4 w-4 text-muted-foreground" />;
    case "PENDING": return <HelpCircle className="h-4 w-4 text-muted-foreground" />;
    case "RUNNING": return <Loader2 className="h-4 w-4 animate-spin text-blue-600 dark:text-blue-400" />;
    default: return <HelpCircle className="h-4 w-4 text-muted-foreground" />;
  }
}

function getEvaluationStateColor(state: string): string {
  switch (state) {
    case "COMPLETED": return "text-emerald-600 dark:text-emerald-400";
    case "RUNNING": return "text-blue-600 dark:text-blue-400";
    case "FAILED": return "text-destructive";
    case "IDLE": 
    default: return "text-muted-foreground";
  }
}

export function DiagnosticsPage() {
  const { mode } = useDataMode();
  const { snapshot, loading: snapshotLoading, refetch: refetchSnapshot } = useApiSnapshot();
  const dataHealth = useApiDataHealth();
  const opsStatus = useApiOpsStatus();

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold">Diagnostics</h1>
      <p className="text-muted-foreground">System state, data health, and operational status.</p>

      {mode !== "LIVE" && (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-muted-foreground">Switch to LIVE mode to view diagnostics.</p>
        </div>
      )}

      {mode === "LIVE" && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Snapshot Lifecycle — explains what the snapshot represents */}
          {snapshot && (
            <section className="rounded-lg border border-border bg-card p-4 lg:col-span-2">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">Snapshot Lifecycle</h2>
                  <p className="text-xs text-muted-foreground">
                    The snapshot is a point-in-time summary of system state. It does not trigger ORATS calls.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={refetchSnapshot}
                  disabled={snapshotLoading}
                  className="rounded-md border border-border bg-secondary/50 px-2 py-1 text-xs font-medium hover:bg-secondary disabled:opacity-50"
                >
                  {snapshotLoading ? "Loading..." : "Refresh"}
                </button>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-6">
                <div>
                  <dt className="text-muted-foreground">Phase</dt>
                  <dd className={cn(
                    "font-semibold",
                    snapshot.snapshot_phase === "COMPLETE" && "text-emerald-600 dark:text-emerald-400",
                    snapshot.snapshot_phase === "EVALUATING" && "text-blue-600 dark:text-blue-400",
                    snapshot.snapshot_phase === "STALE" && "text-amber-600 dark:text-amber-400",
                    snapshot.snapshot_phase === "ERROR" && "text-destructive",
                    snapshot.snapshot_phase === "IDLE" && "text-muted-foreground"
                  )}>
                    {snapshot.snapshot_phase}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Evaluation State</dt>
                  <dd className={cn("font-semibold", getEvaluationStateColor(snapshot.evaluation_state))}>
                    {snapshot.evaluation_state}
                  </dd>
                  <dd className="text-xs text-muted-foreground truncate" title={snapshot.evaluation_state_reason}>
                    {snapshot.evaluation_state_reason}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Decision Age</dt>
                  <dd className="font-medium">
                    {formatSeconds(snapshot.snapshot_state?.decision_age_seconds, "No evaluation yet")}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Stale Threshold</dt>
                  <dd className="font-medium">{formatSeconds(snapshot.stale_threshold_seconds)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Decision Source</dt>
                  <dd className="font-medium">
                    {snapshot.snapshot_state?.decision_source === "artifact" 
                      ? "From artifact" 
                      : "No artifact (evaluation not run)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">ORATS Status</dt>
                  <dd className={cn(
                    "font-medium",
                    snapshot.orats_connected && "text-emerald-600 dark:text-emerald-400",
                    snapshot.orats_status === "DOWN" && "text-destructive",
                    !snapshot.orats_connected && snapshot.orats_status !== "DOWN" && "text-muted-foreground"
                  )}>
                    {snapshot.orats_status}
                  </dd>
                  <dd className="text-xs text-muted-foreground truncate" title={snapshot.orats_status_reason}>
                    {snapshot.orats_status_reason}
                  </dd>
                </div>
              </dl>
              <dl className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-muted-foreground">Last Decision ID</dt>
                  <dd className="font-mono text-xs">
                    {snapshot.snapshot_state?.last_decision_id ?? "None — run evaluation first"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Last Decision Time</dt>
                  <dd className="font-medium">
                    {formatIsoDate(snapshot.snapshot_state?.last_decision_time_utc, "No evaluation run yet")}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Next Scheduled Refresh</dt>
                  <dd className="font-medium">{formatIsoDate(snapshot.next_scheduled_refresh_utc)}</dd>
                </div>
              </dl>
            </section>
          )}

          {/* Pipeline Steps — shows each step's status with full explainability */}
          {snapshot?.pipeline_steps && snapshot.pipeline_steps.length > 0 && (
            <section className="rounded-lg border border-border bg-card p-4 lg:col-span-2">
              <h2 className="text-sm font-semibold text-foreground">Pipeline Steps</h2>
              <p className="text-xs text-muted-foreground">
                Evaluation pipeline status. All steps should be OK for a complete evaluation.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Step</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 pr-4 font-medium">Detail</th>
                      <th className="py-2 pr-4 font-medium">Last Transition</th>
                      <th className="py-2 font-medium">Blocking</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.pipeline_steps.map((step, i) => (
                      <tr key={i} className={cn(
                        "border-b border-border/50",
                        step.blocking && "bg-destructive/5"
                      )}>
                        <td className="py-2 pr-4">
                          <span className="font-medium">{step.step}</span>
                          {step.explanation && (
                            <p className="text-xs text-muted-foreground">{step.explanation}</p>
                          )}
                        </td>
                        <td className="py-2 pr-4">
                          <div className="flex items-center gap-2">
                            <PipelineStepIcon status={step.status} />
                            <span className={cn(
                              step.status === "OK" && "text-emerald-600 dark:text-emerald-400",
                              step.status === "WARN" && "text-amber-600 dark:text-amber-400",
                              step.status === "ERROR" && "text-destructive",
                              step.status === "RUNNING" && "text-blue-600 dark:text-blue-400",
                              (step.status === "NOT_RUN" || step.status === "PENDING") && "text-muted-foreground"
                            )}>
                              {step.status}
                            </span>
                          </div>
                        </td>
                        <td className="py-2 pr-4 text-muted-foreground">{step.detail}</td>
                        <td className="py-2 pr-4 text-muted-foreground text-xs">
                          {formatIsoDate(step.last_transition_time, "Not run yet")}
                        </td>
                        <td className="py-2">
                          {step.blocking ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-destructive/20 px-2 py-0.5 text-xs font-medium text-destructive">
                              <XCircle className="h-3 w-3" /> Blocking
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">No</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Warnings Table */}
          {snapshot && hasSnapshotWarnings(snapshot) && (
            <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 lg:col-span-2">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-amber-700 dark:text-amber-400">
                <AlertTriangle className="h-4 w-4" />
                Warnings ({snapshot.warnings.length})
              </h2>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-amber-500/30 text-left text-amber-700 dark:text-amber-400">
                      <th className="py-2 pr-4 font-medium">Code</th>
                      <th className="py-2 font-medium">Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.warnings.map((w, i) => (
                      <tr key={i} className="border-b border-amber-500/20">
                        <td className="py-2 pr-4 font-mono text-xs">{typeof w === "string" ? "LEGACY" : w.code}</td>
                        <td className="py-2 text-amber-800 dark:text-amber-300">{typeof w === "string" ? w : w.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Errors Table */}
          {snapshot && hasSnapshotErrors(snapshot) && (
            <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 lg:col-span-2">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-destructive">
                <XCircle className="h-4 w-4" />
                Errors ({snapshot.errors.length})
              </h2>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-destructive/30 text-left text-destructive">
                      <th className="py-2 pr-4 font-medium">Code</th>
                      <th className="py-2 font-medium">Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.errors.map((e, i) => (
                      <tr key={i} className="border-b border-destructive/20">
                        <td className="py-2 pr-4 font-mono text-xs">{typeof e === "string" ? "LEGACY" : e.code}</td>
                        <td className="py-2">{typeof e === "string" ? e : e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Main diagnostics panel */}
          <SystemDiagnosticsPanel className="lg:col-span-2" />

          {/* Detailed status sections */}
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-semibold text-foreground">ORATS Data Health</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Provider</dt>
                <dd className="font-medium">{dataHealth.provider}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Live Status</dt>
                <dd className={cn(
                  "font-medium",
                  dataHealth.status === "OK" && "text-emerald-600 dark:text-emerald-400",
                  dataHealth.status === "DOWN" && "text-destructive"
                )}>{dataHealth.status}</dd>
              </div>
              {/* Show snapshot's reasoned ORATS status */}
              {snapshot?.orats_status_reason && (
                <div>
                  <dt className="text-muted-foreground">Cached Status Reason</dt>
                  <dd className="mt-1 text-xs text-muted-foreground">{snapshot.orats_status_reason}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Entitlement</dt>
                <dd className="font-medium">{dataHealth.entitlement || "Not checked"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Last Success</dt>
                <dd className="font-medium">{formatIsoDate(dataHealth.last_success_at, "No successful call yet")}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Last Error</dt>
                <dd className="font-medium">{formatIsoDate(dataHealth.last_error_at, "No errors")}</dd>
              </div>
              {dataHealth.last_error_reason && (
                <div>
                  <dt className="text-muted-foreground">Error Reason</dt>
                  <dd className="mt-1 text-xs text-destructive">{dataHealth.last_error_reason}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Avg Latency</dt>
                <dd className="font-medium">
                  {dataHealth.avg_latency_seconds != null ? `${dataHealth.avg_latency_seconds.toFixed(2)}s` : "Not measured"}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="text-sm font-semibold text-foreground">Operations Status</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Market Phase</dt>
                <dd className="font-medium">{opsStatus.market_phase ?? "—"}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Last Run</dt>
                <dd className="font-medium">{formatIsoDate(opsStatus.last_run_at)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Next Run</dt>
                <dd className="font-medium">{formatIsoDate(opsStatus.next_run_at)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Cadence</dt>
                <dd className="font-medium">{opsStatus.cadence_minutes} min</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Symbols Evaluated</dt>
                <dd className="font-medium">{opsStatus.symbols_evaluated}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Trades Found</dt>
                <dd className="font-medium">{opsStatus.trades_found}</dd>
              </div>
              {opsStatus.last_run_reason && (
                <div>
                  <dt className="text-muted-foreground">Last Skip Reason</dt>
                  <dd className="mt-1 text-xs text-amber-600 dark:text-amber-400">{opsStatus.last_run_reason}</dd>
                </div>
              )}
            </dl>
          </section>

          {/* Blockers summary */}
          {Object.keys(opsStatus.blockers_summary).length > 0 && (
            <section className="rounded-lg border border-border bg-card p-4 lg:col-span-2">
              <h2 className="text-sm font-semibold text-foreground">Blockers Summary</h2>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Code</th>
                      <th className="py-2 font-medium">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(opsStatus.blockers_summary)
                      .sort(([, a], [, b]) => b - a)
                      .map(([code, count]) => (
                        <tr key={code} className="border-b border-border/50">
                          <td className="py-2 pr-4 font-medium">{code}</td>
                          <td className="py-2">{count}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Market Status Details */}
          {snapshot && (
            <section className="rounded-lg border border-border bg-card p-4 lg:col-span-2">
              <h2 className="text-sm font-semibold text-foreground">Market Status Details</h2>
              <dl className="mt-3 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-muted-foreground">Last Market Check</dt>
                  <dd className="font-medium">{formatIsoDate(snapshot.market_status.last_market_check)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Last Evaluated</dt>
                  <dd className="font-medium">{formatIsoDate(snapshot.market_status.last_evaluated_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Evaluation Attempted</dt>
                  <dd className="font-medium">{snapshot.market_status.evaluation_attempted ? "Yes" : "No"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Evaluation Emitted</dt>
                  <dd className="font-medium">{snapshot.market_status.evaluation_emitted ? "Yes" : "No"}</dd>
                </div>
              </dl>
              {snapshot.market_status.skip_reason && (
                <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
                  Skip reason: {snapshot.market_status.skip_reason}
                </p>
              )}
            </section>
          )}

          {/* Evaluation Window */}
          {snapshot?.evaluation_window && (
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-sm font-semibold text-foreground">Evaluation Window</h2>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Date</dt>
                  <dd className="font-medium">{snapshot.evaluation_window.date}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">As-of Time</dt>
                  <dd className="font-medium">{formatIsoDate(snapshot.evaluation_window.asof_time_utc)}</dd>
                </div>
              </dl>
            </section>
          )}

          {/* Universe Counts */}
          {snapshot && (
            <section className="rounded-lg border border-border bg-card p-4">
              <h2 className="text-sm font-semibold text-foreground">Universe Counts</h2>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Total</dt>
                  <dd className="font-medium">{snapshot.universe.total}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Evaluated</dt>
                  <dd className="font-medium">{snapshot.universe.evaluated}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Eligible</dt>
                  <dd className="font-medium">{snapshot.universe.eligible}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Shortlisted</dt>
                  <dd className="font-medium">{snapshot.universe.shortlisted}</dd>
                </div>
              </dl>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
