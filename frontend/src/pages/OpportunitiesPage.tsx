/**
 * R39: Opportunities — CSP / CC / Shares / Watch / Near Miss / Blocked.
 * Backend-driven via action-needed authoritative block + universe-v2 near-misses.
 */
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useActionNeeded, useUiSystemHealth, useUniverseV2NearMisses } from "@/api/queries";
import type { CanonicalLiveItem } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { AuthoritativeRecommendations } from "@/components/AuthoritativeRecommendations";
import { Badge, Card, CardHeader, EmptyState } from "@/components/ui";
import { reasonLabels } from "@/utils/reasonLabels";
import { ExplanationPanel } from "@/components/ExplanationPanel";

function strategyKey(s: string | undefined): string {
  return (s || "").toUpperCase();
}

function OppRow({ item, testIdPrefix }: { item: CanonicalLiveItem; testIdPrefix: string }) {
  const labels = reasonLabels([...(item.reason_codes ?? []), ...(item.risk_flags ?? [])]);
  return (
    <div
      data-testid={`${testIdPrefix}-${item.symbol}`}
      className="rounded border border-zinc-200 p-3 text-sm dark:border-zinc-700"
    >
      <div className="flex items-center justify-between gap-2">
        <Link
          to={`/symbol-diagnostics?symbol=${encodeURIComponent(item.symbol)}`}
          className="font-mono font-semibold text-zinc-800 hover:underline dark:text-zinc-200"
        >
          {item.symbol}
        </Link>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase text-zinc-500">{item.strategy}</span>
          <Badge variant="neutral">{item.next_action_code === "ENTRY" ? "Entry" : item.next_action_code}</Badge>
        </div>
      </div>
      {labels.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {labels.map((l) => (
            <span
              key={l}
              className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
            >
              {l}
            </span>
          ))}
        </div>
      )}
      <ExplanationPanel explanation={item.explanation} />
      <div className="mt-2">
        <Link
          to={`/ticket?symbol=${encodeURIComponent(item.symbol)}&strategy=${encodeURIComponent(strategyKey(item.strategy))}`}
          className="text-xs text-emerald-600 hover:underline dark:text-emerald-400"
        >
          Open ticket →
        </Link>
      </div>
    </div>
  );
}

function Section({
  title,
  testId,
  children,
  empty,
}: {
  title: string;
  testId: string;
  children: ReactNode;
  empty?: boolean;
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader title={title} />
      {empty ? <EmptyState title="None" message="No items in this bucket." /> : <div className="space-y-2">{children}</div>}
    </Card>
  );
}

export function OpportunitiesPage() {
  const { data: actionNeeded, isLoading, isError } = useActionNeeded();
  const { data: health } = useUiSystemHealth();
  const { data: nearMissData } = useUniverseV2NearMisses();

  const auth = actionNeeded?.authoritative_recommendations;
  const actionable = auth?.actionable ?? [];
  const watch = auth?.watch ?? [];
  const blocked = auth?.blocked ?? [];

  const { csp, cc, shares } = useMemo(() => {
    const cspItems: CanonicalLiveItem[] = [];
    const ccItems: CanonicalLiveItem[] = [];
    const sharesItems: CanonicalLiveItem[] = [];
    for (const item of actionable) {
      const s = strategyKey(item.strategy);
      if (s === "CSP") cspItems.push(item);
      else if (s === "CC") ccItems.push(item);
      else if (s === "SHARES" || s === "SHARE") sharesItems.push(item);
      else cspItems.push(item); // unknown strategies still listed under CSP bucket for visibility
    }
    return { csp: cspItems, cc: ccItems, shares: sharesItems };
  }, [actionable]);

  const explanationNearMisses = useMemo(() => {
    const pool = [...actionable, ...watch, ...blocked];
    return pool.filter((item) => item.explanation?.near_miss?.is_near_miss);
  }, [actionable, watch, blocked]);

  const universeNearMisses = nearMissData?.near_misses ?? [];

  return (
    <div className="space-y-6" data-testid="opportunities-page">
      <PageHeader
        title="Opportunities"
        subtext="CSP, covered calls, shares, watch, near miss, and blocked — canonical engine only. Manual execution."
      />

      <AuthoritativeRecommendations
        data={actionNeeded}
        isLoading={isLoading}
        isError={isError}
        providerHealth={{ label: health?.orats?.status, ok: health?.orats?.status === "OK" }}
        maxItems={12}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Section title={`CSP (${csp.length})`} testId="opp-section-csp" empty={csp.length === 0}>
          {csp.map((item) => (
            <OppRow key={`csp-${item.symbol}`} item={item} testIdPrefix="opp-csp" />
          ))}
        </Section>
        <Section title={`Covered calls (${cc.length})`} testId="opp-section-cc" empty={cc.length === 0}>
          {cc.map((item) => (
            <OppRow key={`cc-${item.symbol}`} item={item} testIdPrefix="opp-cc" />
          ))}
        </Section>
        <Section title={`Shares (${shares.length})`} testId="opp-section-shares" empty={shares.length === 0}>
          {shares.map((item) => (
            <OppRow key={`shr-${item.symbol}`} item={item} testIdPrefix="opp-shares" />
          ))}
        </Section>
        <Section title={`Watch (${watch.length})`} testId="opp-section-watch" empty={watch.length === 0}>
          {watch.map((item) => (
            <OppRow key={`w-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-watch" />
          ))}
        </Section>
        <Section
          title={`Near miss (${explanationNearMisses.length + universeNearMisses.length})`}
          testId="opp-section-near-miss"
          empty={explanationNearMisses.length === 0 && universeNearMisses.length === 0}
        >
          {explanationNearMisses.map((item) => (
            <OppRow key={`nm-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-near-miss" />
          ))}
          {universeNearMisses.map((nm) => (
            <div
              key={`uv2-${nm.symbol}`}
              data-testid={`opp-near-miss-uv2-${nm.symbol}`}
              className="rounded border border-zinc-200 p-3 text-sm dark:border-zinc-700"
            >
              <Link
                to={`/symbol-diagnostics?symbol=${encodeURIComponent(nm.symbol)}`}
                className="font-mono font-semibold text-zinc-800 hover:underline dark:text-zinc-200"
              >
                {nm.symbol}
              </Link>
              {nm.reason && (
                <p className="mt-1 text-xs text-zinc-500">
                  {reasonLabels([nm.reason])[0] ?? nm.reason.replace(/_/g, " ")}
                </p>
              )}
            </div>
          ))}
        </Section>
        <Section title={`Blocked (${blocked.length})`} testId="opp-section-blocked" empty={blocked.length === 0}>
          {blocked.map((item) => (
            <OppRow key={`b-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-blocked" />
          ))}
        </Section>
      </div>
    </div>
  );
}
