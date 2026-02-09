/**
 * Phase 5: Ticker Page — Single source of truth for symbol.
 * Above-the-fold: company, sector, price, Band, Risk Status, Selected Strategy.
 * Gates: PASS/FAIL/WAIVED with expandable details; data sufficiency + missing fields when WARN/FAIL.
 * Candidates: Exactly 3 for PRIMARY strategy (Conservative / Balanced / Aggressive).
 * Targets & Lifecycle: Entry, Stop, Target1, Target2; lifecycle guidance textually.
 * Positions: Tracked positions with prominent "Log Exit".
 * Decision context: Entry snapshot; warnings for UNKNOWN return_on_risk or insufficient data.
 */
import { useEffect, useState, useCallback } from "react";
import { apiGet, apiPut, ApiError } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import { ManualExecuteModal } from "@/components/ManualExecuteModal";
import { TrackedPositionDetailDrawer } from "@/components/TrackedPositionDetailDrawer";
import { pushSystemNotification } from "@/lib/notifications";
import type {
  SymbolExplain,
  SymbolCandidates,
  SymbolTargets,
  ContractCandidate,
} from "@/types/symbolIntelligence";
import type { TrackedPosition } from "@/types/trackedPositions";
import type { PositionStrategy } from "@/types/trackedPositions";
import type { RankedOpportunity, OpportunitiesResponse } from "@/types/opportunities";
import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Target,
  Activity,
  Edit2,
  Save,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  LogOut,
} from "lucide-react";

interface DataSufficiency {
  symbol: string;
  status: "PASS" | "WARN" | "FAIL";
  missing_fields: string[];
  required_data_missing?: string[];
  optional_data_missing?: string[];
  required_data_stale?: string[];
  data_as_of_orats?: string | null;
  data_as_of_price?: string | null;
}

interface PositionDetail {
  position_id: string;
  return_on_risk: number | null;
  return_on_risk_status: string | null;
  data_sufficiency: string | null;
  data_sufficiency_missing_fields: string[];
  required_data_missing?: string[];
  required_data_stale?: string[];
  data_as_of_orats?: string | null;
}

function formatPrice(v: number | null | undefined): string {
  if (v == null) return "UNKNOWN";
  return `$${v.toFixed(2)}`;
}

function riskLabel(s: string | null | undefined): string {
  if (s === "OK" || s === "WARN" || s === "BLOCKED") return s;
  return "UNKNOWN";
}

interface TickerIntelligencePanelProps {
  symbol: string;
}

