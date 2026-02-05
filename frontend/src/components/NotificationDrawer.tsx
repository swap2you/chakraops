/**
 * Phase 8.6: Notification detail drawer — full text, links to position or history.
 */
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import type { NotificationItem } from "@/lib/notifications";

export interface NotificationDrawerProps {
  notification: NotificationItem | null;
  open: boolean;
  onClose: () => void;
}

export function NotificationDrawer({
  notification,
  open,
  onClose,
}: NotificationDrawerProps) {
  if (!notification) return null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            role="presentation"
            className="fixed inset-0 z-40 bg-black/50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            onKeyDown={(e) => e.key === "Escape" && onClose()}
          />
          <motion.aside
            className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-border bg-card shadow-xl sm:max-w-lg"
            role="dialog"
            aria-label="Notification detail"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
          >
            <div className="flex h-full flex-col p-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h2 className="text-lg font-semibold text-foreground">{notification.title}</h2>
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  aria-label="Close"
                >
                  ✕
                </button>
              </div>
              <div className="mt-4 flex-1 space-y-4 overflow-y-auto text-sm">
                <p className="text-muted-foreground">{notification.message}</p>
                {notification.symbol && (
                  <Link
                    to={`/positions?open=${encodeURIComponent(notification.symbol)}`}
                    className="inline-flex rounded-md bg-primary/15 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/25 focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    Open position
                  </Link>
                )}
                {notification.decision_ts && !notification.symbol && !notification.runId && (
                  <Link
                    to="/history"
                    className="inline-flex rounded-md bg-primary/15 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/25 focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    View history
                  </Link>
                )}
                {notification.runId && (
                  <Link
                    to="/history"
                    className="inline-flex items-center gap-2 rounded-md bg-purple-500/15 px-3 py-2 text-sm font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-500/25 focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    View run in History
                  </Link>
                )}
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
