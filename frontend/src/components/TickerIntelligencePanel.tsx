/**
 * Phase 2B: Ticker intelligence — company, gates, strategy, candidates, targets, positions.
 * Source of truth for single-symbol deep view.
 */
import { useEffect, useState, useCallback } from "react";
import { apiGet, apiPut, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { ManualExecuteModal } from "@/components/ManualExecuteModal";
import { pushSystemNotification } from "@/lib/notifications";
import type {
  SymbolExplain,
  SymbolCandidates,
  SymbolTargets,
  ContractCandidate,
} from "@/types/symbolIntelligence";
import type { TrackedPosition } from "@/types/trackedPositions";
import type { PositionStrategy } from "@/types/trackedPositions";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Target,
  Building2,
  Activity,
  Edit2,
  Save,
} from "lucide-react";

function formatPrice(v: number | null | undefined): string {
  if (v == null) return "Not provided by source";
  return `$${v.toFixed(2)}`;
}

function formatPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

interface TickerIntelligencePanelProps {
  symbol: string;
}

export function TickerIntelligencePanel({ symbol }: TickerIntelligencePanelProps) {
  const [explain, setExplain] = useState<SymbolExplain | null>(null);
  const [candidates, setCandidates] = useState<SymbolCandidates | null>(null);
  const [targets, setTargets] = useState<SymbolTargets | null>(null);
  const [positions, setPositions] = useState<TrackedPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [targetsEditing, setTargetsEditing] = useState(false);
  const [targetsForm, setTargetsForm] = useState<Partial<SymbolTargets>>({});
  const [savingTargets, setSavingTargets] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeCandidate, setExecuteCandidate] = useState<{
    candidate: ContractCandidate;
    strategy: string;
  } | null>(null);

  const fetchAll = useCallback(async () => {
    if (!symbol?.trim()) return;
    const sym = symbol.trim().toUpperCase();
    setLoading(true);
    setError(null);
    try {
      const [explainRes, candidatesRes, targetsRes, positionsRes] = await Promise.all([
        apiGet<SymbolExplain>(ENDPOINTS.symbolExplain(sym)),
        apiGet<SymbolCandidates>(ENDPOINTS.symbolCandidates(sym)),
        apiGet<SymbolTargets>(ENDPOINTS.symbolTargets(sym)),
        apiGet<{ positions: TrackedPosition[] }>(`${ENDPOINTS.trackedPositions}?symbol=${encodeURIComponent(sym)}`),
      ]);
      setExplain(explainRes);
      setCandidates(candidatesRes);
      setTargets(targetsRes);
      setPositions(positionsRes?.positions ?? []);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleSaveTargets = async () => {
    if (!symbol?.trim()) return;
    setSavingTargets(true);
    try {
      const payload: Record<string, unknown> = {
        entry_low: targetsForm.entry_low ?? null,
        entry_high: targetsForm.entry_high ?? null,
        stop: targetsForm.stop ?? null,
        target1: targetsForm.target1 ?? null,
        target2: targetsForm.target2 ?? null,
        notes: targetsForm.notes ?? "",
      };
      await apiPut(ENDPOINTS.symbolTargetsPut(symbol.trim().toUpperCase()), payload);
      setTargets((t) => (t ? { ...t, ...targetsForm } : null));
      setTargetsEditing(false);
      pushSystemNotification({ source: "system", severity: "info", title: "Targets saved", message: "" });
    } catch (e) {
      pushSystemNotification({
        source: "system",
        severity: "error",
        title: "Failed to save targets",
        message: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSavingTargets(false);
    }
  };

  const openExecute = (c: ContractCandidate, strat: string) => {
    setExecuteCandidate({ candidate: c, strategy: strat });
    setExecuteModalOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading ticker intelligence...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <p className="text-sm text-destructive">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Company Identity Block */}
      {explain?.company && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Building2 className="h-4 w-4" />
            Company
          </h2>
          <div className="mt-3">
            <p className="text-lg font-semibold text-foreground">
              {explain.company.name}
            </p>
            {explain.company.sector && (
              <p className="text-sm text-muted-foreground">
                {explain.company.sector}
                {explain.company.industry && ` • ${explain.company.industry}`}
              </p>
            )}
          </div>
        </section>
      )}

      {/* 2. Gates */}
      {explain && explain.gates.length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Activity className="h-4 w-4" />
            Gates
          </h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Gate</th>
                  <th className="py-2 pr-4 font-medium w-20">Status</th>
                  <th className="py-2 font-medium">Reason</th>
                </tr>
              </thead>
              <tbody>
                {explain.gates.map((g, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-medium">{g.name}</td>
                    <td className="py-2 pr-4">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                          g.status === "PASS" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                          g.status === "FAIL" && "bg-destructive/20 text-destructive",
                          g.status === "WAIVED" && "bg-amber-500/20 text-amber-600 dark:text-amber-400"
                        )}
                      >
                        {g.status === "PASS" && <CheckCircle2 className="h-3 w-3" />}
                        {g.status === "FAIL" && <XCircle className="h-3 w-3" />}
                        {g.status}
                      </span>
                    </td>
                    <td className="py-2 text-muted-foreground">{g.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Data coverage */}
          {explain.data_coverage && (explain.data_coverage.missing?.length > 0 || explain.data_coverage.present?.length > 0) && (
            <p className="mt-2 text-xs text-muted-foreground">
              Data: {explain.data_coverage.present?.join(", ") || "none"}
              {explain.data_coverage.missing?.length ? ` • Missing: ${explain.data_coverage.missing.join(", ")}` : ""}
            </p>
          )}
        </section>
      )}

      {/* 3. Primary Strategy Block */}
      {explain && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            Primary Strategy
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                explain.primary_strategy === "CSP" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                explain.primary_strategy === "CC" && "bg-blue-500/20 text-blue-600 dark:text-blue-400",
                explain.primary_strategy === "STOCK" && "bg-purple-500/20 text-purple-600 dark:text-purple-400",
                !explain.primary_strategy && "bg-muted text-muted-foreground"
              )}
            >
              {explain.primary_strategy ?? "None"}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-bold",
                explain.band === "A" && "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400",
                explain.band === "B" && "bg-blue-500/20 text-blue-700 dark:text-blue-400",
                explain.band === "C" && "bg-muted text-muted-foreground"
              )}
            >
              Band {explain.band}
            </span>
            <span className="text-sm font-medium">Score {explain.score}</span>
          </div>
          {explain.strategy_why_bullets?.length > 0 && (
            <ul className="mt-2 list-inside list-disc text-xs text-muted-foreground">
              {explain.strategy_why_bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
          {(explain.capital_required != null || explain.capital_pct != null) && (
            <p className="mt-2 text-xs text-muted-foreground">
              Capital: {explain.capital_required != null ? formatPrice(explain.capital_required) : "—"}
              {explain.capital_pct != null && ` (${formatPct(explain.capital_pct)} of account)`}
            </p>
          )}
        </section>
      )}

      {/* 4. Top 3 Contract Candidates */}
      {candidates && candidates.candidates?.length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            Top 3 Candidates — {candidates.strategy ?? "—"}
          </h2>
          {candidates.recommended_contracts > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              Recommended: {candidates.recommended_contracts} contract(s)
              {candidates.capital_required != null && ` • ${formatPrice(candidates.capital_required)}`}
            </p>
          )}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-2 font-medium">#</th>
                  <th className="py-2 pr-2 font-medium">Label</th>
                  <th className="py-2 pr-2 font-medium">Exp</th>
                  <th className="py-2 pr-2 font-medium">Strike</th>
                  <th className="py-2 pr-2 font-medium">Δ</th>
                  <th className="py-2 pr-2 font-medium">Premium</th>
                  <th className="py-2 pr-2 font-medium">Collateral</th>
                  <th className="py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {candidates.candidates.map((c) => (
                  <tr key={c.rank} className="border-b border-border/50">
                    <td className="py-2 pr-2">{c.rank}</td>
                    <td className="py-2 pr-2">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{c.label}</span>
                    </td>
                    <td className="py-2 pr-2">{c.expiration ?? "—"}</td>
                    <td className="py-2 pr-2">{c.strike != null ? formatPrice(c.strike) : "—"}</td>
                    <td className="py-2 pr-2">{c.delta != null ? c.delta.toFixed(2) : "—"}</td>
                    <td className="py-2 pr-2">{c.premium_per_contract != null ? formatPrice(c.premium_per_contract) : "Not available from provider"}</td>
                    <td className="py-2 pr-2">{c.collateral_per_contract != null ? formatPrice(c.collateral_per_contract) : "—"}</td>
                    <td className="py-2">
                      <button
                        onClick={() => openExecute(c, candidates.strategy ?? "CSP")}
                        className="flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20"
                      >
                        <Target className="h-3 w-3" />
                        Execute
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 5. Stock Entry/Exit Targets */}
      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            Stock Targets
          </h2>
          {!targetsEditing ? (
            <button
              onClick={() => {
                setTargetsForm(targets ?? {});
                setTargetsEditing(true);
              }}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Edit2 className="h-3 w-3" />
              Edit
            </button>
          ) : (
            <button
              onClick={handleSaveTargets}
              disabled={savingTargets}
              className="flex items-center gap-1 rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {savingTargets ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              Save
            </button>
          )}
        </div>
        {targetsEditing ? (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {(["entry_low", "entry_high", "stop", "target1", "target2"] as const).map((k) => (
              <div key={k}>
                <label className="text-xs text-muted-foreground">
                  {k.replace(/_/g, " ")}
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={targetsForm[k] ?? ""}
                  onChange={(e) => setTargetsForm((f) => ({ ...f, [k]: e.target.value ? parseFloat(e.target.value) : null }))}
                  className="mt-0.5 w-full rounded border border-border bg-background px-2 py-1 text-sm"
                />
              </div>
            ))}
            <div className="col-span-2 sm:col-span-5">
              <label className="text-xs text-muted-foreground">Notes</label>
              <input
                type="text"
                value={targetsForm.notes ?? ""}
                onChange={(e) => setTargetsForm((f) => ({ ...f, notes: e.target.value }))}
                className="mt-0.5 w-full rounded border border-border bg-background px-2 py-1 text-sm"
              />
            </div>
          </div>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-5">
            <div>
              <p className="text-xs text-muted-foreground">Entry zone</p>
              <p className="font-medium">
                {targets?.entry_low != null || targets?.entry_high != null
                  ? `${targets?.entry_low ?? "—"} – ${targets?.entry_high ?? "—"}`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Stop</p>
              <p className="font-medium">{targets?.stop != null ? formatPrice(targets.stop) : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Target 1</p>
              <p className="font-medium">{targets?.target1 != null ? formatPrice(targets.target1) : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Target 2</p>
              <p className="font-medium">{targets?.target2 != null ? formatPrice(targets.target2) : "—"}</p>
            </div>
            {targets?.notes && (
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground">Notes</p>
                <p className="text-sm">{targets.notes}</p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 6. Positions */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          Tracked Positions
        </h2>
        {positions.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No tracked positions for this symbol</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Strategy</th>
                  <th className="py-2 pr-4 font-medium">Contracts</th>
                  <th className="py-2 pr-4 font-medium">Strike</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 font-medium">Opened</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.position_id} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-medium">{p.strategy}</td>
                    <td className="py-2 pr-4">{(p.contracts ?? p.quantity) ?? "—"}</td>
                    <td className="py-2 pr-4">{p.strike != null ? formatPrice(p.strike) : "—"}</td>
                    <td className="py-2 pr-4">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          p.status === "OPEN" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                          p.status === "CLOSED" && "bg-muted text-muted-foreground"
                        )}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="py-2 text-muted-foreground">{p.opened_at ? new Date(p.opened_at).toLocaleDateString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Execute Modal */}
      {executeModalOpen && executeCandidate && (
        <ManualExecuteModal
          symbol={symbol}
          strategy={executeCandidate.strategy as PositionStrategy}
          strike={executeCandidate.candidate.strike}
          expiration={executeCandidate.candidate.expiration}
          creditEstimate={executeCandidate.candidate.premium_per_contract}
          onClose={() => {
            setExecuteModalOpen(false);
            setExecuteCandidate(null);
          }}
          onExecuted={() => {
            setExecuteModalOpen(false);
            setExecuteCandidate(null);
            pushSystemNotification({
              source: "system",
              severity: "info",
              title: "Position recorded",
              message: `${symbol} ${executeCandidate.strategy} tracked. Execute in your brokerage.`,
            });
            fetchAll();
          }}
        />
      )}
    </div>
  );
}
