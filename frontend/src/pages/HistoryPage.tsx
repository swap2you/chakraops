/**
 * Phase 8 / 8.5: Decision Audit UX — review historical system decisions.
 * Read-only: chronological list, filters (date range, decision type), detail view.
 * In MOCK mode uses scenario bundle for coherent Dashboard + Positions + History.
 * 
 * NEW: Also shows evaluation run history from persistent store.
 */
import { useEffect, useState, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { getDecisionHistory } from "@/data/source";
import { useDataMode } from "@/context/DataModeContext";
import { useScenario } from "@/context/ScenarioContext";
import { usePolling } from "@/context/PollingContext";
import { useApiSnapshot } from "@/hooks/useApiSnapshot";
import type { DecisionRecord, DecisionOutcome } from "@/types/views";
import type { EvaluationRunsResponse, EvaluationRunSummary } from "@/types/universeEvaluation";
import { DecisionDetailDrawer } from "@/components/DecisionDetailDrawer";
import { EmptyState } from "@/components/EmptyState";
import { pushSystemNotification, pushSystemNotificationItem, systemNotificationFromWarnings } from "@/lib/notifications";
import { validateDecisionHistory } from "@/mock/validator";
import { cn } from "@/lib/utils";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { Info, CheckCircle2, XCircle, Clock, Loader2 } from "lucide-react";

const OUTCOME_LABEL: Record<DecisionOutcome, string> = {
  TRADE: "Trade",
  NO_TRADE: "No trade",
  RISK_HOLD: "Risk hold",
};

const OUTCOME_CLASS: Record<DecisionOutcome, string> = {
  TRADE: "bg-emerald-500/20 text-emerald-400",
  NO_TRADE: "bg-slate-500/20 text-slate-300",
  RISK_HOLD: "bg-amber-500/20 text-amber-400",
};

function formatDateOnly(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return Number.isNaN(d.getTime()) ? dateStr : d.toLocaleDateString(undefined, { dateStyle: "medium" });
  } catch {
    return dateStr;
  }
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleTimeString(undefined, { timeStyle: "short" });
  } catch {
    return ts;
  }
}

