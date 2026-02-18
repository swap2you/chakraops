import { Link } from "react-router-dom";
import { useUiSystemHealth, useRunFreezeSnapshot } from "@/api/queries";
import { Button } from "@/components/ui";

/** Phase 11.3: One-line banner when market phase is POST/CLOSED. */
export function AfterHoursBanner() {
  const { data: health } = useUiSystemHealth();
  const runFreeze = useRunFreezeSnapshot();
  const phase = health?.market?.phase;
  const show =
    phase && phase !== "OPEN" && phase !== "UNKNOWN" && (phase === "POST" || phase === "CLOSED");

  if (!show) return null;

  return (
    <div className="flex flex-wrap items-center justify-center gap-2 bg-amber-100 px-4 py-1.5 text-sm text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
      <span>Evaluation/recompute disabled (market {phase}).</span>
      <Button
        variant="secondary"
        size="sm"
        className="h-6 px-2 text-xs"
        onClick={() => runFreeze.mutate(true)}
        disabled={runFreeze.isPending}
      >
        {runFreeze.isPending ? "Archiving…" : "Archive Now"}
      </Button>
      <Link
        to="/system"
        className="rounded border border-amber-600 px-2 py-0.5 text-xs font-medium hover:bg-amber-200/60 dark:border-amber-500 dark:hover:bg-amber-800/60"
      >
        System Status
      </Link>
    </div>
  );
}
