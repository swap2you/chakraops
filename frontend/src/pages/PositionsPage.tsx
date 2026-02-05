import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { getPositions } from "@/data/source";
import { useDataMode } from "@/context/DataModeContext";
import { useScenario } from "@/context/ScenarioContext";
import { usePolling } from "@/context/PollingContext";
import { useApiSnapshot } from "@/hooks/useApiSnapshot";
import { PositionDetailDrawer } from "@/components/PositionDetailDrawer";
import { EmptyState } from "@/components/EmptyState";
import { positionHealthStatus, nextActionLabel } from "@/lib/positionHelpers";
import { pushSystemNotification } from "@/lib/notifications";
import type { PositionView } from "@/types/views";
import { cn } from "@/lib/utils";
import { ApiError } from "@/data/apiClient";
import { Info } from "lucide-react";

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "—";
  return `$${Number(val).toFixed(2)}`;
}

function liveErrorMessage(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

export function PositionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { mode } = useDataMode();
  const scenario = useScenario();
  const polling = usePolling();
  const pollTick = polling?.pollTick ?? 0;
  const { snapshot } = useApiSnapshot();
  const [positions, setPositions] = useState<PositionView[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<PositionView | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (mode === "MOCK" && scenario?.bundle) {
      setLiveError(null);
      setPositions(scenario.bundle.positions ?? []);
      return;
    }
    if (mode !== "LIVE") return;
    let cancelled = false;
    setLiveError(null);
    getPositions(mode)
      .then((list) => {
        if (!cancelled) setPositions(list ?? []);
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = liveErrorMessage(e);
          setLiveError(msg);
          pushSystemNotification({
            source: "system",
            severity: "error",
            title: "LIVE fetch failed",
            message: msg,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, scenario?.bundle, mode === "LIVE" ? pollTick : 0]);

  const openSymbol = searchParams.get("open");
  useEffect(() => {
    if (!openSymbol || positions.length === 0) return;
    const p = positions.find((x) => String(x.symbol).toUpperCase() === openSymbol.toUpperCase());
    if (p) {
      setSelectedPosition(p);
      setDrawerOpen(true);
      setSearchParams((prev) => {
        prev.delete("open");
        return prev;
      }, { replace: true });
    }
  }, [openSymbol, positions, setSearchParams]);

  const openDrawer = (p: PositionView) => {
    setSelectedPosition(p);
    setDrawerOpen(true);
  };

  if (mode === "LIVE" && liveError) {
    return (
      <div className="space-y-6 p-6">
        <h1 className="text-2xl font-semibold">Positions</h1>
        <EmptyState title="LIVE data unavailable" message={liveError} />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-semibold">Positions</h1>
      <section className="rounded-lg border border-border bg-card overflow-hidden">
        {/* No evaluation run yet banner */}
        {mode === "LIVE" && snapshot && !snapshot.has_decision_artifact && (
          <div className="flex items-center gap-3 border-b border-border bg-muted/30 p-4">
            <Info className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="font-medium text-foreground">No live data yet — evaluation has not run</p>
              <p className="text-sm text-muted-foreground">
                Positions will appear here once an evaluation cycle completes.{" "}
                <Link to="/diagnostics" className="text-primary hover:underline">View diagnostics</Link>
              </p>
            </div>
          </div>
        )}

        {positions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Symbol</th>
                  <th className="p-3 font-medium">Strategy</th>
                  <th className="p-3 font-medium">Lifecycle</th>
                  <th className="p-3 font-medium">Opened</th>
                  <th className="p-3 font-medium">Entry credit</th>
                  <th className="p-3 font-medium">Realized PnL</th>
                  <th className="p-3 font-medium">Next action</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const health = positionHealthStatus(p);
                  const nextAction = nextActionLabel(p);
                  return (
                    <tr
                      key={String(p.position_id)}
                      role="button"
                      tabIndex={0}
                      onClick={() => openDrawer(p)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openDrawer(p);
                        }
                      }}
                      className={cn(
                        "border-b border-border transition-colors cursor-pointer",
                        "hover:bg-muted/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-inset"
                      )}
                    >
                      <td className="p-3">
                        <span
                          className={cn(
                            "inline-block h-2.5 w-2.5 rounded-full",
                            health === "healthy" && "bg-emerald-500",
                            health === "attention" && "bg-amber-500",
                            health === "closed" && "bg-slate-500"
                          )}
                          title={health}
                          aria-hidden
                        />
                      </td>
                      <td className="p-3 font-medium">{p.symbol}</td>
                      <td className="p-3">{p.strategy_type}</td>
                      <td className="p-3">{p.lifecycle_state}</td>
                      <td className="p-3">{p.opened}</td>
                      <td className="p-3">{formatCurrency(p.entry_credit)}</td>
                      <td className="p-3">{formatCurrency(p.realized_pnl)}</td>
                      <td className="p-3 text-muted-foreground">{nextAction}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-8 text-center text-muted-foreground">
            {mode === "LIVE" && snapshot && !snapshot.has_decision_artifact 
              ? "No positions — evaluation has not run yet."
              : "No positions."}
          </div>
        )}
      </section>

      <PositionDetailDrawer
        position={selectedPosition}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
