// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0 (H-5 cutover): operator-facing PRIMARY recommendation renderer. Renders
// the canonical authoritative block (actionable / WATCH / BLOCKED / STAY_IN_CASH)
// with active profile, manual-only wording, freshness, provider health, event
// availability, safe reason labels, per-suggestion + combined capital, deployable
// cash, and the combined-capital warning. Never renders legacy lists, and never
// shows an actionable primary when canonical data is stale or unavailable.

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, CardHeader } from "@/components/ui";
import type {
  ActionNeededResponse,
  CanonicalLiveItem,
  CapitalSetSafety,
} from "@/api/queries";
import { reasonLabels } from "@/utils/reasonLabels";
import { formatTimestampEt } from "@/utils/formatTimestamp";
import { ExplanationPanel } from "@/components/ExplanationPanel";

interface Props {
  data?: ActionNeededResponse;
  isLoading?: boolean;
  isError?: boolean;
  providerHealth?: { label?: string | null; ok?: boolean | null };
  maxItems?: number;
  renderItemActions?: (item: CanonicalLiveItem) => ReactNode;
}

const ACTION_VARIANT: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  ENTRY: "success",
  WATCH: "warning",
  BLOCKED: "danger",
  STAY_IN_CASH: "neutral",
};

function fmtUsd(v?: number | null): string {
  if (v == null) return "—";
  return `$${Math.round(v).toLocaleString()}`;
}

function fmtPct(v?: number | null): string {
  if (v == null) return "—";
  return `${v.toFixed(1)}%`;
}

function earningsDays(item: CanonicalLiveItem): number | null {
  const ev = item.event_risk as Record<string, unknown> | null | undefined;
  const d = ev?.earnings_days;
  return typeof d === "number" ? d : null;
}

function RecRow({ item, actions }: { item: CanonicalLiveItem; actions?: ReactNode }) {
  const ed = earningsDays(item);
  const labels = reasonLabels([...(item.reason_codes ?? []), ...(item.risk_flags ?? [])]);
  return (
    <div
      data-testid={`canonical-rec-${item.symbol}`}
      className="rounded border border-zinc-200 dark:border-zinc-700 p-3 text-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <Link
          to={`/symbol-diagnostics?symbol=${encodeURIComponent(item.symbol)}`}
          className="font-mono font-semibold text-zinc-800 dark:text-zinc-200 hover:underline"
        >
          {item.symbol}
        </Link>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase text-zinc-500">{item.strategy}</span>
          <Badge variant={ACTION_VARIANT[item.next_action_code] ?? "neutral"}>
            {item.next_action_code === "ENTRY" ? "Entry" : item.next_action_code}
          </Badge>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-zinc-600 dark:text-zinc-400">
        <span data-testid={`canonical-capital-${item.symbol}`}>
          Capital: {fmtUsd(item.capital_required)}
        </span>
        {item.expected_return_pct != null && <span>Est. return: {fmtPct(item.expected_return_pct)}</span>}
        {item.score != null && <span>Score: {Math.round(item.score)}</span>}
        <span>
          Earnings: {ed == null ? "unknown" : ed >= 0 ? `${ed}d` : "n/a"}
        </span>
      </div>
      {labels.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {labels.map((l) => (
            <span key={l} className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
              {l}
            </span>
          ))}
        </div>
      )}
      <ExplanationPanel explanation={item.explanation} />
      {actions && <div className="mt-2">{actions}</div>}
    </div>
  );
}

