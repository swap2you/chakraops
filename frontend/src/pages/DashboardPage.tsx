import { useState, useMemo } from "react";
import { formatTimestampEt } from "@/utils/formatTimestamp";
import { Link } from "react-router-dom";
import { ExternalLink, Activity, Droplets, Zap, Info, Settings, Bell } from "lucide-react";
import { useArtifactList, useDecision, useUniverse, useUiSystemHealth, useUnifiedPositionsFromDb, usePortfolio, usePortfolioMtm, useDefaultAccount, useRunEval, useSharesCandidates, useActionNeeded, useNotifications } from "@/api/queries";
import type { DecisionMode, SymbolEvalSummary, UniverseSymbol } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
import { AuthoritativeRecommendations } from "@/components/AuthoritativeRecommendations";
import { constraintToLabel } from "@/utils/sizingConstraints";
import { reasonLabels } from "@/utils/reasonLabels";
import {
  Card,
  CardHeader,
  StatCard,
  Badge,
  Button,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  EmptyState,
  StatusBadge,
  Tooltip,
} from "@/components/ui";

/** Format score_breakdown for tooltip. Phase 7.7 trust feature. */
function formatScoreBreakdown(bd: unknown): string {
  if (bd == null || typeof bd !== "object") return "";
  const o = bd as Record<string, unknown>;
  const parts: string[] = [];
  if (typeof o.stage1_score === "number") parts.push(`Stage1: ${o.stage1_score}`);
  if (typeof o.stage2_score === "number") parts.push(`Stage2: ${o.stage2_score}`);
  if (o.components && typeof o.components === "object") {
    const comp = o.components as Record<string, unknown>;
    Object.entries(comp).forEach(([k, v]) => {
      if (typeof v === "number") parts.push(`${k}: ${v}`);
    });
  }
  const dq = typeof o.data_quality_score === "number" ? o.data_quality_score : null;
  const reg = typeof o.regime_score === "number" ? o.regime_score : null;
  const liq = typeof o.options_liquidity_score === "number" ? o.options_liquidity_score : null;
  const fit = typeof o.strategy_fit_score === "number" ? o.strategy_fit_score : null;
  const cap = typeof o.capital_efficiency_score === "number" ? o.capital_efficiency_score : null;
  const comp = typeof o.composite_score === "number" ? o.composite_score : null;
  if (parts.length === 0 && (dq != null || reg != null || liq != null || fit != null || cap != null || comp != null)) {
    if (dq != null) parts.push(`Data: ${dq}`);
    if (reg != null) parts.push(`Regime: ${reg}`);
    if (liq != null) parts.push(`Liquidity: ${liq}`);
    if (fit != null) parts.push(`Strategy: ${fit}`);
    if (cap != null) parts.push(`Capital: ${cap}`);
    if (comp != null) parts.push(`Composite: ${comp}`);
  }
  const caps = o.caps_applied;
  if (Array.isArray(caps) && caps.length > 0) parts.push(`Caps: ${(caps as string[]).join(", ")}`);
  else if (typeof caps === "string") parts.push(`Caps: ${caps}`);
  // raw_score / final_score / score_caps
  const raw = typeof o.raw_score === "number" ? o.raw_score : null;
  const final = typeof o.final_score === "number" ? o.final_score : null;
  const scaps = o.score_caps as { applied_caps?: Array<{ type: string; before: number; after: number; reason: string }> } | undefined;
  if (scaps?.applied_caps?.length) {
    const c = scaps.applied_caps[0];
    parts.push(`Raw: ${raw ?? c.before} → Final: ${final ?? c.after} (${c.reason})`);
  } else if (raw != null && final != null && raw !== final) {
    parts.push(`Raw: ${raw}, Final: ${final}`);
  } else if (raw != null) {
    parts.push(`Raw: ${raw}`);
  }
  return parts.length ? parts.join(" · ") : "";
}

function evalFreshnessColor(ts: string | null | undefined): string {
  if (!ts) return "text-zinc-500 dark:text-zinc-400";
  try {
    const d = new Date(ts);
    const now = Date.now();
    const ageHours = (now - d.getTime()) / (1000 * 60 * 60);
    if (ageHours < 2) return "text-emerald-600 dark:text-emerald-400";
    if (ageHours < 6) return "text-amber-600 dark:text-amber-400";
    return "text-red-600 dark:text-red-400";
  } catch {
    return "text-zinc-500 dark:text-zinc-400";
  }
}

