/**
 * Phase 8.6 / 8.7: Notification Center — inbox-style UX, filters, search, grouping, read/unread.
 * LIVE: fetch alerts + evaluation alerts + pending system notifications.
 * Filter pills: ALL / ELIGIBLE / WARN / DATA / TARGET
 */
import { useEffect, useState, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { getAlerts, getDailyOverview } from "@/data/source";
import { useDataMode } from "@/context/DataModeContext";
import { useScenario } from "@/context/ScenarioContext";
import { usePolling } from "@/context/PollingContext";
import {
  notificationsFromAlerts,
  systemNotifications,
  groupNotificationsByTime,
  loadNotificationState,
  loadPendingSystemNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  pushSystemNotification,
  type NotificationItem,
} from "@/lib/notifications";
import { NotificationDrawer } from "@/components/NotificationDrawer";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { cn } from "@/lib/utils";
import { apiGet, apiPost, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import type {
  EvaluationAlertsResponse,
  EvaluationAlert,
  SlackNotifyResponse,
  EvaluationRunsResponse,
} from "@/types/universeEvaluation";
import type { TradesAlertsResponse } from "@/types/journal";
import { getAlertTypeColor } from "@/types/universeEvaluation";
import { Search, Send, Loader2 } from "lucide-react";

type FilterKind = "all" | "actionable" | "warnings" | "errors" | "info" | "eligible" | "data" | "target" | "nightly";

function formatRelative(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function liveErrorMessage(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

export function NotificationsPage() {
  const { mode } = useDataMode();
  const scenario = useScenario();
  const polling = usePolling();
  const pollTick = polling?.pollTick ?? 0;
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [evalAlerts, setEvalAlerts] = useState<EvaluationAlert[]>([]);
  const [, setNightlyRunIds] = useState<string[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<FilterKind>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<NotificationItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [slackSending, setSlackSending] = useState<string | null>(null);

  // Send to Slack
  const sendToSlack = useCallback(async (alert: EvaluationAlert) => {
    setSlackSending(alert.id);
    try {
      const result = await apiPost<SlackNotifyResponse>(ENDPOINTS.notifySlack, {
        meta: {
          symbol: alert.symbol,
          strategy: alert.type,
          reason: alert.message,
        },
      });
      pushSystemNotification({
        source: "system",
        severity: result.sent ? "info" : "warning",
        title: result.sent ? "Sent to Slack" : "Slack not sent",
        message: result.reason ?? `${alert.symbol} notification sent`,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Slack failed",
        message: msg,
      });
    } finally {
      setSlackSending(null);
    }
  }, []);

  useEffect(() => {
    const state = loadNotificationState();
    setReadIds(new Set(state.readIds));
  }, []);

  useEffect(() => {
    if (mode === "MOCK" && scenario?.bundle) {
      setLiveError(null);
      const fromAlerts = notificationsFromAlerts(scenario.bundle.alerts);
      const latestTs =
        scenario.bundle.decisionHistory?.[0]?.evaluated_at ?? scenario.bundle.dailyOverview?.links?.latest_decision_ts;
      const system = systemNotifications({
        latestEvaluatedAt: latestTs ?? null,
        mode,
        scenarioKey: scenario.scenarioKey,
      });
      setNotifications([...system, ...fromAlerts]);
      return;
    }
    if (mode !== "LIVE") return;
    let cancelled = false;
    setLiveError(null);
    Promise.all([
      getAlerts(mode),
      getDailyOverview(mode),
      apiGet<EvaluationAlertsResponse>(ENDPOINTS.evaluationAlerts).catch(() => ({ alerts: [], count: 0, last_generated_at: null })),
      apiGet<EvaluationRunsResponse>(ENDPOINTS.evaluationRuns).catch(() => ({ runs: [], count: 0, latest_run_id: null })),
      apiGet<TradesAlertsResponse>(ENDPOINTS.tradesAlerts).catch(() => ({ alerts: [], count: 0 })),
    ])
      .then(([alerts, overview, evalAlertsResp, evalRunsResp, journalAlertsResp]) => {
        if (cancelled) return;
        const latestTs = overview?.links?.latest_decision_ts ?? null;
        const fromAlerts = notificationsFromAlerts(alerts);
        const system = systemNotifications({ latestEvaluatedAt: latestTs, mode: "LIVE" });
        const pending = loadPendingSystemNotifications();
        
        // Convert evaluation alerts to notification items
        const evalNotifications: NotificationItem[] = evalAlertsResp.alerts.map((ea) => ({
          id: ea.id,
          source: "evaluation",
          severity: ea.severity === "ERROR" ? "error" : ea.severity === "WARN" ? "warning" : "info",
          title: `${ea.type}: ${ea.symbol}`,
          message: ea.message,
          createdAt: ea.created_at,
          symbol: ea.symbol,
          actionable: ea.type === "ELIGIBLE",
        }));
        
        // Journal alerts (stop breached, target hit) — e.g. "Stop breached for SPY trade_id=…"
        const journalAlertsList = journalAlertsResp.alerts ?? [];
        const journalNotifications: NotificationItem[] = journalAlertsList.map((a, i) => ({
          id: `journal-${a.trade_id}-${a.alert_type}-${i}`,
          source: "evaluation",
          severity: a.alert_type === "STOP_BREACHED" ? "warning" : "info",
          title: a.alert_type === "STOP_BREACHED" ? "Stop breached" : "Target hit",
          message: a.message,
          createdAt: a.created_at ?? new Date().toISOString(),
          symbol: a.symbol,
          actionable: true,
        }));
        
        // Nightly run completed entries (runs with source=nightly)
        const nightlyRuns = (evalRunsResp.runs ?? []).filter((r) => r.source === "nightly");
        const nightlyRunIdsList = nightlyRuns.map((r) => r.run_id);
        const nightlyNotifications: NotificationItem[] = nightlyRuns.map((r) => ({
          id: `nightly-${r.run_id}`,
          source: "evaluation",
          severity: "info",
          title: "Nightly run completed",
          message: `Run ${r.run_id} completed. ${r.eligible ?? 0} eligible, ${r.holds ?? 0} holds, ${r.blocks ?? 0} blocks.`,
          createdAt: r.completed_at ?? r.started_at,
          symbol: undefined,
          actionable: false,
          runId: r.run_id,
        }));
        
        setEvalAlerts(evalAlertsResp.alerts);
        setNightlyRunIds(nightlyRunIdsList);
        setNotifications([...system, ...fromAlerts, ...evalNotifications, ...journalNotifications, ...nightlyNotifications, ...pending]);
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
          setNotifications(loadPendingSystemNotifications());
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, scenario?.bundle, scenario?.scenarioKey, mode === "LIVE" ? pollTick : 0]);

  const filtered = useMemo(() => {
    let list = [...notifications];
    if (filter === "actionable") list = list.filter((n) => n.actionable);
    else if (filter === "warnings") list = list.filter((n) => n.severity === "warning");
    else if (filter === "errors") list = list.filter((n) => n.severity === "error");
    else if (filter === "info") list = list.filter((n) => n.severity === "info");
    else if (filter === "eligible") list = list.filter((n) => n.title.includes("ELIGIBLE"));
    else if (filter === "data") list = list.filter((n) => n.title.includes("DATA_STALE") || n.title.includes("LIQUIDITY"));
    else if (filter === "target") list = list.filter((n) => n.title.includes("TARGET_HIT"));
    else if (filter === "nightly") list = list.filter((n) => n.title === "Nightly run completed");
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (n) =>
          n.title.toLowerCase().includes(q) ||
          n.message.toLowerCase().includes(q) ||
          (n.symbol ?? "").toLowerCase().includes(q)
      );
    }
    return list.sort((a, b) => (b.createdAt < a.createdAt ? -1 : 1));
  }, [notifications, filter, search]);

  const grouped = useMemo(() => groupNotificationsByTime(filtered), [filtered]);

  const handleMarkAllRead = () => {
    markAllNotificationsRead(filtered.map((n) => n.id));
    setReadIds(new Set([...readIds, ...filtered.map((n) => n.id)]));
  };

  const openDetail = (n: NotificationItem) => {
    markNotificationRead(n.id);
    setReadIds((prev) => new Set([...prev, n.id]));
    setSelected(n);
    setDrawerOpen(true);
  };

  const closeDetail = () => {
    setDrawerOpen(false);
    setSelected(null);
  };

  if (mode === "LIVE" && liveError) {
    return (
      <div className="space-y-6 p-6">
        <PageHeader title="Notifications" subtext="Inbox-style view of alerts and system events." />
        <EmptyState
          title="LIVE data unavailable"
          message={`${liveError} A system notification was added for this error.`}
        />
      </div>
    );
  }

  if (mode === "LIVE" && notifications.length === 0) {
    return (
      <div className="space-y-6 p-6">
        <PageHeader title="Notifications" subtext="Inbox-style view of alerts and system events." />
        <EmptyState
          title="No notifications available"
          message="In LIVE mode, notifications will appear here when data is available."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Notifications"
        subtext="Alerts and system events. Filter and search; mark as read locally."
        actions={
          filtered.length > 0 ? (
            <button
              type="button"
              onClick={handleMarkAllRead}
              className="rounded-md border border-border bg-secondary/50 px-3 py-1.5 text-sm text-foreground hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-ring"
            >
              Mark all as read
            </button>
          ) : undefined
        }
      />

      <section className="rounded-lg border border-border bg-card p-4" role="region" aria-label="Filters">
        <div className="flex flex-wrap items-center gap-3">
          {/* Filter pills */}
          <div className="flex flex-wrap gap-2">
            {(["all", "nightly", "eligible", "warnings", "data", "errors", "info"] as FilterKind[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                  filter === f
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                {f === "all" ? "ALL" :
                 f === "nightly" ? "NIGHTLY" :
                 f === "eligible" ? "ELIGIBLE" :
                 f === "warnings" ? "WARN" :
                 f === "data" ? "DATA" :
                 f === "errors" ? "ERRORS" : "INFO"}
              </button>
            ))}
          </div>
          <input
            type="search"
            placeholder="Search symbol or message..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-[200px] rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Search notifications"
          />
        </div>
      </section>

      {/* Evaluation Alerts Section */}
      {mode === "LIVE" && evalAlerts.length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4" role="region" aria-label="Evaluation Alerts">
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">Evaluation Alerts ({evalAlerts.length})</h2>
          <div className="space-y-2">
            {evalAlerts.slice(0, 10).map((alert) => (
              <div
                key={alert.id}
                className={cn(
                  "flex items-center justify-between rounded-lg border p-3",
                  alert.severity === "ERROR" && "border-destructive/30 bg-destructive/5",
                  alert.severity === "WARN" && "border-amber-500/30 bg-amber-500/5",
                  alert.severity === "INFO" && "border-border bg-muted/30"
                )}
              >
                <div className="flex items-center gap-3">
                  <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", getAlertTypeColor(alert.type))}>
                    {alert.type}
                  </span>
                  <span className="font-medium">{alert.symbol}</span>
                  <span className="text-sm text-muted-foreground">{alert.message}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    to={`/analysis?symbol=${alert.symbol}`}
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-primary hover:bg-muted"
                  >
                    <Search className="h-3 w-3" />
                    Analyze
                  </Link>
                  <button
                    onClick={() => sendToSlack(alert)}
                    disabled={slackSending === alert.id}
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    {slackSending === alert.id ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Send className="h-3 w-3" />
                    )}
                    Slack
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {filtered.length === 0 ? (
        <EmptyState
          title="No notifications match"
          message="Try changing the filter or search."
        />
      ) : (
        <section className="rounded-lg border border-border bg-card overflow-hidden" role="region" aria-label="Notification list">
          {grouped.map((group) => (
            <div key={group.label} className="border-b border-border last:border-b-0">
              <h3 className="bg-muted/30 px-4 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {group.label}
              </h3>
              <ul className="divide-y divide-border">
                {group.items.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => openDetail(n)}
                      className={cn(
                        "flex w-full flex-col gap-1 px-4 py-3 text-left hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset",
                        !readIds.has(n.id) && "bg-primary/5"
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-foreground">{n.title}</span>
                        <span className="text-xs text-muted-foreground">{formatRelative(n.createdAt)}</span>
                      </div>
                      <p className="line-clamp-2 text-sm text-muted-foreground">{n.message}</p>
                      <div
                        className={cn(
                          "mt-1 h-0.5 w-8 rounded-full",
                          n.severity === "error" && "bg-red-500/50",
                          n.severity === "warning" && "bg-amber-500/50",
                          n.severity === "info" && "bg-blue-500/50"
                        )}
                        aria-hidden
                      />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}

      <NotificationDrawer notification={selected} open={drawerOpen} onClose={closeDetail} />
    </div>
  );
}
