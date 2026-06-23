import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useUiSystemHealth,
  useOperationsStatus,
  useEarningsDebug,
  useDiagnosticsHistory,
  useRunDiagnostics,
  useRunEval,
  useLatestSnapshot,
  useRunFreezeSnapshot,
  useStoresIntegrity,
  useRepairStore,
  useAdminSlackTest,
  useAdminEvaluationForce,
  usePositionsUnifiedRebuild,
  usePositionsUnifiedIntegrityCheck,
  useReconcileDiff,
} from "@/api/queries";
import type { UiPositionsUnifiedRebuildResponse } from "@/api/types";
import { formatTimestampEt, formatTimestampEtFull } from "@/utils/formatTimestamp";
import { sanitizeForDisplay } from "@/utils/sanitizeDisplay";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, StatusBadge, Badge, Button, Tooltip } from "@/components/ui";

const DIAGNOSTIC_CHECKS = ["orats", "decision_store", "universe", "positions", "portfolio_risk", "scheduler", "store_integrity"] as const;

/** R22.2: Map ORATS threshold_triggered to safe display label (no raw codes). */
function oratsThresholdLabel(triggered: string | null | undefined): string {
  const t = (triggered ?? "").toLowerCase();
  if (t === "ok_minutes") return "Within OK window";
  if (t === "warn_minutes") return "Staleness threshold";
  if (t === "error") return "Error (no data or failure)";
  return triggered ? String(triggered) : "—";
}

/** R22.2: Friendly skip reason for scheduler (market closed = set-and-forget, not error). */
function schedulerSkipReasonLabel(reason: string | null | undefined): string {
  const r = (reason ?? "").toLowerCase();
  if (r === "market_closed") return "Market closed — scheduler skips until open";
  if (r === "evaluation_running") return "Evaluation already running";
  if (r === "no_symbols") return "No symbols in universe";
  return reason ?? "—";
}

/** R24.3.1 / R24.6: Safe display label for diagnostic checks (no raw FAIL/WARN in UI). */
function checkDisplayLabel(ch: { check?: string; status?: string; status_label?: string }): string {
  if (ch.check === "portfolio_risk" && ch.status_label) return ch.status_label;
  const s = (ch.status ?? "").toUpperCase();
  if (s === "PASS" || s === "OK") return s === "PASS" ? "Passed" : "OK";
  if (s === "FAIL") return "Blocked";
  if (s === "WARN") return "Degraded";
  if (s === "SKIP") return "Skipped";
  return ch.status ?? "—";
}

/** R24.3.1: Badge variant for check status (deterministic). */
function checkBadgeVariant(ch: { status?: string }): "success" | "warning" | "danger" | "neutral" {
  const s = (ch.status ?? "").toUpperCase();
  if (s === "FAIL" || s === "CRITICAL") return "danger";
  if (s === "WARN") return "warning";
  if (s === "PASS" || s === "OK" || s === "SKIP") return "success";
  return "neutral";
}

/** R28.7 / R24.6: Safe display label for diagnostics run overall_status (no raw PASS/FAIL/WARN in UI). */
function overallStatusDisplayLabel(raw: string | null | undefined): string {
  const s = (raw ?? "").toUpperCase();
  if (s === "PASS") return "Passed";
  if (s === "FAIL") return "Blocked";
  if (s === "WARN") return "Degraded";
  if (s === "OK" || s === "SKIP") return raw ?? "—";
  return raw ?? "—";
}

