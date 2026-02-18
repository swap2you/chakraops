import { useState, useMemo } from "react";
import { useNotifications, useAckNotification } from "@/api/queries";
import type { UiNotification } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, StatusBadge, Button } from "@/components/ui";
import { formatTimestampEtFull } from "@/utils/formatTimestamp";

export function NotificationsPage() {
  const { data, isLoading, isError, refetch } = useNotifications(100);
  const ackMutation = useAckNotification(100);
  const [filter, setFilter] = useState("");
  const [unackedOnly, setUnackedOnly] = useState(false);
  const [selected, setSelected] = useState<UiNotification | null>(null);

  const notifications = data?.notifications ?? [];
  const filtered = useMemo(() => {
    let list = notifications;
    if (unackedOnly) {
      list = list.filter((n) => !n.ack_at_utc);
    }
    if (!filter.trim()) return list;
    const q = filter.trim().toLowerCase();
    return list.filter(
      (n) =>
        (n.type ?? "").toLowerCase().includes(q) ||
        (n.subtype ?? "").toLowerCase().includes(q) ||
        (n.severity ?? "").toLowerCase().includes(q) ||
        (n.symbol ?? "").toLowerCase().includes(q) ||
        (n.message ?? "").toLowerCase().includes(q)
    );
  }, [notifications, filter, unackedOnly]);

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Notifications" />
        <p className="text-zinc-400">Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Notifications" />
        <p className="text-red-400">Failed to load notifications.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Notifications" subtext="Events and alerts (UI parity with Slack)" />
      <Card>
        <CardHeader
          title="Notifications"
          actions={
            <Button variant="secondary" size="sm" onClick={() => refetch()}>
              Refresh
            </Button>
          }
        />
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-4">
            <input
              type="text"
              placeholder="Filter by type, subtype, severity, symbol, message…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full max-w-md rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:placeholder-zinc-500"
            />
            <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
              <input
                type="checkbox"
                checked={unackedOnly}
                onChange={(e) => setUnackedOnly(e.target.checked)}
                className="rounded border-zinc-300"
              />
              Unacknowledged only
            </label>
          </div>
          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No notifications.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Time (ET)</th>
                    <th className="py-2 pr-2">Severity</th>
                    <th className="py-2 pr-2">Type</th>
                    <th className="py-2 pr-2">Subtype</th>
                    <th className="py-2 pr-2">Symbol</th>
                    <th className="py-2">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((n, i) => (
                    <tr
                      key={i}
                      className="cursor-pointer border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800/50 dark:hover:bg-zinc-800/30"
                      onClick={() => setSelected(n)}
                    >
                      <td className="py-2 pr-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">
                        {formatTimestampEtFull(n.timestamp_utc)}
                      </td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={n.severity ?? "—"} />
                      </td>
                      <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{n.type ?? "—"}</td>
                      <td className="py-2 pr-2 text-zinc-600 dark:text-zinc-400">{n.subtype ?? "—"}</td>
                      <td className="py-2 pr-2 font-mono text-zinc-600 dark:text-zinc-400">{n.symbol ?? "—"}</td>
                      <td className="py-2 text-zinc-600 dark:text-zinc-400 truncate max-w-xs" title={n.message}>
                        {n.message ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {selected && (
        <Card>
          <CardHeader
            title="Detail"
            actions={
              <div className="flex items-center gap-2">
                {selected.id && !selected.ack_at_utc && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() =>
                      ackMutation.mutate(selected.id!, {
                        onSuccess: () => setSelected((prev) =>
                          prev ? { ...prev, ack_at_utc: new Date().toISOString(), ack_by: "ui" } : null
                        ),
                      })
                    }
                    disabled={ackMutation.isPending}
                  >
                    {ackMutation.isPending ? "Acking…" : "Ack"}
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                  Close
                </Button>
              </div>
            }
          />
          <div className="space-y-2 text-sm">
            {selected.ack_at_utc && (
              <p>
                <span className="text-zinc-500 dark:text-zinc-500">Acknowledged: </span>
                {formatTimestampEtFull(selected.ack_at_utc)}
                {selected.ack_by && ` by ${selected.ack_by}`}
              </p>
            )}
            <p>
              <span className="text-zinc-500 dark:text-zinc-500">Time: </span>
              {formatTimestampEtFull(selected.timestamp_utc)}
            </p>
            <p>
              <span className="text-zinc-500 dark:text-zinc-500">Severity: </span>
              <StatusBadge status={selected.severity ?? "—"} />
            </p>
            <p>
              <span className="text-zinc-500 dark:text-zinc-500">Type: </span>
              {selected.type ?? "—"}
            </p>
            <p>
              <span className="text-zinc-500 dark:text-zinc-500">Subtype: </span>
              {selected.subtype ?? "—"}
            </p>
            <p>
              <span className="text-zinc-500 dark:text-zinc-500">Symbol: </span>
              {selected.symbol ?? "—"}
            </p>
            <p>
              <span className="text-zinc-500 dark:text-zinc-500">Message: </span>
              {selected.message ?? "—"}
            </p>
            {selected.details && Object.keys(selected.details).length > 0 && (
              <pre className="mt-2 overflow-auto rounded border border-zinc-200 bg-zinc-50 p-2 text-xs dark:border-zinc-700 dark:bg-zinc-900">
                {JSON.stringify(selected.details, null, 2)}
              </pre>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
