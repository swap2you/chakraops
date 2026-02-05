/**
 * Phase 8.6 / 8.7: Notification model (UI-only, derived from AlertsView + system events).
 * Read-only; no backend contract changes. LIVE: pushSystemNotification for fetch errors; systemNotificationFromWarnings for validation.
 */

import type { AlertsView } from "@/types/views";
import { isActionable, severityFromLevel, type AlertSeverity } from "./alertClassifier";
import type { ValidationWarning } from "@/mock/validator";

export type NotificationSource = "alert" | "system" | "evaluation";

export interface NotificationItem {
  id: string;
  source: NotificationSource;
  severity: AlertSeverity;
  title: string;
  message: string;
  /** For "Open position" link */
  symbol?: string | null;
  position_id?: string | null;
  /** For "Open decision" link */
  decision_ts?: string | null;
  /** ISO timestamp for grouping (Today / This week / Older) */
  createdAt: string;
  /** Alert-derived: actionable for filter */
  actionable: boolean;
  /** For nightly run: link to evaluation run detail / history */
  runId?: string | null;
}

const STORAGE_KEY = "chakraops_notification_state";
const PENDING_STORAGE_KEY = "chakraops_system_pending";
const MAX_PENDING = 50;

export interface NotificationState {
  readIds: string[];
}

export function loadNotificationState(): NotificationState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { readIds: [] };
    const parsed = JSON.parse(raw) as NotificationState;
    return Array.isArray(parsed.readIds) ? { readIds: parsed.readIds } : { readIds: [] };
  } catch {
    return { readIds: [] };
  }
}

export function saveNotificationState(state: NotificationState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore when localStorage disabled */
  }
}

export function markNotificationRead(id: string): void {
  const state = loadNotificationState();
  if (state.readIds.includes(id)) return;
  saveNotificationState({ readIds: [...state.readIds, id] });
}

export function markAllNotificationsRead(ids: string[]): void {
  const state = loadNotificationState();
  const combined = new Set([...state.readIds, ...ids]);
  saveNotificationState({ readIds: [...combined] });
}

function stableId(prefix: string, ...parts: (string | number | undefined)[]): string {
  return `${prefix}-${parts.filter(Boolean).join("-")}`;
}

/**
 * Build notifications from AlertsView items (deterministic in MOCK).
 */
export function notificationsFromAlerts(alerts: AlertsView | null): NotificationItem[] {
  const items = alerts?.items ?? [];
  const asOf = alerts?.as_of ?? new Date().toISOString();
  return items.map((item, i) => {
    const code = item.code ?? "Alert";
    const message = item.message ?? "";
    const title = item.symbol ? `${item.symbol} — ${code}` : code;
    return {
      id: stableId("alert", asOf, i, code, item.symbol ?? ""),
      source: "alert",
      severity: severityFromLevel(item.level),
      title,
      message,
      symbol: item.symbol ?? null,
      position_id: item.position_id ?? null,
      decision_ts: item.decision_ts ?? null,
      createdAt: asOf,
      actionable: isActionable(item),
    };
  });
}

/**
 * System notifications (e.g. Decision evaluated, Mode changed, Scenario changed).
 * MOCK-only events can be pushed via a simple event bus or passed from context;
 * for now we derive "Decision evaluated" from latest decision_ts when available.
 */
