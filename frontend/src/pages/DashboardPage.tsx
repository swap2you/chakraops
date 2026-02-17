import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Activity, Droplets, Zap, Info } from "lucide-react";
import { useArtifactList, useDecision, useUniverse, useUiSystemHealth, useUiTrackedPositions, useRunEval } from "@/api/queries";
import type { DecisionMode, SymbolEvalSummary, UniverseSymbol } from "@/api/types";
import { PageHeader } from "@/components/PageHeader";
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

/** Phase 8.5: Display timestamps in ET. */
function fmtTs(s: string | null | undefined): string {
  if (!s) return "n/a";
  try {
    const d = new Date(s);
    return d.toLocaleString(undefined, {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }) + " ET";
  } catch {
    return String(s ?? "n/a");
  }
}

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
  const { data: decision } = useDecision(mode, filename);
  const { data: universe } = useUniverse();
  const { data: health } = useUiSystemHealth();
  const { data: positionsRes } = useUiTrackedPositions();
  const runEval = useRunEval();

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
  const positions = positionsRes?.positions ?? [];
  const openPositions = positions.filter((p) => (p.status ?? "").toUpperCase() === "OPEN" || (p.status ?? "").toUpperCase() === "PARTIAL_EXIT");
  const capitalDeployed = openPositions.reduce((sum, p) => sum + (p.notional ?? 0), 0);

  const isReady = !!decision;
  const metadata = decision?.artifact?.metadata;
  const marketPhase = health?.market?.phase ?? "n/a";
  const oratsStatus = health?.orats?.status ?? "n/a";
  const lastEvalTs = metadata?.pipeline_timestamp ?? health?.market?.timestamp;

  return (
    <div className="space-y-8">
      <PageHeader title="Command Center" subtext={isReady ? "Mode, market, and evaluation status" : "AI trading command center"} />
      {!isReady ? (
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
        <button
          type="button"
          disabled={runEval.isPending}
          onClick={() => runEval.mutate({ mode: "LIVE" })}
          className="rounded border border-emerald-600 bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {runEval.isPending ? "Running…" : "Run Evaluation"}
        </button>
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
              <span className={`font-mono text-base font-medium ${evalFreshnessColor(lastEvalTs)}`}>{fmtTs(lastEvalTs)}</span>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">ORATS</span>
              <StatusBadge status={oratsStatus} />
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

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <section role="region" aria-label="Decision" className="space-y-8 lg:col-span-2">
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
        </section>
        <section role="region" aria-label="Trade plan" className="space-y-6">
          <StatCard
            label="Open positions"
            value={openPositions.length}
            badge={positions.length > 0 ? <span className="text-xs text-zinc-500 dark:text-zinc-500">{positions.length} total</span> : undefined}
          />
          <StatCard label="Capital deployed" value={`$${capitalDeployed.toLocaleString()}`} />
          <Card>
            <CardHeader title="Data freshness" />
            <p className="font-mono text-sm text-zinc-700 dark:text-zinc-300">{health?.orats?.status ?? "n/a"}</p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
              {health?.orats?.last_success_at ? fmtTs(health.orats.last_success_at) : "n/a"}
            </p>
          </Card>
          <Card>
            <CardHeader title="Positions" />
            {positions.length === 0 ? (
              <EmptyState title="No positions" message="Tracked positions will appear here." />
            ) : (
              <div className="space-y-1.5">
                {positions.slice(0, 5).map((p, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <Link
                      to={`/symbol-diagnostics?symbol=${encodeURIComponent(p.symbol)}`}
                      className="font-mono text-zinc-700 hover:underline dark:text-zinc-300 dark:hover:text-zinc-100"
                    >
                      {p.symbol}
                    </Link>
                    <span className="font-mono text-zinc-500 dark:text-zinc-500">
                      {p.contracts != null ? `${p.contracts}×` : p.qty != null ? `${p.qty}` : ""}{" "}
                      {p.notional != null ? `$${p.notional.toLocaleString()}` : ""}
                    </span>
                  </div>
                ))}
                {positions.length > 5 && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-500">+{positions.length - 5} more</p>
                )}
              </div>
            )}
          </Card>
        </section>
      </div>

      <Card>
        <CardHeader title="System health" />
        <div className="flex flex-wrap gap-6 text-sm">
          <div className="flex items-center gap-2">
            <Activity className={health?.api?.status === "OK" ? "h-4 w-4 text-emerald-500 dark:text-emerald-400" : "h-4 w-4 text-red-500 dark:text-red-400"} />
            <span className="text-zinc-500 dark:text-zinc-500">API</span>
            <StatusBadge status={health?.api?.status ?? "n/a"} />
            {health?.api?.latency_ms != null && (
              <span className="text-zinc-500 dark:text-zinc-500">{health.api.latency_ms}ms</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Droplets
              className={
                health?.orats?.status === "OK"
                  ? "h-4 w-4 text-emerald-500 dark:text-emerald-400"
                  : health?.orats?.status === "WARN"
                    ? "h-4 w-4 text-amber-500 dark:text-amber-400"
                    : "h-4 w-4 text-zinc-500 dark:text-zinc-500"
              }
            />
            <span className="text-zinc-500 dark:text-zinc-500">ORATS</span>
            <StatusBadge status={health?.orats?.status ?? "n/a"} />
          </div>
          <div className="flex items-center gap-2">
            <Zap className={health?.market?.is_open ? "h-4 w-4 text-emerald-500 dark:text-emerald-400" : "h-4 w-4 text-zinc-500 dark:text-zinc-500"} />
            <span className="text-zinc-500 dark:text-zinc-500">Market</span>
            <span className="text-zinc-700 dark:text-zinc-400">{health?.market?.phase ?? "n/a"}</span>
          </div>
        </div>
      </Card>
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
