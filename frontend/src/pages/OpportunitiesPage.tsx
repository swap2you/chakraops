/**
 * R39/R42/R56: Opportunities — Options (CSP/CC), Stocks, ETF/Hedge workspaces.
 * Backend-driven via action-needed authoritative block + universe-v2 near-misses.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useActionNeeded, useUiSystemHealth, useUniverseV2NearMisses } from "@/api/queries";
import type { CanonicalLiveItem } from "@/api/queries";
import { PageHeader } from "@/components/PageHeader";
import { AuthoritativeRecommendations } from "@/components/AuthoritativeRecommendations";
import { Badge, Card, CardHeader, EmptyState } from "@/components/ui";
import { reasonLabels } from "@/utils/reasonLabels";
import { ExplanationPanel } from "@/components/ExplanationPanel";

export type StrategyWorkspace = "options" | "stocks" | "etf-hedge";

const STRATEGY_TABS: Array<{ id: StrategyWorkspace; label: string; hint: string }> = [
  { id: "options", label: "Options", hint: "CSP / Covered calls (wheel)" },
  { id: "stocks", label: "Stocks", hint: "Share entries & manage" },
  { id: "etf-hedge", label: "ETF / Hedge", hint: "Advisory / research" },
];

function parseStrategy(raw: string | null): StrategyWorkspace {
  const v = (raw || "").trim().toLowerCase();
  if (v === "stocks" || v === "shares") return "stocks";
  if (v === "etf-hedge" || v === "etf" || v === "hedge") return "etf-hedge";
  return "options";
}

function strategyKey(s: string | undefined): string {
  return (s || "").toUpperCase();
}

function isSharesStrategy(s: string | undefined): boolean {
  const k = strategyKey(s);
  return k === "SHARES" || k === "SHARE";
}

function isOptionsStrategy(s: string | undefined): boolean {
  const k = strategyKey(s);
  return k === "CSP" || k === "CC" || (!isSharesStrategy(s) && k !== "");
}

function ticketAction(item: CanonicalLiveItem): string {
  const code = (item.next_action_code || "").toUpperCase();
  const s = strategyKey(item.strategy);
  if (code === "ENTRY") return s === "SHARES" || s === "SHARE" ? "BUY" : "OPEN";
  if (code === "CLOSE") return s === "SHARES" || s === "SHARE" ? "SELL" : "CLOSE";
  return "OPEN";
}

function OppRow({ item, testIdPrefix }: { item: CanonicalLiveItem; testIdPrefix: string }) {
  const labels = reasonLabels([...(item.reason_codes ?? []), ...(item.risk_flags ?? [])]);
  const strategy = strategyKey(item.strategy);
  const action = ticketAction(item);
  const asOf = (item as { as_of_utc?: string }).as_of_utc;
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
      {asOf && (
        <p className="mt-1 text-[11px] text-zinc-500" data-testid={`${testIdPrefix}-${item.symbol}-asof`}>
          Source as-of {asOf}
        </p>
      )}
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
      <div className="mt-2 flex flex-wrap gap-3">
        <Link
          to={`/ticket?symbol=${encodeURIComponent(item.symbol)}&strategy=${encodeURIComponent(strategy)}&action=${encodeURIComponent(action)}`}
          className="text-xs text-emerald-600 hover:underline dark:text-emerald-400"
        >
          Open ticket →
        </Link>
        {!isSharesStrategy(item.strategy) && (
          <Link
            to={`/wheel?symbol=${encodeURIComponent(item.symbol)}`}
            className="text-xs text-zinc-600 hover:underline dark:text-zinc-400"
            title="Advanced — wheel admin / CSP vs Shares arbitration"
          >
            CSP vs Shares arbitration →
          </Link>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  testId,
  children,
  empty,
  note,
}: {
  title: string;
  testId: string;
  children: ReactNode;
  empty?: boolean;
  note?: string;
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader title={title} />
      {note && <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">{note}</p>}
      {empty ? <EmptyState title="None" message="No items in this bucket." /> : <div className="space-y-2">{children}</div>}
    </Card>
  );
}

const PROFILES = ["balanced", "conservative", "aggressive"] as const;

export function OpportunitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const workspace = parseStrategy(searchParams.get("strategy"));
  const [profile, setProfile] = useState<string>("balanced");
  const [sortBy, setSortBy] = useState<"symbol" | "strategy">("symbol");
  const { data: actionNeeded, isLoading, isError } = useActionNeeded(profile);
  const { data: health } = useUiSystemHealth();
  const { data: nearMissData } = useUniverseV2NearMisses();

  const setWorkspace = (next: StrategyWorkspace) => {
    const params = new URLSearchParams(searchParams);
    if (next === "options") params.delete("strategy");
    else params.set("strategy", next);
    setSearchParams(params, { replace: true });
  };

  const auth = actionNeeded?.authoritative_recommendations;
  const actionable = auth?.actionable ?? [];
  const watch = auth?.watch ?? [];
  const blocked = auth?.blocked ?? [];

  const { csp, cc, shares, manage } = useMemo(() => {
    const cspItems: CanonicalLiveItem[] = [];
    const ccItems: CanonicalLiveItem[] = [];
    const sharesItems: CanonicalLiveItem[] = [];
    const manageItems: CanonicalLiveItem[] = [];
    const pool = [...actionable, ...watch];
    for (const item of pool) {
      const code = (item.next_action_code || "").toUpperCase();
      if (code === "CLOSE" || code === "ROLL" || code === "MANAGE") {
        manageItems.push(item);
        continue;
      }
      if (!actionable.includes(item)) continue;
      const s = strategyKey(item.strategy);
      if (s === "CSP") cspItems.push(item);
      else if (s === "CC") ccItems.push(item);
      else if (s === "SHARES" || s === "SHARE") sharesItems.push(item);
      else cspItems.push(item);
    }
    const sorter = (a: CanonicalLiveItem, b: CanonicalLiveItem) =>
      sortBy === "strategy"
        ? strategyKey(a.strategy).localeCompare(strategyKey(b.strategy)) || a.symbol.localeCompare(b.symbol)
        : a.symbol.localeCompare(b.symbol);
    return {
      csp: [...cspItems].sort(sorter),
      cc: [...ccItems].sort(sorter),
      shares: [...sharesItems].sort(sorter),
      manage: [...manageItems].sort(sorter),
    };
  }, [actionable, watch, sortBy]);

  const explanationNearMisses = useMemo(() => {
    const pool = [...actionable, ...watch, ...blocked];
    return pool.filter((item) => item.explanation?.near_miss?.is_near_miss);
  }, [actionable, watch, blocked]);

  const universeNearMisses = nearMissData?.near_misses ?? [];

  const manageForWorkspace = useMemo(() => {
    if (workspace === "options") return manage.filter((i) => isOptionsStrategy(i.strategy) && !isSharesStrategy(i.strategy));
    if (workspace === "stocks") return manage.filter((i) => isSharesStrategy(i.strategy));
    return [];
  }, [manage, workspace]);

  const watchForWorkspace = useMemo(() => {
    if (workspace === "options") return watch.filter((i) => !isSharesStrategy(i.strategy));
    if (workspace === "stocks") return watch.filter((i) => isSharesStrategy(i.strategy));
    return [];
  }, [watch, workspace]);

  const blockedForWorkspace = useMemo(() => {
    if (workspace === "options") return blocked.filter((i) => !isSharesStrategy(i.strategy));
    if (workspace === "stocks") return blocked.filter((i) => isSharesStrategy(i.strategy));
    return [];
  }, [blocked, workspace]);

  const nearMissForWorkspace = useMemo(() => {
    if (workspace === "options") return explanationNearMisses.filter((i) => !isSharesStrategy(i.strategy));
    if (workspace === "stocks") return explanationNearMisses.filter((i) => isSharesStrategy(i.strategy));
    return [];
  }, [explanationNearMisses, workspace]);

  const activeTab = STRATEGY_TABS.find((t) => t.id === workspace) ?? STRATEGY_TABS[0];

  return (
    <div className="space-y-6" data-testid="opportunities-page">
      <PageHeader
        title="Opportunities"
        subtext="Strategy workspaces: Options (CSP/CC), Stocks, and ETF/Hedge. Canonical engine only · manual execution. Near Miss / Blocked are not approval."
      />

      <div
        role="tablist"
        aria-label="Strategy workspace"
        className="flex flex-wrap gap-1 rounded-lg border border-zinc-200 bg-zinc-50/80 p-1 dark:border-zinc-700 dark:bg-zinc-900/50"
        data-testid="opp-strategy-tabs"
      >
        {STRATEGY_TABS.map((tab) => {
          const selected = tab.id === workspace;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              data-testid={`opp-tab-${tab.id}`}
              onClick={() => setWorkspace(tab.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                selected
                  ? "bg-white text-emerald-700 shadow-sm dark:bg-zinc-800 dark:text-emerald-300"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-zinc-500 dark:text-zinc-400" data-testid="opp-workspace-hint">
        {activeTab.hint}
        {workspace === "options" && " · Wheel admin tools remain under Advanced"}
      </p>

      <div className="flex flex-wrap items-center gap-3 text-sm" data-testid="opp-filters">
        <label className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Profile</span>
          <select
            data-testid="opp-profile-filter"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            className="rounded border border-zinc-200 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          >
            {PROFILES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Sort</span>
          <select
            data-testid="opp-sort"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "symbol" | "strategy")}
            className="rounded border border-zinc-200 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="symbol">Symbol</option>
            <option value="strategy">Strategy</option>
          </select>
        </label>
        <span className="text-xs text-zinc-500">
          Active: {actionNeeded?.active_profile ?? profile} · as-of {auth?.as_of_utc ?? "—"}
        </span>
      </div>

      {workspace !== "etf-hedge" && (
        <AuthoritativeRecommendations
          data={actionNeeded}
          isLoading={isLoading}
          isError={isError}
          providerHealth={{ label: health?.orats?.status, ok: health?.orats?.status === "OK" }}
          maxItems={12}
        />
      )}

      {workspace === "etf-hedge" ? (
        <Card data-testid="opp-section-etf-hedge">
          <CardHeader title="ETF / Hedge — advisory" />
          <EmptyState
            title="Optimizer not shipped yet"
            message="ETF / Hedge is research-oriented in R56. No full hedge optimizer or dedicated opportunity feed exists yet — use Universe and Symbol Diagnostics for research. This workspace is intentional empty, not an error."
          />
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <Link to="/universe" className="text-emerald-600 hover:underline dark:text-emerald-400">
              Open Universe →
            </Link>
            <Link to="/symbol-diagnostics" className="text-emerald-600 hover:underline dark:text-emerald-400">
              Symbol Diagnostics →
            </Link>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2" data-testid={`opp-workspace-${workspace}`}>
          {workspace === "options" && (
            <>
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
            </>
          )}
          {workspace === "stocks" && (
            <Section title={`Shares (${shares.length})`} testId="opp-section-shares" empty={shares.length === 0}>
              {shares.map((item) => (
                <OppRow key={`shr-${item.symbol}`} item={item} testIdPrefix="opp-shares" />
              ))}
            </Section>
          )}
          <Section
            title={`Manage (${manageForWorkspace.length})`}
            testId="opp-section-manage"
            empty={manageForWorkspace.length === 0}
            note="Close / roll / manage — not new entries."
          >
            {manageForWorkspace.map((item) => (
              <OppRow key={`m-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-manage" />
            ))}
          </Section>
          <Section
            title={`Watch (${watchForWorkspace.length})`}
            testId="opp-section-watch"
            empty={watchForWorkspace.length === 0}
          >
            {watchForWorkspace.map((item) => (
              <OppRow key={`w-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-watch" />
            ))}
          </Section>
          <Section
            title={`Near miss (${nearMissForWorkspace.length + (workspace === "options" ? universeNearMisses.length : 0)})`}
            testId="opp-section-near-miss"
            empty={nearMissForWorkspace.length === 0 && !(workspace === "options" && universeNearMisses.length > 0)}
            note="Near Miss is not approval — safety gates still apply."
          >
            {nearMissForWorkspace.map((item) => (
              <OppRow key={`nm-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-near-miss" />
            ))}
            {workspace === "options" &&
              universeNearMisses.map((nm) => (
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
          <Section
            title={`Blocked (${blockedForWorkspace.length})`}
            testId="opp-section-blocked"
            empty={blockedForWorkspace.length === 0}
            note="Blocked is not actionable."
          >
            {blockedForWorkspace.map((item) => (
              <OppRow key={`b-${item.symbol}-${item.strategy}`} item={item} testIdPrefix="opp-blocked" />
            ))}
          </Section>
        </div>
      )}
    </div>
  );
}
