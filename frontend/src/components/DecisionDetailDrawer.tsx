/**
 * Phase 8 / 8.6: Decision Detail View — full context; Framer Motion.
 */
import { AnimatePresence, motion } from "framer-motion";
import type { DecisionRecord } from "@/types/views";
import { DecisionBanner } from "./DecisionBanner";
import { TradePlanCard } from "./TradePlanCard";
import { DailyOverviewCard } from "./DailyOverviewCard";

export interface DecisionDetailDrawerProps {
  record: DecisionRecord | null;
  open: boolean;
  onClose: () => void;
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

function formatEvaluatedAt(ts: string): string {
  try {
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return ts;
  }
}

export function DecisionDetailDrawer({
  record,
  open,
  onClose,
}: DecisionDetailDrawerProps) {
  if (!record) return null;

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
            className="fixed right-0 top-0 z-50 h-full w-full max-w-lg overflow-hidden border-l border-border bg-card shadow-xl sm:max-w-xl"
            role="dialog"
            aria-label="Decision detail"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
          >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-border p-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                Decision — {record.date}
              </h2>
              <p className="text-sm text-muted-foreground">
                Evaluated {formatEvaluatedAt(record.evaluated_at)}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Historical decision banner — read-only, no CTA; S8: overview may be missing */}
            <DecisionBanner
              overview={record.overview ?? null}
              tradePlan={record.trade_plan}
              label="Decision"
            />

            {/* Trade plan (if any) — read-only, no primary action */}
            <TradePlanCard
              tradePlan={record.trade_plan}
              overview={record.overview ?? null}
            />

            {/* Why this / why not — overview may be missing; show placeholders */}
            <DailyOverviewCard overview={record.overview ?? null} />

            {/* Snapshot of positions at decision time */}
            <section
              className="rounded-lg border border-border bg-card p-4"
              role="region"
              aria-label="Positions at decision time"
            >
              <h3 className="text-sm font-medium text-muted-foreground">
                Positions at decision time
              </h3>
              {record.positions.length === 0 ? (
                <p className="mt-2 text-sm text-muted-foreground">No open positions.</p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-muted-foreground">
                        <th className="pb-2 pr-2 font-medium">Symbol</th>
                        <th className="pb-2 pr-2 font-medium">Strategy</th>
                        <th className="pb-2 pr-2 font-medium">State</th>
                        <th className="pb-2 pr-2 font-medium">Entry</th>
                        <th className="pb-2 font-medium">Expiry</th>
                      </tr>
                    </thead>
                    <tbody>
                      {record.positions.map((p) => (
                        <tr key={String(p.position_id)} className="border-b border-border/60">
                          <td className="py-2 pr-2 font-medium text-foreground">{p.symbol}</td>
                          <td className="py-2 pr-2 text-muted-foreground">{p.strategy_type}</td>
                          <td className="py-2 pr-2 text-muted-foreground">{p.lifecycle_state}</td>
                          <td className="py-2 pr-2 text-muted-foreground">
                            {formatCurrency(p.entry_credit)}
                          </td>
                          <td className="py-2 text-muted-foreground">{p.expiry ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
