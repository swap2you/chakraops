/**
 * Phase 7.2 / 7.3 / 8.6: Position detail drawer — read-only + Risk context; Framer Motion.
 */
import { AnimatePresence, motion } from "framer-motion";
import type { PositionView } from "@/types/views";

export interface PositionDetailDrawerProps {
  position: PositionView | null;
  open: boolean;
  onClose: () => void;
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

function assignmentRiskLevel(dte: number | null | undefined): string {
  if (dte == null) return "—";
  if (dte > 21) return "Low";
  if (dte >= 7) return "Medium";
  return "High";
}

function proximitySummary(
  lastMark: number | null | undefined,
  targets: Record<string, number> | undefined
): string {
  const t1 = targets?.t1;
  if (lastMark == null || t1 == null) return "—";
  const pct = (lastMark / t1) * 100;
  if (pct >= 100) return "At or above T1";
  if (pct >= 90) return "Within 10% of T1";
  if (pct >= 70) return "Approaching T1";
  return "Below target range";
}

export function PositionDetailDrawer({
  position,
  open,
  onClose,
}: PositionDetailDrawerProps) {
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
            className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-border bg-card shadow-xl sm:max-w-lg"
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
              {position.symbol} — {position.lifecycle_state}
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
              <p className="text-muted-foreground">Strategy</p>
              <p className="font-medium text-foreground">{position.strategy_type}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Opened</p>
              <p className="font-medium text-foreground">{position.opened}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Expiry</p>
              <p className="font-medium text-foreground">{position.expiry ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Entry credit</p>
              <p className="font-medium text-foreground">
                {formatCurrency(position.entry_credit)}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Realized PnL</p>
              <p className="font-medium text-foreground">
                {formatCurrency(position.realized_pnl)}
              </p>
            </div>

            <div className="rounded-md border border-border bg-muted/30 p-3">
              <h3 className="text-sm font-medium text-foreground">Risk context</h3>
              <dl className="mt-2 space-y-1.5 text-sm">
                <div>
                  <dt className="text-muted-foreground">Assignment risk</dt>
                  <dd className="font-medium text-foreground">
                    {assignmentRiskLevel(position.dte)}
                    {position.dte != null && (
                      <span className="ml-1 font-normal text-muted-foreground">
                        ({position.dte} DTE)
                      </span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Proximity to targets</dt>
                  <dd className="font-medium text-foreground">
                    {proximitySummary(position.last_mark, position.profit_targets)}
                    {position.last_mark != null && (
                      <span className="ml-1 font-normal text-muted-foreground">
                        (current {formatCurrency(position.last_mark)} vs T1{" "}
                        {formatCurrency(position.profit_targets?.t1)})
                      </span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Days remaining</dt>
                  <dd className="font-medium text-foreground">
                    {position.dte != null ? `${position.dte} days` : "—"}
                  </dd>
                </div>
              </dl>
            </div>

            {position.needs_attention && (
              <div>
                <p className="text-muted-foreground">Review reasons</p>
                <p className="font-medium text-foreground">
                  {position.attention_reasons?.join(", ") ?? "Flagged for review"}
                </p>
              </div>
            )}
            {position.notes && (
              <div>
                <p className="text-muted-foreground">Notes</p>
                <p className="font-medium text-foreground">{position.notes}</p>
              </div>
            )}
          </div>
        </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
