import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { useAlerts } from "@/api/queries";

export function NotificationBell() {
  const { data } = useAlerts();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const alerts = data?.alerts ?? [];

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
        aria-label={alerts.length > 0 ? `${alerts.length} alerts` : "Alerts"}
      >
        <Bell className="h-5 w-5" />
        {alerts.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
            {alerts.length > 99 ? "99+" : alerts.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          <div className="border-b border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-700 dark:border-zinc-700 dark:text-zinc-300">
            Alerts ({alerts.length})
          </div>
          <div className="max-h-64 overflow-auto">
            {alerts.length === 0 ? (
              <p className="px-3 py-4 text-sm text-zinc-500 dark:text-zinc-400">No active alerts.</p>
            ) : (
              <ul className="py-1">
                {alerts.map((a, i) => (
                  <li key={`${a.position_id}-${a.type}-${i}`}>
                    <Link
                      to={`/symbol-diagnostics?symbol=${encodeURIComponent(a.symbol)}`}
                      onClick={() => setOpen(false)}
                      className="block px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    >
                      <span className="font-mono font-medium">{a.symbol}</span>{" "}
                      <span className="text-zinc-500 dark:text-zinc-400">{a.type}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
