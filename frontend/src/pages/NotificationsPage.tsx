import { useState, useMemo } from "react";
import {
  useNotifications,
  useAckNotification,
  useArchiveNotification,
  useDeleteNotification,
  useArchiveAllNotifications,
} from "@/api/queries";
import type { UiNotification } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, StatusBadge, Button } from "@/components/ui";
import { formatTimestampEtFull } from "@/utils/formatTimestamp";

type TabState = "NEW" | "ACKED" | "ARCHIVED" | "ALL";

export function NotificationsPage() {
  const [activeTab, setActiveTab] = useState<TabState>("NEW");
  const limit = 100;
  const stateFilter = activeTab === "ALL" ? undefined : activeTab;
  const { data, isLoading, isError, refetch } = useNotifications(limit, stateFilter);
  const ackMutation = useAckNotification(limit);
  const archiveMutation = useArchiveNotification();
  const deleteMutation = useDeleteNotification();
  const archiveAllMutation = useArchiveAllNotifications();
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<UiNotification | null>(null);

  const notifications = data?.notifications ?? [];
  const filtered = useMemo(() => {
    if (!filter.trim()) return notifications;
    const q = filter.trim().toLowerCase();
    return notifications.filter(
      (n) =>
        (n.type ?? "").toLowerCase().includes(q) ||
        (n.subtype ?? "").toLowerCase().includes(q) ||
        (n.severity ?? "").toLowerCase().includes(q) ||
        (n.symbol ?? "").toLowerCase().includes(q) ||
        (n.message ?? "").toLowerCase().includes(q)
    );
  }, [notifications, filter]);

  const canArchiveAll = activeTab === "NEW" || activeTab === "ACKED" || activeTab === "ALL";

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
            <div className="flex items-center gap-2">
              {canArchiveAll && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => archiveAllMutation.mutate()}
                  disabled={archiveAllMutation.isPending || notifications.length === 0}
                >
                  {archiveAllMutation.isPending ? "Archiving…" : "Archive all"}
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={() => refetch()}>
                Refresh
              </Button>
            </div>
          }
        />
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex rounded border border-zinc-200 dark:border-zinc-700 p-0.5">
              {(["NEW", "ACKED", "ARCHIVED", "ALL"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`rounded px-3 py-1.5 text-sm font-medium ${
                    activeTab === tab
                      ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
            <input
              type="text"
              placeholder="Filter by type, subtype, severity, symbol, message…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full max-w-md rounded border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:placeholder-zinc-500"
            />
          </div>
          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No notifications.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Time (ET)</th>
                    <th className="py-2 pr-2">State</th>
                    <th className="py-2 pr-2">Severity</th>
                    <th className="py-2 pr-2">Type</th>
                    <th className="py-2 pr-2">Subtype</th>
                    <th className="py-2 pr-2">Symbol</th>
                    <th className="py-2 pr-2">Message</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((n, i) => (
                    <tr
                      key={n.id ?? i}
                      className="cursor-pointer border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800/50 dark:hover:bg-zinc-800/30"
                      onClick={() => setSelected(n)}
                    >
                      <td className="py-2 pr-2 font-mono text-xs text-zinc-600 dark:text-zinc-400">
                        {formatTimestampEtFull(n.timestamp_utc)}
                      </td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={n.state ?? "NEW"} />
                      </td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={n.severity ?? "—"} />
                      </td>
                      <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{n.type ?? "—"}</td>
                      <td className="py-2 pr-2 text-zinc-600 dark:text-zinc-400">{n.subtype ?? "—"}</td>
                      <td className="py-2 pr-2 font-mono text-zinc-600 dark:text-zinc-400">{n.symbol ?? "—"}</td>
                      <td className="py-2 pr-2 text-zinc-600 dark:text-zinc-400 truncate max-w-xs" title={n.message}>
                        {n.message ?? "—"}
                      </td>
                      <td className="py-2 text-right">
                        <div className="flex justify-end gap-1">
                          {n.state === "NEW" && n.id && (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                ackMutation.mutate(n.id!);
                              }}
                              disabled={ackMutation.isPending}
                            >
                              Ack
                            </Button>
                          )}
                          {(n.state === "NEW" || n.state === "ACKED") && n.id && (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                archiveMutation.mutate(n.id!);
                              }}
                              disabled={archiveMutation.isPending}
                            >
                              Archive
                            </Button>
                          )}
                          {n.id && (
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteMutation.mutate(n.id!);
                              }}
                              disabled={deleteMutation.isPending}
                            >
                              Delete
                            </Button>
                          )}
                        </div>
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
                {selected.id && selected.state === "NEW" && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() =>
                      ackMutation.mutate(selected.id!, {
                        onSuccess: () =>
                          setSelected((prev) =>
                            prev ? { ...prev, state: "ACKED" as const, updated_at: new Date().toISOString() } : null
                          ),
                      })
                    }
                    disabled={ackMutation.isPending}
                  >
                    {ackMutation.isPending ? "Acking…" : "Ack"}
                  </Button>
                )}
                {selected.id && (selected.state === "NEW" || selected.state === "ACKED") && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      archiveMutation.mutate(selected.id!, {
                        onSuccess: () => setSelected(null),
                      })
                    }
                    disabled={archiveMutation.isPending}
                  >
                    Archive
                  </Button>
                )}
                {selected.id && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      deleteMutation.mutate(selected.id!, {
                        onSuccess: () => setSelected(null),
                      })
                    }
                    disabled={deleteMutation.isPending}
                  >
                    Delete
                  </Button>
                )}
                <Button variant="secondary" size="sm" onClick={() => setSelected(null)}>
                  Close
                </Button>
              </div>
            }
          />
          <div className="space-y-2 text-sm">
            {(selected.state ?? selected.ack_at_utc) && (
              <p>
                <span className="text-zinc-500 dark:text-zinc-500">State: </span>
                <StatusBadge status={selected.state ?? "NEW"} />
                {selected.updated_at && ` · ${formatTimestampEtFull(selected.updated_at)}`}
              </p>
            )}
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
