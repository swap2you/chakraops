/**
 * R26.3: Daily operator workflow — Run/Refresh, Action Needed, Ticket queue, Journal checkpoint, Notifications.
 * Safe labels only; no FAIL/WARN in UI.
 */
import { useState, useCallback, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  useTodaySummary,
  useActionNeeded,
  useRunEval,
  useJournal,
  useNotifications,
  useAckNotification,
  useArchiveNotification,
  useAckBulkNotifications,
  useArchiveBulkNotifications,
  useOpsChecklist,
  useOpsEodSummary,
  useOpsChecklistMarkDone,
  useExecutionLogPost,
} from "@/api/queries";
import type { ActionNeededItem } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { AuthoritativeRecommendations } from "@/components/AuthoritativeRecommendations";
import { Card, CardHeader, Button, Badge } from "@/components/ui";
import { constraintToLabel } from "@/utils/sizingConstraints";

const TICKET_QUEUE_KEY = "chakraops_r263_ticket_queue";
const DONE_TODAY_KEY = "chakraops_r263_done_today";

interface QueueItem {
  id: string;
  ticket_id?: string;
  symbol: string;
  strategy: string;
  action: string;
  created_ts: string;
  journal_saved?: boolean;
}

function todayDate(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function loadQueue(): QueueItem[] {
  try {
    const raw = localStorage.getItem(TICKET_QUEUE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    const arr = Array.isArray(parsed) ? parsed : [];
    return arr.map((item: QueueItem) => ({
      ...item,
      ticket_id: item.ticket_id ?? item.id,
      journal_saved: item.journal_saved ?? false,
    }));
  } catch {
    return [];
  }
}

function saveQueue(items: QueueItem[]) {
  localStorage.setItem(TICKET_QUEUE_KEY, JSON.stringify(items));
}

function loadDoneToday(): { symbol: string; date: string }[] {
  try {
    const raw = localStorage.getItem(DONE_TODAY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveDoneToday(items: { symbol: string; date: string }[]) {
  localStorage.setItem(DONE_TODAY_KEY, JSON.stringify(items));
}

function actionLabel(code: string): string {
  const c = (code || "").toUpperCase();
  if (c === "ENTRY") return "Entry";
  if (c === "CLOSE") return "Close";
  if (c === "ROLL") return "Roll";
  if (c === "HOLD") return "Hold";
  return code || "—";
}

function ticketHref(item: ActionNeededItem, isOptions: boolean): string {
  const symbol = encodeURIComponent(item.symbol);
  const strategy = (item.strategy || (isOptions ? "CSP" : "SHARES")).toUpperCase();
  const action =
    item.next_action_code === "ENTRY"
      ? isOptions
        ? "OPEN"
        : "BUY"
      : item.next_action_code === "CLOSE"
        ? isOptions
          ? "CLOSE"
          : "SELL"
        : "OPEN";
  return `/ticket?symbol=${symbol}&strategy=${strategy}&action=${action}`;
}

export function TodayPage() {
  const today = useMemo(() => todayDate(), []);
  const [queue, setQueue] = useState<QueueItem[]>(() => loadQueue());
  const [doneToday, setDoneToday] = useState<{ symbol: string; date: string }[]>(() => loadDoneToday());

  const { data: summary, isLoading: summaryLoading } = useTodaySummary();
  const { data: actionNeeded, isLoading: actionNeededLoading, isError: actionNeededError } = useActionNeeded();
  const runEval = useRunEval();
  const { data: eodChecklist } = useOpsChecklist("EOD", today);
  const { data: eodSummary } = useOpsEodSummary(today);
  const markEodDone = useOpsChecklistMarkDone();
  const executionLogPost = useExecutionLogPost();
  const { data: journalData } = useJournal({ from_date: today, to_date: today, limit: 100 });
  const journalEntries = journalData?.entries ?? [];
  const journalSymbols = useMemo(() => new Set(journalEntries.map((e) => (e.symbol || "").toUpperCase())), [journalEntries]);
  const journalSymbolStrategySet = useMemo(
    () => new Set(journalEntries.map((e) => `${(e.symbol || "").toUpperCase()}|${(e.strategy || "").toUpperCase()}`)),
    [journalEntries]
  );
  const [skipModalItem, setSkipModalItem] = useState<QueueItem | null>(null);
  const [skipReason, setSkipReason] = useState("");
  const [eodShowOverride, setEodShowOverride] = useState(false);
  const [eodOverrideReason, setEodOverrideReason] = useState("");

  const { data: notifData, refetch: refetchNotif } = useNotifications(100, "NEW");
  const notifications = notifData?.notifications ?? [];
  const ackMutation = useAckNotification(100);
  const archiveMutation = useArchiveNotification();
  const ackBulkMutation = useAckBulkNotifications();
  const archiveBulkMutation = useArchiveBulkNotifications();

  useEffect(() => {
    saveQueue(queue);
  }, [queue]);
  useEffect(() => {
    saveDoneToday(doneToday);
  }, [doneToday]);

  useEffect(() => {
    const handler = (e: Event) => {
      const ev = e as CustomEvent<{ ticket_id: string }>;
      const tid = ev.detail?.ticket_id;
      if (!tid) return;
      setQueue((prev) => prev.map((q) => (q.ticket_id === tid || q.id === tid ? { ...q, journal_saved: true } : q)));
    };
    window.addEventListener("chakraops-journal-saved", handler);
    return () => window.removeEventListener("chakraops-journal-saved", handler);
  }, []);

  const addToQueue = useCallback((item: ActionNeededItem, isOptions: boolean) => {
    const strategy = (item.strategy || (isOptions ? "CSP" : "SHARES")).toUpperCase();
    const action =
      item.next_action_code === "ENTRY" ? (isOptions ? "OPEN" : "BUY") : item.next_action_code === "CLOSE" ? (isOptions ? "CLOSE" : "SELL") : "OPEN";
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    setQueue((prev) => [
      ...prev,
      {
        id,
        ticket_id: id,
        symbol: item.symbol,
        strategy,
        action,
        created_ts: new Date().toISOString(),
        journal_saved: false,
      },
    ]);
  }, []);

  const removeFromQueue = useCallback((id: string) => {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  }, []);

  const hasJournalForItem = useCallback(
    (item: QueueItem) => journalSymbolStrategySet.has(`${item.symbol.toUpperCase()}|${item.strategy.toUpperCase()}`),
    [journalSymbolStrategySet]
  );

  const performMarkDone = useCallback(
    (item: QueueItem) => {
      setDoneToday((prev) => [...prev, { symbol: item.symbol, date: today }]);
      setQueue((prev) => prev.filter((q) => q.id !== item.id));
    },
    [today]
  );

  const markDone = useCallback(
    (id: string) => {
      const item = queue.find((q) => q.id === id);
      if (!item) return;
      if (item.journal_saved || hasJournalForItem(item)) {
        performMarkDone(item);
        return;
      }
      setSkipModalItem(item);
      setSkipReason("");
    },
    [queue, hasJournalForItem, performMarkDone]
  );

  const confirmSkipAndMarkDone = useCallback(async () => {
    if (!skipModalItem || !skipReason.trim()) return;
    const item = skipModalItem;
    const reason = skipReason.trim().slice(0, 140);
    setSkipModalItem(null);
    setSkipReason("");
    try {
      await executionLogPost.mutateAsync({
        event_type: "SKIP_JOURNAL",
        symbol: item.symbol,
        strategy: item.strategy,
        action: item.action,
        ticket_id: item.ticket_id ?? item.id,
        reason,
      });
      await executionLogPost.mutateAsync({
        event_type: "MARK_DONE",
        symbol: item.symbol,
        strategy: item.strategy,
        action: item.action,
        ticket_id: item.ticket_id ?? item.id,
      });
    } catch {
      setSkipModalItem(item);
      setSkipReason(reason);
      return;
    }
    performMarkDone(item);
  }, [skipModalItem, skipReason, executionLogPost, performMarkDone]);

  const missingJournalSymbols = useMemo(() => {
    return doneToday.filter((d) => d.date === today && !journalSymbols.has(d.symbol.toUpperCase())).map((d) => d.symbol);
  }, [doneToday, today, journalSymbols]);

  const allOptions = useMemo(
    () => [...(actionNeeded?.top_options ?? []), ...(actionNeeded?.top_shares ?? [])].map((item, i) => ({ item, isOptions: i < (actionNeeded?.top_options?.length ?? 0) })),
    [actionNeeded]
  );

  const eodPending = (eodChecklist?.row?.status ?? "OPEN").toUpperCase() !== "DONE";

  return (
    <div className="space-y-4">
      <PageHeader title="Today" subtext="Daily workflow: run, action needed, tickets, journal, notifications" />
      {eodPending && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200" data-testid="today-eod-pending-banner">
          EOD checklist pending. Complete before tomorrow.
        </div>
      )}

      {/* A) Run / Refresh */}
      <Card data-testid="today-run-section">
        <CardHeader title="Run / Refresh" />
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Button
            onClick={() => runEval.mutate(undefined)}
            disabled={runEval.isPending}
            data-testid="today-run-eval-btn"
          >
            {runEval.isPending ? "Running…" : "Run evaluation"}
          </Button>
          {summaryLoading ? (
            <span className="text-zinc-500">Loading…</span>
          ) : (
            <>
              <span className="text-zinc-600 dark:text-zinc-400">
                As of: {String(summary?.as_of_et ?? "—")} · Cadence: {String(summary?.cadence?.mode ?? "—")}
              </span>
              <span className="text-zinc-500">
                ORATS: {String(summary?.orats_status ?? "—")}
                {summary?.orats_freshness_state_label ? ` (${summary.orats_freshness_state_label})` : ""}
              </span>
              <span className="text-zinc-500">
                Earnings: {String((summary?.earnings_probe as Record<string, unknown>)?.status ?? "—")}
              </span>
              <span className="text-zinc-500">
                Guardrails: {String((summary?.guardrails as Record<string, unknown>)?.status ?? "—")}
              </span>
            </>
          )}
        </div>
      </Card>

      {/* B) R34.0 (H-5 cutover): canonical authoritative recommendation is PRIMARY. */}
      <AuthoritativeRecommendations
        data={actionNeeded}
        isLoading={actionNeededLoading}
        isError={actionNeededError}
        providerHealth={{ label: summary?.orats_status, ok: summary?.orats_status === "OK" }}
      />
      {/* R34.0: legacy options/shares list is NON-authoritative diagnostics only. */}
      <details data-testid="today-legacy-diagnostics">
        <summary className="cursor-pointer text-sm font-medium text-zinc-500 dark:text-zinc-400">
          Diagnostics — non-authoritative legacy output
        </summary>
      <Card data-testid="today-action-needed-card" className="mt-2">
        <CardHeader title="Action Needed (legacy diagnostics)" description="Non-authoritative. Superseded by the canonical recommendations above; queue actions remain here." />
        <div className="space-y-1.5">
          {allOptions.length === 0 ? (
            <p className="text-xs text-zinc-500">No actions.</p>
          ) : (
            allOptions.slice(0, 8).map(({ item, isOptions }) => {
              const href = `/symbol-diagnostics?symbol=${encodeURIComponent(item.symbol)}&tab=${isOptions ? "Options" : "Shares"}`;
              const label = actionLabel(item.next_action_code ?? "");
              const ticketHrefStr = ticketHref(item, isOptions);
              return (
                <div
                  key={`${item.symbol}-${isOptions ? "opt" : "shr"}`}
                  className="flex items-center justify-between gap-2 rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs"
                  data-testid={`today-action-row-${item.symbol}`}
                >
                  <div className="min-w-0 flex-1">
                    <Link to={href} className="font-mono font-medium text-zinc-800 dark:text-zinc-200 hover:underline">
                      {item.symbol}
                    </Link>
                    <Badge variant="neutral" className="ml-2">
                      {label}
                    </Badge>
                    {item.recommended_contracts != null && item.recommended_contracts > 0 && (
                      <span className="ml-2 text-zinc-500">Size: {item.recommended_contracts} contracts</span>
                    )}
                    {item.recommended_qty != null && item.recommended_qty > 0 && (
                      <span className="ml-2 text-zinc-500">Size: {item.recommended_qty} shares</span>
                    )}
                    {(item.sizing_constraints_hit?.length ?? 0) > 0 && (
                      <span className="ml-2 text-zinc-500">
                        Constraints: {item.sizing_constraints_hit!.map((c) => constraintToLabel(c)).join(", ")}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => addToQueue(item, isOptions)}
                      data-testid={`today-add-queue-${item.symbol}`}
                    >
                      Add to queue
                    </Button>
                    <Link
                      to={ticketHrefStr}
                      onClick={() => addToQueue(item, isOptions)}
                      className="text-emerald-600 hover:underline dark:text-emerald-400"
                      data-testid={`today-ticket-${item.symbol}`}
                    >
                      Ticket
                    </Link>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>
      </details>

      {/* C) Trade Ticket queue */}
      <Card data-testid="today-queue-card">
        <CardHeader title="Trade Ticket queue" description="Local queue (saved in browser)." />
        <div className="space-y-1.5">
          {queue.length === 0 ? (
            <p className="text-xs text-zinc-500">Queue is empty. Add from Action Needed.</p>
          ) : (
            queue.map((q) => (
              <div
                key={q.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs"
                data-testid={`today-queue-item-${q.symbol}`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono">{q.symbol}</span>
                  <span className="text-zinc-500">{q.strategy} · {q.action}</span>
                  <span className="text-zinc-400">{new Date(q.created_ts).toLocaleTimeString()}</span>
                  {q.journal_saved && (
                    <Badge variant="neutral" className="shrink-0" data-testid="today-queue-badge-journal-saved">Journal saved</Badge>
                  )}
                </div>
                <div className="flex gap-1 shrink-0">
                  <Link to={`/ticket?symbol=${encodeURIComponent(q.symbol)}&strategy=${q.strategy}&action=${q.action}&ticket_id=${encodeURIComponent(q.ticket_id ?? q.id)}`}>
                    <Button variant="secondary" size="sm">Open Ticket</Button>
                  </Link>
                  <Button variant="secondary" size="sm" onClick={() => markDone(q.id)} data-testid={`today-queue-done-${q.symbol}`}>
                    Mark Done
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => removeFromQueue(q.id)}>Remove</Button>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* D) End of Day Checklist — R26.4 / R26.9 */}
      <Card data-testid="today-eod-card">
        <CardHeader
          title="End of Day Checklist"
          description="Summary for today; mark done when complete."
          actions={
            eodPending ? (
              <>
                {!eodShowOverride ? (
                  <Button
                    onClick={() =>
                      markEodDone.mutate(
                        { kind: "EOD", key: today },
                        {
                          onError: (err: unknown) => {
                            const e = err as { status?: number };
                            if (e?.status === 409) setEodShowOverride(true);
                          },
                        }
                      )
                    }
                    disabled={markEodDone.isPending}
                    data-testid="today-eod-mark-done"
                  >
                    {markEodDone.isPending ? "Saving…" : "Mark EOD Done"}
                  </Button>
                ) : (
                  <div className="flex flex-wrap items-center gap-2" data-testid="today-eod-override">
                    <input
                      type="text"
                      placeholder="Override reason (required)"
                      value={eodOverrideReason}
                      onChange={(e) => setEodOverrideReason(e.target.value.slice(0, 140))}
                      className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1 text-sm max-w-[200px]"
                      data-testid="today-eod-override-reason"
                    />
                    <Button
                      onClick={() => {
                        markEodDone.mutate(
                          { kind: "EOD", key: today, override_reason: eodOverrideReason.trim().slice(0, 140) },
                          {
                            onSuccess: () => {
                              setEodShowOverride(false);
                              setEodOverrideReason("");
                            },
                          }
                        );
                      }}
                      disabled={markEodDone.isPending || !eodOverrideReason.trim()}
                      data-testid="today-eod-mark-done-with-override"
                    >
                      Complete EOD anyway
                    </Button>
                    <Button variant="secondary" size="sm" onClick={() => { setEodShowOverride(false); setEodOverrideReason(""); }}>
                      Cancel
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <span className="text-sm text-zinc-500">Done</span>
            )
          }
        />
        <div className="text-sm space-y-1">
          <p className="text-zinc-600 dark:text-zinc-400">
            Status: {eodChecklist?.row?.status ?? "OPEN"}
            {eodSummary && (
              <> · Eval as of: {eodSummary.eval_as_of ?? "—"} · Notifications (new): {eodSummary.notifications_new_count} · Journal entries today: {eodSummary.journal_entries_count}</>
            )}
          </p>
          {eodShowOverride && (
            <p className="text-amber-600 dark:text-amber-400" data-testid="today-eod-blocked-message">
              Cannot complete EOD while inbox has NEW items.
            </p>
          )}
        </div>
      </Card>

      {/* E) Journal checkpoint */}
      <Card data-testid="today-journal-card">
        <CardHeader
          title="Journal checkpoint"
          actions={
            <Link to="/journal" data-testid="today-journal-add">
              <Button variant="secondary" size="sm">
                Add manual entry
              </Button>
            </Link>
          }
        />
        <div className="text-sm">
          <p className="text-zinc-600 dark:text-zinc-400">
            Entries today ({today}): {journalEntries.length}
          </p>
          {missingJournalSymbols.length > 0 && (
            <p className="mt-1 text-amber-600 dark:text-amber-400" data-testid="today-missing-journal">
              Consider adding a journal entry for: {missingJournalSymbols.join(", ")} (marked done without entry today).
            </p>
          )}
        </div>
      </Card>

      {/* E) Notifications inbox */}
      <Card data-testid="today-notifications-card">
        <CardHeader
          title="Notifications inbox"
          description="Clear inbox daily."
          actions={
            <div className="flex gap-2">
              {notifications.some((n) => n.state === "NEW") && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => ackBulkMutation.mutate()}
                  disabled={ackBulkMutation.isPending}
                  data-testid="today-ack-all-new"
                >
                  {ackBulkMutation.isPending ? "Acking…" : "Ack all NEW"}
                </Button>
              )}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => archiveBulkMutation.mutate()}
                disabled={archiveBulkMutation.isPending}
                data-testid="today-archive-all-acked"
              >
                {archiveBulkMutation.isPending ? "Archiving…" : "Archive all ACKED"}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => refetchNotif()}>
                Refresh
              </Button>
            </div>
          }
        />
        <div className="space-y-1.5">
          {notifications.length === 0 ? (
            <p className="text-xs text-zinc-500">No NEW notifications.</p>
          ) : (
            notifications.slice(0, 10).map((n, i) => (
              <div
                key={n.id ?? i}
                className="flex items-center justify-between gap-2 rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs"
                data-testid={`today-notif-${n.id ?? i}`}
              >
                <span className="font-mono text-zinc-600 dark:text-zinc-400">{n.symbol ?? "—"}</span>
                <span className="text-zinc-600 dark:text-zinc-400 truncate flex-1">{n.type ?? "—"}</span>
                <div className="flex gap-1">
                  {n.state === "NEW" && n.id && (
                    <Button variant="secondary" size="sm" onClick={() => ackMutation.mutate(n.id!)} disabled={ackMutation.isPending}>
                      Ack
                    </Button>
                  )}
                  {n.id && (
                    <Button variant="secondary" size="sm" onClick={() => archiveMutation.mutate(n.id!)} disabled={archiveMutation.isPending}>
                      Archive
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      {/* R26.9: Skip journal modal */}
      {skipModalItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" data-testid="today-skip-modal">
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-4 shadow-lg max-w-md">
            <p className="text-sm text-zinc-700 dark:text-zinc-300 mb-2">
              No journal entry for {skipModalItem.symbol} ({skipModalItem.strategy} · {skipModalItem.action}) today. Enter a short reason to skip and mark done.
            </p>
            <input
              type="text"
              placeholder="Reason (required, max 140 chars)"
              value={skipReason}
              onChange={(e) => setSkipReason(e.target.value.slice(0, 140))}
              className="w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-2 py-1.5 text-sm mb-3"
              data-testid="today-skip-reason-input"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" size="sm" onClick={() => { setSkipModalItem(null); setSkipReason(""); }}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => confirmSkipAndMarkDone()}
                disabled={!skipReason.trim() || executionLogPost.isPending}
                data-testid="today-skip-confirm"
              >
                {executionLogPost.isPending ? "Saving…" : "Skip journal (reason recorded)"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
