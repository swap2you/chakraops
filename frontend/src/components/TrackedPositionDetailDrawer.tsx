/**
 * Phase 4: Tracked position detail drawer — position info + Exit panel.
 */
import { AnimatePresence, motion } from "framer-motion";
import type { TrackedPosition } from "@/types/trackedPositions";
import { ExitPanel } from "./ExitPanel";

export interface TrackedPositionDetailDrawerProps {
  position: TrackedPosition | null;
  open: boolean;
  onClose: () => void;
  onExitLogged?: () => void;
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "short" });
  } catch {
    return iso;
  }
}

export function TrackedPositionDetailDrawer({
  position,
  open,
  onClose,
  onExitLogged,
}: TrackedPositionDetailDrawerProps) {
  if (!position) return null;

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
            transition={{ duration: 0.2 }}
            onClick={onClose}
            onKeyDown={(e) => e.key === "Escape" && onClose()}
          />
          <motion.aside
            className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-border bg-card shadow-xl sm:max-w-lg overflow-y-auto"
            role="dialog"
            aria-label="Position detail"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
          >
            <div className="flex h-full flex-col p-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <h2 className="text-lg font-semibold text-foreground">
                  {position.symbol} — {position.strategy}
                </h2>
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
                <div>
                  <p className="text-muted-foreground">Status</p>
                  <p className="font-medium text-foreground">{position.status}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Opened</p>
                  <p className="font-medium text-foreground">{formatDate(position.opened_at)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Strike</p>
                  <p className="font-medium text-foreground">
                    {position.strike != null ? `$${position.strike}` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Expiration</p>
                  <p className="font-medium text-foreground">{position.expiration ?? "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Credit Expected</p>
                  <p className="font-medium text-foreground">
                    {formatCurrency(position.credit_expected)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Lifecycle</p>
                  <p className="font-medium text-foreground">
                    {position.lifecycle_state ?? "—"}
                  </p>
                </div>
                {position.last_directive && (
                  <div>
                    <p className="text-muted-foreground">Last Directive</p>
                    <p className="font-medium text-foreground">{position.last_directive}</p>
                  </div>
                )}
                {position.notes && (
                  <div>
                    <p className="text-muted-foreground">Notes</p>
                    <p className="font-medium text-foreground">{position.notes}</p>
                  </div>
                )}

                <div className="border-t border-border pt-4">
                  <h3 className="mb-2 text-sm font-medium text-muted-foreground">Exit Panel</h3>
                  <ExitPanel
                    positionId={position.position_id}
                    symbol={position.symbol}
                    status={position.status}
                    onSuccess={onExitLogged}
                  />
                </div>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
