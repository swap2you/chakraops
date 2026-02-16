import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, Activity, Droplets, Zap } from "lucide-react";
import { useArtifactList, useDecision, useUniverse, useUiSystemHealth, useUiTrackedPositions } from "@/api/queries";
import type { DecisionMode, UniverseSymbol } from "@/api/types";
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
} from "@/components/ui";

function fmtTs(s: string | null | undefined): string {
  if (!s) return "n/a";
  try {
    const d = new Date(s);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return String(s ?? "n/a");
  }
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

  const mergedBySymbol = useMemo(() => {
    const snapshot = decision?.decision_snapshot;
    const candidates = snapshot?.candidates ?? [];
    const selectedSignals = snapshot?.selected_signals ?? [];
    const map = new Map<string, UniverseSymbol>();
    for (const s of universe?.symbols ?? []) {
      map.set((s.symbol || "").toUpperCase(), { ...s });
    }
    for (const c of candidates) {
      const sym = (c.symbol || "").toUpperCase();
      const existing = map.get(sym) ?? ({ symbol: c.symbol } as UniverseSymbol);
      map.set(sym, {
        ...existing,
        symbol: c.symbol || existing.symbol,
        verdict: c.verdict ?? existing.verdict,
        final_verdict: c.verdict ?? existing.final_verdict,
        score: (c as { score?: number }).score ?? existing.score,
        band: (c as { band?: string }).band ?? existing.band,
        primary_reason: (c as { primary_reason?: string }).primary_reason ?? existing.primary_reason,
        expiration: c.candidate?.expiry ? String(c.candidate.expiry).slice(0, 10) : existing.expiration,
        price: (c.candidate as { price?: number })?.price ?? existing.price,
      });
    }
    for (const ss of selectedSignals) {
      const sym = (ss.symbol || "").toUpperCase();
      if (!map.has(sym)) {
        map.set(sym, {
          symbol: ss.symbol,
          verdict: ss.verdict,
          final_verdict: ss.verdict,
          expiration: ss.candidate?.expiry ? String(ss.candidate.expiry).slice(0, 10) : undefined,
        } as UniverseSymbol);
      }
    }
    return map;
  }, [universe?.symbols, decision?.decision_snapshot]);

  const universeSymbols = Array.from(mergedBySymbol.values());
  const snapshot = decision?.decision_snapshot;
  const selectedSignals = snapshot?.selected_signals ?? [];
  const aTier = universeSymbols.filter(
    (s) => (s.band ?? "").toUpperCase() === "A" && ((s.final_verdict ?? s.verdict ?? "").toUpperCase() === "ELIGIBLE")
  );
  const bTier = universeSymbols.filter(
    (s) => (s.band ?? "").toUpperCase() === "B" && ((s.final_verdict ?? s.verdict ?? "").toUpperCase() === "ELIGIBLE")
  );
  const eligibleFromDecision = selectedSignals.length > 0 && aTier.length === 0 && bTier.length === 0;
  const selectedBySymbol = new Map(
    selectedSignals.map((s) => [s.symbol.toUpperCase(), s.candidate?.strategy ?? "n/a"])
  );
  const positions = positionsRes?.positions ?? [];
  const openPositions = positions.filter((p) => (p.status ?? "").toUpperCase() === "OPEN" || (p.status ?? "").toUpperCase() === "PARTIAL_EXIT");
  const capitalDeployed = openPositions.reduce((sum, p) => sum + (p.notional ?? 0), 0);

  const isReady = !!decision;
  const metadata = decision?.metadata;
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
      </div>

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

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
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
        </div>
        <div className="space-y-6">
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
        </div>
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
                <TableCell numeric>{row.score ?? "n/a"}</TableCell>
                <TableCell>
                  <Badge variant={row.band === "A" ? "success" : row.band === "B" ? "warning" : "neutral"}>
                    {row.band ?? "n/a"}
                  </Badge>
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
