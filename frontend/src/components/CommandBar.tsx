import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Zap, LayoutDashboard, Briefcase, BookOpen, Bell, BarChart3, History, Sun, Moon, User, ChevronDown, Stethoscope, AlertTriangle, RefreshCw, Search as SearchIcon, Activity, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDataMode } from "@/context/DataModeContext";
import { useTheme } from "@/context/ThemeContext";
import { useScenario } from "@/context/ScenarioContext";
import { useApiHealth } from "@/hooks/useApiHealth";
import { useApiDataHealth, formatDataAge } from "@/hooks/useApiDataHealth";
import { useApiMarketStatus } from "@/hooks/useApiMarketStatus";
import { useApiOpsStatus } from "@/hooks/useApiOpsStatus";
import { useRefreshLiveData } from "@/hooks/useRefreshLiveData";
import { SCENARIO_LABELS, type ScenarioKey } from "@/mock/scenarios";
import { DiagnosticsDrawer } from "@/components/DiagnosticsDrawer";

const VIEWS = [
  { path: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { path: "/positions", label: "Positions", icon: Briefcase },
  { path: "/journal", label: "Journal", icon: BookOpen },
  { path: "/notifications", label: "Notifications", icon: Bell },
  { path: "/analytics", label: "Universe", icon: BarChart3 },
  { path: "/history", label: "History", icon: History },
  { path: "/analysis", label: "Ticker", icon: SearchIcon },
  { path: "/strategy", label: "Strategy", icon: FileText },
  { path: "/diagnostics", label: "Diagnostics", icon: Activity },
] as const;

function evalRangeFromHistory(decisionHistory: { evaluated_at: string }[]): { min: string; max: string } | null {
  if (!decisionHistory?.length) return null;
  const times = decisionHistory.map((r) => r.evaluated_at).filter(Boolean);
  if (times.length === 0) return null;
  const min = times.reduce((a, b) => (a < b ? a : b));
  const max = times.reduce((a, b) => (a > b ? a : b));
  return { min, max };
}

const STALE_MS = 24 * 60 * 60 * 1000;

function formatEvaluatedPill(ts: string | null | undefined): string | null {
  if (!ts) return null;
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return null;
  }
}

function isStale(ts: string | null | undefined): boolean {
  if (!ts) return false;
  try {
    const d = new Date(ts);
    return !Number.isNaN(d.getTime()) && Date.now() - d.getTime() > STALE_MS;
  } catch {
    return false;
  }
}