function liveErrorMessage(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

const STATUS_CLASS: Record<string, string> = {
  COMPLETED: "bg-emerald-500/20 text-emerald-400",
  FAILED: "bg-red-500/20 text-red-400",
  RUNNING: "bg-blue-500/20 text-blue-400",
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  COMPLETED: <CheckCircle2 className="h-4 w-4" />,
  FAILED: <XCircle className="h-4 w-4" />,
  RUNNING: <Loader2 className="h-4 w-4 animate-spin" />,
};

export function HistoryPage() {
  const { mode } = useDataMode();
  const scenario = useScenario();
  const polling = usePolling();
  const pollTick = polling?.pollTick ?? 0;
  const { snapshot } = useApiSnapshot();
  const [records, setRecords] = useState<DecisionRecord[]>([]);
  const [evalRuns, setEvalRuns] = useState<EvaluationRunSummary[]>([]);
  const [latestRunId, setLatestRunId] = useState<string | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DecisionRecord | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filterType, setFilterType] = useState<DecisionOutcome | "">("");
  const [activeTab, setActiveTab] = useState<"decisions" | "evaluations">("evaluations");

  // Fetch evaluation runs
  const fetchEvalRuns = useCallback(async () => {
    if (mode !== "LIVE") return;
    try {
      const data = await apiGet<EvaluationRunsResponse>(ENDPOINTS.evaluationRuns);
      setEvalRuns(data.runs);
      setLatestRunId(data.latest_run_id);
    } catch (e) {
      console.error("Failed to fetch evaluation runs:", e);
    }
  }, [mode]);

  // Fetch evaluation runs on mount
  useEffect(() => {
    if (mode === "LIVE") {
      fetchEvalRuns();
    }
  }, [mode, fetchEvalRuns, pollTick]);

  useEffect(() => {
    if (mode === "MOCK" && scenario?.bundle) {
      setLiveError(null);
      setRecords(scenario.bundle.decisionHistory ?? []);
      return;
    }
    if (mode !== "LIVE") return;
    let cancelled = false;
    setLiveError(null);
    getDecisionHistory(mode)
      .then((list) => {
        if (!cancelled) {
          setRecords(list ?? []);
          const evaluatedAt = list?.[0]?.evaluated_at ?? new Date().toISOString();
          const warnings = validateDecisionHistory(list ?? null);
          if (warnings.length > 0) {
            const items = systemNotificationFromWarnings(warnings, "LIVE", evaluatedAt);
            items.forEach((item) => pushSystemNotificationItem(item));
          }
        }
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = liveErrorMessage(e);
          setLiveError(msg);
          pushSystemNotification({
            source: "system",
            severity: "error",
            title: "LIVE fetch failed",
            message: msg,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, scenario?.bundle, mode === "LIVE" ? pollTick : 0]);

  const filtered = useMemo(() => {
    let list = [...records];
    if (dateFrom) {
      list = list.filter((r) => r.date >= dateFrom);
    }
    if (dateTo) {
      list = list.filter((r) => r.date <= dateTo);
    }
    if (filterType) {
      list = list.filter((r) => r.outcome === filterType);
    }
    return list.sort((a, b) => (b.date.localeCompare(a.date)) || (b.evaluated_at.localeCompare(a.evaluated_at)));
  }, [records, dateFrom, dateTo, filterType]);

  const openDetail = (record: DecisionRecord) => {
    setSelected(record);
    setDetailOpen(true);
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setSelected(null);
  };

  if (mode === "LIVE" && liveError) {
    return (
      <div className="space-y-6 p-6">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Decision history</h1>
          <p className="mt-1 text-sm text-muted-foreground">Review past system decisions. Entries are read-only.</p>
        </div>
        <EmptyState title="LIVE data unavailable" message={liveError} />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">History</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Review past evaluation runs and system decisions. All entries are read-only.
        </p>
      </div>

      {/* Tabs */}
      {mode === "LIVE" && (
        <div className="flex gap-2 border-b border-border">
          <button
            onClick={() => setActiveTab("evaluations")}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === "evaluations"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            Evaluation Runs ({evalRuns.length})
          </button>
          <button
            onClick={() => setActiveTab("decisions")}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === "decisions"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            Decisions ({filtered.length})
          </button>
        </div>
      )}

      {/* Evaluation Runs Tab */}
      {mode === "LIVE" && activeTab === "evaluations" && (
        <section
          className="rounded-lg border border-border bg-card overflow-hidden"
          role="region"
          aria-label="Evaluation runs"
        >
          <div className="p-4 border-b border-border bg-muted/30">
            <h2 className="text-sm font-medium text-foreground">Evaluation Run History</h2>
            <p className="text-xs text-muted-foreground mt-1">
              Persisted evaluation runs. All screens read from the same source of truth.
            </p>
          </div>

          {evalRuns.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              <Clock className="h-8 w-8 mx-auto mb-2 text-muted-foreground/50" />
              <p>No evaluation runs yet.</p>
              <p className="mt-1">Run an evaluation from the Universe page to see history here.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground bg-muted/30">
                    <th className="px-4 py-2 font-medium">Run ID</th>
                    <th className="px-4 py-2 font-medium">Source</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Started</th>
                    <th className="px-4 py-2 font-medium">Duration</th>
                    <th className="px-4 py-2 font-medium">Stage1/2</th>
                    <th className="px-4 py-2 font-medium">Eligible</th>
                    <th className="px-4 py-2 font-medium">Holds</th>
                  </tr>
                </thead>
                <tbody>
                  {evalRuns.map((run) => {
                    const sourceInfo = {
                      nightly: { label: "Nightly", color: "bg-purple-500/20 text-purple-400", icon: "🌙" },
                      scheduled: { label: "Scheduled", color: "bg-blue-500/20 text-blue-400", icon: "⏰" },
                      api: { label: "API", color: "bg-gray-500/20 text-gray-400", icon: "🔌" },
                      manual: { label: "Manual", color: "bg-green-500/20 text-green-400", icon: "👤" },
                    }[run.source ?? "manual"] ?? { label: "Unknown", color: "bg-gray-500/20 text-gray-400", icon: "?" };
                    return (
                    <tr
                      key={run.run_id}
                      className={cn(
                        "border-b border-border/50 hover:bg-muted/30",
                        run.run_id === latestRunId && "bg-emerald-500/5",
                        run.source === "nightly" && "bg-purple-500/5"
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <code className="text-xs font-mono">{run.run_id.slice(-16)}</code>
                          {run.run_id === latestRunId && (
                            <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs text-emerald-600 dark:text-emerald-400">
                              latest
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                          sourceInfo.color
                        )}>
                          {sourceInfo.icon} {sourceInfo.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                          STATUS_CLASS[run.status] ?? "bg-gray-500/20 text-gray-400"
                        )}>
                          {STATUS_ICON[run.status] ?? null}
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(run.started_at).toLocaleString(undefined, {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {run.duration_seconds.toFixed(1)}s
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-medium">{run.stage1_pass ?? run.evaluated}</span>
                        <span className="text-muted-foreground">/</span>
                        <span className="font-medium">{run.stage2_pass ?? 0}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "font-medium",
                          run.eligible > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"
                        )}>
                          {run.eligible}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "font-medium",
                          (run.holds ?? 0) > 0 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                        )}>
                          {run.holds ?? 0}
                        </span>
                      </td>
                    </tr>
                  );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Decisions Tab - Filters */}
      {(mode !== "LIVE" || activeTab === "decisions") && (
        <>
          {/* Filters — minimal: date range, decision type */}
      <section
        className="rounded-lg border border-border bg-card p-4"
        role="region"
        aria-label="Filters"
      >
        <h2 className="text-sm font-medium text-muted-foreground">Filters</h2>
        <div className="mt-3 flex flex-wrap items-end gap-4">
          <div>
            <label htmlFor="history-date-from" className="block text-xs text-muted-foreground">
              From date
            </label>
            <input
              id="history-date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label htmlFor="history-date-to" className="block text-xs text-muted-foreground">
              To date
            </label>
            <input
              id="history-date-to"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label htmlFor="history-type" className="block text-xs text-muted-foreground">
              Decision type
            </label>
            <select
              id="history-type"
              value={filterType}
              onChange={(e) => setFilterType((e.target.value || "") as DecisionOutcome | "")}
              className="mt-1 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All</option>
              <option value="TRADE">Trade</option>
              <option value="NO_TRADE">No trade</option>
              <option value="RISK_HOLD">Risk hold</option>
            </select>
          </div>
        </div>
      </section>

      {/* Chronological list — date/time, outcome, rationale */}
      <section
        className="rounded-lg border border-border bg-card overflow-hidden"
        role="region"
        aria-label="Decision list"
      >
        <h2 className="sr-only">Past decisions</h2>
        {/* No evaluation run yet banner */}
        {mode === "LIVE" && snapshot && !snapshot.has_decision_artifact && filtered.length === 0 && (
          <div className="flex items-center gap-3 p-4">
            <Info className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="font-medium text-foreground">No live data yet — evaluation has not run</p>
              <p className="text-sm text-muted-foreground">
                Decision history will appear here once evaluation cycles complete.{" "}
                <Link to="/diagnostics" className="text-primary hover:underline">View diagnostics</Link>
              </p>
            </div>
          </div>
        )}

        {filtered.length === 0 && !(mode === "LIVE" && snapshot && !snapshot.has_decision_artifact) ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No decisions match the current filters.
          </div>
        ) : filtered.length === 0 ? null : (
          <ul className="divide-y divide-border">
            {filtered.map((record) => (
              <li key={`${record.date}-${record.evaluated_at}`}>
                <button
                  type="button"
                  onClick={() => openDetail(record)}
                  className="flex w-full flex-col gap-1 p-4 text-left hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-foreground">
                      {formatDateOnly(record.date)}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {formatTime(record.evaluated_at)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                        OUTCOME_CLASS[record.outcome]
                      )}
                    >
                      {OUTCOME_LABEL[record.outcome]}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {record.rationale}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

        </>
      )}

      <DecisionDetailDrawer
        record={selected}
        open={detailOpen}
        onClose={closeDetail}
      />
    </div>
  );
}