function CapitalSafetyBanner({ cs }: { cs: CapitalSetSafety }) {
  const cashKnown = cs.cash_known !== false && cs.available_cash != null;
  return (
    <div data-testid="canonical-capital-safety" className="rounded border border-zinc-200 dark:border-zinc-700 p-3 text-xs space-y-1">
      <p className="text-zinc-600 dark:text-zinc-400">
        Each suggestion is sized independently — quantities are <strong>not jointly executable</strong>.
      </p>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-zinc-600 dark:text-zinc-400">
        <span>Combined displayed capital: {fmtUsd(cs.total_capital_required_displayed)}</span>
        <span>Deployable cash: {fmtUsd(cs.deployable_capital)}</span>
        <span>Available cash: {cashKnown ? fmtUsd(cs.available_cash) : "unknown"}</span>
      </div>
      {cs.exceeds_deployable_capital && (
        <p data-testid="canonical-combined-warning" className="text-amber-600 dark:text-amber-400">
          Combined displayed capital exceeds deployable cash — you cannot take all suggestions at once.
        </p>
      )}
      {reasonLabels(cs.flags).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {reasonLabels(cs.flags).map((l) => (
            <span key={l} className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function AuthoritativeRecommendations({
  data,
  isLoading,
  isError,
  providerHealth,
  maxItems = 7,
  renderItemActions,
}: Props) {
  const auth = data?.authoritative_recommendations ?? null;
  const profile = data?.active_profile ?? (auth?.active_profile ?? "balanced");
  const unavailable =
    !auth || auth.status === "UNAVAILABLE" || auth.decision_source === "canonical_decision_engine_unavailable";

  const header = (
    <CardHeader title="Recommendations">
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="default">Canonical engine</Badge>
        <Badge variant="neutral">Profile: {profile}</Badge>
        <span className="text-zinc-500" data-testid="canonical-manual-only">
          Manual execution only — no orders are placed.
        </span>
        {auth?.as_of_utc && (
          <span className="text-zinc-500" data-testid="canonical-freshness">
            As of {formatTimestampEt(auth.as_of_utc)}
          </span>
        )}
        {providerHealth?.label && (
          <span className="text-zinc-500" data-testid="canonical-provider-health">
            Data: {providerHealth.label}
          </span>
        )}
      </div>
    </CardHeader>
  );

  if (isLoading) {
    return (
      <Card data-testid="canonical-primary">
        {header}
        <p className="text-sm text-zinc-500">Loading recommendations…</p>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card data-testid="canonical-primary">
        {header}
        <p className="text-sm text-red-500" data-testid="canonical-error">
          Recommendations are temporarily unavailable. Try again shortly.
        </p>
      </Card>
    );
  }

  if (unavailable) {
    const labels = reasonLabels(auth?.reason_codes);
    return (
      <Card data-testid="canonical-primary">
        {header}
        <div data-testid="canonical-unavailable" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-500/40 dark:bg-amber-500/10">
          <p className="font-medium text-amber-700 dark:text-amber-400">
            No authoritative recommendation available.
          </p>
          <p className="mt-1 text-amber-700/80 dark:text-amber-400/80">
            The canonical decision engine could not produce a result
            {labels.length > 0 ? `: ${labels.join("; ")}` : "."}. Legacy lists are shown
            below for diagnostics only and are not recommendations.
          </p>
        </div>
      </Card>
    );
  }

  const actionable = (auth?.actionable ?? []).slice(0, maxItems);
  const watch = auth?.watch ?? [];
  const blocked = auth?.blocked ?? [];
  const cs = data?.capital_safety ?? null;
  const stayCodes = reasonLabels(
    Array.isArray((auth?.stay_in_cash as { reason_codes?: string[] } | null | undefined)?.reason_codes)
      ? (auth?.stay_in_cash as { reason_codes?: string[] }).reason_codes
      : undefined
  );

  return (
    <Card data-testid="canonical-primary">
      {header}
      {cs && <CapitalSafetyBanner cs={cs} />}
      <div className="mt-3 space-y-2" data-testid="canonical-actionable">
        {actionable.length === 0 ? (
          <div data-testid="canonical-stay-in-cash" className="rounded border border-zinc-200 dark:border-zinc-700 p-3 text-sm text-zinc-600 dark:text-zinc-400">
            No actionable recommendations right now — staying in cash is a valid outcome.
            {stayCodes.length > 0 && (
              <p className="mt-1 text-xs text-zinc-500" data-testid="canonical-stay-in-cash-reason">
                Reason: {stayCodes.join("; ")}
              </p>
            )}
          </div>
        ) : (
          actionable.map((item) => (
            <RecRow key={`${item.symbol}-${item.strategy}`} item={item} actions={renderItemActions?.(item)} />
          ))
        )}
      </div>

      {watch.length > 0 && (
        <details className="mt-3" data-testid="canonical-watch">
          <summary className="cursor-pointer text-xs font-medium text-zinc-500">
            Watch ({watch.length})
          </summary>
          <div className="mt-2 space-y-2">
            {watch.slice(0, maxItems).map((item) => (
              <RecRow key={`w-${item.symbol}-${item.strategy}`} item={item} />
            ))}
          </div>
        </details>
      )}

      {blocked.length > 0 && (
        <details className="mt-2" data-testid="canonical-blocked">
          <summary className="cursor-pointer text-xs font-medium text-zinc-500">
            Blocked ({blocked.length})
          </summary>
          <div className="mt-2 space-y-2">
            {blocked.slice(0, maxItems).map((item) => (
              <RecRow key={`b-${item.symbol}-${item.strategy}`} item={item} />
            ))}
          </div>
        </details>
      )}
    </Card>
  );
}
