import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { useNotifications, useAckNotification, useArchiveNotification } from "@/api/queries";
import { formatTimestampEtFull } from "@/utils/formatTimestamp";

export function NotificationBell() {
  const { data } = useNotifications(20, "NEW");
  const ackMutation = useAckNotification();
  const archiveMutation = useArchiveNotification();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const newList = data?.notifications ?? [];
  const newCount = newList.length;

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="relative rounded p-2 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        aria-label={newCount > 0 ? `${newCount} new notifications` : "Notifications"}
      >
        <Bell className="h-5 w-5" />
        {newCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
            {newCount > 99 ? "99+" : newCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-80 rounded border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          <div className="border-b border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-700 dark:border-zinc-700 dark:text-zinc-300">
            New notifications ({newCount})
          </div>
          <div className="max-h-72 overflow-auto">
            {newCount === 0 ? (
              <p className="px-3 py-4 text-sm text-zinc-500 dark:text-zinc-400">No new notifications.</p>
            ) : (
              <ul className="py-1">
                {newList.map((n, i) => (
                  <li key={n.id ?? i} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
                    <div className="flex items-start justify-between gap-2 px-3 py-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-200">
                          {n.type ?? "—"} {n.symbol ? `· ${n.symbol}` : ""}
                        </p>
                        <p className="truncate text-xs text-zinc-500 dark:text-zinc-400" title={n.message}>
                          {n.message ?? "—"}
                        </p>
                        <p className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500">
                          {formatTimestampEtFull(n.timestamp_utc)}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        {n.id && (
                          <>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.preventDefault();
                                ackMutation.mutate(n.id!);
                              }}
                              disabled={ackMutation.isPending}
                              className="rounded bg-zinc-200 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
                            >
                              Ack
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.preventDefault();
                                archiveMutation.mutate(n.id!);
                              }}
                              disabled={archiveMutation.isPending}
                              className="rounded bg-zinc-200 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
                            >
                              Archive
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="border-t border-zinc-200 px-3 py-2 dark:border-zinc-700">
            <Link
              to="/notifications"
              onClick={() => setOpen(false)}
              className="text-sm font-medium text-zinc-600 hover:underline dark:text-zinc-400"
            >
              View all notifications →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
