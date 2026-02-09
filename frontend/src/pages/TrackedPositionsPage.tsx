/**
 * Phase 1: Tracked Positions Page — read-only view of manually executed positions.
 * LIVE only. No editing, no exits (Phase 2).
 */
import { useEffect, useState, useCallback } from "react";
import { useDataMode } from "@/context/DataModeContext";
import { apiGet, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { pushSystemNotification } from "@/lib/notifications";
import type { TrackedPosition, TrackedPositionsListResponse } from "@/types/trackedPositions";
import { cn } from "@/lib/utils";
import { Loader2, Target } from "lucide-react";
import { TrackedPositionDetailDrawer } from "@/components/TrackedPositionDetailDrawer";

function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "\u2014";
  return `$${Number(val).toFixed(2)}`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "short" });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

const STATUS_STYLES: Record<string, string> = {
  OPEN: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
  PARTIAL_EXIT: "bg-amber-500/20 text-amber-600 dark:text-amber-400",
  CLOSED: "bg-muted text-muted-foreground",
  ABORTED: "bg-red-500/20 text-red-600 dark:text-red-400",
};

const LIFECYCLE_STYLES: Record<string, string> = {
  OPEN: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
  PARTIAL_EXIT: "bg-amber-500/20 text-amber-600 dark:text-amber-400",
  CLOSED: "bg-muted text-muted-foreground",
  ABORTED: "bg-red-500/20 text-red-600 dark:text-red-400",
};

export function TrackedPositionsPage() {
  const { mode } = useDataMode();
  const [positions, setPositions] = useState<TrackedPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailPosition, setDetailPosition] = useState<TrackedPosition | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const fetchPositions = useCallback(async () => {
    if (mode !== "LIVE") return;
    setError(null);
    try {
      const res = await apiGet<TrackedPositionsListResponse>(ENDPOINTS.trackedPositions);
      setPositions(res.positions ?? []);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
      setPositions([]);
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Positions fetch failed",
        message: msg,
      });
    } finally {
      setLoading(false);
    }
  }, [mode]);

  useEffect(() => {
    if (mode === "MOCK") {
      setLoading(false);
      setPositions([]);
      setError(null);
      return;
    }
    fetchPositions();
  }, [mode, fetchPositions]);

  if (mode === "MOCK") {
    return (
      <div className="space-y-6 p-6">
        <PageHeader
          title="Tracked Positions"
          subtext="Manually tracked positions. Switch to LIVE to use."
        />
        <EmptyState
          title="Tracked Positions is LIVE only"
          message="Switch to LIVE mode to view tracked positions."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Tracked Positions"
        subtext="Positions you've manually executed. ChakraOps tracks them but never places trades."
      />

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-border bg-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-12 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading...
          </div>
        ) : positions.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground">
            <Target className="mx-auto h-8 w-8 mb-3 opacity-40" />
            <p className="font-medium">No tracked positions</p>
            <p className="mt-1 text-sm">
              Use the Execute (Manual) button on the Ticker page to record a position.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                  <th className="p-3 font-medium">Symbol</th>
                  <th className="p-3 font-medium">Strategy</th>
                  <th className="p-3 font-medium">Contracts / Qty</th>
                  <th className="p-3 font-medium">Strike</th>
                  <th className="p-3 font-medium">Expiration</th>
                  <th className="p-3 font-medium">Credit Expected</th>
                  <th className="p-3 font-medium">Account</th>
                  <th className="p-3 font-medium">Opened</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Lifecycle</th>
                  <th className="p-3 font-medium">Last Directive</th>
                  <th className="p-3 font-medium">Last Alert</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr
                    key={p.position_id}
                    className="border-b border-border transition-colors hover:bg-muted/50 cursor-pointer"
                    onClick={() => {
                      setDetailPosition(p);
                      setDrawerOpen(true);
                    }}
                  >
                    <td className="p-3 font-medium">{p.symbol}</td>
                    <td className="p-3">
                      <span className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                        p.strategy === "CSP" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                        p.strategy === "CC" && "bg-blue-500/20 text-blue-600 dark:text-blue-400",
                        p.strategy === "STOCK" && "bg-purple-500/20 text-purple-600 dark:text-purple-400"
                      )}>
                        {p.strategy}
                      </span>
                    </td>
                    <td className="p-3">
                      {p.strategy === "STOCK" ? (p.quantity ?? "\u2014") : p.contracts}
                    </td>
                    <td className="p-3">{p.strike != null ? `$${p.strike}` : "\u2014"}</td>
                    <td className="p-3">{p.expiration ?? "\u2014"}</td>
                    <td className="p-3">{formatCurrency(p.credit_expected)}</td>
                    <td className="p-3 text-xs text-muted-foreground">{p.account_id}</td>
                    <td className="p-3">{formatDate(p.opened_at)}</td>
                    <td className="p-3">
                      <span className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                        STATUS_STYLES[p.status] ?? "bg-muted text-muted-foreground"
                      )}>
                        {p.status}
                      </span>
                    </td>
                    <td className="p-3">
                      {p.lifecycle_state ? (
                        <span className={cn(
                          "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                          LIFECYCLE_STYLES[p.lifecycle_state] ?? "bg-muted text-muted-foreground"
                        )}>
                          {p.lifecycle_state}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="p-3 text-sm text-muted-foreground max-w-[180px] truncate" title={p.last_directive ?? undefined}>
                      {p.last_directive ?? "—"}
                    </td>
                    <td className="p-3 text-xs text-muted-foreground">
                      {p.last_alert_at ? formatDateTime(p.last_alert_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {positions.length > 0 && (
        <p className="text-xs text-muted-foreground text-center">
          {positions.filter((p) => p.status === "OPEN").length} open ·{" "}
          {positions.filter((p) => p.status === "CLOSED").length} closed ·{" "}
          {positions.length} total
        </p>
      )}

      <TrackedPositionDetailDrawer
        position={detailPosition}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setDetailPosition(null);
        }}
        onExitLogged={() => {
          fetchPositions();
          setDrawerOpen(false);
          setDetailPosition(null);
        }}
      />
    </div>
  );
}