export function systemNotifications(options: {
  latestEvaluatedAt?: string | null;
  mode?: string;
  scenarioKey?: string | null;
  previousMode?: string | null;
  previousScenarioKey?: string | null;
}): NotificationItem[] {
  const out: NotificationItem[] = [];
  const now = new Date().toISOString();
  if (options.latestEvaluatedAt) {
    out.push({
      id: stableId("system", "decision", options.latestEvaluatedAt),
      source: "system",
      severity: "info",
      title: "Decision evaluated",
      message: `System evaluation completed at ${options.latestEvaluatedAt}.`,
      createdAt: options.latestEvaluatedAt,
      actionable: false,
    });
  }
  if (options.previousMode != null && options.mode !== options.previousMode) {
    out.push({
      id: stableId("system", "mode", options.mode, now),
      source: "system",
      severity: "info",
      title: "Mode changed",
      message: `Data mode set to ${options.mode}.`,
      createdAt: now,
      actionable: false,
    });
  }
  if (
    options.scenarioKey != null &&
    options.previousScenarioKey != null &&
    options.scenarioKey !== options.previousScenarioKey
  ) {
    out.push({
      id: stableId("system", "scenario", options.scenarioKey, now),
      source: "system",
      severity: "info",
      title: "Scenario changed",
      message: `Mock scenario set to ${options.scenarioKey}.`,
      createdAt: now,
      actionable: false,
    });
  }
  return out;
}

/**
 * Phase 8.7: Pending system notifications (e.g. LIVE fetch errors). Stored in localStorage; merged on NotificationsPage.
 */
export function loadPendingSystemNotifications(): NotificationItem[] {
  try {
    const raw = localStorage.getItem(PENDING_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as NotificationItem[];
    return Array.isArray(parsed) ? parsed.slice(-MAX_PENDING) : [];
  } catch {
    return [];
  }
}

function savePendingSystemNotifications(items: NotificationItem[]): void {
  try {
    localStorage.setItem(PENDING_STORAGE_KEY, JSON.stringify(items.slice(-MAX_PENDING)));
  } catch {
    /* ignore */
  }
}

/**
 * Phase 8.7: Push a system notification (e.g. LIVE fetch failed). Appears in Notifications page; stable id for dedupe.
 */
export function pushSystemNotification(item: {
  source: NotificationSource;
  severity: AlertSeverity;
  title: string;
  message: string;
  actionable?: boolean;
}): void {
  const now = new Date().toISOString();
  const id = stableId("system", item.title, now);
  const full: NotificationItem = {
    id,
    source: item.source,
    severity: item.severity,
    title: item.title,
    message: item.message,
    createdAt: now,
    actionable: item.actionable ?? false,
  };
  const pending = loadPendingSystemNotifications();
  if (pending.some((p) => p.id === id)) return;
  savePendingSystemNotifications([...pending, full]);
}

/** Phase 8.7: Push full notification (e.g. from validation warnings with stable id); skip if id already in pending. */
export function pushSystemNotificationItem(full: NotificationItem): void {
  const pending = loadPendingSystemNotifications();
  if (pending.some((p) => p.id === full.id)) return;
  savePendingSystemNotifications([...pending, full]);
}

/**
 * Phase 8.7: Convert validation warnings to NotificationItems (stable id = code + date day to avoid spam).
 */
export function systemNotificationFromWarnings(
  warnings: ValidationWarning[],
  _source: string,
  evaluatedAt: string
): NotificationItem[] {
  const day = evaluatedAt.slice(0, 10);
  return warnings.map((w) => {
    const id = stableId("warn", w.code, day, w.affectedId ?? "");
    return {
      id,
      source: "system" as const,
      severity: (w.code.includes("MISSING") || w.code.includes("PARTIAL") ? "warning" : "info") as AlertSeverity,
      title: `Validation: ${w.code}`,
      message: w.message,
      createdAt: evaluatedAt,
      actionable: false,
    };
  });
}

export function groupNotificationsByTime(
  notifications: NotificationItem[]
): { label: string; items: NotificationItem[] }[] {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const weekStart = todayStart - 7 * 24 * 60 * 60 * 1000;
  const groups: { label: string; items: NotificationItem[] }[] = [
    { label: "Today", items: [] },
    { label: "This week", items: [] },
    { label: "Older", items: [] },
  ];
  for (const n of notifications) {
    const t = new Date(n.createdAt).getTime();
    if (t >= todayStart) groups[0].items.push(n);
    else if (t >= weekStart) groups[1].items.push(n);
    else groups[2].items.push(n);
  }
  return groups.filter((g) => g.items.length > 0);
}
