import { useState, useMemo } from "react";
import { useNotifications } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, StatusBadge, Button } from "@/components/ui";
import { formatTimestampEtFull } from "@/utils/formatTimestamp";

export function NotificationsPage() {
  const { data, isLoading, isError, refetch } = useNotifications(100);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<typeof notifications[0] | null>(null);

  const notifications = data?.notifications ?? [];
  const filtered = useMemo(() => {
    if (!filter.trim()) return notifications;
    const q = filter.trim().toLowerCase();
    return notifications.filter(
      (n) =>
        (n.type ?? "").toLowerCase().includes(q) ||
        (n.severity ?? "").toLowerCase().includes(q) ||
        (n.symbol ?? "").toLowerCase().includes(q) ||
        (n.message ?? "").toLowerCase().includes(q)
    );
  }, [notifications, filter]);

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
          <input
            type="text"
            placeholder="Filter by type, severity, symbol, message…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full max-w-md rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:placeholder-zinc-500"
          />
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
              <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                Close
              </Button>
            }
          />
          <div className="space-y-2 text-sm">
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
