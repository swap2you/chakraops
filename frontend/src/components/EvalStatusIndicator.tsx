/**
 * Global evaluation-run indicator (app header, top right).
 *
 * Polls the existing read-only status endpoint and, while an evaluation run is in
 * flight (manual button or the 30-minute market-hours scheduler), shows a live pill
 * with elapsed time and the typical duration. Purely presentational — reads the
 * same status the Analytics page already consumes; triggers nothing.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiGet } from "@/data/apiClient";
import { ENDPOINTS } from "@/data/endpoints";
import type { EvaluationStatusCurrentResponse } from "@/types/universeEvaluation";

const IDLE_POLL_MS = 15_000;
const RUNNING_POLL_MS = 4_000;
/** Operator-observed runs often take several minutes for the full universe. */
const TYPICAL_DURATION_LABEL = "several minutes";

function useElapsedSeconds(startedAt: string | null | undefined, active: boolean): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (!active || !startedAt) {
      setElapsed(null);
      return;
    }
    const startMs = Date.parse(startedAt);
    if (Number.isNaN(startMs)) {
      setElapsed(null);
      return;
    }
    const update = () => setElapsed(Math.max(0, Math.round((Date.now() - startMs) / 1000)));
    update();
    const id = window.setInterval(update, 1000);
    return () => window.clearInterval(id);
  }, [startedAt, active]);

  return elapsed;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function EvalStatusIndicator() {
  const { data } = useQuery<EvaluationStatusCurrentResponse>({
    queryKey: ["evaluation-status-current"],
    queryFn: () => apiGet<EvaluationStatusCurrentResponse>(ENDPOINTS.evaluationStatusCurrent),
    refetchInterval: (query) =>
      query.state.data?.is_running ? RUNNING_POLL_MS : IDLE_POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: RUNNING_POLL_MS,
    retry: false,
  });

  const running = data?.is_running === true;
  const elapsed = useElapsedSeconds(data?.started_at, running);

  if (!running) return null;

  return (
    <div
      data-testid="eval-status-indicator"
      className="animate-scale-in inline-flex items-center gap-2 rounded-full bg-amber-50 py-1 pl-2.5 pr-3 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-600/30 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/30"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
      <span className="whitespace-nowrap">
        Evaluation running
        {elapsed != null && <span className="tabular-nums"> · {formatElapsed(elapsed)}</span>}
        <span className="hidden text-amber-600/80 sm:inline dark:text-amber-400/70"> · may take {TYPICAL_DURATION_LABEL}</span>
      </span>
    </div>
  );
}
