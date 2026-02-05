/**
 * Phase 12: Universe Summary — universe size, evaluated count, eligible count, top blockers (LIVE only).
 */
import { useEffect, useState, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, ApiError, getResolvedUrl } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { useApiOpsStatus } from "@/hooks/useApiOpsStatus";
import { pushSystemNotification } from "@/lib/notifications";
import type { UniverseView } from "@/types/universe";

export function UniverseSummaryCard() {
  const { mode } = useDataMode();
  const opsStatus = useApiOpsStatus();
  const [universe, setUniverse] = useState<UniverseView | null>(null);
  const [universeError, setUniverseError] = useState<string | null>(null);

  const fetchUniverse = useCallback(() => {
    if (mode !== "LIVE") return;
    setUniverseError(null);
    apiGet<UniverseView>(ENDPOINTS.universe)
      .then((data) => setUniverse(data ?? null))
      .catch((e) => {
        setUniverse(null);
        const status = e instanceof ApiError ? e.status : 0;
        const is404 = status === 404;
        const is503 = status === 503;
        setUniverseError(is503 ? "ORATS down — universe blocked" : is404 ? "Universe disabled (check proxy/backend)" : `Universe unavailable (API error${status ? `: ${status}` : ""})`);
        if (import.meta.env?.DEV && typeof console !== "undefined") {
          console.warn("[ChakraOps] Universe fetch failed:", ENDPOINTS.universe, status, getResolvedUrl(ENDPOINTS.universe));
        }
        pushSystemNotification({
          source: "system",
          severity: "error",
          title: is404 ? "Universe disabled" : "Universe load failed",
          message: is404 ? "Endpoint not found. Check proxy and backend." : is503 ? "ORATS down — universe blocked." : `${ENDPOINTS.universe} failed. Check VITE_API_BASE_URL and backend.`,
        });
      });
  }, [mode]);

  useEffect(() => {
    if (mode !== "LIVE") return;
    fetchUniverse();
  }, [mode, fetchUniverse]);

  if (mode !== "LIVE") return null;

  const size = universeError ? null : (universe?.symbols?.length ?? 0);
  const enabledCount = universeError ? null : (universe?.symbols?.filter((s) => s.enabled !== false).length ?? size ?? 0);
  const evaluated = opsStatus.symbols_evaluated;
  const eligible = opsStatus.trades_found;
  const blockers = opsStatus.blockers_summary;
  const topBlockers = Object.entries(blockers)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <section
      className="rounded-lg border border-border bg-card p-4"
      role="region"
      aria-label="Universe summary"
    >
      <h2 className="text-sm font-medium text-muted-foreground">
        Universe summary
      </h2>
      <p className="mt-1 text-xs text-muted-foreground" title="Evaluation scope = Universe symbols">
        Evaluation scope = Universe symbols
      </p>
      {universeError && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <p className="text-sm text-destructive">{universeError}</p>
          <button
            type="button"
            onClick={fetchUniverse}
            className="rounded-md border border-border bg-secondary/50 px-2 py-1 text-xs font-medium text-foreground hover:bg-secondary"
          >
            Retry
          </button>
        </div>
      )}
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <p>
          <span className="text-muted-foreground">Universe size</span>{" "}
          <span className="font-medium text-foreground">{universeError ? "— (universe endpoint failed)" : size}</span>
        </p>
        <p>
          <span className="text-muted-foreground">Enabled</span>{" "}
          <span className="font-medium text-foreground">{universeError ? "—" : enabledCount}</span>
        </p>
        <p>
          <span className="text-muted-foreground">Evaluated</span>{" "}
          <span className="font-medium text-foreground">{evaluated}</span>
        </p>
        <p>
          <span className="text-muted-foreground">Eligible</span>{" "}
          <span className="font-medium text-foreground">{eligible}</span>
        </p>
      </div>
      {topBlockers.length > 0 && (
        <div className="mt-3">
          <p className="text-xs text-muted-foreground">Top blockers (by code)</p>
          <ul className="mt-1 list-inside list-disc text-sm text-foreground">
            {topBlockers.map(([code, count]) => (
              <li key={code}>
                <span className="font-medium">{code}</span>: {count}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
