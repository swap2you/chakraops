/**
 * Modal: Universe size, symbols evaluated, top blockers summary. Evaluation scope = Universe symbols.
 */
import { useEffect, useState } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { pushSystemNotification } from "@/lib/notifications";
import type { UniverseView } from "@/types/universe";
import type { DailyOverviewView } from "@/types/views";
import { X } from "lucide-react";

const SCOPE_TOOLTIP = "Evaluation scope = Universe symbols";

export interface WhyOnlyThisSymbolModalProps {
  open: boolean;
  onClose: () => void;
  overview: DailyOverviewView | null;
  symbol: string;
}

export function WhyOnlyThisSymbolModal({
  open,
  onClose,
  overview,
  symbol,
}: WhyOnlyThisSymbolModalProps) {
  const { mode } = useDataMode();
  const [universe, setUniverse] = useState<UniverseView | null>(null);
  const [universeFailed, setUniverseFailed] = useState(false);

  useEffect(() => {
    if (!open || mode !== "LIVE") return;
    setUniverseFailed(false);
    apiGet<UniverseView>(ENDPOINTS.universe)
      .then((data) => setUniverse(data ?? null))
      .catch((e) => {
        setUniverse(null);
        setUniverseFailed(true);
        const status = e instanceof ApiError ? e.status : 0;
        const is404 = status === 404;
        pushSystemNotification({
          source: "system",
          severity: "error",
          title: is404 ? "Universe disabled" : "Universe endpoint failed",
          message: is404 ? "Endpoint not found. Check proxy and backend." : "Could not load universe for Why only this symbol? Check backend.",
        });
      });
  }, [open, mode]);

  if (!open) return null;

  const universeSize = universeFailed ? null : (universe?.symbols?.length ?? null);
  const universeSizeLabel = universeFailed ? "— (universe endpoint failed)" : (universeSize ?? "—");
  const symbolsEvaluated = overview?.symbols_evaluated ?? null;
  const topBlockers = overview?.top_blockers ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="why-only-modal-title"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="max-h-[80vh] w-full max-w-md overflow-auto rounded-lg border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2">
          <h2 id="why-only-modal-title" className="text-lg font-semibold text-foreground">
            Why only this symbol?
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground" title={SCOPE_TOOLTIP}>
          {SCOPE_TOOLTIP}
        </p>
        <dl className="mt-4 space-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Universe size</dt>
            <dd className="font-medium text-foreground">{universeSizeLabel}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Symbols evaluated</dt>
            <dd className="font-medium text-foreground">{symbolsEvaluated ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Trade plan symbol</dt>
            <dd className="font-medium text-foreground">{symbol}</dd>
          </div>
          {topBlockers.length > 0 && (
            <div>
              <dt className="text-muted-foreground">Top blockers (run)</dt>
              <dd className="mt-1">
                <ul className="list-inside list-disc space-y-0.5 text-muted-foreground">
                  {topBlockers.map((b, i) => (
                    <li key={i}>
                      {b.code}: {b.count}
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}
