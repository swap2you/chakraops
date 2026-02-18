/**
 * Phase 13.0: Portfolio position detail drawer — Details + Timeline tabs, Roll action.
 */
import { useState } from "react";
import { X, History, FileText } from "lucide-react";
import { usePositionEvents } from "@/api/queries";
import type { PortfolioPosition } from "@/api/types";
import type { PositionEvent } from "@/api/queries";
import { Button, Badge, EmptyState } from "@/components/ui";
import { RollPositionDrawer } from "./RollPositionDrawer";
import { cn } from "@/lib/utils";

export interface PortfolioPositionDetailDrawerProps {
  position: PortfolioPosition | null;
  open: boolean;
  onClose: () => void;
  onClosed?: () => void;
}

function fmtCurrency(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "n/a";
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function eventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    OPEN: "Opened",
    FILL: "Fill",
    ADJUST: "Adjustment",
    CLOSE: "Closed",
    ABORT: "Aborted",
    NOTE: "Note",
  };
  return labels[type] ?? type;
}

function eventTypeVariant(type: string): "success" | "warning" | "danger" | "neutral" {
  const s = type.toUpperCase();
  if (s === "OPEN" || s === "FILL") return "success";
  if (s === "CLOSE") return "neutral";
  if (s === "ABORT") return "danger";
  if (s === "ADJUST") return "warning";
  return "neutral";
}

export function PortfolioPositionDetailDrawer({ position, open, onClose, onClosed }: PortfolioPositionDetailDrawerProps) {
  const [activeTab, setActiveTab] = useState<"details" | "timeline">("details");
  const [showRollDrawer, setShowRollDrawer] = useState(false);

  const posId = position?.id ?? position?.position_id ?? null;
  const { data: eventsData } = usePositionEvents(posId, open && !!posId);

  const events = eventsData?.events ?? [];
  const isOpen = position && ["OPEN", "PARTIAL_EXIT"].includes((position.status ?? "").toUpperCase());
  const strategy = (position?.strategy ?? "").toUpperCase();
  const canRoll = isOpen && (strategy === "CSP" || strategy === "CC");

  if (!position || !open) return null;

  return (
    <>
      <div
        role="presentation"
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
        aria-hidden="true"
      />
      <aside
        className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-zinc-200 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900 sm:max-w-lg"
        role="dialog"
        aria-label="Position detail"
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-zinc-200 p-4 dark:border-zinc-700">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {position.symbol} — {position.strategy}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="flex gap-2 border-b border-zinc-200 px-4 dark:border-zinc-700">
            <button
              onClick={() => setActiveTab("details")}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium -mb-px transition-colors",
                activeTab === "details"
                  ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                  : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
            >
              <FileText className="h-4 w-4" />
              Details
            </button>
            <button
              onClick={() => setActiveTab("timeline")}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium -mb-px transition-colors",
                activeTab === "timeline"
                  ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                  : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
            >
              <History className="h-4 w-4" />
              Timeline {events.length > 0 && `(${events.length})`}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {activeTab === "details" && (
              <div className="space-y-4 text-sm">
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Status</span>
                  <Badge variant="neutral">{position.status ?? "OPEN"}</Badge>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Symbol</span>
                  <span className="font-mono font-medium text-zinc-900 dark:text-zinc-100">{position.symbol}</span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Strategy</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">{position.strategy ?? "n/a"}</span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Strike</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {position.strike != null ? fmtNum(position.strike) : "n/a"}
                  </span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Expiration</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">{position.expiry ?? "n/a"}</span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Contracts</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">{position.contracts ?? "n/a"}</span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Entry credit</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {position.entry_credit != null ? fmtNum(position.entry_credit) : "n/a"}
                  </span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Mark</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {position.mark != null ? fmtNum(position.mark) : "n/a"}
                  </span>
                </div>
                <div>
                  <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-400">Realized PnL</span>
                  <span
                    className={cn(
                      "font-mono font-medium",
                      (position.realized_pnl ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                    )}
                  >
                    {fmtCurrency(position.realized_pnl)}
                  </span>
                </div>
                {canRoll && (
                  <div className="border-t border-zinc-200 pt-4 dark:border-zinc-700">
                    <Button variant="secondary" onClick={() => setShowRollDrawer(true)}>
                      Roll position
                    </Button>
                    <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                      Close this position and open a new one (same symbol/strategy, new strike/expiry).
                    </p>
                  </div>
                )}
              </div>
            )}

            {activeTab === "timeline" && (
              <div className="space-y-3">
                {events.length === 0 ? (
                  <EmptyState
                    title="No events yet"
                    message="Position lifecycle events will appear here when you open, adjust, or close positions."
                  />
                ) : (
                  <ul className="space-y-2">
                    {events.map((evt: PositionEvent) => (
                      <li
                        key={evt.event_id}
                        className="rounded-lg border border-zinc-200 bg-zinc-50/50 p-3 dark:border-zinc-700 dark:bg-zinc-800/50"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <Badge variant={eventTypeVariant(evt.type)}>{eventTypeLabel(evt.type)}</Badge>
                          <span className="text-xs text-zinc-500 dark:text-zinc-400">{fmtDate(evt.at_utc)}</span>
                        </div>
                        {evt.payload && Object.keys(evt.payload).length > 0 && (
                          <pre className="mt-2 overflow-x-auto rounded bg-zinc-100 px-2 py-1.5 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                            {Object.entries(evt.payload)
                              .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
                              .join(" · ")}
                          </pre>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      </aside>

      {showRollDrawer && (
        <RollPositionDrawer
          position={position}
          onClose={() => setShowRollDrawer(false)}
          onSuccess={() => {
            setShowRollDrawer(false);
            onClosed?.();
          }}
        />
      )}
    </>
  );
}
