/**
 * Phase 8.5: Developer diagnostics (MOCK only) — scenario name, warnings, counts, timestamp range.
 */
import type { ValidationWarning } from "@/mock/validator";
import { cn } from "@/lib/utils";

export interface DiagnosticsDrawerProps {
  open: boolean;
  onClose: () => void;
  scenarioName: string;
  warnings: ValidationWarning[];
  decisionCount: number;
  positionCount: number;
  alertCount: number;
  evalRange: { min: string; max: string } | null;
}

export function DiagnosticsDrawer({
  open,
  onClose,
  scenarioName,
  warnings,
  decisionCount,
  positionCount,
  alertCount,
  evalRange,
}: DiagnosticsDrawerProps) {
  return (
    <>
      <div
        role="presentation"
        className={cn(
          "fixed inset-0 z-40 bg-black/50 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-50 h-full w-full max-w-md border-l border-border bg-card shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full"
        )}
        role="dialog"
        aria-label="Mock diagnostics"
      >
        <div className="flex h-full flex-col p-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <h2 className="text-lg font-semibold text-foreground">Scenario diagnostics</h2>
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
              <p className="text-muted-foreground">Scenario</p>
              <p className="font-medium text-foreground">{scenarioName}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Counts</p>
              <ul className="mt-1 list-inside text-foreground">
                <li>Decisions: {decisionCount}</li>
                <li>Positions: {positionCount}</li>
                <li>Alerts: {alertCount}</li>
              </ul>
            </div>
            {evalRange && (
              <div>
                <p className="text-muted-foreground">Evaluation timestamp range</p>
                <p className="font-medium text-foreground">
                  {evalRange.min} — {evalRange.max}
                </p>
              </div>
            )}
            <div>
              <p className="text-muted-foreground">Warnings ({warnings.length})</p>
              {warnings.length === 0 ? (
                <p className="mt-1 text-foreground">None</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {warnings.map((w, i) => (
                    <li key={i} className="rounded border border-border bg-muted/30 px-2 py-1.5">
                      <span className="font-medium text-foreground">{w.code}</span>
                      <span className="text-muted-foreground"> — {w.message}</span>
                      {w.affectedId != null && (
                        <span className="block text-xs text-muted-foreground">Affected: {String(w.affectedId)}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
