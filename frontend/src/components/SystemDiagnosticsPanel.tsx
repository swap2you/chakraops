/**
 * Lightweight diagnostics panel showing system state, ORATS status, and warnings/errors.
 * Can be used standalone or embedded in other views.
 */
import { useApiSnapshot, formatSnapshotAge, hasSnapshotWarnings, hasSnapshotErrors } from "@/hooks/useApiSnapshot";
import { useApiDataHealth, formatDataAge } from "@/hooks/useApiDataHealth";
import { useDataMode } from "@/context/DataModeContext";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCw, Clock, Database, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface SystemDiagnosticsPanelProps {
  className?: string;
  compact?: boolean;
}

export function SystemDiagnosticsPanel({ className }: SystemDiagnosticsPanelProps) {
  const { mode } = useDataMode();
  const { snapshot, loading: snapshotLoading, error: snapshotError, refetch: refetchSnapshot } = useApiSnapshot();
  const dataHealth = useApiDataHealth();

  if (mode !== "LIVE") {
    return (
      <div className={cn("rounded-lg border border-border bg-card p-4", className)}>
        <p className="text-sm text-muted-foreground">Diagnostics available in LIVE mode only.</p>
      </div>
    );
  }

  const oratsOk = dataHealth.status === "OK";
  const oratsDown = dataHealth.status === "DOWN" || dataHealth.status === "UNKNOWN";
  const oratsDegraded = dataHealth.status === "DEGRADED";

  return (
    <div className={cn("space-y-4 rounded-lg border border-border bg-card p-4", className)}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">System Diagnostics</h2>
        <button
          type="button"
          onClick={refetchSnapshot}
          disabled={snapshotLoading}
          className="flex items-center gap-1 rounded-md border border-border bg-secondary/50 px-2 py-1 text-xs font-medium hover:bg-secondary disabled:opacity-50"
          title="Refresh snapshot"
        >
          <RefreshCw className={cn("h-3 w-3", snapshotLoading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* ORATS Data Health */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm">
          <Database className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium">ORATS Data Provider</span>
        </div>
        <div className="ml-6 space-y-1 text-sm">
          <div className="flex items-center gap-2">
            {oratsOk && <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />}
            {oratsDegraded && <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />}
            {oratsDown && <XCircle className="h-4 w-4 text-destructive" />}
            <span className={cn(
              oratsOk && "text-green-600 dark:text-green-400",
              oratsDegraded && "text-amber-600 dark:text-amber-400",
              oratsDown && "text-destructive"
            )}>
              {dataHealth.status}
            </span>
            {dataHealth.last_success_at && (
              <span className="text-muted-foreground">
                — last success {formatDataAge(dataHealth.last_success_at)}
              </span>
            )}
          </div>
          {dataHealth.last_error_reason && (
            <p className="text-xs text-destructive">{dataHealth.last_error_reason}</p>
          )}
          {dataHealth.avg_latency_seconds != null && (
            <p className="text-xs text-muted-foreground">
              Avg latency: {dataHealth.avg_latency_seconds.toFixed(2)}s
            </p>
          )}
        </div>
      </div>

      {/* System Snapshot */}
      {snapshot && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <Zap className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">System Snapshot</span>
            <span className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium",
              snapshot.snapshot_phase === "COMPLETE" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
              snapshot.snapshot_phase === "STALE" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
              snapshot.snapshot_phase === "ERROR" && "bg-destructive/20 text-destructive",
              snapshot.snapshot_phase === "IDLE" && "bg-muted text-muted-foreground",
              snapshot.snapshot_phase === "EVALUATING" && "bg-blue-500/20 text-blue-600 dark:text-blue-400"
            )}>
              {snapshot.snapshot_phase}
            </span>
            <span className="text-xs text-muted-foreground">
              {formatSnapshotAge(snapshot.snapshot_time_utc)}
            </span>
          </div>
          <div className="ml-6 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
            <div>
              <span className="text-muted-foreground">Mode:</span>{" "}
              <span className="font-medium">{snapshot.run_mode}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Market:</span>{" "}
              <span className="font-medium">{snapshot.market_status.phase ?? "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">ORATS:</span>{" "}
              <span className={cn(
                "font-medium",
                snapshot.orats_status === "OK" && "text-emerald-600 dark:text-emerald-400",
                snapshot.orats_status === "DOWN" && "text-destructive"
              )}>{snapshot.orats_status}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Universe:</span>{" "}
              <span className="font-medium">{snapshot.universe.total}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Evaluated:</span>{" "}
              <span className="font-medium">{snapshot.universe.evaluated}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Eligible:</span>{" "}
              <span className="font-medium">{snapshot.universe.eligible}</span>
            </div>
          </div>

          {/* Decision state */}
          {snapshot.snapshot_state && (
            <div className="ml-6 flex flex-wrap items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Decision age:</span>
                <span className={cn(
                  "font-medium",
                  snapshot.snapshot_state.decision_stale && "text-amber-600 dark:text-amber-400"
                )}>
                  {snapshot.snapshot_state.decision_age_seconds != null
                    ? `${Math.floor(snapshot.snapshot_state.decision_age_seconds / 60)}m`
                    : "—"}
                </span>
                {snapshot.snapshot_state.decision_stale && (
                  <span className="text-xs text-amber-600 dark:text-amber-400">(stale)</span>
                )}
              </div>
              <div>
                <span className="text-muted-foreground">Source:</span>{" "}
                <span className="font-medium">{snapshot.snapshot_state.decision_source}</span>
              </div>
            </div>
          )}

          {/* Final Trade */}
          {snapshot.final_trade && (
            <div className="ml-6 rounded-md bg-green-500/10 p-2 text-sm">
              <span className="font-medium text-green-700 dark:text-green-400">
                Final Trade: {snapshot.final_trade.symbol}
              </span>
              {snapshot.final_trade.strategy && (
                <span className="ml-2 text-muted-foreground">
                  ({snapshot.final_trade.strategy})
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Warnings */}
      {snapshot && hasSnapshotWarnings(snapshot) && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            Warnings ({snapshot.warnings.length})
          </div>
          <ul className="ml-6 list-inside list-disc space-y-0.5 text-sm text-amber-600 dark:text-amber-400">
            {snapshot.warnings.map((w, i) => (
              <li key={i}>
                {typeof w === "string" ? w : w.message}
                {typeof w !== "string" && w.code && <span className="ml-1 text-xs opacity-75">({w.code})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Errors */}
      {snapshot && hasSnapshotErrors(snapshot) && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm font-medium text-destructive">
            <XCircle className="h-4 w-4" />
            Errors ({snapshot.errors.length})
          </div>
          <ul className="ml-6 list-inside list-disc space-y-0.5 text-sm text-destructive">
            {snapshot.errors.map((e, i) => (
              <li key={i}>
                {typeof e === "string" ? e : e.message}
                {typeof e !== "string" && e.code && <span className="ml-1 text-xs opacity-75">({e.code})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Snapshot Error */}
      {snapshotError && (
        <div className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">
          <span className="font-medium">Snapshot fetch failed:</span> {snapshotError}
        </div>
      )}

      {/* Loading state */}
      {snapshotLoading && !snapshot && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading diagnostics...
        </div>
      )}

      {/* No data */}
      {!snapshot && !snapshotLoading && !snapshotError && (
        <p className="text-sm text-muted-foreground">No snapshot data available.</p>
      )}
    </div>
  );
}