export function SystemDiagnosticsPage() {
  const { data, isLoading, isError } = useUiSystemHealth();
  const { data: opsData } = useOperationsStatus();
  const probeSymbol = data?.earnings_probe_symbol ?? "SPY";
  const { data: earningsDebug } = useEarningsDebug(probeSymbol);
  const { data: historyData } = useDiagnosticsHistory(10);
  const { data: latestSnapshot, isError: snapshotError } = useLatestSnapshot();
  const runDiagnostics = useRunDiagnostics();
  const runEval = useRunEval();
  const runFreeze = useRunFreezeSnapshot();
  const { data: integrityData } = useStoresIntegrity();
  const repairStore = useRepairStore();
  const adminSlackTest = useAdminSlackTest();
  const adminForceEval = useAdminEvaluationForce();
  const rebuildUnified = usePositionsUnifiedRebuild();
  const integrityCheck = usePositionsUnifiedIntegrityCheck();
  const reconcileStatus = data?.positions_unified_reconcile?.status;
  const { data: reconcileDiff, isLoading: reconcileDiffLoading } = useReconcileDiff({
    include_paper: true,
    limit: 200,
    enabled: reconcileStatus === "Review",
  });
  const [reconcileDiffExpanded, setReconcileDiffExpanded] = useState(false);
  const [integrityCheckDetailsExpanded, setIntegrityCheckDetailsExpanded] = useState(false);
  const [selectedChecks, setSelectedChecks] = useState<Set<string>>(new Set(DIAGNOSTIC_CHECKS));
  const [latestResult, setLatestResult] = useState<typeof runDiagnostics.data | null>(null);

  const handleRunAll = () => {
    runDiagnostics.mutate(undefined, {
      onSuccess: (res) => setLatestResult(res),
    });
  };

  const handleRunSelected = () => {
    const checks = selectedChecks.size === DIAGNOSTIC_CHECKS.length
      ? undefined
      : Array.from(selectedChecks).join(",");
    runDiagnostics.mutate(checks, {
      onSuccess: (res) => setLatestResult(res),
    });
  };

  const toggleCheck = (c: string) => {
    setSelectedChecks((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  };

  const selectAllChecks = () => setSelectedChecks(new Set(DIAGNOSTIC_CHECKS));
  const clearChecks = () => setSelectedChecks(new Set());

  const runSingleCheck = (check: string) => {
    runDiagnostics.mutate(check, {
      onSuccess: (res) => setLatestResult(res),
    });
  };

  const displayResult = latestResult ?? historyData?.runs?.[0];
  const runs = historyData?.runs ?? [];
  const api = data?.api;
  const decisionStore = data?.decision_store;
  const orats = data?.orats;
  const market = data?.market;
  const scheduler = data?.scheduler;
  const slack = data?.slack;
  const eodFreeze = data?.eod_freeze;
  const markRefresh = data?.mark_refresh;
  const portfolioRiskNotifier = data?.portfolio_risk_notifier;
  const notificationsHealth = data?.notifications;
  const marketClosed = market?.phase ? market.phase !== "OPEN" && market.phase !== "UNKNOWN" : false;

  if (isLoading) {
    return (
      <div>
        <PageHeader title="System Diagnostics" />
        <p className="text-zinc-400">Loading…</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="System Diagnostics" />
        <p className="text-red-400">Failed to load system diagnostics.</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        <PageHeader title="System Diagnostics" />
        <p className="text-zinc-500">No data.</p>
      </div>
    );
  }

  const cadence = data?.cadence;
  const cadenceLabel = (cadence?.mode ?? "EOD_BIASED").replace(/_/g, "-").toLowerCase();
  const asOfEt = cadence?.eligibility_as_of ? formatTimestampEt(cadence.eligibility_as_of) : null;

  return (
    <div className="space-y-4">
      <PageHeader title="System Status" subtext="API, Decision Store, ORATS, market, and scheduler" />
      {cadence?.mode === "EOD_BIASED" && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400" data-testid="cadence-banner">
          Cadence: {cadenceLabel} (as of {asOfEt ?? "—"})
        </p>
      )}
      <Card data-testid="operations-panel-r35">
        <CardHeader title="Operations (R35)" description="Scheduler, jobs, backup — manual only; no trade execution" />
        <div className="grid gap-4 p-4 md:grid-cols-2">
          <div>
            <p className="text-xs uppercase text-zinc-500">Scheduler master</p>
            <p className="mt-1 font-mono">{opsData?.scheduler?.master_enabled ? "Enabled" : "Disabled"}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-zinc-500">ORATS token</p>
            <p className="mt-1 font-mono">{opsData?.orats_token_present ? "Present" : "Not configured"}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-zinc-500">Registered jobs</p>
            <p className="mt-1 font-mono">{opsData?.scheduler?.jobs?.length ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-zinc-500">Latest backup</p>
            <p className="mt-1 font-mono text-sm">{opsData?.backup?.latest?.backup_id ?? "—"}</p>
          </div>
        </div>
      </Card>
      <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
        <Card>
          <CardHeader title="API" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={api?.status ?? "—"} />
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">latency_ms</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{api?.latency_ms ?? "—"}</p>
            </div>
          </div>
        </Card>
        <Card className={decisionStore?.status === "CRITICAL" ? "border-red-500 dark:border-red-600" : ""}>
          <CardHeader
            title="Decision Store"
            description={decisionStore?.status === "CRITICAL" ? decisionStore.reason ?? "CRITICAL" : undefined}
          />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={decisionStore?.status ?? "—"} />
              </p>
            </div>
            {decisionStore?.reason && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">reason</span>
                <p className="mt-1 text-zinc-600 dark:text-zinc-400">{decisionStore.reason}</p>
              </div>
            )}
            {decisionStore?.evaluation_timestamp_utc && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">evaluation_timestamp (ET)</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(decisionStore.evaluation_timestamp_utc)}</p>
              </div>
            )}
            {decisionStore?.canonical_path && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">path</span>
                <p className="mt-1 font-mono text-xs text-zinc-600 dark:text-zinc-400 truncate" title={decisionStore.canonical_path}>
                  {decisionStore.canonical_path}
                </p>
              </div>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="ORATS" description="R22.2: Freshness OK / DELAYED (within window) / Degraded / ERROR" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Freshness</span>
              <p className="mt-1 font-medium text-zinc-700 dark:text-zinc-200">
                {orats?.orats_freshness_state_label ?? orats?.status ?? "—"}
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <StatusBadge status={orats?.status ?? "—"} />
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">as_of (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(orats?.orats_as_of ?? orats?.last_success_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Threshold</span>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">{oratsThresholdLabel(orats?.orats_threshold_triggered)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Age / threshold</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                {orats?.age_minutes != null && orats?.staleness_threshold_minutes != null
                  ? `${orats.age_minutes}m (threshold: ${orats.staleness_threshold_minutes}m)`
                  : orats?.age_minutes != null
                    ? `${orats.age_minutes}m`
                    : "—"}
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_success_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(orats?.last_success_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">avg_latency_seconds</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                {orats?.avg_latency_seconds != null ? orats.avg_latency_seconds : "—"}
              </p>
            </div>
            <div className="col-span-2">
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_error_reason</span>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">{orats?.last_error_reason ?? "—"}</p>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Market" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">phase</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{market?.phase ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">is_open</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{market?.is_open ? "true" : "false"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">timestamp (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(market?.timestamp)}</p>
            </div>
          </div>
        </Card>
        <Card data-testid="earnings-probe-card">
          <CardHeader title="Earnings probe" description={`R25.8: Probe symbol ${probeSymbol} (advisory only)`} />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1 font-medium text-zinc-700 dark:text-zinc-200">{earningsDebug?.status ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">next_date</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{earningsDebug?.next_date ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">days</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{earningsDebug?.days ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">implied_move_pct</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{earningsDebug?.implied_move_pct != null ? `${earningsDebug.implied_move_pct}%` : "—"}</p>
            </div>
            <div className="col-span-2">
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">as_of (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{earningsDebug?.as_of ? formatTimestampEt(earningsDebug.as_of) : "—"}</p>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Scheduler" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">interval_minutes</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler?.interval_minutes ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_run_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(scheduler?.last_run_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">next_run_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(scheduler?.next_run_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_result</span>
              <p className="mt-1">
                <StatusBadge status={scheduler?.last_result ?? "—"} />
              </p>
            </div>
            {scheduler?.last_skip_reason && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_skip_reason</span>
                <p className={`mt-1 ${(scheduler.last_skip_reason || "").toLowerCase() === "market_closed" ? "text-zinc-500 dark:text-zinc-400" : "text-zinc-600 dark:text-zinc-400"}`}>
                  {schedulerSkipReasonLabel(scheduler.last_skip_reason)}
                </p>
              </div>
            )}
            {scheduler?.last_duration_ms != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_duration_ms</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler.last_duration_ms}</p>
              </div>
            )}
            {scheduler?.last_run_ok != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_run_ok</span>
                <p className="mt-1">
                  <StatusBadge status={scheduler.last_run_ok ? "OK" : "FAIL"} />
                </p>
              </div>
            )}
            {scheduler?.run_count_today != null && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">run_count_today</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler.run_count_today}</p>
              </div>
            )}
            {scheduler?.last_run_error && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_run_error</span>
                <p className="mt-1 text-red-600 dark:text-red-400">{scheduler.last_run_error}</p>
              </div>
            )}
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">nightly_next_at</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler?.nightly_next_at ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">eod_next_at</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{scheduler?.eod_next_at ?? "—"}</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Tooltip content={marketClosed ? "Market closed. Scheduler skips evaluation. Use Force evaluation to run anyway." : undefined}>
              <span className="inline-block">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => runEval.mutate({ mode: "LIVE" })}
                  disabled={runEval.isPending || marketClosed}
                >
                  {runEval.isPending ? "Running…" : "Run Scheduler now"}
                </Button>
              </span>
            </Tooltip>
            <Button
              variant="primary"
              size="sm"
              onClick={() => adminForceEval.mutate()}
              disabled={adminForceEval.isPending}
            >
              {adminForceEval.isPending ? "Running…" : "Force evaluation now"}
            </Button>
            <Link to="/" className="ml-2 text-sm text-zinc-600 hover:underline dark:text-zinc-400">
              Dashboard
            </Link>
          </div>
          {adminForceEval.data && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Forced: {adminForceEval.data.started ? "started" : "not started"} — {adminForceEval.data.reason ?? ""}
            </p>
          )}
        </Card>
        {/* Phase 21.5 / R21.5.1: Slack per-channel status + 4 test buttons */}
        <Card>
          <CardHeader title="Slack" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_any_send_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(slack?.last_any_send_at ?? slack?.last_send_at)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_any_send_ok</span>
              <p className="mt-1">
                <StatusBadge status={slack?.last_any_send_ok === true ? "OK" : slack?.last_any_send_ok === false ? "FAIL" : "—"} />
              </p>
            </div>
            {slack?.last_any_send_error && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_any_send_error</span>
                <p className="mt-1 text-red-600 dark:text-red-400">{slack.last_any_send_error}</p>
              </div>
            )}
          </div>
          {/* R21.5.1 / R22.2: Per-channel status (last_send_at, last_send_ok, last_error, last_payload_type) */}
          {slack?.channels && Object.keys(slack.channels).length > 0 && (
            <div className="mt-4 space-y-2">
              <span className="block text-xs font-medium text-zinc-500 dark:text-zinc-500">Per channel</span>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {["signals", "daily", "data_health", "critical"].map((ch) => {
                  const c = slack.channels?.[ch];
                  if (!c) return null;
                  return (
                    <div key={ch} className="rounded border border-zinc-200 p-2 dark:border-zinc-700">
                      <p className="text-xs font-medium text-zinc-700 dark:text-zinc-300">{ch}</p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">last_send: {formatTimestampEt(c.last_send_at) ?? "—"}</p>
                      <p className="text-xs">
                        <StatusBadge status={c.last_send_ok === true ? "OK" : c.last_send_ok === false ? "FAIL" : "—"} />
                      </p>
                      {c.last_payload_type != null && c.last_payload_type !== "" && (
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">last_payload_type: {String(c.last_payload_type)}</p>
                      )}
                      {c.last_error && <p className="mt-1 truncate text-xs text-red-600 dark:text-red-400" title={c.last_error}>{c.last_error === "no_webhook" ? "Not configured" : c.last_error}</p>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {(["signals", "daily", "data_health", "critical"] as const).map((ch) => (
              <Button
                key={ch}
                variant="secondary"
                size="sm"
                onClick={() => adminSlackTest.mutate(ch)}
                disabled={adminSlackTest.isPending}
              >
                {adminSlackTest.isPending ? "Sending…" : `Test ${ch.replace("_", " ")}`}
              </Button>
            ))}
          </div>
          {adminSlackTest.data && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {adminSlackTest.data.ok ? `Test sent to ${adminSlackTest.data.channel ?? "channel"}.` : adminSlackTest.data.message ?? "—"}
            </p>
          )}
        </Card>
        <Card>
          <CardHeader
            title="Freeze Snapshot (PR2)"
            description="EOD archival. No eval after market close; archive-only always safe."
          />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Market phase</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{market?.phase ?? "—"}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Last snapshot</span>
              <p className="mt-1 font-mono text-xs text-zinc-600 dark:text-zinc-400 truncate" title={latestSnapshot?.snapshot_dir}>
                {latestSnapshot?.snapshot_dir ? latestSnapshot.snapshot_dir.split(/[/\\]/).pop() ?? latestSnapshot.snapshot_dir : snapshotError ? "—" : "None"}
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Last auto-freeze (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(eodFreeze?.last_run_at_utc)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Scheduled</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{eodFreeze?.scheduled_time_et ?? "15:58"} ET</p>
            </div>
            {eodFreeze?.next_scheduled_et && (
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">next_scheduled_et</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{eodFreeze.next_scheduled_et}</p>
              </div>
            )}
            {eodFreeze?.last_error && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_error</span>
                <p className="mt-1 text-red-600 dark:text-red-400">{eodFreeze.last_error}</p>
              </div>
            )}
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <Tooltip content={marketClosed ? "Market closed or after 4 PM ET. Eval disabled to protect canonical decision. Use Archive Now for archive-only." : undefined}>
              <span className="inline-block">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => runFreeze.mutate(false)}
                  disabled={runFreeze.isPending || marketClosed}
                >
                  {runFreeze.isPending ? "Running…" : "Run EOD Freeze (eval + archive)"}
                </Button>
              </span>
            </Tooltip>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => runFreeze.mutate(true)}
              disabled={runFreeze.isPending}
            >
              Archive Now (no eval)
            </Button>
          </div>
          {runFreeze.data && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {runFreeze.data.ran_eval ? "Ran eval + archive." : "Archive only."} Snapshot: {runFreeze.data.snapshot_dir.split(/[/\\]/).pop()}
            </p>
          )}
        </Card>
        {/* Phase 16.0: Mark refresh state */}
        <Card>
          <CardHeader title="Mark Refresh" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">last_run_at (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{formatTimestampEt(markRefresh?.last_run_at_utc)}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status</span>
              <p className="mt-1">
                <StatusBadge status={markRefresh?.status ?? markRefresh?.last_result ?? "—"} />
              </p>
              {markRefresh?.status_label != null && markRefresh.status_label !== "" && (
                <p className="mt-0.5 text-xs text-zinc-600 dark:text-zinc-400">{markRefresh.status_label}</p>
              )}
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">updated / skipped / errors</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                {markRefresh?.updated_count ?? 0} / {markRefresh?.skipped_count ?? 0} / {markRefresh?.error_count ?? 0}
              </p>
            </div>
            {markRefresh?.errors_sample && markRefresh.errors_sample.length > 0 && (
              <div className="col-span-2">
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">errors_sample</span>
                <ul className="mt-1 list-inside list-disc text-xs text-zinc-600 dark:text-zinc-400">
                  {markRefresh.errors_sample.slice(0, 5).map((e, i) => (
                    <li key={i} className="truncate">{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>
        {/* R24.3.1: Portfolio risk notifier — safe status/label only (OK/Degraded/Advisory). */}
        <Card>
          <CardHeader title="Portfolio risk notifier" description="Limit breach notifications; safe labels only." />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">status</span>
              <p className="mt-1">
                <Badge
                  variant={
                    portfolioRiskNotifier?.status === "Degraded"
                      ? "danger"
                      : portfolioRiskNotifier?.status === "Advisory"
                        ? "warning"
                        : "success"
                  }
                >
                  {portfolioRiskNotifier?.status ?? "OK"}
                </Badge>
              </p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">label</span>
              <p className="mt-1 text-zinc-700 dark:text-zinc-200">{portfolioRiskNotifier?.label ?? "OK"}</p>
            </div>
          </div>
        </Card>
        {/* R25.4: Notifications health — counts and last emitted (safe labels only). */}
        <Card>
          <CardHeader title="Notifications" description="Inbox counts and last emitted; safe labels only." />
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">New</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{notificationsHealth?.count_new ?? 0}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Acked</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{notificationsHealth?.count_acked ?? 0}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Archived</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{notificationsHealth?.count_archived ?? 0}</p>
            </div>
            <div>
              <span className="block text-xs text-zinc-500 dark:text-zinc-500">Last emitted (ET)</span>
              <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                {notificationsHealth?.last_emitted_ts ? formatTimestampEt(notificationsHealth.last_emitted_ts) : "—"}
              </p>
            </div>
          </div>
        </Card>
        {/* R28.1: Unified Positions Reconcile — status OK/Review, counts; safe labels only. */}
        {data?.positions_unified_reconcile != null && (
          <Card data-testid="positions-unified-reconcile-card">
            <CardHeader title="Unified Positions Reconcile" description="Paper vs unified counts; safe labels only." />
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status</span>
                <p className="mt-1">
                  <StatusBadge status={data.positions_unified_reconcile.status ?? "Review"} />
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Paper open</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_reconcile.paper_open_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Paper closed</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_reconcile.paper_closed_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Unified open (paper)</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_reconcile.unified_open_paper_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Unified closed (paper)</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_reconcile.unified_closed_paper_count ?? "—"}</p>
              </div>
            </div>
          </Card>
        )}
        {/* R28.8: Unified Positions Reconcile Diff — read-only; show what is mismatched when reconcile is Review. */}
        {data?.positions_unified_reconcile != null && (
          <Card data-testid="positions-unified-reconcile-diff-card">
            <CardHeader
              title="Unified Positions Reconcile Diff"
              description="Source vs unified DB (when reconcile needs review). Safe labels only."
            />
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Reconcile status</span>
                <p className="mt-1">
                  <StatusBadge status={data.positions_unified_reconcile.status ?? "Review"} />
                </p>
              </div>
              {reconcileStatus === "Review" && (
                <>
                  <div>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-500">Missing in unified</span>
                    <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                      {reconcileDiffLoading ? "…" : reconcileDiff?.missing_count ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-500">Extra in unified</span>
                    <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                      {reconcileDiffLoading ? "…" : reconcileDiff?.extra_count ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="block text-xs text-zinc-500 dark:text-zinc-500">Mismatched</span>
                    <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                      {reconcileDiffLoading ? "…" : reconcileDiff?.mismatched_count ?? "—"}
                    </p>
                  </div>
                </>
              )}
            </div>
            {reconcileStatus === "Review" && (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setReconcileDiffExpanded((e) => !e)}
                    data-testid="reconcile-diff-view-details-btn"
                  >
                    {reconcileDiffExpanded ? "Hide details" : "View details"}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={rebuildUnified.isPending}
                    onClick={() => {
                      if (window.confirm("This will rebuild the unified positions DB from authoritative sources. Manual action. Continue?")) {
                        rebuildUnified.mutate(
                          { include_paper: true },
                          { onSuccess: () => setReconcileDiffExpanded(false) }
                        );
                      }
                    }}
                    data-testid="reconcile-diff-rebuild-now-btn"
                  >
                    {rebuildUnified.isPending ? ((rebuildUnified.data as UiPositionsUnifiedRebuildResponse | undefined)?.result?.status_label ?? "Rebuilding…") : "Rebuild now"}
                  </Button>
                  <Link
                    to="/positions?source=db&include_paper=true"
                    className="text-sm text-blue-600 hover:underline dark:text-blue-400"
                    data-testid="reconcile-diff-view-db-link"
                  >
                    View DB stored positions
                  </Link>
                </div>
                {reconcileDiffExpanded && reconcileDiff?.items != null && reconcileDiff.items.length > 0 && (
                  <ul className="mt-2 max-h-60 list-none overflow-y-auto rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900/50">
                    {reconcileDiff.items.map((item, i) => (
                      <li key={`${item.id}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-zinc-200 py-1 last:border-0 dark:border-zinc-700">
                        <span className="font-medium text-zinc-700 dark:text-zinc-300">{item.kind}</span>
                        <span className="font-mono text-zinc-600 dark:text-zinc-400">{item.symbol ?? item.id}</span>
                        {item.instrument_type && (
                          <span className="text-zinc-500 dark:text-zinc-500">{item.instrument_type}</span>
                        )}
                        {item.fields_diff && item.fields_diff.length > 0 && (
                          <span className="text-zinc-500 dark:text-zinc-500">({item.fields_diff.join(", ")})</span>
                        )}
                        <Link
                          to={`/positions?symbol=${encodeURIComponent(item.symbol ?? "")}&include_paper=true`}
                          className="text-blue-600 hover:underline dark:text-blue-400"
                        >
                          View positions
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                {reconcileDiffExpanded && reconcileDiff?.items != null && reconcileDiff.items.length === 0 && !reconcileDiffLoading && (
                  <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">No diff items (counts may be from a previous run).</p>
                )}
              </div>
            )}
            {reconcileStatus === "OK" && (
              <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">Reconcile OK; no diff needed.</p>
            )}
          </Card>
        )}
        {/* R28.7: Unified Positions Rebuild — manual rebuild from authoritative sources; safe labels only. */}
        {data?.positions_unified_rebuild != null && (
          <Card data-testid="positions-unified-rebuild-card">
            <CardHeader title="Unified Positions Rebuild" description="Manual rebuild of unified positions DB from authoritative sources." />
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status</span>
                <p className="mt-1">
                  <StatusBadge status={data.positions_unified_rebuild.status ?? "OK"} />
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Last rebuild (ET)</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                  {data.positions_unified_rebuild.last_rebuild_at_utc
                    ? formatTimestampEt(data.positions_unified_rebuild.last_rebuild_at_utc)
                    : "—"}
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Open count</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_rebuild.last_rebuild_open_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Closed count</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_rebuild.last_rebuild_closed_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Include paper</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_rebuild.last_include_paper == null ? "—" : data.positions_unified_rebuild.last_include_paper ? "Yes" : "No"}</p>
              </div>
            </div>
            <div className="mt-3">
              <Button
                size="sm"
                variant="secondary"
                disabled={rebuildUnified.isPending}
                onClick={() => {
                  if (window.confirm("This will rebuild the unified positions DB from authoritative sources. Manual action. Continue?")) {
                    rebuildUnified.mutate({ include_paper: true });
                  }
                }}
                data-testid="positions-unified-rebuild-btn"
              >
                {rebuildUnified.isPending ? "Rebuilding…" : "Rebuild unified positions"}
              </Button>
            </div>
          </Card>
        )}
        {/* R29.4: Unified Positions Integrity Check — last run status, counts, view details; parity with PositionsPage. */}
        {data?.positions_unified_integrity_check != null && (
          <Card data-testid="positions-unified-integrity-check-card">
            <CardHeader
              title="Unified Positions Integrity Check"
              description="Last integrity check (staleness + reconcile). Safe labels only."
            />
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status</span>
                <p className="mt-1">
                  <StatusBadge status={data.positions_unified_integrity_check.last_status ?? "OK"} />
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Last run (ET)</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                  {data.positions_unified_integrity_check.last_checked_at_utc
                    ? formatTimestampEt(data.positions_unified_integrity_check.last_checked_at_utc)
                    : "—"}
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status label</span>
                <p className="mt-1 text-zinc-700 dark:text-zinc-200">{sanitizeForDisplay(data.positions_unified_integrity_check.last_status_label)}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Missing</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_integrity_check.last_reconcile_missing_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Extra</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_integrity_check.last_reconcile_extra_count ?? "—"}</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Mismatched</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.positions_unified_integrity_check.last_reconcile_mismatched_count ?? "—"}</p>
              </div>
            </div>
            {/* R29.5: Remediation guidance — OK vs Review with safe labels only. */}
            <div className="mt-3" data-testid="integrity-check-remediation-guidance">
              {(data.positions_unified_integrity_check.last_status ?? "OK") === "OK" ? (
                <p className="text-sm text-zinc-600 dark:text-zinc-400">No action needed.</p>
              ) : (
                <ul className="list-inside list-disc space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
                  <li>
                    <Link to="/positions?source=db&include_paper=true" className="text-blue-600 hover:underline dark:text-blue-400">
                      View diff details
                    </Link>
                    {" "}(Positions, stored view)
                  </li>
                  <li>Run integrity check (button below)</li>
                  <li>Rebuild unified positions (from Positions or Reconcile Diff card)</li>
                </ul>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setIntegrityCheckDetailsExpanded((e) => !e)}
                data-testid="integrity-check-view-details-btn"
              >
                {integrityCheckDetailsExpanded ? "Hide details" : "View details"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={integrityCheck.isPending}
                onClick={() => {
                  if (window.confirm("This will run an integrity check comparing stored positions with authoritative sources and staleness. Manual action. Continue?")) {
                    integrityCheck.mutate({ include_paper: true }, { onSuccess: () => setIntegrityCheckDetailsExpanded(true) });
                  }
                }}
                data-testid="integrity-check-run-btn"
              >
                {integrityCheck.isPending ? "Check running" : "Run integrity check"}
              </Button>
              {data.positions_unified_integrity_check.last_status === "Review" && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => void import("@/api/queries").then((m) => m.downloadIntegrityBundle(true))}
                  data-testid="integrity-check-download-bundle-btn"
                >
                  Download integrity bundle
                </Button>
              )}
              <Link to="/positions?source=db" className="text-sm text-blue-600 hover:underline dark:text-blue-400">
                Positions
              </Link>
            </div>
            {integrityCheckDetailsExpanded && data.positions_unified_integrity_check.last_sample_items != null && data.positions_unified_integrity_check.last_sample_items.length > 0 && (
              <ul className="mt-2 max-h-48 list-none space-y-1 overflow-y-auto rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900/50" data-testid="integrity-check-details-list">
                {data.positions_unified_integrity_check.last_sample_items.map((item, i) => (
                  <li key={`${item.id ?? i}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-zinc-200 py-1.5 last:border-0 dark:border-zinc-700">
                    <span className="font-medium text-zinc-700 dark:text-zinc-300">{sanitizeForDisplay(item.kind)}</span>
                    <span className="font-mono text-zinc-600 dark:text-zinc-400">{sanitizeForDisplay(item.symbol ?? item.id)}</span>
                    {item.instrument_type != null && <span className="text-zinc-500 dark:text-zinc-500">{sanitizeForDisplay(item.instrument_type)}</span>}
                    <span className="text-zinc-400 dark:text-zinc-500">{sanitizeForDisplay(item.id)}</span>
                    {item.fields_diff != null && item.fields_diff.length > 0 && (
                      <span className="text-zinc-500 dark:text-zinc-500">({item.fields_diff.map(sanitizeForDisplay).join(", ")})</span>
                    )}
                    {item.link_positions_url != null && item.link_positions_url !== "" && (
                      <Link to={item.link_positions_url} className="text-blue-600 hover:underline dark:text-blue-400" data-testid="integrity-sample-open-positions">
                        Open positions
                      </Link>
                    )}
                    {item.link_diagnostics_url != null && item.link_diagnostics_url !== "" && (
                      <Link to={item.link_diagnostics_url} className="text-blue-600 hover:underline dark:text-blue-400" data-testid="integrity-sample-open-diagnostics">
                        Open diagnostics
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {integrityCheckDetailsExpanded && data.positions_unified_integrity_check.last_sample_items != null && data.positions_unified_integrity_check.last_sample_items.length === 0 && (
              <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-500">No sample items from last check.</p>
            )}
          </Card>
        )}
        {/* R25.9: Guardrails — status (OK/Advisory/Blocked), metrics, limits; safe labels only. */}
        {data?.guardrails != null && (
          <Card data-testid="guardrails-card">
            <CardHeader title="Guardrails" description="Portfolio guardrails; safe labels only." />
            <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Status</span>
                <p className="mt-1">
                  <StatusBadge status={data.guardrails.status ?? "OK"} />
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Cash reserve %</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.guardrails.metrics?.cash_reserve_pct ?? "—"}%</p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Open options</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                  {data.guardrails.metrics?.open_options_count ?? "—"} / {data.guardrails.limits?.MAX_OPEN_OPTIONS_POSITIONS ?? "—"}
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Open shares</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                  {data.guardrails.metrics?.open_shares_count ?? "—"} / {data.guardrails.limits?.MAX_OPEN_SHARES_POSITIONS ?? "—"}
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Symbols exposure</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">
                  {data.guardrails.metrics?.symbols_exposure_count ?? "—"} / {data.guardrails.limits?.MAX_SYMBOLS_EXPOSURE ?? "—"}
                </p>
              </div>
              <div>
                <span className="block text-xs text-zinc-500 dark:text-zinc-500">Max symbol notional %</span>
                <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200">{data.guardrails.metrics?.max_symbol_notional_pct ?? "—"}%</p>
              </div>
              {/* R26.0: Available budget (post cash reserve) */}
              {data.guardrails.metrics?.available_budget_usd != null && (
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Available budget</span>
                  <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200" data-testid="guardrails-available-budget">
                    ${data.guardrails.metrics.available_budget_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </p>
                </div>
              )}
              {/* R26.1: Cash-secured committed and CSP cash available */}
              {data.guardrails.metrics?.cash_secured_committed_usd != null && (
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">Cash-secured committed</span>
                  <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200" data-testid="guardrails-cash-secured-committed">
                    ${data.guardrails.metrics.cash_secured_committed_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </p>
                </div>
              )}
              {data.guardrails.metrics?.csp_cash_available_usd != null && (
                <div>
                  <span className="block text-xs text-zinc-500 dark:text-zinc-500">CSP cash available</span>
                  <p className="mt-1 font-mono text-zinc-700 dark:text-zinc-200" data-testid="guardrails-csp-cash-available">
                    ${data.guardrails.metrics.csp_cash_available_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </p>
                </div>
              )}
            </div>
          </Card>
        )}
      </div>

      {/* Store Integrity (Phase 17.0) */}
      <Card>
        <CardHeader title="Store Integrity" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                <th className="py-2 pr-2">Store</th>
                <th className="py-2 pr-2">Total lines</th>
                <th className="py-2 pr-2">Invalid</th>
                <th className="py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {integrityData?.stores
                ? Object.entries(integrityData.stores).map(([name, s]) => (
                    <tr key={name} className="border-b border-zinc-100 dark:border-zinc-800/50">
                      <td className="py-2 pr-2 font-mono text-zinc-700 dark:text-zinc-300">{name}</td>
                      <td className="py-2 pr-2 font-mono">{s.exists ? s.total_lines : "—"}</td>
                      <td className="py-2 pr-2">
                        <span className={s.invalid_lines > 0 ? "text-red-600 dark:text-red-400 font-medium" : ""}>
                          {s.exists ? s.invalid_lines : "—"}
                        </span>
                      </td>
                      <td className="py-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => repairStore.mutate(name)}
                          disabled={repairStore.isPending || !s.exists || s.invalid_lines === 0}
                        >
                          {repairStore.isPending ? "Repairing…" : "Repair"}
                        </Button>
                      </td>
                    </tr>
                  ))
                : (
                    <tr>
                      <td colSpan={4} className="py-4 text-center text-zinc-500 dark:text-zinc-500">
                        Loading integrity scan…
                      </td>
                    </tr>
                  )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Sanity Checks (Phase 8.2) */}
      <Card>
        <CardHeader title="Sanity Checks" />
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="sm"
              onClick={handleRunAll}
              disabled={runDiagnostics.isPending}
            >
              {runDiagnostics.isPending ? "Running…" : "Run All"}
            </Button>
            <Button variant="secondary" size="sm" onClick={selectAllChecks}>
              Select All
            </Button>
            <Button variant="secondary" size="sm" onClick={clearChecks}>
              Clear
            </Button>
            <div className="flex flex-wrap gap-3">
              {DIAGNOSTIC_CHECKS.map((c) => (
                <span key={c} className="flex items-center gap-1.5">
                  <label className="flex cursor-pointer items-center gap-1 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedChecks.has(c)}
                      onChange={() => toggleCheck(c)}
                      className="rounded border-zinc-300 dark:border-zinc-600"
                    />
                    <span className="text-zinc-700 dark:text-zinc-300">{c}</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => runSingleCheck(c)}
                    disabled={runDiagnostics.isPending}
                    className="rounded px-1.5 py-0.5 text-xs text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-50 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                  >
                    Run
                  </button>
                </span>
              ))}
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRunSelected}
              disabled={runDiagnostics.isPending || selectedChecks.size === 0}
            >
              Run selected
            </Button>
          </div>

          {displayResult && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Latest run — {formatTimestampEtFull(displayResult.timestamp_utc)} · Overall: {overallStatusDisplayLabel(displayResult.overall_status)}
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Check</th>
                    <th className="py-2 pr-2">Status</th>
                    <th className="py-2">Details</th>
                    <th className="py-2">Recommended action</th>
                  </tr>
                </thead>
                <tbody>
                  {displayResult.checks?.map((ch, i) => (
                    <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800/50">
                      <td className="py-2 pr-2 font-medium text-zinc-700 dark:text-zinc-300">{ch.check}</td>
                      <td className="py-2 pr-2">
                        <Badge variant={checkBadgeVariant(ch)}>{checkDisplayLabel(ch)}</Badge>
                      </td>
                      <td className="py-2 text-zinc-500 dark:text-zinc-400">
                        {typeof ch.details === "object" && ch.details
                          ? JSON.stringify(ch.details)
                          : String(ch.details ?? "—")}
                      </td>
                      <td className="py-2 text-zinc-600 dark:text-zinc-300">
                        {ch.recommended_action ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {runs.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Last {runs.length} runs
              </h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left text-zinc-600 dark:border-zinc-700 dark:text-zinc-500">
                    <th className="py-2 pr-2">Timestamp (UTC)</th>
                    <th className="py-2 pr-2">Overall</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r, i) => (
                    <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800/50">
                      <td className="py-2 pr-2 font-mono text-zinc-700 dark:text-zinc-300">{formatTimestampEtFull(r.timestamp_utc)}</td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={r.overall_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