export function TickerIntelligencePanel({ symbol }: TickerIntelligencePanelProps) {
  const [explain, setExplain] = useState<SymbolExplain | null>(null);
  const [candidates, setCandidates] = useState<SymbolCandidates | null>(null);
  const [targets, setTargets] = useState<SymbolTargets | null>(null);
  const [positions, setPositions] = useState<TrackedPosition[]>([]);
  const [positionDetails, setPositionDetails] = useState<Record<string, PositionDetail>>({});
  const [dataSufficiency, setDataSufficiency] = useState<DataSufficiency | null>(null);
  const [opportunity, setOpportunity] = useState<RankedOpportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [targetsEditing, setTargetsEditing] = useState(false);
  const [targetsForm, setTargetsForm] = useState<Partial<SymbolTargets>>({});
  const [savingTargets, setSavingTargets] = useState(false);
  const [executeModalOpen, setExecuteModalOpen] = useState(false);
  const [executeCandidate, setExecuteCandidate] = useState<{ candidate: ContractCandidate; strategy: string } | null>(null);
  const [expandedGates, setExpandedGates] = useState<Set<number>>(new Set());
  const [positionDrawerOpen, setPositionDrawerOpen] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState<TrackedPosition | null>(null);

  const fetchAll = useCallback(async () => {
    if (!symbol?.trim()) return;
    const sym = symbol.trim().toUpperCase();
    setLoading(true);
    setError(null);
    try {
      const [explainRes, candidatesRes, targetsRes, positionsRes, dsRes, oppRes] = await Promise.all([
        apiGet<SymbolExplain>(ENDPOINTS.symbolExplain(sym)),
        apiGet<SymbolCandidates>(ENDPOINTS.symbolCandidates(sym)),
        apiGet<SymbolTargets>(ENDPOINTS.symbolTargets(sym)),
        apiGet<{ positions: TrackedPosition[] }>(`${ENDPOINTS.trackedPositions}?symbol=${encodeURIComponent(sym)}`),
        apiGet<DataSufficiency>(ENDPOINTS.symbolDataSufficiency(sym)).catch(() => null),
        apiGet<OpportunitiesResponse>(`${ENDPOINTS.dashboardOpportunities}?limit=50&include_blocked=true`).catch(() => null),
      ]);
      setExplain(explainRes);
      setCandidates(candidatesRes);
      setTargets(targetsRes);
      const positionsList = positionsRes?.positions ?? [];
      setPositions(positionsList);
      setDataSufficiency(dsRes);
      const opp = oppRes?.opportunities?.find((o) => o.symbol === sym) ?? null;
      setOpportunity(opp);

      const openPositions = positionsList.filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT");
      const details: Record<string, PositionDetail> = {};
      await Promise.all(
        openPositions.map(async (p) => {
          try {
            const d = await apiGet<PositionDetail>(ENDPOINTS.positionDetail(p.position_id));
            details[p.position_id] = {
              position_id: p.position_id,
              return_on_risk: d.return_on_risk ?? null,
              return_on_risk_status: d.return_on_risk_status ?? null,
              data_sufficiency: d.data_sufficiency ?? null,
              data_sufficiency_missing_fields: d.data_sufficiency_missing_fields ?? [],
              required_data_missing: d.required_data_missing ?? [],
              required_data_stale: d.required_data_stale ?? [],
              data_as_of_orats: d.data_as_of_orats ?? null,
            };
          } catch {
            details[p.position_id] = {
              position_id: p.position_id,
              return_on_risk: null,
              return_on_risk_status: "UNKNOWN_INSUFFICIENT_RISK_DEFINITION",
              data_sufficiency: null,
              data_sufficiency_missing_fields: [],
              required_data_missing: [],
              required_data_stale: [],
              data_as_of_orats: null,
            };
          }
        })
      );
      setPositionDetails(details);
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

  const openLogExit = (p: TrackedPosition) => {
    setSelectedPosition(p);
    setPositionDrawerOpen(true);
  };

  const toggleGateExpand = (i: number) => {
    setExpandedGates((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const primaryStrategy = explain?.primary_strategy ?? candidates?.strategy ?? null;
  const topCandidates = (candidates?.candidates ?? []).slice(0, 3);

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
    <div className="space-y-4">
      {/* Above-the-fold: Company, sector, price, Band, Risk Status, Selected Strategy */}
      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-foreground">
              {explain?.company?.name ?? symbol}
            </h1>
            <p className="text-sm text-muted-foreground">
              {explain?.company?.sector ?? "UNKNOWN"}
              {explain?.company?.industry && ` • ${explain.company.industry}`}
            </p>
            <p className="mt-1 text-sm font-medium">
              Price: {opportunity?.price != null ? formatPrice(opportunity.price) : "UNKNOWN"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-bold",
                explain?.band === "A" && "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400",
                explain?.band === "B" && "bg-blue-500/20 text-blue-700 dark:text-blue-400",
                (explain?.band === "C" || !explain?.band) && "bg-muted text-muted-foreground"
              )}
            >
              Band {explain?.band ?? "UNKNOWN"}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                opportunity?.risk_status === "OK" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                opportunity?.risk_status === "WARN" && "bg-amber-500/20 text-amber-600 dark:text-amber-400",
                opportunity?.risk_status === "BLOCKED" && "bg-red-500/20 text-red-600 dark:text-red-400",
                !opportunity?.risk_status && "bg-muted text-muted-foreground"
              )}
              title={opportunity?.risk_status === "BLOCKED" ? (opportunity.risk_reasons ?? []).join("; ") : undefined}
            >
              Risk: {riskLabel(opportunity?.risk_status)}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                primaryStrategy === "CSP" && "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400",
                primaryStrategy === "CC" && "bg-blue-500/20 text-blue-600 dark:text-blue-400",
                primaryStrategy === "STOCK" && "bg-purple-500/20 text-purple-600 dark:text-purple-400",
                !primaryStrategy && "bg-muted text-muted-foreground"
              )}
            >
              Strategy: {primaryStrategy ?? "UNKNOWN"}
            </span>
          </div>
        </div>
      </section>

      {/* Gates panel: PASS/FAIL/WAIVED with expandable details */}
      {explain && explain.gates.length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Activity className="h-4 w-4" />
            Gates
          </h2>
          <div className="mt-3 space-y-2">
            {explain.gates.map((g, i) => (
              <div key={i} className="rounded border border-border/50 bg-muted/10">
                <button
                  type="button"
                  onClick={() => toggleGateExpand(i)}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-muted/20"
                >
                  <span className="font-medium">{g.name}</span>
                  <span className="flex items-center gap-1">
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
                    {expandedGates.has(i) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </span>
                </button>
                {expandedGates.has(i) && (
                  <div className="border-t border-border/50 px-3 py-2 text-xs text-muted-foreground">
                    {g.reason || "No detail"}
                    {g.metric != null && ` (${g.metric})`}
                  </div>
                )}
              </div>
            ))}
          </div>
          {/* Data sufficiency when WARN/FAIL */}
          {dataSufficiency && (dataSufficiency.status === "WARN" || dataSufficiency.status === "FAIL") && (
            <div className={cn(
              "mt-3 flex items-start gap-2 rounded border px-3 py-2 text-xs",
              dataSufficiency.status === "FAIL" ? "border-destructive/50 bg-destructive/5" : "border-amber-500/30 bg-amber-500/5"
            )}>
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">Data sufficiency: {dataSufficiency.status}</p>
                {dataSufficiency.required_data_missing?.length ? (
                  <p className="mt-0.5 text-muted-foreground">Required missing: {dataSufficiency.required_data_missing.join(", ")}</p>
                ) : null}
                {dataSufficiency.required_data_stale?.length ? (
                  <p className="mt-0.5 text-muted-foreground">Stale: {dataSufficiency.required_data_stale.join(", ")}</p>
                ) : null}
                {dataSufficiency.missing_fields?.length > 0 && !dataSufficiency.required_data_missing?.length && (
                  <p className="mt-0.5 text-muted-foreground">Missing: {dataSufficiency.missing_fields.join(", ")}</p>
                )}
                {dataSufficiency.data_as_of_orats && (
                  <p className="mt-0.5 text-muted-foreground">Data as of (ORATS): {dataSufficiency.data_as_of_orats}</p>
                )}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Candidates: Exactly 3 for PRIMARY strategy, Conservative / Balanced / Aggressive */}
      {candidates && topCandidates.length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            Contract Candidates — {primaryStrategy ?? candidates.strategy ?? "PRIMARY"}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Exactly 3 candidates for primary strategy
            {candidates.capital_required != null && ` • Capital: ${formatPrice(candidates.capital_required)}`}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="py-2 pr-2 font-medium">Label</th>
                  <th className="py-2 pr-2 font-medium">Exp</th>
                  <th className="py-2 pr-2 font-medium">Strike</th>
                  <th className="py-2 pr-2 font-medium">Δ</th>
                  <th className="py-2 pr-2 font-medium">Premium</th>
                  <th className="py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {topCandidates.map((c) => (
                  <tr key={c.rank} className="border-b border-border/50">
                    <td className="py-2 pr-2">
                      <span className={cn(
                        "rounded px-1.5 py-0.5 text-xs font-medium",
                        c.label === "Conservative" && "bg-blue-500/15 text-blue-700 dark:text-blue-400",
                        c.label === "Balanced" && "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
                        c.label === "Aggressive" && "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                      )}>
                        {c.label || "—"}
                      </span>
                    </td>
                    <td className="py-2 pr-2">{c.expiration ?? "UNKNOWN"}</td>
                    <td className="py-2 pr-2">{c.strike != null ? formatPrice(c.strike) : "UNKNOWN"}</td>
                    <td className="py-2 pr-2">{c.delta != null ? c.delta.toFixed(2) : "UNKNOWN"}</td>
                    <td className="py-2 pr-2">{c.premium_per_contract != null ? formatPrice(c.premium_per_contract) : "UNKNOWN"}</td>
                    <td className="py-2">
                      <button
                        onClick={() => openExecute(c, candidates.strategy ?? "CSP")}
                        className="flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20"
                      >
                        <Target className="h-3 w-3" />
                        Execute (Manual)
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Targets & Lifecycle */}
      <section className="rounded-lg border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Targets & Lifecycle</h2>
          {!targetsEditing ? (
            <button
              onClick={() => { setTargetsForm(targets ?? {}); setTargetsEditing(true); }}
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
                <label className="text-xs text-muted-foreground">{k.replace(/_/g, " ")}</label>
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
          <div className="mt-3 space-y-2">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground">Entry</p>
                <p className="font-medium">
                  {targets?.entry_low != null || targets?.entry_high != null
                    ? `${targets?.entry_low ?? "—"} – ${targets?.entry_high ?? "—"}`
                    : "UNKNOWN"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Stop</p>
                <p className="font-medium">{targets?.stop != null ? formatPrice(targets.stop) : "UNKNOWN"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Target 1</p>
                <p className="font-medium">{targets?.target1 != null ? formatPrice(targets.target1) : "UNKNOWN"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Target 2</p>
                <p className="font-medium">{targets?.target2 != null ? formatPrice(targets.target2) : "UNKNOWN"}</p>
              </div>
            </div>
            {targets?.notes && (
              <p className="text-xs text-muted-foreground">Notes: {targets.notes}</p>
            )}
            {/* Lifecycle guidance textually */}
            {positions.filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT").length > 0 && (
              <div className="rounded border border-border/50 bg-muted/10 px-3 py-2 text-xs">
                <p className="font-medium text-foreground">Lifecycle guidance</p>
                {positions
                  .filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT")
                  .map((p) => (
                    <p key={p.position_id} className="mt-0.5 text-muted-foreground">
                      {p.strategy} — {p.lifecycle_state ?? "OPEN"}: {p.last_directive ?? "No directive"}
                    </p>
                  ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Positions panel: prominent Log Exit */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold text-foreground">Positions</h2>
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
                  <th className="py-2 pr-4 font-medium">Lifecycle</th>
                  <th className="py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.position_id} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-medium">{p.strategy}</td>
                    <td className="py-2 pr-4">{(p.contracts ?? p.quantity) ?? "—"}</td>
                    <td className="py-2 pr-4">{p.strike != null ? formatPrice(p.strike) : "UNKNOWN"}</td>
                    <td className="py-2 pr-4">{p.lifecycle_state ?? "UNKNOWN"}</td>
                    <td className="py-2">
                      {(p.status === "OPEN" || p.status === "PARTIAL_EXIT") && (
                        <button
                          onClick={() => openLogExit(p)}
                          className="inline-flex items-center gap-1 rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                        >
                          <LogOut className="h-3 w-3" />
                          Log Exit
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Decision context: entry snapshot, UNKNOWN return_on_risk / insufficient data */}
      {positions.filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT").length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="text-sm font-semibold text-foreground">Decision Context</h2>
          <div className="mt-3 space-y-3">
            {positions
              .filter((p) => p.status === "OPEN" || p.status === "PARTIAL_EXIT")
              .map((p) => {
                const pd = positionDetails[p.position_id];
                const hasUnknownRor = pd?.return_on_risk_status === "UNKNOWN_INSUFFICIENT_RISK_DEFINITION";
                const hasInsufficientData = pd?.data_sufficiency === "WARN" || pd?.data_sufficiency === "FAIL";
                return (
                  <div key={p.position_id} className="rounded border border-border/50 bg-muted/5 px-3 py-2 text-sm">
                    <p className="font-medium">{p.strategy} — Opened {p.opened_at ? new Date(p.opened_at).toLocaleDateString() : "—"}</p>
                    <p className="text-xs text-muted-foreground">
                      Strike: {p.strike != null ? formatPrice(p.strike) : "UNKNOWN"} • {p.contracts ?? "—"} contracts
                    </p>
                    {hasUnknownRor && (
                      <div className="mt-2 flex items-start gap-2 rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1.5 text-xs">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        <span>Return on risk: UNKNOWN (insufficient risk definition at entry)</span>
                      </div>
                    )}
                    {hasInsufficientData && pd?.data_sufficiency_missing_fields?.length && (
                      <div className="mt-2 flex items-start gap-2 rounded border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-xs">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                        <span>Data sufficiency: {pd.data_sufficiency}. Missing: {pd.data_sufficiency_missing_fields.join(", ")}</span>
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </section>
      )}

      {/* Execute Modal */}
      {executeModalOpen && executeCandidate && (
        <ManualExecuteModal
          symbol={symbol}
          strategy={executeCandidate.strategy as PositionStrategy}
          strike={executeCandidate.candidate.strike}
          expiration={executeCandidate.candidate.expiration}
          creditEstimate={executeCandidate.candidate.premium_per_contract}
          onClose={() => { setExecuteModalOpen(false); setExecuteCandidate(null); }}
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

      {/* Position detail drawer for Log Exit */}
      <TrackedPositionDetailDrawer
        position={selectedPosition}
        open={positionDrawerOpen}
        onClose={() => { setPositionDrawerOpen(false); setSelectedPosition(null); }}
        onExitLogged={() => {
          setPositionDrawerOpen(false);
          setSelectedPosition(null);
          fetchAll();
        }}
      />
    </div>
  );
}