export function DashboardPage() {
  const [mode, setMode] = useState<DecisionMode>("LIVE");
  const [filename, setFilename] = useState<string>("decision_latest.json");

  const { data: files } = useArtifactList(mode);
  const { data: decision, isLoading: decisionLoading, isError: decisionError, refetch: refetchDecision } = useDecision(mode, filename);
  const { data: universe } = useUniverse();
  const { data: health, isError: healthError } = useUiSystemHealth();
  const { data: unifiedDb } = useUnifiedPositionsFromDb({ state: "open", include_paper: false });
  const { data: portfolioData } = usePortfolio();
  const { data: defaultAccount } = useDefaultAccount();
  const accountId = (defaultAccount?.account as { account_id?: string })?.account_id ?? null;
  const { data: mtmData } = usePortfolioMtm(accountId);
  const runEval = useRunEval();
  const { data: sharesCandidatesData } = useSharesCandidates();
  const sharesCandidates = sharesCandidatesData?.shares_candidates ?? [];
  const { data: actionNeeded, isLoading: actionNeededLoading, isError: actionNeededError } = useActionNeeded();
  const { data: notifData } = useNotifications(20, "NEW");
  const newAlerts = notifData?.notifications ?? [];

  const auth = actionNeeded?.authoritative_recommendations;
  const oppCounts = {
    actionable: auth?.actionable?.length ?? 0,
    watch: auth?.watch?.length ?? 0,
    blocked: auth?.blocked?.length ?? 0,
  };
  const stayReasons = reasonLabels(
    Array.isArray((auth?.stay_in_cash as { reason_codes?: string[] } | null)?.reason_codes)
      ? (auth?.stay_in_cash as { reason_codes?: string[] }).reason_codes
      : undefined
  );
  const manageNeeded = useMemo(() => {
    const items = [...(actionNeeded?.top_options ?? []), ...(actionNeeded?.top_shares ?? [])];
    return items.filter((i) => {
      const code = (i.next_action_code || "").toUpperCase();
      return code === "CLOSE" || code === "ROLL" || code === "MANAGE";
    }).length;
  }, [actionNeeded]);
  const portfolioAsOf =
    (portfolioData as { as_of?: string; updated_at?: string } | undefined)?.as_of ||
    (portfolioData as { updated_at?: string } | undefined)?.updated_at ||
    (mtmData as { as_of?: string } | undefined)?.as_of ||
    null;
  const portfolioSourceLabel =
    (defaultAccount as { source?: string } | undefined)?.source ||
    (portfolioData as { source?: string } | undefined)?.source ||
    "manual trusted snapshot";

  const { universeSymbols, selectedSignals } = useMemo(() => {
    const artifact = decision?.artifact;
    if (decision?.artifact_version === "v2" && artifact?.symbols) {
      return {
        universeSymbols: artifact.symbols,
        selectedSignals: (artifact.selected_candidates ?? []).map((c) => ({
          symbol: c.symbol,
          verdict: "ELIGIBLE",
          candidate: c,
        })),
      };
    }
    // v2 only: use universe from API (same v2 store) or empty
    const symbols = universe?.symbols ?? [];
    const selected = (artifact?.selected_candidates ?? []).map((c) => ({
      symbol: c.symbol,
      verdict: "ELIGIBLE" as const,
      candidate: c,
    }));
    return {
      universeSymbols: symbols as SymbolEvalSummary[],
      selectedSignals: selected,
    };
  }, [universe?.symbols, decision]);

  const selectedBySymbol = new Map(
    selectedSignals.map((s) => [s.symbol.toUpperCase(), (s.candidate as { strategy?: string })?.strategy ?? "n/a"])
  );
  const aTier = universeSymbols.filter(
    (s) => (s.band ?? "").toUpperCase() === "A" && ((s.final_verdict ?? s.verdict ?? "").toUpperCase() === "ELIGIBLE")
  );
  const bTier = universeSymbols.filter(
    (s) => (s.band ?? "").toUpperCase() === "B" && ((s.final_verdict ?? s.verdict ?? "").toUpperCase() === "ELIGIBLE")
  );
  const eligibleFromDecision = selectedSignals.length > 0 && aTier.length === 0 && bTier.length === 0;
  const positions = unifiedDb?.items ?? [];
  const openPositions = positions; // already open-state query
  const capitalDeployed = portfolioData?.capital_deployed ?? 0;

  const isReady = !!decision;
  const backendOutage = decisionError || (healthError && !decision && !decisionLoading);
  const metadata = decision?.artifact?.metadata;
  const marketPhase = health?.market?.phase ?? "n/a";
  const oratsStatus = health?.orats?.status ?? "n/a";
  const lastEvalTs = (decision as { evaluation_timestamp_utc?: string } | undefined)?.evaluation_timestamp_utc
    ?? health?.decision_store?.evaluation_timestamp_utc
    ?? metadata?.pipeline_timestamp
    ?? health?.market?.timestamp;

  return (
    <div className="space-y-8" data-testid="page-command-center">
      <PageHeader
        title="Command Center"
        subtext={
          backendOutage
            ? "Backend unavailable — decision surface cannot load"
            : isReady
            ? "Today’s actions, positions, cash/collateral, data health, Stay in Cash, and alerts — manual execution only"
            : "Loading daily command surface…"
        }
      />
      {backendOutage ? (
        <Card data-testid="command-center-outage">
          <div className="space-y-3 text-sm">
            <p className="text-red-600 dark:text-red-400">
              Unable to reach the decision API. Risk and recommendations are unavailable — not PASS.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void refetchDecision();
              }}
            >
              Retry
            </Button>
          </div>
        </Card>
      ) : !isReady ? (
        <Card>
          <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-zinc-400" />
            Loading decision and health…
          </div>
        </Card>
      ) : (
        <>
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as DecisionMode)}
          className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
        >
          <option value="LIVE">LIVE</option>
          <option value="MOCK">MOCK</option>
        </select>
        <select
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          className="rounded border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
        >
          {(files?.files ?? []).map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
        <Tooltip content={marketPhase !== "OPEN" ? "Market closed: evaluation disabled to protect canonical decision. Use System Diagnostics or force=true to override." : undefined}>
          <span className="inline-block">
            <button
              type="button"
              disabled={runEval.isPending || (marketPhase !== "OPEN" && marketPhase !== "UNKNOWN")}
              onClick={() => runEval.mutate({ mode: "LIVE" })}
              className="rounded border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {runEval.isPending ? "Running…" : "Run Evaluation"}
            </button>
          </span>
        </Tooltip>
      </div>

      <section role="region" aria-label="Daily overview">
        <Card>
          <CardHeader title="Status" />
          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Mode</span>
              <span className="font-mono font-medium text-zinc-900 dark:text-zinc-200">{mode}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Market</span>
              <span className="font-mono text-zinc-700 dark:text-zinc-300">{marketPhase}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Last evaluation</span>
              <span className={`font-mono text-base font-medium ${evalFreshnessColor(lastEvalTs)}`}>{formatTimestampEt(lastEvalTs)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">ORATS</span>
              <StatusBadge status={oratsStatus} />
            </div>
            {health?.orats?.orats_freshness_state_label && (
              <div data-testid="command-center-orats-freshness">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">ORATS freshness</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">
                  {health.orats.orats_freshness_state_label}
                  {health.orats.orats_as_of ? ` · as-of ${formatTimestampEt(health.orats.orats_as_of)}` : ""}
                </span>
              </div>
            )}
            <div data-testid="command-center-calc-timestamp">
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Decision / calc as-of</span>
              <span className={`font-mono text-base font-medium ${evalFreshnessColor(lastEvalTs)}`}>
                {formatTimestampEt(lastEvalTs)}
              </span>
            </div>
            {health?.api?.latency_ms != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">API latency</span>
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{health.api.latency_ms}ms</span>
              </div>
            )}
          </div>
        </Card>
      </section>

      {/* R39: daily surface links + opportunities / alerts summary */}
      <section role="region" aria-label="Command center actions" className="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="command-center-summary">
        <Card>
          <CardHeader title="Actions today" />
          <div className="space-y-2 text-sm">
            <p className="text-zinc-600 dark:text-zinc-400">
              {oppCounts.actionable > 0
                ? `${oppCounts.actionable} actionable recommendation${oppCounts.actionable === 1 ? "" : "s"}`
                : "No actionable items — staying in cash is valid"}
            </p>
            <div className="flex flex-wrap gap-3 text-xs">
              <Link to="/today" className="text-emerald-600 hover:underline dark:text-emerald-400">
                Today checklist →
              </Link>
              <Link to="/ticket" className="text-emerald-600 hover:underline dark:text-emerald-400">
                Trade Ticket →
              </Link>
              <Link to="/positions" className="text-emerald-600 hover:underline dark:text-emerald-400">
                Manage positions →
              </Link>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400" data-testid="command-center-manage-needed">
              Positions needing management: {manageNeeded}
            </p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400" data-testid="command-center-portfolio-freshness">
              Portfolio: {portfolioSourceLabel}
              {portfolioAsOf ? ` · ${formatTimestampEt(portfolioAsOf)}` : " · as-of unknown"}
            </p>
          </div>
        </Card>
        <Card data-testid="command-center-opportunities-summary">
          <CardHeader
            title="Opportunities"
            actions={
              <Link to="/opportunities" className="text-xs text-emerald-600 hover:underline dark:text-emerald-400">
                View all →
              </Link>
            }
          />
          <div className="flex flex-wrap gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500">Actionable</span>
              <span className="font-mono font-medium">{oppCounts.actionable}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">Watch</span>
              <span className="font-mono font-medium">{oppCounts.watch}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500">Blocked</span>
              <span className="font-mono font-medium">{oppCounts.blocked}</span>
            </div>
          </div>
          {oppCounts.actionable === 0 && (
            <div className="mt-2 rounded border border-zinc-200 p-2 text-xs text-zinc-600 dark:border-zinc-700 dark:text-zinc-400" data-testid="command-center-stay-in-cash">
              Stay in Cash
              {stayReasons.length > 0 ? `: ${stayReasons.join("; ")}` : " — no actionable candidates right now."}
            </div>
          )}
        </Card>
        <Card data-testid="command-center-alerts">
          <CardHeader
            title="Alerts"
            actions={
              <Link to="/notifications" className="inline-flex items-center gap-1 text-xs text-emerald-600 hover:underline dark:text-emerald-400">
                <Bell className="h-3 w-3" />
                Inbox →
              </Link>
            }
          />
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            {newAlerts.length === 0
              ? "No new alerts."
              : `${newAlerts.length} new notification${newAlerts.length === 1 ? "" : "s"}`}
          </p>
          {newAlerts.slice(0, 3).map((n, i) => (
            <p key={n.id ?? `alert-${i}`} className="mt-1 truncate text-xs text-zinc-500">
              {n.symbol ?? "—"} · {n.type ?? "alert"}
            </p>
          ))}
        </Card>
      </section>

      {mode === "MOCK" && (
        <div data-testid="mock-artifact-banner" className="rounded border border-amber-500/50 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">
          Artifact browser (non-live). MOCK mode is forensics only — not a live recommendation.
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <section role="region" aria-label="Decision" className="space-y-8 lg:col-span-2">
          {/* R34.0 / R36.3: canonical authoritative recommendation is PRIMARY (left column). */}
          <AuthoritativeRecommendations
            data={actionNeeded}
            isLoading={actionNeededLoading}
            isError={actionNeededError}
            providerHealth={{ label: health?.orats?.status, ok: health?.orats?.status === "OK" }}
            maxItems={5}
          />
          <p className="text-xs text-zinc-500">
            Full CSP / CC / Shares / Watch / Near Miss / Blocked buckets:{" "}
            <Link to="/opportunities" className="text-emerald-600 hover:underline dark:text-emerald-400">
              Opportunities
            </Link>
          </p>
          {/* R34.0 / R36.3: legacy options/shares lists and tier panels are NON-authoritative diagnostics only. */}
          <details data-testid="legacy-diagnostics">
            <summary className="cursor-pointer text-sm font-medium text-zinc-500 dark:text-zinc-400">
              Diagnostics — non-authoritative legacy output
            </summary>
            <div className="mt-2 space-y-4">
              {aTier.length === 0 && bTier.length === 0 && selectedSignals.length === 0 ? (
                <Card>
                  <EmptyState title="No eligible opportunities" message="No eligible opportunities in current run." />
                </Card>
              ) : (
                <>
                  <CandidatePanel title="A-tier candidates" rows={aTier} selectedBySymbol={selectedBySymbol} />
                  <CandidatePanel title="B-tier candidates" rows={bTier} selectedBySymbol={selectedBySymbol} />
                  {eligibleFromDecision && (
                    <CandidatePanel
                      title="Eligible candidates"
                      rows={selectedSignals.map((s) => ({ symbol: s.symbol, verdict: s.verdict, final_verdict: s.verdict } as UniverseSymbol))}
                      selectedBySymbol={selectedBySymbol}
                    />
                  )}
                </>
              )}
              {/* R24.1/R24.2: Action Needed — GET /api/ui/action-needed; sorted by severity; safe labels only */}
              <Card data-testid="action-needed-card">
                <CardHeader title="Action Needed (legacy diagnostics)" description="Non-authoritative. Superseded by the canonical recommendations above." />
                <div className="space-y-4">
                  <div>
                    <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-500 mb-2">Options</span>
                    {(!actionNeeded?.top_options?.length) ? (
                      <p className="text-xs text-zinc-500 dark:text-zinc-500">No options actions.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {(actionNeeded.top_options.slice(0, 5)).map((item) => {
                          const href = `/symbol-diagnostics?symbol=${encodeURIComponent(item.symbol)}&tab=Options${item.accordion_id ? `&accordion=${encodeURIComponent(item.accordion_id)}` : ""}`;
                          const actionLabel = item.next_action_code === "ENTRY" ? "Entry" : item.next_action_code === "CLOSE" ? "Close" : item.next_action_code === "ROLL" ? "Roll" : item.next_action_code === "HOLD" ? "Hold" : item.next_action_code;
                          const recommendLabel = item.recommended_action_code === "CLOSE" ? "Close" : item.recommended_action_code === "ROLL" ? "Roll" : item.recommended_action_code === "HOLD" ? "Hold" : item.recommended_action_code;
                          const rollReasonLabel = (item.roll_reason_codes?.includes("DTE_WINDOW") && item.recommended_action_code === "ROLL") ? "DTE window" : null;
                          const ticketHref = `/ticket?symbol=${encodeURIComponent(item.symbol)}&strategy=${encodeURIComponent((item.strategy || "CSP").toUpperCase())}&action=${encodeURIComponent(item.next_action_code === "ENTRY" ? "OPEN" : item.next_action_code === "CLOSE" ? "CLOSE" : "OPEN")}`;
                          return (
                            <div key={`opt-${item.symbol}`} className="rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/50 flex items-center justify-between gap-2">
                            <Link to={href} className="flex-1 min-w-0" data-testid={`action-needed-options-row-${item.symbol}`}>
                              <span className="font-mono font-medium text-zinc-800 dark:text-zinc-200">{item.symbol}</span>
                              <Badge variant={item.next_action_code === "ENTRY" ? "success" : item.next_action_code === "CLOSE" ? "danger" : "neutral"} className="ml-2">
                                {actionLabel}
                              </Badge>
                              {item.severity && item.severity !== "low" && (
                                <span className="ml-1.5 text-zinc-500 dark:text-zinc-500" data-testid={`action-needed-severity-${item.symbol}`}>
                                  ({item.severity})
                                </span>
                              )}
                              {(item.dte != null || item.strike != null) && (
                                <span className="ml-1.5 text-zinc-500 dark:text-zinc-500">
                                  {item.dte != null && `DTE ${item.dte}`}
                                  {item.dte != null && item.strike != null && " · "}
                                  {item.strike != null && `$${item.strike}`}
                                </span>
                              )}
                              {(item.rationale_lines?.[0]) && (
                                <p className="mt-1 text-zinc-600 dark:text-zinc-400 truncate">{item.rationale_lines[0]}</p>
                              )}
                              {/* R26.0: ENTRY sizing — size, notional, constraints (safe labels only) */}
                              {item.next_action_code === "ENTRY" && item.sizing_recommended_by === "r260" && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500" data-testid={`action-needed-sizing-${item.symbol}`}>
                                  {item.recommended_contracts != null && item.recommended_contracts > 0 && (
                                    <>Size: {item.recommended_contracts} contracts</>
                                  )}
                                  {item.recommended_qty != null && item.recommended_qty > 0 && (
                                    <>Size: {item.recommended_qty} shares</>
                                  )}
                                  {item.recommended_notional_usd != null && item.recommended_notional_usd > 0 && (
                                    <> · Notional: ${item.recommended_notional_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</>
                                  )}
                                  {(item.sizing_constraints_hit?.length ?? 0) > 0 && (
                                    <> · Constraints: {item.sizing_constraints_hit!.map((c) => constraintToLabel(c)).join(", ")}</>
                                  )}
                                </p>
                              )}
                              {/* R26.1: CSP advisory — cash-secured, risk proxy (safe labels only) */}
                              {item.next_action_code === "ENTRY" && (item.cash_secured_available_usd != null || item.csp_risk_proxy_move_pct != null) && (
                                <div className="mt-0.5 text-zinc-500 dark:text-zinc-500 text-xs" data-testid={`action-needed-csp-advisory-${item.symbol}`}>
                                  {item.cash_secured_available_usd != null && (
                                    <p>Cash-secured available: ${item.cash_secured_available_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                                  )}
                                  {item.csp_risk_proxy_move_pct != null && (
                                    <p>Risk proxy move: {item.csp_risk_proxy_move_pct}%</p>
                                  )}
                                  {item.csp_risk_proxy_loss_per_contract_usd != null && (
                                    <p>Risk proxy loss (per contract): ${item.csp_risk_proxy_loss_per_contract_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
                                  )}
                                  {item.csp_risk_proxy_cap_contracts != null && (
                                    <p>Risk proxy cap: {item.csp_risk_proxy_cap_contracts} contracts{item.csp_risk_proxy_enforced ? " (enforced)" : ""}</p>
                                  )}
                                </div>
                              )}
                              {item.key_number != null && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500">Key: {item.key_number}</p>
                              )}
                              {item.mark_value != null && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500" data-testid={`action-needed-mark-${item.symbol}`}>
                                  Mark: {item.mark_value}
                                  {item.mark_source && ` (${item.mark_source}${item.mark_age_sec != null ? `, ${item.mark_age_sec}s old` : ""})`}
                                </p>
                              )}
                              {item.pct_max_profit != null && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500" data-testid={`action-needed-pct-profit-${item.symbol}`}>
                                  Max profit: {item.pct_max_profit}%
                                </p>
                              )}
                              {recommendLabel && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500">Recommend: {recommendLabel}</p>
                              )}
                              {rollReasonLabel && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500" data-testid={`action-needed-roll-reason-${item.symbol}`}>Reason: {rollReasonLabel}</p>
                              )}
                            </Link>
                            <Link to={ticketHref} className="shrink-0 text-emerald-600 hover:underline dark:text-emerald-400" data-testid={`action-needed-ticket-${item.symbol}`}>Ticket</Link>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  <div>
                    <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-500 mb-2">Shares</span>
                    {(!actionNeeded?.top_shares?.length) ? (
                      <p className="text-xs text-zinc-500 dark:text-zinc-500">No shares actions.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {(actionNeeded.top_shares.slice(0, 5)).map((item) => {
                          const href = `/symbol-diagnostics?symbol=${encodeURIComponent(item.symbol)}&tab=Shares${item.accordion_id ? `&accordion=${encodeURIComponent(item.accordion_id)}` : ""}`;
                          const actionLabel = item.next_action_code === "ENTRY" ? "Entry" : item.next_action_code === "CLOSE" ? "Close" : item.next_action_code;
                          const ticketHrefShares = `/ticket?symbol=${encodeURIComponent(item.symbol)}&strategy=SHARES&action=${item.next_action_code === "ENTRY" ? "BUY" : item.next_action_code === "CLOSE" ? "SELL" : "BUY"}`;
                          return (
                            <div key={`shr-${item.symbol}`} className="rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/50 flex items-center justify-between gap-2">
                            <Link to={href} className="flex-1 min-w-0" data-testid={`action-needed-shares-row-${item.symbol}`}>
                              <span className="font-mono font-medium text-zinc-800 dark:text-zinc-200">{item.symbol}</span>
                              <Badge variant={item.next_action_code === "ENTRY" ? "success" : item.next_action_code === "CLOSE" ? "danger" : "neutral"} className="ml-2">
                                {actionLabel}
                              </Badge>
                              {item.severity && item.severity !== "low" && (
                                <span className="ml-1.5 text-zinc-500 dark:text-zinc-500">({item.severity})</span>
                              )}
                              {(item.rationale_lines?.[0]) && (
                                <p className="mt-1 text-zinc-600 dark:text-zinc-400 truncate">{item.rationale_lines[0]}</p>
                              )}
                              {/* R26.0: ENTRY sizing for shares */}
                              {item.next_action_code === "ENTRY" && item.sizing_recommended_by === "r260" && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500" data-testid={`action-needed-sizing-${item.symbol}`}>
                                  {item.recommended_qty != null && item.recommended_qty > 0 && (
                                    <>Size: {item.recommended_qty} shares</>
                                  )}
                                  {item.recommended_notional_usd != null && item.recommended_notional_usd > 0 && (
                                    <> · Notional: ${item.recommended_notional_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</>
                                  )}
                                  {(item.sizing_constraints_hit?.length ?? 0) > 0 && (
                                    <> · Constraints: {item.sizing_constraints_hit!.map((c) => constraintToLabel(c)).join(", ")}</>
                                  )}
                                </p>
                              )}
                              {item.key_number != null && (
                                <p className="mt-0.5 text-zinc-500 dark:text-zinc-500">Key: {item.key_number}</p>
                              )}
                            </Link>
                            <Link to={ticketHrefShares} className="shrink-0 text-emerald-600 hover:underline dark:text-emerald-400" data-testid={`action-needed-ticket-${item.symbol}`}>Ticket</Link>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </Card>
              {/* R22.5 / R36.3: Shares candidates demoted into legacy diagnostics */}
              <Card>
                <CardHeader title="Shares candidates" description="Non-authoritative diagnostic — superseded by canonical recommendations." />
                {sharesCandidates.length === 0 ? (
                  <EmptyState title="No shares candidates" message="Symbols with support + regime UP may appear here." />
                ) : (
                  <div className="space-y-2">
                    {sharesCandidates.slice(0, 3).map((plan) => {
                      const codes = plan.reason_codes ?? plan.eligibility_codes ?? [];
                      const primaryReason = codes[0]?.replace(/_/g, " ").toLowerCase() ?? plan.why_recommended ?? "—";
                      const entryStr =
                        plan.entry_zone?.low != null && plan.entry_zone?.high != null
                          ? `${plan.entry_zone.low}–${plan.entry_zone.high}`
                          : "—";
                      return (
                        <Link
                          key={plan.symbol ?? ""}
                          to={`/symbol-diagnostics?symbol=${encodeURIComponent(plan.symbol ?? "")}&tab=Shares`}
                          className="block rounded border border-zinc-200 dark:border-zinc-700 p-2 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono font-medium text-zinc-800 dark:text-zinc-200">{plan.symbol}</span>
                            <StatusBadge status={plan.eligible ? "ELIGIBLE" : "NOT_ELIGIBLE"} />
                          </div>
                          <div className="mt-1 text-zinc-600 dark:text-zinc-400 truncate" title={primaryReason}>
                            {primaryReason}
                          </div>
                          <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0 text-zinc-500 dark:text-zinc-500">
                            {plan.spot != null && <span>Spot {plan.spot}</span>}
                            {entryStr !== "—" && <span>Entry {entryStr}</span>}
                          </div>
                        </Link>
                      );
                    })}
                    {sharesCandidates.length > 3 && (
                      <p className="text-xs text-zinc-500 dark:text-zinc-500">+{sharesCandidates.length - 3} more</p>
                    )}
                  </div>
                )}
              </Card>
            </div>
          </details>
        </section>
        <section role="region" aria-label="Trade plan" className="space-y-6">
          <StatCard
            label="Open positions (live)"
            value={openPositions.length}
            badge={
              <span className="text-xs text-zinc-500 dark:text-zinc-500" data-testid="open-positions-provenance">
                source={unifiedDb?.authority ?? "positions_unified_db"}
                {unifiedDb?.as_of ? ` · as_of ${formatTimestampEt(unifiedDb.as_of)}` : ""}
                {(unifiedDb?.count_expired_excluded ?? 0) > 0
                  ? ` · excluded expired ${unifiedDb?.count_expired_excluded}`
                  : ""}
              </span>
            }
          />
          <StatCard label="Capital deployed" value={`$${capitalDeployed.toLocaleString()}`} />
          {health?.guardrails != null && (
            <Card data-testid="guardrails-card">
              <CardHeader title="Guardrails" />
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status</span>
                  <StatusBadge
                    status={
                      health.guardrails.status === "Blocked"
                        ? "Blocked"
                        : health.guardrails.status === "Advisory"
                          ? "Advisory"
                          : "OK"
                    }
                  />
                </div>
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Cash reserve %</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {health.guardrails.metrics?.cash_reserve_pct ?? "—"}%
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Open options</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {health.guardrails.metrics?.open_options_count ?? "—"} / {health.guardrails.limits?.MAX_OPEN_OPTIONS_POSITIONS ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Open shares</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {health.guardrails.metrics?.open_shares_count ?? "—"} / {health.guardrails.limits?.MAX_OPEN_SHARES_POSITIONS ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Symbols exposure</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {health.guardrails.metrics?.symbols_exposure_count ?? "—"} / {health.guardrails.limits?.MAX_SYMBOLS_EXPOSURE ?? "—"}
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Max symbol notional %</span>
                  <span className="font-mono text-zinc-700 dark:text-zinc-300">
                    {health.guardrails.metrics?.max_symbol_notional_pct ?? "—"}%
                  </span>
                </div>
                {/* R26.0: Available budget (post cash reserve) */}
                {health.guardrails.metrics?.available_budget_usd != null && (
                  <div>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-500">Available budget</span>
                    <span className="font-mono text-zinc-700 dark:text-zinc-300" data-testid="guardrails-available-budget">
                      ${health.guardrails.metrics.available_budget_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                )}
                {/* R26.1: Cash-secured committed and CSP cash available */}
                {health.guardrails.metrics?.cash_secured_committed_usd != null && (
                  <div>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-500">Cash-secured committed</span>
                    <span className="font-mono text-zinc-700 dark:text-zinc-300" data-testid="guardrails-cash-secured-committed">
                      ${health.guardrails.metrics.cash_secured_committed_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                )}
                {health.guardrails.metrics?.csp_cash_available_usd != null && (
                  <div>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-500">CSP cash available</span>
                    <span className="font-mono text-zinc-700 dark:text-zinc-300" data-testid="guardrails-csp-cash-available">
                      ${health.guardrails.metrics.csp_cash_available_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                )}
              </div>
            </Card>
          )}
          {mtmData && (
            <Card>
              <CardHeader title="Net PnL (Phase 15.0)" />
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Realized</span>
                  <span className={`font-mono font-medium ${(mtmData.realized_total ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                    ${(mtmData.realized_total ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Unrealized</span>
                  <span className={`font-mono font-medium ${(mtmData.unrealized_total ?? 0) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                    ${(mtmData.unrealized_total ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            </Card>
          )}
          <Card>
            <CardHeader
              title="Positions"
              actions={
                <Link to="/positions">
                  <Button size="sm" variant="secondary">
                    Manage positions
                    <ExternalLink className="ml-1 h-3 w-3" />
                  </Button>
                </Link>
              }
            />
            {positions.length === 0 ? (
              <EmptyState title="No positions" message="Unified open positions will appear here." />
            ) : (
              <div className="space-y-1.5">
                {positions.slice(0, 5).map((p, i) => (
                  <div key={p.id ?? i} className="flex items-center justify-between text-xs">
                    <Link
                      to={`/symbol-diagnostics?symbol=${encodeURIComponent(p.symbol)}`}
                      className="font-mono text-zinc-700 hover:underline dark:text-zinc-300 dark:hover:text-zinc-100"
                    >
                      {p.symbol}
                    </Link>
                    <span className="font-mono text-zinc-500 dark:text-zinc-500">
                      {p.qty != null ? `${p.qty}` : ""}{" "}
                      {p.avg_price != null ? `$${p.avg_price.toLocaleString()}` : ""}
                    </span>
                  </div>
                ))}
                {positions.length > 5 && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-500">+{positions.length - 5} more</p>
                )}
              </div>
            )}
            {positions.length === 0 && (
              <Link to="/positions" className="mt-2 block text-sm text-emerald-600 hover:underline dark:text-emerald-400">
                Manage positions →
              </Link>
            )}
          </Card>
        </section>
      </div>

      <div className="flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900/50">
        <div className="flex flex-wrap gap-6">
          <span className="flex items-center gap-2">
            <Activity className={health?.api?.status === "OK" ? "h-4 w-4 text-emerald-500" : "h-4 w-4 text-red-500"} />
            <StatusBadge status={health?.api?.status ?? "n/a"} />
          </span>
          <span className="flex items-center gap-2">
            <Droplets className={health?.orats?.status === "OK" ? "h-4 w-4 text-emerald-500" : "h-4 w-4 text-amber-500"} />
            <StatusBadge status={health?.orats?.status ?? "n/a"} />
          </span>
          <span className="flex items-center gap-2">
            <Zap className={health?.market?.is_open ? "h-4 w-4 text-emerald-500" : "h-4 w-4 text-zinc-500"} />
            {health?.market?.phase ?? "n/a"}
          </span>
        </div>
        <Link to="/system" className="flex items-center gap-1 text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
          <Settings className="h-4 w-4" />
          System
        </Link>
      </div>
        </>
      )}
    </div>
  );
}

function CandidatePanel({
  title,
  rows,
  selectedBySymbol,
}: {
  title: string;
  rows: UniverseSymbol[];
  selectedBySymbol: Map<string, string>;
}) {
  return (
    <Card>
      <CardHeader title={title} />
      {rows.length === 0 ? (
        <EmptyState title="None" message="No candidates in this tier." />
      ) : (
        <Table>
          <TableHeader>
            <TableHead>symbol</TableHead>
            <TableHead>verdict</TableHead>
            <TableHead>score</TableHead>
            <TableHead>band</TableHead>
            <TableHead>strategy</TableHead>
            <TableHead className="w-16">{" "}</TableHead>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.symbol}>
                <TableCell>
                  <span className="font-mono font-medium text-zinc-900 dark:text-zinc-200">{row.symbol}</span>
                </TableCell>
                <TableCell>
                  <StatusBadge status={row.final_verdict ?? row.verdict ?? "n/a"} />
                </TableCell>
                <TableCell numeric>
                  <span className="inline-flex items-center gap-1">
                    {row.score ?? "n/a"}
                    {(() => {
                      const rb = row as { score_breakdown?: unknown };
                      const txt = formatScoreBreakdown(rb.score_breakdown);
                      return txt ? (
                        <Tooltip content={`Why this score: ${txt}`} className="max-w-md">
                          <Info className="h-3.5 w-3.5 shrink-0 cursor-help text-zinc-500" />
                        </Tooltip>
                      ) : null;
                    })()}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="inline-flex items-center gap-1">
                    <Badge variant={row.band === "A" ? "success" : row.band === "B" ? "warning" : "neutral"}>
                      {row.band ?? "n/a"}
                    </Badge>
                    {(() => {
                      const rb = row as { band_reason?: string };
                      return rb.band_reason ? (
                        <Tooltip content={`Why this band: ${rb.band_reason}`} className="max-w-md">
                          <Info className="h-3.5 w-3.5 shrink-0 cursor-help text-zinc-500" />
                        </Tooltip>
                      ) : null;
                    })()}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-zinc-700 dark:text-zinc-300">
                  {selectedBySymbol.get(row.symbol.toUpperCase()) ?? "n/a"}
                </TableCell>
                <TableCell>
                  <Link to={`/symbol-diagnostics?symbol=${encodeURIComponent(row.symbol)}`}>
                    <Button size="sm" variant="secondary">
                      Open
                      <ExternalLink className="ml-1 h-3 w-3" />
                    </Button>
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
