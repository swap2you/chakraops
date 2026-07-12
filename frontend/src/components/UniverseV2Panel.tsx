// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R36.2 — Universe V2 panel (additive, read-only). Renders the lifecycle funnel,
// per-strategy eligible counts, snapshot freshness/version, and top rejection reasons
// from the precomputed published snapshot. Humanized titles only; never raw codes.

import { Card, CardHeader, Badge, Button } from "@/components/ui";
import { useUniverseV2Summary, useUniverseV2Refresh } from "@/api/queries";
import { formatTimestampEt } from "@/utils/formatTimestamp";
import type { UniverseV2Strategy } from "@/api/types";

const LIFECYCLE_ORDER = ["ADMITTED", "WATCH", "QUARANTINE", "REMOVED"] as const;
const STRATEGY_ORDER: UniverseV2Strategy[] = [
  "CORE_WHEEL",
  "BALANCED_WHEEL",
  "AGGRESSIVE_WHEEL",
  "SHARES",
];

const STRATEGY_LABEL: Record<string, string> = {
  CORE_WHEEL: "Core Wheel",
  BALANCED_WHEEL: "Balanced Wheel",
  AGGRESSIVE_WHEEL: "Aggressive Wheel",
  SHARES: "Shares",
};

function lifecycleVariant(state: string): "success" | "warning" | "danger" | "neutral" {
  if (state === "ADMITTED") return "success";
  if (state === "WATCH") return "warning";
  if (state === "QUARANTINE") return "danger";
  return "neutral";
}

export function UniverseV2Panel() {
  const { data, isLoading, isError } = useUniverseV2Summary();
  const refresh = useUniverseV2Refresh();

  const refreshBtn = (
    <Button
      variant="secondary"
      onClick={() => refresh.mutate()}
      disabled={refresh.isPending}
    >
      {refresh.isPending ? "Refreshing…" : "Rebuild snapshot"}
    </Button>
  );

  return (
    <div data-testid="universe-v2-panel">
    <Card className="mb-4">
      <CardHeader
        title="Universe V2"
        description="Research pool vs. strategy-specific eligible universes (advisory)."
        actions={refreshBtn}
      />

      {isLoading && <div className="text-sm text-zinc-500">Loading universe snapshot…</div>}
      {isError && <div className="text-sm text-red-500">Failed to load universe snapshot.</div>}

      {refresh.isError && (
        <div className="mb-2 text-sm text-red-500" data-testid="universe-v2-refresh-error">
          Rebuild failed — the previously published snapshot is unchanged. Try again after an
          evaluation has completed.
        </div>
      )}

      {data && data.status === "NO_SNAPSHOT" && (
        <div className="text-sm text-zinc-500" data-testid="universe-v2-empty">
          No published universe snapshot yet. Use “Rebuild snapshot” after an evaluation has run.
        </div>
      )}

      {data && data.status !== "NO_SNAPSHOT" && (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2" data-testid="universe-v2-freshness">
            <Badge variant="neutral">Research pool: {data.research_pool_count}</Badge>
            <Badge variant="neutral">Version v{data.version}</Badge>
            {data.stale ? (
              <Badge variant="warning">Stale</Badge>
            ) : (
              <Badge variant="success">Fresh</Badge>
            )}
            {data.created_at_utc && (
              <span className="text-xs text-zinc-500">
                as of {formatTimestampEt(data.created_at_utc)}
              </span>
            )}
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-zinc-500">Lifecycle</div>
            <div className="flex flex-wrap gap-2" data-testid="universe-v2-lifecycle">
              {LIFECYCLE_ORDER.map((state) => (
                <Badge key={state} variant={lifecycleVariant(state)}>
                  {state}: {data.lifecycle_funnel?.[state] ?? 0}
                </Badge>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-zinc-500">
              Eligible by strategy
            </div>
            <div className="flex flex-wrap gap-2" data-testid="universe-v2-strategies">
              {STRATEGY_ORDER.map((s) => (
                <Badge key={s} variant="default">
                  {STRATEGY_LABEL[s]}: {data.strategy_eligible?.[s] ?? 0}
                </Badge>
              ))}
            </div>
          </div>

          {data.top_rejection_reasons?.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-zinc-500">
                Top reasons
              </div>
              <ul className="space-y-0.5" data-testid="universe-v2-top-reasons">
                {data.top_rejection_reasons.slice(0, 5).map((r) => (
                  <li key={r.reason} className="text-xs text-zinc-600 dark:text-zinc-400">
                    {r.reason} · {r.count}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
    </div>
  );
}