export function CommandBar() {
  console.log("[CommandBar] render start");
  const location = useLocation();
  const { mode, toggleMode } = useDataMode();
  const { theme, setTheme } = useTheme();
  const scenario = useScenario();
  useApiHealth(); // keep polling for API health
  const dataHealth = useApiDataHealth();
  const marketStatus = useApiMarketStatus();
  const opsStatus = useApiOpsStatus();
  const { trigger: triggerRefresh, state: refreshState } = useRefreshLiveData();
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);

  const isMock = mode === "MOCK";
  const showDataWarning = mode === "LIVE" && dataHealth.status !== "OK";
  // LIVE = attempted; OK = data confirmed (do not assume data exists just because mode is LIVE)
  console.log("[DATA_HEALTH]", dataHealth);

  return (
    <>
    <header className="sticky top-0 z-50 flex h-14 items-center gap-4 border-b border-border bg-card px-4">
      {/* Logo */}
      <Link to="/dashboard" className="flex items-center gap-2 text-foreground no-underline">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20">
          <Zap className="h-4 w-4 text-primary" />
        </div>
        <span className="font-semibold">ChakraOps</span>
      </Link>

      {/* Strategy selector */}
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-md border border-border bg-secondary/50 px-3 py-1.5 text-sm text-foreground hover:bg-secondary"
          >
            Chakra
            <ChevronDown className="h-3.5 w-3.5 opacity-70" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="min-w-[140px] rounded-md border border-border bg-card p-1 shadow-lg"
            sideOffset={6}
            align="start"
          >
            <DropdownMenu.Item
              className="cursor-pointer rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent"
              onSelect={(e) => e.preventDefault()}
            >
              Chakra (only)
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      {/* View selector */}
      <nav className="flex items-center gap-0.5">
        {VIEWS.map(({ path, label, icon: Icon }) => {
          const isActive = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium no-underline transition-colors",
                isActive
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        {/* Refresh now = immediate ORATS fetch (LIVE only) */}
        {mode === "LIVE" && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => void triggerRefresh()}
              disabled={refreshState.loading}
              className={cn(
                "flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium transition-colors",
                refreshState.loading
                  ? "cursor-not-allowed border-border bg-muted text-muted-foreground"
                  : "bg-secondary/50 text-foreground hover:bg-secondary"
              )}
              title="Pull fresh ORATS data"
              aria-label="Refresh live data"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshState.loading && "animate-spin")} />
              {refreshState.loading ? "Fetching…" : "Refresh now"}
            </button>
            {refreshState.message && (
              <span className="text-xs text-muted-foreground" role="status">
                {refreshState.message}
              </span>
            )}
          </div>
        )}

        {/* System Status — ORATS data health (LIVE), Last market check / Evaluated / Stale */}
        {(() => {
          const liveEvaluatedTs = mode === "LIVE" ? (marketStatus.last_evaluated_at ?? null) : null;
          const mockTs = scenario?.bundle?.decisionHistory?.[0]?.evaluated_at ?? scenario?.bundle?.dailyOverview?.links?.latest_decision_ts;
          const latestTs = mode === "LIVE" ? liveEvaluatedTs : mockTs ?? undefined;
          const evaluatedStr = formatEvaluatedPill(latestTs ?? null);
          const lastCheckStr = formatEvaluatedPill(mode === "LIVE" ? marketStatus.last_market_check ?? null : null);
          const stale = isStale(latestTs ?? null);
          const oratsOk = dataHealth.status === "OK";
          const oratsDown = mode === "LIVE" && (dataHealth.status === "DOWN" || dataHealth.status === "UNKNOWN");
          const oratsStale = mode === "LIVE" && dataHealth.status === "DEGRADED";
          const dataAge = formatDataAge(dataHealth.last_success_at);
          const checkedNoDecision =
            mode === "LIVE" &&
            marketStatus.last_market_check &&
            (marketStatus.last_evaluated_at == null || new Date(marketStatus.last_market_check).getTime() >= new Date(marketStatus.last_evaluated_at).getTime()) &&
            !marketStatus.evaluation_emitted;
          const tooltipParts: string[] = [];
          if (mode === "LIVE") {
            tooltipParts.push(`ORATS: ${dataHealth.status} — ${dataHealth.last_success_at ? `last success ${dataAge ?? dataHealth.last_success_at}` : "no successful fetch"}`);
            if (dataHealth.last_error_reason) tooltipParts.push(`Last error: ${dataHealth.last_error_reason.slice(0, 80)}`);
            if (lastCheckStr) tooltipParts.push(`Last data fetched at: ${lastCheckStr}`);
            if (evaluatedStr) tooltipParts.push(`Last evaluated at: ${evaluatedStr}`);
            if (checkedNoDecision) tooltipParts.push("Checked, no new decision");
            if (marketStatus.skip_reason) tooltipParts.push(`Skip: ${marketStatus.skip_reason}`);
            if (opsStatus.next_run_at) {
              const nextStr = formatEvaluatedPill(opsStatus.next_run_at);
              if (nextStr) tooltipParts.push(`Next run: ${nextStr}`);
            }
          }
          tooltipParts.push(`Data: ${mode}`);
          if (stale) tooltipParts.push("Stale = no new evaluation since last scheduled run.");
          const statusTooltip = tooltipParts.join(" · ");
          if (!evaluatedStr && !lastCheckStr && mode !== "LIVE") return null;
          return (
            <div
              className="flex items-center gap-2 rounded-full border border-border bg-muted/30 px-2.5 py-1 text-xs text-muted-foreground"
              title={statusTooltip}
            >
              {mode === "LIVE" && (
                <span
                  className={cn(
                    "flex items-center gap-1 font-medium",
                    oratsOk && "text-emerald-600 dark:text-emerald-400",
                    oratsStale && "text-amber-600 dark:text-amber-400",
                    oratsDown && "text-red-600 dark:text-red-400"
                  )}
                  title={oratsOk ? `ORATS: LIVE (updated ${dataAge ?? "—"})` : (dataHealth.last_error_reason ?? dataHealth.status)}
                >
                  ORATS: {oratsOk ? `LIVE (${dataAge ?? "—"})` : oratsStale ? `STALE (${dataAge ?? "—"})` : "DOWN"}
                  {(oratsDown || oratsStale) && <AlertTriangle className="h-3.5 w-3.5" aria-hidden />}
                </span>
              )}
              {lastCheckStr && mode === "LIVE" && (
                <span title="Last data fetched at (backend heartbeat)">Last fetched: {lastCheckStr}</span>
              )}
              {evaluatedStr && (
                <span title="Last evaluation run (decision pipeline)">Last evaluated: {evaluatedStr}</span>
              )}
              {checkedNoDecision && (
                <span className="text-muted-foreground/80" title="Backend checked; no new decision emitted">No new decision</span>
              )}
              {stale && mode === "LIVE" && (
                <span className="text-amber-600 dark:text-amber-400" title="No new evaluation since last scheduled run">No new evaluation since last scheduled run</span>
              )}
              {mode === "LIVE" && opsStatus.next_run_at && (
                <span className="text-muted-foreground/90" title="Next scheduled evaluation">
                  Next run: {formatEvaluatedPill(opsStatus.next_run_at) ?? "—"}
                </span>
              )}
              {stale && mode !== "LIVE" && (
                <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-amber-600 dark:text-amber-400" title="Data older than 24h">Stale</span>
              )}
              <span title="Data source">Data: {mode}</span>
            </div>
          );
        })()}

        {/* Scenario picker — MOCK only */}
        {isMock && scenario && (
          <select
            value={scenario.scenarioKey}
            onChange={(e) => scenario.setScenarioKey(e.target.value as ScenarioKey)}
            className="rounded-md border border-border bg-secondary/50 px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Mock scenario"
          >
            {scenario.scenarioKeys.map((key) => (
              <option key={key} value={key}>
                {SCENARIO_LABELS[key]}
              </option>
            ))}
          </select>
        )}

        {/* Diagnostics — MOCK only */}
        {isMock && scenario && (
          <button
            type="button"
            onClick={() => setDiagnosticsOpen(true)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Scenario diagnostics"
            title="Scenario diagnostics"
          >
            <Stethoscope className="h-4 w-4" />
          </button>
        )}

        {/* Run mode badge */}
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            mode === "LIVE"
              ? "bg-destructive/20 text-destructive"
              : "bg-muted text-muted-foreground"
          )}
          title={mode === "LIVE" ? "LIVE = data from backend API. DRY_RUN means no trades executed, signals only." : "MOCK = local scenario data."}
        >
          {mode}
        </span>

        {/* Risk posture badge */}
        <span
          className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground"
          title="Conservative posture = stricter risk gates; no trades executed in DRY_RUN."
        >
          CONSERVATIVE
        </span>

        {/* MOCK / LIVE toggle */}
        <button
          type="button"
          onClick={toggleMode}
          className="rounded-md border border-border bg-secondary/50 px-2 py-1 text-xs text-foreground hover:bg-secondary"
        >
          {mode === "MOCK" ? "MOCK" : "LIVE"}
        </button>

        {/* Theme toggle */}
        <button
          type="button"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        {/* Profile menu */}
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-secondary/50 text-muted-foreground hover:bg-secondary"
              aria-label="Profile"
            >
              <User className="h-4 w-4" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="min-w-[160px] rounded-md border border-border bg-card p-1 shadow-lg"
            sideOffset={6}
            align="end"
          >
            <DropdownMenu.Item className="cursor-pointer rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent">
              Profile
            </DropdownMenu.Item>
            <DropdownMenu.Item className="cursor-pointer rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent">
              Settings
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="my-1 h-px bg-border" />
            <DropdownMenu.Item className="cursor-pointer rounded px-2 py-1.5 text-sm text-muted-foreground outline-none data-[highlighted]:bg-accent">
              Sign out
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>

      {showDataWarning && console.log("[CommandBar] showDataWarning = true")}
      {showDataWarning && (
        <div
          className="flex items-center justify-center gap-2 border-b border-amber-500/50 bg-amber-500/10 px-4 py-2 text-sm font-medium text-amber-700 dark:text-amber-300"
          role="alert"
        >
          <span>ORATS data is unavailable or stale.</span>
        </div>
      )}

      {isMock && scenario && (
        <DiagnosticsDrawer
          open={diagnosticsOpen}
          onClose={() => setDiagnosticsOpen(false)}
          scenarioName={SCENARIO_LABELS[scenario.scenarioKey]}
          warnings={scenario.warnings}
          decisionCount={scenario.bundle.decisionHistory?.length ?? 0}
          positionCount={scenario.bundle.positions?.length ?? 0}
          alertCount={scenario.bundle.alerts?.items?.length ?? 0}
          evalRange={evalRangeFromHistory(scenario.bundle.decisionHistory ?? [])}
        />
      )}
    </>
  );
}
